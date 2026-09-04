import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_stories_apify import ranked_usernames, select_active_due


class ApifyStoryTests(unittest.TestCase):
    def test_active_profiles_are_ranked_before_dormant_profiles(self):
        now = datetime(2026, 9, 5, tzinfo=timezone.utc).timestamp()
        history = {
            "daily": [
                "2026-09-05T00:00:00+00:00",
                "2026-09-04T00:00:00+00:00",
                "2026-09-03T00:00:00+00:00",
            ],
            "dormant": [
                "2026-05-01T00:00:00+00:00",
                "2026-04-30T00:00:00+00:00",
            ],
        }
        ranked, intervals = ranked_usernames(["dormant", "daily"], history, now=now)
        self.assertEqual(ranked, ["daily", "dormant"])
        self.assertEqual(intervals["daily"], 12)
        self.assertEqual(intervals["dormant"], 168)

    def test_active_due_profiles_win_over_never_seen_dormant_profiles(self):
        intervals = {"active": 12, "dormant": 168}
        state = {"accounts": {"active": {"next_eligible": 900, "last_attempt": 100}}}
        self.assertEqual(
            select_active_due(["dormant", "active"], intervals, state, 1, now=1000),
            ["active"],
        )


if __name__ == "__main__":
    unittest.main()
