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
                  "posted_at": "2099-01-01T12:00:00+08:00", "text": "未來日期貼文"}]
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(build_site, "SITE", Path(tmp)), \
             patch.object(build_site, "now_iso", return_value="2026-09-23T00:00:00+08:00"), \
             patch("chumei_lib.iter_inbox", return_value=iter(posts)):
            build_site.org_pages([org], [event])
            page = (Path(tmp) / "org/test-org/index.html").read_text()
        self.assertIn("即將舉行（1）", page)
        self.assertIn("收錄貼文（2 則）", page)
        self.assertIn("9/23", page)
        self.assertLess(page.index("未來日期貼文"), page.index("正常貼文"))
