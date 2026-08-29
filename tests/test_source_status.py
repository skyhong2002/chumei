import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import source_status


class SourceStatusTests(unittest.TestCase):
    def test_registry_has_independent_profile_story_and_backends(self):
        registry = {item["id"]: item for item in source_status.source_registry()}
        self.assertIn("instagram:nthu_official", registry)
        self.assertIn("story:nthu_official", registry)
        self.assertEqual(registry["instagram:nthu_official"]["targetIntervalHours"], 24)
        self.assertEqual(registry["story:nthu_official"]["backend"], "Instaloader")
        self.assertTrue(any(item["backend"] == "Apify" for item in registry.values()))
        self.assertTrue(any(item["backend"] == "RSSHub" for item in registry.values()))

    def test_ledger_records_success_history_and_real_average(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.json"
            with patch.object(source_status, "LEDGER_PATH", ledger):
                source_status.record_fetch("threads:test", backend="RSSHub", ok=True, attempted_at=1000)
                source_status.record_fetch("threads:test", backend="RSSHub", ok=True, attempted_at=8200)
                entry = source_status.load_ledger()["threads:test"]
            self.assertEqual(entry["lastSuccess"], 8200)
            self.assertEqual(source_status._average_interval(entry["successHistory"]), 2.0)

    def test_api_usage_counts_requests_and_sources_separately(self):
        with tempfile.TemporaryDirectory() as td:
            usage = Path(td) / "usage.jsonl"
            with patch.object(source_status, "USAGE_PATH", usage), patch.object(source_status.time, "time", return_value=100000):
                source_status.record_api_call("Apify", operation="http", source_count=0, request_count=3)
                source_status.record_api_call("Apify", operation="batch", source_count=4, request_count=0, cost_usd=.25)
                summary = source_status.api_usage_summary(now=100000)["Apify"]
            self.assertEqual(summary["requests24h"], 3)
            self.assertEqual(summary["sources24h"], 4)
            self.assertEqual(summary["cost30dUsd"], .25)

    def test_method_summaries_include_frequency_and_status_counts(self):
        rows = [
            {"backend": "NTHU RPage", "targetIntervalHours": 3.0, "status": "ok",
             "lastAttempt": 1000, "nextDue": 11800, "blockedReason": ""},
            {"backend": "NTHU RPage", "targetIntervalHours": 3.0, "status": "error",
             "lastAttempt": 2000, "nextDue": 12800, "blockedReason": ""},
            {"backend": "Apify", "targetIntervalHours": 168.0, "status": "ok",
             "lastAttempt": 500, "nextDue": 605300, "blockedReason": "額度已用完"},
        ]
        methods = {row["backend"]: row for row in source_status.method_summaries(rows)}
        self.assertEqual(methods["NTHU RPage"]["sources"], 2)
        self.assertEqual(methods["NTHU RPage"]["targetIntervalHours"], 3.0)
        self.assertEqual(methods["NTHU RPage"]["errors"], 1)
        self.assertEqual(methods["NTHU RPage"]["lastAttempt"], 2000)
        self.assertEqual(methods["Apify"]["blocked"], 1)

    def test_exhausted_apify_sources_are_reported_as_blocked(self):
        facebook = {
            "id": "facebook:test", "sourceId": "fb_test", "name": "Test", "username": "test",
            "platform": "Facebook", "kind": "facebook", "backend": "Apify",
            "kindLabel": "粉專貼文", "school": "other", "targetIntervalHours": 168.0,
        }
        empty_usage = {name: {"requests24h": 0, "requests30d": 0, "sources24h": 0,
                              "errors24h": 0, "cost30dUsd": 0}
                       for name in ("RSSHub", "Instaloader", "Apify")}
        with patch.object(source_status, "source_registry", return_value=[facebook]), \
             patch.object(source_status, "load_ledger", return_value={}), \
             patch.object(source_status, "_inbox_last_success", return_value={}), \
             patch.object(source_status, "_read_json", return_value={}), \
             patch.object(source_status, "apify_quota", return_value={"exhausted": True}), \
             patch.object(source_status, "api_usage_summary", return_value=empty_usage):
            payload = source_status.build_status_payload(now=1000)
        self.assertEqual(payload["sources"][0]["status"], "blocked")
        self.assertEqual(payload["counts"]["blocked"], 1)
        self.assertEqual(payload["counts"]["fresh"], 0)

    def test_active_instagram_cooldown_is_blocked_not_error(self):
        instagram = {
            "id": "instagram:test", "sourceId": "ig_test", "name": "Test", "username": "test",
            "platform": "Instagram", "kind": "instagram_profile", "backend": "RSSHub → Instaloader",
            "kindLabel": "貼文", "school": "other", "targetIntervalHours": 24.0,
        }
        empty_usage = {name: {"requests24h": 0, "requests30d": 0, "sources24h": 0,
                              "errors24h": 0, "cost30dUsd": 0}
                       for name in ("RSSHub", "Instaloader", "Apify")}

        def read_state(path):
            if path.name == "instagram_profile_schedule.json":
                return {"global_cooldown_until": 2000, "accounts": {}}
            return {}

        with patch.object(source_status, "source_registry", return_value=[instagram]), \
             patch.object(source_status, "load_ledger", return_value={
                 "instagram:test": {"lastError": "401 rate limited"}
             }), \
             patch.object(source_status, "_inbox_last_success", return_value={}), \
             patch.object(source_status, "_read_json", side_effect=read_state), \
             patch.object(source_status, "apify_quota", return_value={"exhausted": False}), \
             patch.object(source_status, "api_usage_summary", return_value=empty_usage):
            payload = source_status.build_status_payload(now=1000)
        row = payload["sources"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertIn("冷卻", row["blockedReason"])
        self.assertEqual(payload["counts"]["errors"], 0)
        self.assertEqual(payload["counts"]["blocked"], 1)


if __name__ == "__main__":
    unittest.main()
