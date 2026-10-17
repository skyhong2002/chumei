"""Offline retry/circuit regressions; all times and provider replies are synthetic."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extract_events as x
import extraction_retry as retry
from pipeline_state import atomic_json, read_json

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def item(pid="one"):
    return {"source_id": "fixture", "post_id": pid, "source_name": "Fixture club",
            "school": "nycu", "org_type": "club", "platform": "api", "raw_source": "fixture",
            "url": f"https://example.org/{pid}", "text": "synthetic announcement", "images": [],
            "posted_at": "2026-10-17T00:00:00+00:00", "fetched_at": NOW.isoformat()}


def http_error(status, body="", headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = body.encode()
    response.headers.update(headers or {})
    return requests.HTTPError(f"HTTP {status}", response=response)


class RetryTests(unittest.TestCase):
    def test_classification_and_safe_persisted_errors(self):
        for error, kind in [(requests.Timeout("secret transport"), "timeout"),
                            (requests.ConnectionError("secret host"), "connection"),
                            (http_error(503), "unavailable"), (http_error(429), "rate_limit"),
                            (http_error(429, '{"code":"insufficient_quota", "token":"secret"}'), "quota"),
                            (RuntimeError("gateway unavailable after 1 attempts (HTTP 429)"), "quota"),
                            (http_error(401), "authentication"), (http_error(400), "permanent"),
                            (ValueError("secret raw JSON"), "invalid_response"),
                            (RuntimeError("secret unknown"), "unknown")]:
            with self.subTest(kind=kind):
                result = retry.error_record(error, now=NOW)
                self.assertEqual(result["error_kind"], kind)
                self.assertNotIn("secret", json.dumps(result))

    def test_backoff_retry_after_and_four_attempt_ceiling(self):
        record = None
        now = NOW
        for attempt, seconds in enumerate([900, 3600, 14400, 57600], 1):
            record = retry.error_record(requests.Timeout(), record, now=now)
            self.assertEqual(record["attempts"], attempt)
            self.assertEqual(retry.timestamp(record["retry_after"]), now + timedelta(seconds=seconds))
            self.assertFalse(retry.retry_due(record, x.PROMPT_VERSION, now=now))
            now = retry.timestamp(record["retry_after"])
            self.assertEqual(retry.retry_due(record, x.PROMPT_VERSION, now=now), attempt < 4)
        self.assertFalse(retry.retry_due(record, 999, now=now + timedelta(days=100), retry_errors=True))

    def test_success_and_non_events_remain_cached(self):
        for events in [[], [{"id": "past-event"}]]:
            record = {"prompt_version": x.PROMPT_VERSION, "events": events}
            self.assertFalse(retry.retry_due(record, x.PROMPT_VERSION, now=NOW, retry_errors=True))

    def test_legacy_transient_is_due_without_flag_and_permanent_requires_flag(self):
        old = {"error": "timeout", "ts": (NOW - timedelta(hours=3)).isoformat(),
               "prompt_version": x.PROMPT_VERSION}
        self.assertTrue(retry.retry_due(old, x.PROMPT_VERSION, now=NOW))
        self.assertFalse(retry.retry_due({**old, "error": "400: bad request"}, x.PROMPT_VERSION, now=NOW))
        self.assertTrue(retry.retry_due({**old, "error": "400: bad request"}, x.PROMPT_VERSION,
                                        now=NOW, retry_errors=True))

    def test_quota_cooldown_and_numeric_or_http_date_retry_after(self):
        quota = retry.error_record(http_error(429, "insufficient_quota"), now=NOW)
        self.assertEqual(retry.timestamp(quota["retry_after"]), NOW + timedelta(days=1))
        for header in ["7200", "Sun, 18 Oct 2026 02:00:00 GMT"]:
            rec = retry.error_record(http_error(429, headers={"Retry-After": header}), now=NOW)
            self.assertEqual(retry.timestamp(rec["retry_after"]), NOW + timedelta(hours=2))
        for header in ["junk", "NaN", "inf", "-30"]:
            self.assertIsNotNone(retry.error_record(http_error(429, headers={"Retry-After": header}), now=NOW))


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.patches = mock.patch.multiple(x, EXTRACT_DIR=root / "extraction", GATEWAY_STATE=root / "gateway.json",
                                          load_env=lambda: {"CHUMEI_LLM_API_KEY": "fixture-only"})
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.args = argparse.Namespace(source=None, limit=0, workers=1, retry_errors=False)

    def test_error_then_success_preserves_first_discovery_and_no_immediate_retry(self):
        with mock.patch.object(x, "call_llm", side_effect=requests.Timeout("secret")) as call:
            result = x.process_item({}, item(), None, {})[2]
        call.assert_called_once()
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["first_seen"], NOW.isoformat())
        with mock.patch.object(x, "call_llm", return_value=('{"events":[]}', "fixture-model")):
            success = x.process_item({}, item(), None, {"fixture": {"one": result}})[2]
        self.assertEqual(success["attempts"], 2)
        self.assertEqual(success["first_seen"], result["first_seen"])
        self.assertNotIn("error", success)

    def test_malformed_reply_is_cached_without_raw_provider_content(self):
        for raw in ["secret broken json", "null", "[]", '{"events":"secret"}', '{"events":[null]}']:
            with self.subTest(raw=raw), mock.patch.object(x, "call_llm", return_value=(raw, "fixture-model")):
                result = x.process_item({}, item())[2]
                self.assertEqual(result["error_kind"], "invalid_response")
                self.assertNotIn("secret", json.dumps(result))

    def test_prompt_upgrade_failure_preserves_historical_activity(self):
        previous = {"prompt_version": 1, "ts": "2025-01-01T00:00:00+00:00",
                    "first_seen": "2025-01-01T00:00:00+00:00", "events": [{"id": "history"}]}
        with mock.patch.object(x, "call_llm", side_effect=requests.Timeout()):
            result = x.process_item({}, item(), None, {"fixture": {"one": previous}})[2]
        self.assertEqual(result["events"][0]["id"], "history")
        self.assertEqual(result["first_seen"], previous["first_seen"])

    def test_extracted_event_retains_discovery_and_unknown_publication(self):
        post = {**item(), "published_at": None, "publication_time_basis": "first_seen"}
        event = {"title": "fixture", "start_at": "2026-10-19T12:00:00+00:00",
                 "source_timezone": "UTC", "confidence": .99}
        with mock.patch.object(x, "call_llm", return_value=(json.dumps({"events": [event]}), "fixture-model")):
            result = x.process_item({}, post)[2]["events"][0]
        self.assertEqual(result["first_seen"], NOW.isoformat())
        self.assertEqual(result["fetched_at"], NOW.isoformat())
        self.assertIsNone(result["published_at"])
        self.assertEqual(result["publication_time_basis"], "first_seen")
        self.assertEqual(result["start_at"], "2026-10-19T20:00:00+08:00")

    def test_legacy_timeout_recovers_once_and_duplicate_inbox_is_deduplicated(self):
        x._save_cache("fixture", {"one": {"error": "timeout", "prompt_version": x.PROMPT_VERSION,
                                          "ts": "2020-01-01T00:00:00+00:00"},
                                   "cached": {"events": [], "prompt_version": x.PROMPT_VERSION}})
        with mock.patch.object(x, "iter_inbox", return_value=iter([item(), item(), item("cached")])), \
             mock.patch.object(x, "call_llm", return_value=('{"events":[]}', "fixture-model")) as call:
            self.assertEqual(x.extract(self.args), 0)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(x._load_cache("fixture")["one"]["attempts"], 2)

    def test_quota_stops_unscheduled_work_and_cooldown_survives_next_run(self):
        with mock.patch.object(x, "iter_inbox", side_effect=lambda: iter([item(str(i)) for i in range(30)])), \
             mock.patch.object(x, "call_llm", side_effect=http_error(429, "insufficient_quota")) as call:
            self.assertEqual(x.extract(self.args), 0)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(x.extract(self.args), 0)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(len(x._load_cache("fixture")), 1)
        circuit = read_json(x.GATEWAY_STATE)
        self.assertEqual(circuit["error_kind"], "quota")

    def test_exhausted_budget_and_retry_errors_never_bypass_cooldown(self):
        record = retry.error_record(http_error(429), now=NOW)
        x._save_cache("fixture", {"one": {**record, "attempts": 4, "exhausted": True}})
        self.args.retry_errors = True
        with mock.patch.object(x, "iter_inbox", return_value=iter([item()])), mock.patch.object(x, "call_llm") as call:
            x.extract(self.args)
        call.assert_not_called()

    def test_longest_global_cooldown_wins(self):
        long = retry.error_record(http_error(429, "insufficient_quota"), now=NOW)
        short = retry.error_record(http_error(503), now=NOW)
        retry.record_gateway_failure(x.GATEWAY_STATE, long)
        retry.record_gateway_failure(x.GATEWAY_STATE, short)
        self.assertEqual(read_json(x.GATEWAY_STATE)["retry_after"], long["retry_after"])


if __name__ == "__main__":
    unittest.main()
