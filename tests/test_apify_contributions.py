import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apify_contributions as contributions


QUOTA = {
    "limitUsd": 5.0,
    "usedUsd": 1.25,
    "remainingUsd": 3.75,
    "cycleStart": "2026-09-01T00:00:00Z",
    "cycleEnd": "2026-10-01T00:00:00Z",
    "checkedAt": 1000,
}


class ApifyContributionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "auth.sqlite3"
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TABLE users (id TEXT PRIMARY KEY,display_name TEXT NOT NULL,"
                "handle TEXT,profile_public INTEGER NOT NULL DEFAULT 1)"
            )
            conn.execute("INSERT INTO users VALUES ('user_1','竹梅同學','friend',1)")
            conn.execute("INSERT INTO users VALUES ('user_2','第二位','second',1)")
            contributions.ensure_schema(conn)
        self.secret = patch.object(contributions, "encryption_secret", return_value="test-secret")
        self.secret.start()

    def tearDown(self):
        self.secret.stop()
        self.tempdir.cleanup()

    def test_register_encrypts_token_and_builds_public_dashboard(self):
        raw_token = "apify_api_" + "x" * 40
        code, item = contributions.register(self.path, "user_1", raw_token, QUOTA)
        self.assertEqual(code, "created")

        with sqlite3.connect(self.path) as conn:
            stored = conn.execute(
                "SELECT token_hash,token_ciphertext FROM apify_contributions"
            ).fetchone()
        self.assertNotIn(raw_token, stored)
        self.assertEqual(contributions.active_tokens(self.path)[0]["token"], raw_token)

        public = contributions.dashboard(self.path)
        self.assertEqual(public["totals"]["accounts"], 1)
        self.assertEqual(public["totals"]["extraSlots"], 3)
        self.assertEqual(public["scoreboard"][0]["priorityBonus"], 3)
        self.assertEqual(public["scoreboard"][0]["accounts"], 1)
        self.assertEqual(public["scoreboard"][0]["usableAccounts"], 1)
        self.assertNotIn(raw_token, repr(public))
        self.assertTrue(item["accountLabel"].startswith("COMMUNITY-"))

    def test_duplicate_token_cannot_be_claimed_by_another_user(self):
        raw_token = "apify_api_" + "y" * 40
        contributions.register(self.path, "user_1", raw_token, QUOTA)
        code, item = contributions.register(self.path, "user_2", raw_token, QUOTA)
        self.assertEqual(code, "claimed")
        self.assertIsNone(item)

    def test_disable_clears_ciphertext_and_removes_runtime_account(self):
        raw_token = "apify_api_" + "z" * 40
        _, item = contributions.register(self.path, "user_1", raw_token, QUOTA)
        self.assertTrue(contributions.disable(self.path, "user_1", item["publicId"]))
        self.assertEqual(contributions.active_tokens(self.path), [])
        with sqlite3.connect(self.path) as conn:
            stored = conn.execute(
                "SELECT status,token_ciphertext FROM apify_contributions"
            ).fetchone()
        self.assertEqual(stored, ("disabled", ""))

    def test_invalidate_fails_closed_and_removes_priority_bonus(self):
        raw_token = "apify_api_" + "i" * 40
        contributions.register(self.path, "user_1", raw_token, QUOTA)
        contribution_id = contributions.active_tokens(self.path)[0]["contributionId"]

        contributions.invalidate(self.path, contribution_id, "401 Client Error")

        self.assertEqual(contributions.active_tokens(self.path), [])
        self.assertEqual(contributions.active_count(self.path, "user_1"), 0)
        with sqlite3.connect(self.path) as conn:
            stored = conn.execute(
                "SELECT status,token_ciphertext,remaining_usd FROM apify_contributions"
            ).fetchone()
        self.assertEqual(stored, ("invalid", "", 0.0))

    def test_reactivation_respects_active_account_limit(self):
        old_token = "apify_api_" + "o" * 40
        _, item = contributions.register(self.path, "user_1", old_token, QUOTA)
        contributions.disable(self.path, "user_1", item["publicId"])
        for index in range(contributions.MAX_ACCOUNTS_PER_USER):
            token = "apify_api_" + str(index) * 40
            self.assertEqual(contributions.register(self.path, "user_1", token, QUOTA)[0], "created")

        code, restored = contributions.register(self.path, "user_1", old_token, QUOTA)

        self.assertEqual(code, "limit")
        self.assertIsNone(restored)


if __name__ == "__main__":
    unittest.main()
