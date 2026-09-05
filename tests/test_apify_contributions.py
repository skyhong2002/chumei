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
        code, item = contributions.register(
            self.path, "user_1", raw_token, QUOTA, name="學生會帳號"
        )
        self.assertEqual(code, "created")
        self.assertEqual(item["accountLabel"], "學生會帳號")

        with sqlite3.connect(self.path) as conn:
            stored = conn.execute(
                "SELECT token_hash,token_ciphertext FROM apify_contributions"
            ).fetchone()
        self.assertNotIn(raw_token, stored)
        self.assertEqual(contributions.active_tokens(self.path)[0]["token"], raw_token)
        self.assertEqual(contributions.active_tokens(self.path)[0]["label"], "學生會帳號")
        self.assertEqual(contributions.active_tokens(self.path)[0]["verifiedQuota"], QUOTA)

        public = contributions.dashboard(self.path)
        self.assertEqual(public["totals"]["accounts"], 1)
        self.assertEqual(public["totals"]["extraSlots"], 3)
        self.assertEqual(public["scoreboard"][0]["priorityBonus"], 3)
        self.assertEqual(public["scoreboard"][0]["accounts"], 1)
        self.assertEqual(public["scoreboard"][0]["usableAccounts"], 1)
        self.assertEqual(public["scoreboard"][0]["name"], "竹梅同學")
        self.assertNotIn(raw_token, repr(public))
        self.assertEqual(public["accounts"][0]["accountLabel"], "學生會帳號")

    def test_registered_and_disabled_account_changes_local_capacity_without_refresh(self):
        import apify_pool
        from run_pipeline import instagram_batch_size

        with patch.object(apify_pool, "CACHE_PATH", Path(self.tempdir.name) / "absent-cache.json"), \
             patch.object(apify_pool, "load_env", return_value={}), \
             patch.object(apify_pool, "active_tokens", side_effect=lambda: contributions.active_tokens(self.path)), \
             patch.object(apify_pool, "_fetch_quota") as fetch:
            before = apify_pool.pool_status(refresh=False)
            self.assertEqual(before["accountCount"], 0)
            code, item = contributions.register(
                self.path, "user_1", "apify_api_" + "n" * 40, QUOTA, name="New account"
            )
            self.assertEqual(code, "created")
            after = apify_pool.pool_status(refresh=False)
            self.assertEqual(after["usableAccountCount"], 1)
            self.assertEqual(after["remainingUsd"], QUOTA["remainingUsd"])
            self.assertEqual(instagram_batch_size(after), instagram_batch_size(before) + 3)
            contributions.disable(self.path, "user_1", item["publicId"])
            self.assertEqual(apify_pool.pool_status(refresh=False)["usableAccountCount"], 0)
            fetch.assert_not_called()

    def test_owner_can_rename_an_account_without_resubmitting_the_token(self):
        raw_token = "apify_api_" + "n" * 40
        _, item = contributions.register(
            self.path, "user_1", raw_token, QUOTA, name="舊名稱"
        )

        self.assertEqual(
            contributions.rename(self.path, "user_1", item["publicId"], " 新 名稱 "),
            "新 名稱",
        )
        self.assertIsNone(
            contributions.rename(self.path, "user_2", item["publicId"], "偷改")
        )
        self.assertEqual(contributions.user_rows(self.path, "user_1")[0]["accountLabel"], "新 名稱")
        self.assertEqual(contributions.dashboard(self.path)["accounts"][0]["accountLabel"], "新 名稱")
        with self.assertRaises(ValueError):
            contributions.rename(self.path, "user_1", item["publicId"], "")

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

    def test_system_spending_the_quota_does_not_remove_contributor_bonus(self):
        raw_token = "apify_api_" + "s" * 40
        _, item = contributions.register(self.path, "user_1", raw_token, QUOTA)
        contribution_id = contributions.active_tokens(self.path)[0]["contributionId"]
        contributions.update_quota(self.path, contribution_id, {
            **QUOTA, "usedUsd": 4.999, "remainingUsd": 0.001,
        })

        self.assertEqual(contributions.active_count(self.path, "user_1"), 1)
        self.assertEqual(contributions.user_rows(self.path, "user_1")[0]["priorityBonus"], 3)
        public = contributions.dashboard(self.path)
        self.assertEqual(public["scoreboard"][0]["priorityBonus"], 3)
        self.assertEqual(public["scoreboard"][0]["usableAccounts"], 0)
        self.assertEqual(public["totals"]["extraSlots"], 0)
        self.assertEqual(item["accountLabel"].startswith("COMMUNITY-"), True)

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
