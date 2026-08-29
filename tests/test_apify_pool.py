import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apify_pool


class ApifyPoolTests(unittest.TestCase):
    def test_token_accounts_are_named_and_deduplicated(self):
        accounts = apify_pool.token_accounts({
            "APIFY_TOKEN": "primary-secret",
            "APIFY_TOKEN_BETA": "beta-secret",
            "APIFY_TOKEN_DUPLICATE": "primary-secret",
            "UNRELATED": "ignored",
        })
        self.assertEqual([row["label"] for row in accounts], ["PRIMARY", "BETA"])

    def test_recommended_interval_spends_capacity_before_reset(self):
        status = {
            "accounts": [
                {"available": True, "remainingUsd": 5.0, "cycleEnd": "1970-01-25T00:00:00Z"}
                for _ in range(4)
            ]
        }
        with tempfile.TemporaryDirectory() as td, patch.object(
            apify_pool, "POOL_STATE_PATH", Path(td) / "pool.json"
        ):
            interval = apify_pool.recommended_interval_hours(status, source_count=327, now=0)
        self.assertEqual(interval, 115.2)

    def test_choose_token_uses_earliest_expiring_usable_account(self):
        accounts = [
            {"label": "LATER", "token": "secret-later"},
            {"label": "SOON", "token": "secret-soon"},
        ]
        status = {"accounts": [
            {"label": "LATER", "available": True, "exhausted": False, "remainingUsd": 5,
             "usedUsd": 0, "limitUsd": 5, "activeActorJobs": 0, "cycleEnd": "2026-10-01T00:00:00Z"},
            {"label": "SOON", "available": True, "exhausted": False, "remainingUsd": 5,
             "usedUsd": 0, "limitUsd": 5, "activeActorJobs": 0, "cycleEnd": "2026-09-01T00:00:00Z"},
        ]}
        with tempfile.TemporaryDirectory() as td, \
             patch.object(apify_pool, "POOL_STATE_PATH", Path(td) / "pool.json"), \
             patch.object(apify_pool, "token_accounts", return_value=accounts), \
             patch.object(apify_pool, "pool_status", return_value=status):
            label, token, _ = apify_pool.choose_token()
        self.assertEqual(label, "SOON")
        self.assertEqual(token, "secret-soon")


if __name__ == "__main__":
    unittest.main()
