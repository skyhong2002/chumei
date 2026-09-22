import json
from datetime import datetime, timezone
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import source_status


class SourceStatusTests(unittest.TestCase):
    def test_quota_missing_account_and_real_fetch_errors_are_distinct(self):
        self.assertEqual(source_status.error_category("no unauthenticated provider available within free-credit reserve"), "quota_wait")
        self.assertEqual(source_status.error_category("user_daily_exhausted"), "quota_wait")
        self.assertEqual(source_status.error_category("{'error': 'user_not_found'}"), "account_unavailable")
        self.assertEqual(source_status.error_category("503 upstream failure"), "fetch_error")

    def test_retry_in_future_does_not_make_stale_success_healthy(self):
        row = {"id": "story:test", "sourceId": "ig_test", "username": "test",
               "kind": "instagram_story", "backend": "Apify Stories", "targetIntervalHours": 24}
        with patch.object(source_status, "source_registry", return_value=[row]), \
             patch.object(source_status, "load_ledger", return_value={"story:test": {"lastSuccess": 100}}), \
             patch.object(source_status, "_inbox_last_success", return_value={"ig_test": 199999}), \
             patch.object(source_status, "_read_json", return_value={"accounts": {"test": {"next_eligible": 300000}}}), \
             patch.object(source_status, "apify_quota", return_value={}), \
             patch.object(source_status, "api_usage_summary", return_value={}):
            payload = source_status.build_status_payload(now=200000)
        self.assertEqual(payload["sources"][0]["status"], "due")
        self.assertEqual(payload["coverage"]["missedTarget"], 1)
        self.assertEqual(payload["coverage"]["overdueTwoIntervals"], 1)
        self.assertEqual(payload["coverageByKind"]["instagram_story"]["success24h"], 0)
        self.assertEqual(payload["counts"]["fresh"], 0)

    def test_health_rechecks_ages_independently_from_pipeline_success(self):
        payload = {"generatedAt": "1970-01-02T00:00:00Z", "pipeline": {
            "lastCompletedRun": "1970-01-02T00:00:00Z", "lastResults": {"build": True}},
            "sources": [{"lastSuccess": 86400, "targetIntervalHours": 3, "status": "ok"}]}
        self.assertEqual(source_status.assess_health(payload, now=86401)["status"], "ok")
        result = source_status.assess_health(payload, now=86400 + 4 * 3600)
        self.assertIn("source_targets_missed", result["issues"])
        self.assertNotIn("snapshot_stale", result["issues"])
        result = source_status.assess_health(payload, now=86400 + 10 * 3600)
        self.assertIn("snapshot_stale", result["issues"])
        self.assertIn("pipeline_completion_stale", result["issues"])
        payload["sources"][0]["status"] = "blocked"
        self.assertIn("source_failures_or_limits", source_status.assess_health(payload, now=86401)["issues"])
        self.assertEqual(source_status.assess_health({}, now=86401)["status"], "degraded")

    def test_empty_success_streak_resets_when_content_returns(self):
        with tempfile.TemporaryDirectory() as td, patch.object(source_status, "LEDGER_PATH", Path(td) / "ledger.json"):
            for ts in (100, 200, 300):
                source_status.record_fetch("test", backend="RSSHub", ok=True, attempted_at=ts)
            entry = source_status.load_ledger()["test"]
            self.assertEqual(entry["consecutiveEmptySuccesses"], 3)
            self.assertEqual(source_status.coverage_summary([entry], now=301)["emptySuccessStreaks"], 1)
            source_status.record_fetch("test", backend="RSSHub", ok=True, items=1, attempted_at=400)
            self.assertEqual(source_status.load_ledger()["test"]["consecutiveEmptySuccesses"], 0)

    def test_health_cli_reads_only_snapshot_and_fails_closed(self):
        import check_source_health
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            with patch("builtins.print"):
                self.assertEqual(check_source_health.main(["--snapshot", str(path)]), 1)
                path.write_text("not json")
                self.assertEqual(check_source_health.main(["--snapshot", str(path)]), 1)
                path.write_text(json.dumps({"generatedAt": "2020-01-01T00:00:00Z", "sources": []}))
                self.assertEqual(check_source_health.main(["--snapshot", str(path)]), 1)
                now = datetime.now(timezone.utc)
                path.write_text(json.dumps({"generatedAt": now.isoformat(),
                    "pipeline": {"lastCompletedRun": now.isoformat(), "lastResults": {"build": True}},
                    "sources": [{"lastSuccess": now.timestamp(), "targetIntervalHours": 3, "status": "ok"}]}))
                self.assertEqual(check_source_health.main(["--snapshot", str(path)]), 0)
            self.assertEqual(list(Path(td).iterdir()), [path])

    def test_live_schedule_estimate_uses_new_pool_and_current_instagram_intervals(self):
        import apify_pool
        sources = [
            {"kind": "facebook", "targetIntervalHours": 168},
            {"kind": "instagram_profile", "username": "test", "targetIntervalHours": 168},
            {"kind": "instagram_story", "username": "test", "targetIntervalHours": 168},
        ]
        pool = {"usableAccountCount": 1, "accounts": [
            {"available": True, "community": True, "remainingUsd": 5, "cycleEnd": "1970-01-25T00:00:00Z"}
        ]}
        with tempfile.TemporaryDirectory() as td, \
             patch.object(apify_pool, "POOL_STATE_PATH", Path(td) / "pool.json"), \
             patch.object(source_status, "source_registry", side_effect=lambda: [dict(s) for s in sources]), \
             patch.object(source_status, "_read_json", return_value={"accounts": {"test": {"interval_hours": 48}}}), \
             patch.object(source_status, "pool_status", return_value=pool) as status:
            before = source_status.crawl_schedule_snapshot(now=0)
            pool["accounts"].append(dict(pool["accounts"][0]))
            pool["usableAccountCount"] = 2
            after = source_status.crawl_schedule_snapshot(now=0)
        status.assert_called_with(refresh=False, now=0)
        self.assertLess(after["sources"][0]["targetIntervalHours"], before["sources"][0]["targetIntervalHours"])
        self.assertEqual(after["sources"][1]["targetIntervalHours"], 48)
        self.assertEqual(after["sources"][2]["targetIntervalHours"], 48)
        self.assertEqual(before["instagramBatchSize"], 8)
        self.assertEqual(after["instagramBatchSize"], 11)
        self.assertEqual(after["usableApifyAccounts"], 2)

    def test_registry_has_independent_profile_story_and_backends(self):
        registry = {item["id"]: item for item in source_status.source_registry()}
        self.assertIn("instagram:nthu_official", registry)
        self.assertIn("story:nthu_official", registry)
        self.assertEqual(registry["instagram:nthu_official"]["targetIntervalHours"], 168)
        self.assertEqual(registry["instagram:nthu_official"]["backend"], "Instagram public")
        self.assertEqual(registry["story:nthu_official"]["backend"], "Apify Stories")
        self.assertTrue(any(item["backend"] == "Apify" for item in registry.values()))
        self.assertTrue(any(item["backend"] == "RSSHub" for item in registry.values()))
        self.assertTrue(any(item["backend"] == "NYCU Open Data" for item in registry.values()))

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
                       for name in ("Instagram public web", "Apify Instagram", "RSSHub", "Instaloader", "Apify")}
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
            "platform": "Instagram", "kind": "instagram_profile", "backend": "Instagram public",
            "kindLabel": "貼文", "school": "other", "targetIntervalHours": 168.0,
        }
        empty_usage = {name: {"requests24h": 0, "requests30d": 0, "sources24h": 0,
                              "errors24h": 0, "cost30dUsd": 0}
                       for name in ("Instagram public web", "Apify Instagram", "RSSHub", "Instaloader", "Apify")}

        def read_state(path):
            if path.name == "instagram_public_profile_schedule.json":
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

    def test_legacy_instagram_error_becomes_due_for_replacement_backend(self):
        instagram = {
            "id": "instagram:test", "sourceId": "ig_test", "name": "Test", "username": "test",
            "platform": "Instagram", "kind": "instagram_profile", "backend": "Instagram public",
            "kindLabel": "貼文", "school": "other", "targetIntervalHours": 168.0,
        }
        empty_usage = {name: {"requests24h": 0, "requests30d": 0, "sources24h": 0,
                              "errors24h": 0, "cost30dUsd": 0}
                       for name in ("Instagram public web", "Apify Instagram", "RSSHub", "Instaloader", "Apify")}
        with patch.object(source_status, "source_registry", return_value=[instagram]), \
             patch.object(source_status, "load_ledger", return_value={
                 "instagram:test": {
                     "backend": "Instaloader", "lastAttempt": 950, "lastSuccess": 900,
                     "lastError": "challenge_required", "consecutiveFailures": 4,
                 }
             }), \
             patch.object(source_status, "_inbox_last_success", return_value={}), \
             patch.object(source_status, "_read_json", return_value={}), \
             patch.object(source_status, "apify_quota", return_value={"exhausted": False}), \
             patch.object(source_status, "api_usage_summary", return_value=empty_usage):
            payload = source_status.build_status_payload(now=1000)
        row = payload["sources"][0]
        self.assertEqual(row["status"], "due")
        self.assertEqual(row["nextDue"], 1000)
        self.assertEqual(row["lastError"], "")
        self.assertEqual(row["consecutiveFailures"], 0)

    def test_apify_pacing_incident_describes_shared_instagram_usage(self):
        incidents = source_status.detect_incidents(
            now=1000,
            profile_schedule={},
            story_schedule={},
            apify={"exhausted": False, "remainingUsd": 14.25},
            facebook_interval_hours=168,
            rows=[],
        )
        self.assertEqual(incidents[0]["id"], "apify-slow-pacing")
        self.assertIn("Instagram 限時動態", incidents[0]["detail"])
        self.assertIn("US$10", incidents[0]["detail"])


if __name__ == "__main__":
    unittest.main()
