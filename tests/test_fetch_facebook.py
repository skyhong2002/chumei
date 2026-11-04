import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_facebook import rebase_intervals

HOUR = 3600.0


class RebaseIntervalTests(unittest.TestCase):
    def test_successful_pages_follow_the_current_budget_interval(self):
        schedule = {"accounts": {
            # Fetched under the old one-week interval: now due 300h after success.
            "ok": {"last_attempt": 1000.0, "last_success": 1000.0, "consecutive_failures": 0,
                   "interval_hours": 168.0, "next_eligible": 1000.0 + 170 * HOUR},
            # In failure backoff: its retry time is kept.
            "failing": {"last_attempt": 5000.0, "last_success": 1000.0, "consecutive_failures": 1,
                        "interval_hours": 168.0, "next_eligible": 5000.0 + 3 * HOUR},
            "never": {},
        }}
        self.assertEqual(rebase_intervals(schedule, 300.0), 1)
        accounts = schedule["accounts"]
        self.assertEqual(accounts["ok"]["next_eligible"], 1000.0 + 300 * HOUR)
        self.assertEqual(accounts["ok"]["interval_hours"], 300.0)
        self.assertEqual(accounts["failing"]["next_eligible"], 5000.0 + 3 * HOUR)
        self.assertEqual(accounts["never"], {})
        # Already on the current interval: nothing to rewrite (keeps jitter).
        self.assertEqual(rebase_intervals(schedule, 300.0), 0)
        # The budget wobbles a little every round; that alone rewrites nothing.
        self.assertEqual(rebase_intervals(schedule, 310.0), 0)
        self.assertEqual(rebase_intervals(schedule, 400.0), 1)


if __name__ == "__main__":
    unittest.main()
