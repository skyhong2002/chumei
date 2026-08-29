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


if __name__ == "__main__":
    unittest.main()
