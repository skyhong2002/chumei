import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import process_submissions as s
from pipeline_state import atomic_json, read_json
from submissions import SubmissionStore
from test_extraction_retry import http_error


class SubmissionRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.store = SubmissionStore(self.root / "auth.sqlite3")
        patch = mock.patch.multiple(s, EXTRACT_CACHE=self.root / "extraction/user_submission.json",
                                    GATEWAY_STATE=self.root / "gateway.json", STATE_DIR=self.root / "submissions")
        patch.start()
        self.addCleanup(patch.stop)
        self.index = {"by_id": {}, "by_source": {}, "by_url": {}, "events": [], "generated_at": ""}

    def accepted(self):
        sub = self.store.create("fixture-user", "https://example.org/fixture")
        self.store.update(sub["id"], "accepted", "", verdict='{"accepted_at":"2026-01-01T00:00:00+08:00"}')
        return sub

    def test_accepted_report_is_retried_without_new_pending_reports(self):
        sub = self.accepted()
        atomic_json(s.EXTRACT_CACHE, {sub["id"]: {"error": "timeout", "attempts": 1,
                                                "ts": "2020-01-01T00:00:00+00:00"}})
        with mock.patch.object(sys, "argv", ["process_submissions.py"]), \
             mock.patch.object(s, "load_env", return_value={"CHUMEI_AUTH_DATABASE": str(self.store.path)}), \
             mock.patch.object(s, "load_events_index", return_value=self.index), \
             mock.patch.object(s, "load_inbox_index", return_value=({}, {})), \
             mock.patch.object(s, "load_tracked_handles", return_value={}), \
             mock.patch.object(s, "load_org_index", return_value={}), \
             mock.patch.object(s, "run_extract", return_value=True) as extract:
            self.assertEqual(s.main(), 0)
        extract.assert_called_once()
        self.assertEqual(self.store.get(sub["id"])["status"], "accepted")

    def test_exhausted_extraction_is_manual_instead_of_not_event(self):
        sub = self.accepted()
        atomic_json(s.EXTRACT_CACHE, {sub["id"]: {"error": "timeout", "attempts": 4,
                                                "exhausted": True, "events": []}})
        self.assertFalse(s.accepted_needs_extract(self.store))
        s.settle_accepted(self.store, self.index)
        self.assertEqual(self.store.get(sub["id"])["status"], "manual")

    def test_existing_inbox_error_is_not_reported_as_non_event(self):
        sub = self.store.create("fixture-user", "https://example.org/fixture")
        ctx = {"events": self.index, "inbox": ({sub["url"]: ("fixture-source", "post")}, {}),
               "handles": {}, "env": {}, "orgs": {}, "needs_extract": False}
        for record, expected in [({"error": "timeout"}, "manual"), ({"events": []}, "not_event")]:
            atomic_json(s.EXTRACT_CACHE.parent / "fixture-source.json", {"post": record})
            with mock.patch.object(s, "fetch_content", side_effect=AssertionError("must not fetch again")):
                s.process_one(self.store, sub, ctx)
            self.assertEqual(self.store.get(sub["id"])["status"], expected)

    def test_review_quota_failure_uses_one_attempt_and_shared_safe_cooldown(self):
        with mock.patch.object(s, "chat_json", side_effect=http_error(429, "insufficient_quota secret")) as chat, \
             mock.patch.object(s, "load_schema", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "判讀服務"):
                s._review({}, "system", "fixture", Path("fixture-schema"), "fixture")
        self.assertEqual(chat.call_args.kwargs["attempts"], 1)
        self.assertEqual(read_json(s.GATEWAY_STATE)["error_kind"], "quota")
        self.assertNotIn("secret", s.GATEWAY_STATE.read_text())

    def test_submission_unknown_publication_keeps_explicit_null(self):
        sub = self.store.create("fixture-user", "https://example.org/fixture")
        written = []
        with mock.patch.object(s, "append_inbox", side_effect=lambda source, items: written.extend(items)), \
             mock.patch.object(s, "now_iso", return_value="2026-10-18T09:00:00+08:00"):
            s.write_inbox_item(sub, sub["url"], {"platform": "web"}, {"text": "fixture"}, {})
        post = written[0]
        self.assertEqual(post["posted_at"], post["first_seen"])
        self.assertIsNone(post["published_at"])
        self.assertEqual(post["publication_time_basis"], "first_seen")

    def test_dry_run_does_not_persist_provider_failure(self):
        with mock.patch.object(s, "chat_json", side_effect=http_error(429, "insufficient_quota")), \
             mock.patch.object(s, "load_schema", return_value={}):
            with self.assertRaises(RuntimeError):
                s._review({"_submission_dry_run": True}, "s", "fixture", Path("fixture"), "fixture")
        self.assertFalse(s.GATEWAY_STATE.exists())


if __name__ == "__main__":
    unittest.main()
