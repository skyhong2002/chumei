import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site


class OrganizationTimesTests(unittest.TestCase):
    def test_reviewed_official_accounts_do_not_merge_into_similar_units(self):
        rows = {
            "club_roster_nycu.csv": [{"club_name": "健康心理中心志工團", "category": "服務性",
                                       "notes": "光復校區"}],
            "fb_pages.csv": [
                {"page": "arts", "name": "陽明交大藝術與音樂跨域學程", "school": "nycu", "org_type": "official"},
                {"page": "cross", "name": "國立陽明交通大學跨域學程", "school": "nycu",
                 "org_type": "official", "directory_match": "exact"},
                {"page": "center", "name": "陽明交大健康心理中心（交大校區）", "school": "nycu",
                 "org_type": "official", "directory_match": "exact"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(build_site, "ROOT", Path(tmp)), \
             patch.object(build_site, "SITE", Path(tmp) / "site"), \
             patch.object(build_site, "read_sources_csv", side_effect=lambda name: rows.get(name, [])), \
             patch.object(build_site, "load_recurrings", return_value={}), \
             patch("chumei_lib.iter_inbox", return_value=iter([])), \
             patch("chumei_lib.save_avatar"):
            (Path(tmp) / "data/sources").mkdir(parents=True)
            entries = build_site.build_sources_data([])
        self.assertEqual(len(entries), 4)
        cross = next(e for e in entries if "fb_cross" in e.get("sids", []))
        self.assertEqual(cross["sids"], ["fb_cross"])
        center = next(e for e in entries if "fb_center" in e.get("sids", []))
        self.assertEqual(center["kind"], "unit")
        self.assertFalse(center["roster"])

    def test_posts_and_ongoing_events_render_together(self):
        org = {"id": "test-org", "name": "清大測試", "school": "nthu",
               "kind": "club", "links": [], "sids": ["test-source"]}
        event = {"id": "ongoing", "title": "進行中測試活動",
                 "start_at": "2000-01-01T00:00:00+08:00",
                 "end_at": "2099-12-31T23:59:59+08:00",
                 "source": {"source_id": "test-source", "post_id": "p1"}}
        posts = [{"source_id": "test-source", "post_id": "p1",
                  "posted_at": "2026-09-21T12:00:00+08:00", "text": "正常貼文"},
                 {"source_id": "test-source", "post_id": "p2",
                  "posted_at": "2099-01-01T12:00:00+08:00",
                  "fetched_at": "2026-09-20T12:00:00+08:00", "text": "未來日期貼文"}]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(build_site, "SITE", Path(tmp)), \
             patch.object(build_site, "now_iso", return_value="2026-09-23T00:00:00+08:00"), \
             patch("chumei_lib.iter_inbox", return_value=iter(posts)):
            build_site.org_pages([org], [event])
            page = (Path(tmp) / "org/test-org/index.html").read_text()
        self.assertIn("即將舉行（1）", page)
        self.assertIn("收錄貼文（2 則）", page)
        self.assertIn("9/20", page)
        self.assertNotIn("9/23", page)
        self.assertLess(page.index("正常貼文"), page.index("未來日期貼文"))

    def test_org_api_merges_cross_posts_and_prefers_instagram(self):
        org = {"id": 7, "name": "清大測試", "school": "nthu",
               "kind": "club", "links": [], "sids": ["fb_test", "ig_test"]}
        caption = "【期末成果發表】\n" + "歡迎大家一起來聽我們這學期準備的曲目，現場還有小禮物。" * 3
        posts = [{"source_id": "fb_test", "post_id": "1", "platform": "facebook",
                  "url": "https://www.facebook.com/test/posts/1",
                  "posted_at": "2026-09-21T12:00:05+08:00", "text": caption},
                 {"source_id": "ig_test", "post_id": "A", "platform": "instagram",
                  "url": "https://www.instagram.com/p/A/",
                  "posted_at": "2026-09-21T12:00:00+08:00", "text": "\u200b" + caption + " #口琴"},
                 {"source_id": "fb_test", "post_id": "2", "platform": "facebook",
                  "url": "https://www.facebook.com/test/posts/2",
                  "posted_at": "2026-09-10T09:00:00+08:00", "text": "社課公告：本週改到二樓教室上課"},
                 {"source_id": "fb_test", "post_id": "3", "platform": "facebook",
                  "url": "javascript:alert(1)",
                  "posted_at": "2026-09-22T09:00:00+08:00", "text": "不安全的連結不會輸出"}]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(build_site, "SITE", Path(tmp)), \
             patch.object(build_site, "POST_IMG_DIR", Path(tmp) / "assets/posts"), \
             patch.object(build_site, "cache_post_image", return_value=None), \
             patch.object(build_site, "now_iso", return_value="2026-09-23T00:00:00+08:00"), \
             patch("chumei_lib.iter_inbox", return_value=iter(posts)):
            build_site.org_pages([org], [])
            payload = json.loads((Path(tmp) / "api/org/7.json").read_text())
            (Path(tmp) / "api/org/999.json").write_text("{}")
            with patch("chumei_lib.iter_inbox", return_value=iter(posts)):
                build_site.org_pages([org], [])
            self.assertFalse((Path(tmp) / "api/org/999.json").exists())
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["org"], {"id": 7, "name": "清大測試",
                                          "pageUrl": "https://chumei.observe.tw/org/7/"})
        self.assertEqual([item["url"] for item in payload["items"]],
                         ["https://www.instagram.com/p/A/", "https://www.facebook.com/test/posts/2"])
        lead = payload["items"][0]
        self.assertEqual(lead["id"], "ig_test:A")
        self.assertEqual(lead["title"], "【期末成果發表】")
        self.assertEqual(lead["platform"], "Instagram")
        self.assertEqual(lead["publishedAt"], "2026-09-21T04:00:00Z")
        self.assertEqual(lead["alternates"], [{"platform": "Facebook",
                                               "url": "https://www.facebook.com/test/posts/1"}])
        self.assertNotIn("image", lead)

    def test_future_event_date_uses_stable_discovery_across_builds(self):
        post = {"posted_at": "2099-01-01T12:00:00+08:00",
                "first_seen_at": "2026-09-20T04:00:00Z",
                "fetched_at": "2026-09-22T12:00:00+08:00"}
        for now in ("2026-09-23T00:00:00+08:00", "2026-09-24T00:00:00+08:00"):
            self.assertEqual(build_site.post_publication_time(post, now), "2026-09-20T12:00:00+08:00")

    def test_publication_and_timezone_evidence_precede_discovery(self):
        self.assertEqual(build_site.post_publication_time({
            "published_at": "2026-09-22T15:00:00Z", "posted_at": "2099-01-01",
            "fetched_at": "2026-09-23T00:00:00+08:00",
        }, "2026-09-23T00:00:00+08:00"), "2026-09-22T23:00:00+08:00")
        self.assertEqual(build_site.post_publication_time({
            "posted_at": "2026-09-22T20:00:00-08:00",
            "fetched_at": "2026-09-22T12:00:00+08:00",
        }, "2026-09-23T00:00:00+08:00"), "2026-09-22T12:00:00+08:00")

    def test_missing_invalid_or_future_evidence_does_not_invent_freshness(self):
        for post in ({}, {"posted_at": "invalid"}, {"posted_at": "2099-01-01"}):
            self.assertEqual(build_site.post_publication_time(post, "2026-09-23T00:00:00+08:00"), "")
