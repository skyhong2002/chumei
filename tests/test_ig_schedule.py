import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ig_schedule import (clear_global_rate_limit, is_rate_limited, load_schedule,
                         mark_failure, mark_success, save_schedule, select_due,
                         set_global_rate_limit)
from fetch_stories import story_lifecycle


class InstagramScheduleTests(unittest.TestCase):
    def test_due_selection_is_fair_and_honors_next_eligible(self):
        state = {"accounts": {
            "a": {"next_eligible": 500, "last_attempt": 100},
            "b": {"next_eligible": 0, "last_attempt": 200},
            "c": {"next_eligible": 0, "last_attempt": 50},
        }}
        self.assertEqual(select_due(["a", "b", "c"], state, 2, now=100), ["c", "b"])
        self.assertEqual(select_due(["a", "b", "c"], state, 2, now=100, force=True), ["c", "b"])

    def test_success_and_failure_apply_jittered_account_backoff(self):
        state = {"accounts": {}}
        mark_success(state, "club", now=100, interval_hours=48, jitter_hours=6,
                     rng=lambda low, high: high)
        self.assertEqual(state["accounts"]["club"]["next_eligible"], 100 + 54 * 3600)
        mark_failure(state, "club", now=200, base_hours=6, jitter_hours=1,
                     rng=lambda low, high: 0)
        self.assertEqual(state["accounts"]["club"]["next_eligible"], 200 + 6 * 3600)
        mark_failure(state, "club", now=300, base_hours=6, jitter_hours=1,
                     rng=lambda low, high: 0)
        self.assertEqual(state["accounts"]["club"]["next_eligible"], 300 + 12 * 3600)

    def test_global_rate_limit_is_exponential_and_capped(self):
        state = {"accounts": {}, "rate_limit_streak": 0, "global_cooldown_until": 0}
        first = set_global_rate_limit(state, now=100, rng=lambda low, high: 0)
        second = set_global_rate_limit(state, now=200, rng=lambda low, high: 0)
        self.assertEqual(first, 100 + 12 * 3600)
        self.assertEqual(second, 200 + 24 * 3600)
        clear_global_rate_limit(state)
        self.assertEqual(state["global_cooldown_until"], 0)
        self.assertEqual(state["rate_limit_streak"], 0)

    def test_rate_limit_detection_catches_observed_instagram_errors(self):
        self.assertTrue(is_rate_limited('401 Unauthorized: "Please wait a few minutes"'))
        self.assertTrue(is_rate_limited("Fatal error status code 401"))
        self.assertTrue(is_rate_limited("429 Too Many Requests"))
        self.assertFalse(is_rate_limited("404 profile not found"))

    def test_schedule_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schedule.json"
            state = load_schedule(path)
            mark_success(state, "club", now=100, rng=lambda low, high: 0)
            save_schedule(path, state)
            self.assertEqual(load_schedule(path)["accounts"]["club"]["last_success"], 100)

    def test_story_stays_visible_for_48_hours_then_has_media_grace(self):
        now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
        live_at = (now - timedelta(hours=47)).isoformat(timespec="seconds")
        archived_at = (now - timedelta(hours=49)).isoformat(timespec="seconds")
        expired_at = (now - timedelta(hours=73)).isoformat(timespec="seconds")
        self.assertEqual(story_lifecycle(live_at, now)[0], "live")
        self.assertEqual(story_lifecycle(archived_at, now)[0], "archived")
        self.assertEqual(story_lifecycle(expired_at, now)[0], "expired")


if __name__ == "__main__":
    unittest.main()
