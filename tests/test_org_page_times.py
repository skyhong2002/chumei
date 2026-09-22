import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site


class OrganizationTimesTests(unittest.TestCase):
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
