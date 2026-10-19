import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_stories_public
from fetch_stories_public import (ranked_usernames, remember_story_times, select_active_due,
                                  story_interval_hours, viewer_pass)
from story_viewers import AccountUnavailable, ViewerUnavailable


NOW = datetime(2026, 9, 5, tzinfo=timezone.utc).timestamp()
HOUR = 3600.0


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class StorySchedulingTests(unittest.TestCase):
    def test_recent_story_posters_are_checked_before_their_stories_expire(self):
        self.assertEqual(story_interval_hours([_iso(NOW - 5 * HOUR)], [], now=NOW), 12)
        # The interval stretches as an account stops posting Stories.
        self.assertEqual(story_interval_hours([_iso(NOW - 4 * 24 * HOUR)], [], now=NOW), 24)
        self.assertEqual(story_interval_hours([_iso(NOW - 60 * 24 * HOUR)], [], now=NOW), 168)

    def test_accounts_never_seen_with_a_story_are_probed_slowly(self):
        daily_posts = [_iso(NOW - day * 24 * HOUR) for day in range(5)]
        self.assertEqual(story_interval_hours([], daily_posts, now=NOW), 72)
        self.assertEqual(story_interval_hours([], [], now=NOW), 168)

    def test_story_posters_rank_ahead_of_frequent_post_publishers(self):
        schedule = {"accounts": {"teller": {"story_seen": [_iso(NOW - 2 * HOUR)]}}}
        posts = {"poster": [_iso(NOW - day * 24 * HOUR) for day in range(5)]}
        ranked, intervals = ranked_usernames(["poster", "quiet", "teller"], posts, schedule, now=NOW)
        self.assertEqual(ranked, ["teller", "poster", "quiet"])
        self.assertEqual([intervals[name] for name in ranked], [12, 72, 168])

    def test_active_due_profiles_win_over_never_seen_dormant_profiles(self):
        intervals = {"active": 12, "dormant": 168}
        state = {"accounts": {"active": {"next_eligible": 900, "last_attempt": 100}}}
        self.assertEqual(
            select_active_due(["dormant", "active"], intervals, state, 1, now=1000),
            ["active"],
        )

    def test_story_history_is_deduplicated_and_bounded(self):
        schedule = {"accounts": {}}
        stories = [{"taken_at": _iso(NOW - minute * 60)} for minute in range(30)]
        remember_story_times(schedule, "club", stories)
        remember_story_times(schedule, "club", stories[:3])
        seen = schedule["accounts"]["club"]["story_seen"]
        self.assertEqual(len(seen), fetch_stories_public.STORY_HISTORY_LIMIT)
        self.assertEqual(seen[-1], _iso(NOW))


class _Viewer:
    def __init__(self, name, answers):
        self.name, self.answers = name, answers


class _Pool:
    """Answers lookups from canned per-viewer, per-account results."""

    def __init__(self, *viewers):
        self.viewers = list(viewers)
        self.calls = []

    def available(self):
        return list(self.viewers)

    def lookup(self, viewer, username):
        self.calls.append((viewer.name, username))
        answer = viewer.answers.get(username, [])
        if isinstance(answer, Exception):
            if isinstance(answer, ViewerUnavailable):
                self.viewers.remove(viewer)
            raise answer
        return answer


class ViewerPassTests(unittest.TestCase):
    def setUp(self):
        for name in ("record_fetch", "record_api_call"):
            patcher = patch.object(fetch_stories_public, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(fetch_stories_public, "save_media",
                               side_effect=lambda story: f"/assets/stories/{story['id']}.jpg")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_pass(self, pool, usernames):
        self.state, self.schedule = {}, {"accounts": {}}
        metadata = {name: {"name": name.title()} for name in usernames}
        return viewer_pass(usernames, pool=pool, state=self.state, schedule=self.schedule,
                           metadata=metadata, intervals={name: 12 for name in usernames})

    def test_next_viewer_is_tried_when_the_first_cannot_see_the_account(self):
        story = {"id": "1", "taken_at": NOW - HOUR, "image_url": "https://x/1.jpg", "is_video": True}
        first = _Viewer("first", {"club": AccountUnavailable("code 430")})
        second = _Viewer("second", {"club": [story]})
        uncovered, added = self.run_pass(_Pool(first, second), ["club"])
        self.assertEqual((uncovered, added), ([], 1))
        saved = self.state["1"]
        self.assertTrue(saved["is_video"])
        self.assertEqual(saved["ig_url"], "https://www.instagram.com/stories/club/1/")
        self.assertEqual(self.schedule["accounts"]["club"]["story_seen"], [saved["taken_at"]])
        self.assertIn("next_eligible", self.schedule["accounts"]["club"])

    def test_accounts_no_viewer_covers_are_left_for_apify(self):
        parked = _Viewer("only", {"a": [], "b": ViewerUnavailable("HTTP 429")})
        pool = _Pool(parked)
        uncovered, added = self.run_pass(pool, ["a", "b", "c"])
        self.assertEqual((uncovered, added), (["b", "c"], 0))
        self.assertEqual(pool.calls, [("only", "a"), ("only", "b")])
        self.assertNotIn("b", self.schedule["accounts"])


if __name__ == "__main__":
    unittest.main()
