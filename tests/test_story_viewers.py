import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import story_viewers
from story_viewers import (AccountUnavailable, Inflact, InstaStoriesViewer, ViewerPool,
                           ViewerUnavailable)


MIDNIGHT = 20713 * 86400.0


class ParsingTests(unittest.TestCase):
    def test_insta_stories_viewer_result_becomes_stories(self):
        reel = {"id": "4011390791265157816", "taken_at": "1792415067", "is_video": "True",
                "display_url": "11a+b/c=", "video_url": "zz"}
        body = json.dumps(["searchResult", {"data": {"status": "success", "user": {"reels": [reel, {"id": "x"}]}}}])
        [story] = InstaStoriesViewer()._parse(body)
        self.assertEqual(story["id"], "4011390791265157816")
        self.assertEqual(story["taken_at"], 1792415067.0)
        self.assertTrue(story["is_video"])
        self.assertEqual(story["image_url"], "https://cdn.iqsaved.com/img2.php?url=11a%2Bb%2Fc%3D")

    def test_insta_stories_viewer_error_is_about_the_account(self):
        body = json.dumps(["searchResult", {"data": {"status": "error", "code": 430}}])
        with self.assertRaises(AccountUnavailable):
            InstaStoriesViewer()._parse(body)
        with self.assertRaises(ViewerUnavailable):
            InstaStoriesViewer()._parse('["searchResult"]')

    def test_inflact_key_is_rebuilt_from_the_masked_bundle_arrays(self):
        def mask(text):
            return ",".join(str(ord(char) ^ index) for index, char in enumerate(text))
        script = (f'let i=[{mask("ab")}],s=t=>t,a=[{mask("ef")}],d=[{mask("cd")}],c=t=>t,'
                  f'u=[{mask("gh")}];l=[s(c(i).join("")),s(c(d).join("")),s(c(a).join("")),'
                  f's(c(u).join(""))].join("");o.set("X-Client-Signature",v)')
        self.assertEqual(Inflact.signing_key(script), "abcdefgh")
        self.assertIsNone(Inflact.signing_key("X-Client-Signature"))


class _Fake(story_viewers.Viewer):
    daily_limit = 3

    def __init__(self, answers, name="fake"):
        self.answers, self.name = list(answers), name

    def fetch(self, username):
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.now = MIDNIGHT
        self.slept = []

    def pool(self, *viewers):
        pool = ViewerPool((), path=Path(self.tempdir.name) / "viewers.json",
                          sleep=self.sleep, clock=lambda: self.now)
        pool.viewers = list(viewers)
        return pool

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def test_lookups_are_spaced_and_capped_per_day(self):
        viewer = _Fake([[], [], [], []])
        pool = self.pool(viewer)
        for _ in range(3):
            pool.lookup(viewer, "club")
        self.assertEqual(self.slept, [story_viewers.MIN_GAP_SECONDS] * 2)
        self.assertEqual(pool.available(), [])
        self.now = MIDNIGHT + 86400
        self.assertEqual(pool.available(), [viewer])

    def test_refusal_parks_the_viewer_for_hours(self):
        viewer = _Fake([ViewerUnavailable("HTTP 429")])
        pool = self.pool(viewer)
        with self.assertRaises(ViewerUnavailable):
            pool.lookup(viewer, "club")
        self.assertEqual(pool.available(), [])
        self.now += story_viewers.PARK_HOURS * 3600 + 1
        self.assertEqual(pool.available(), [viewer])

    def test_repeated_missing_accounts_look_like_throttling(self):
        viewer = _Fake([AccountUnavailable("430")] * 2 + [[]] + [AccountUnavailable("430")] * 3)
        viewer.daily_limit = 10
        pool = self.pool(viewer)
        for _ in range(2):
            with self.assertRaises(AccountUnavailable):
                pool.lookup(viewer, "gone")
        pool.lookup(viewer, "club")  # a success resets the streak
        for _ in range(2):
            with self.assertRaises(AccountUnavailable):
                pool.lookup(viewer, "gone")
        with self.assertRaises(ViewerUnavailable):
            pool.lookup(viewer, "gone")
        self.assertEqual(pool.available(), [])


if __name__ == "__main__":
    unittest.main()
