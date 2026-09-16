import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apify_pool
from fetch_stories_apify import attempted_targets, auto_max_runs


DAY = 20713 * 86400 + 43200.0  # noon UTC, so +2h stays on the same day


def _status(*rows):
    return {"accounts": [
        {"label": label, "available": True, "exhausted": False, "remainingUsd": remaining,
         "usedUsd": 1.0, "limitUsd": 5.0, "activeActorJobs": 0}
        for label, remaining in rows
    ]}


class StoryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tempdir.name) / "pool.json"
        patches = [
            patch.object(apify_pool, "POOL_STATE_PATH", self.state_path),
            patch.object(apify_pool, "token_accounts", return_value=[
                {"label": "A", "token": "ta"}, {"label": "B", "token": "tb"},
            ]),
            patch.object(apify_pool, "pool_status", return_value=_status(("A", 2.0), ("B", 2.0))),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(self.tempdir.cleanup)

    def test_first_run_of_day_and_remaining_allowance_drive_rotation(self):
        label, token, _, allowance = apify_pool.choose_story_token(now=DAY)
        self.assertEqual((label, token, allowance), ("A", "ta", 10))
        apify_pool.record_story_run("A", delivered=10, now=DAY)
        # B has not run today, so its guaranteed first run goes next.
        self.assertEqual(apify_pool.choose_story_token(now=DAY)[0], "B")
        apify_pool.record_story_run("B", delivered=4, now=DAY)
        # Both ran; the account with more allowance left wins.
        self.assertEqual(apify_pool.choose_story_token(now=DAY)[0], "B")

    def test_daily_exhaustion_blocks_until_next_utc_day(self):
        apify_pool.record_story_run("A", delivered=0, denied_reason="user_daily_exhausted", now=DAY)
        self.assertEqual(apify_pool.choose_story_token(now=DAY)[0], "B")
        apify_pool.record_story_run("B", delivered=0, denied_reason="free_capacity_exhausted", now=DAY)
        with self.assertRaises(RuntimeError):
            apify_pool.choose_story_token(now=DAY)
        # Shared-pool denial only cools down briefly; daily exhaustion lasts all day.
        self.assertEqual(apify_pool.choose_story_token(now=DAY + 2 * 3600)[0], "B")
        self.assertEqual(apify_pool.choose_story_token(now=DAY + 86400)[0], "A")

    def test_allowance_caps_last_run_and_counts_runs_available(self):
        apify_pool.record_story_run("A", delivered=34, now=DAY)
        self.assertEqual(apify_pool.choose_story_token(now=DAY, exclude={"B"})[3], 6)
        status = _status(("A", 2.0), ("B", 2.0), ("C", 0.0))
        self.assertEqual(apify_pool.story_runs_available(status, now=DAY), 1 + 4)
        self.assertEqual(auto_max_runs(status), 1)
        apify_pool.record_story_run("A", delivered=6, now=DAY)
        with self.assertRaises(RuntimeError):
            apify_pool.choose_story_token(now=DAY, exclude={"B"})

    def test_state_survives_reload(self):
        apify_pool.record_story_run("A", delivered=7, now=DAY)
        stored = json.loads(self.state_path.read_text())["accounts"]["A"]["story"]
        self.assertEqual((stored["results"], stored["runs"]), (7, 1))


class AttemptedTargetsTests(unittest.TestCase):
    def test_unattempted_profiles_stay_due(self):
        selected = ["a", "b", "c", "d"]
        self.assertEqual(attempted_targets(selected, {"granted_targets": 2}), ["a", "b"])
        self.assertEqual(attempted_targets(selected, {"granted_targets": 4}), selected)
        self.assertEqual(attempted_targets(selected, {}), selected)


if __name__ == "__main__":
    unittest.main()
