"""Sitemap, robots 與站內連結的收錄訊號要一致：sitemap 只列可收錄且有站內入口的頁。"""
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site
from chumei_lib import TZ_TAIPEI
from search_discovery import write_search_sitemap

ROBOTS_RE = re.compile(r'<meta name="robots" content="([^"]*)">')


def _event(event_id, end, source_id="src"):
    start = end - timedelta(hours=2)
    return {"id": event_id, "title": f"活動 {event_id}",
            "start_at": start.isoformat(), "end_at": end.isoformat(),
            "source": {"source_id": source_id, "post_id": event_id}}


class OrgPageIndexSignalTests(unittest.TestCase):
    def render(self, entries, events):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(build_site, "SITE", Path(tmp)), \
             patch("chumei_lib.iter_inbox", return_value=iter([])):
            build_site.org_pages(entries, events)
            return {ent["id"]: (Path(tmp) / "org" / ent["id"] / "index.html").read_text() for ent in entries}

    def test_past_list_covers_every_event_inside_the_sitemap_window(self):
        now = datetime.now(TZ_TAIPEI)
        recent = [_event(f"recent{i:02d}", now - timedelta(days=2 + i * 2)) for i in range(30)]
        old = [_event(f"old{i}", now - timedelta(days=200 + i)) for i in range(3)]
        org = {"id": "busy", "name": "演講公告", "school": "nthu", "kind": "unit",
               "links": [{"platform": "website", "url": "https://example.com"}], "sids": ["src"]}
        page = self.render([org], recent + old)["busy"]
        for event in recent:
            self.assertIn(f'href="/event/{event["id"]}/"', page)
        # 超出範圍的舊活動維持原本「最近 20 場」的上限，不無限加長頁面。
        for event in old:
            self.assertNotIn(f'href="/event/{event["id"]}/"', page)
        self.assertIsNone(ROBOTS_RE.search(page))

    def test_short_history_still_shows_the_latest_twenty(self):
        now = datetime.now(TZ_TAIPEI)
        old = [_event(f"old{i:02d}", now - timedelta(days=200 + i)) for i in range(25)]
        org = {"id": "quiet", "name": "社團", "school": "nycu", "kind": "club",
               "links": [], "sids": ["src"]}
        page = self.render([org], old)["quiet"]
        self.assertEqual(len(re.findall(r'href="/event/old\d+/"', page)), 20)

    def test_orgs_without_events_or_schedule_are_noindex(self):
        links = [{"platform": "instagram", "url": "https://instagram.com/x"}]
        entries = [
            {"id": "empty", "name": "空單位", "school": "nthu", "kind": "club", "links": links, "sids": ["none"]},
            {"id": "weekly", "name": "例行社團", "school": "nthu", "kind": "club", "links": links, "sids": ["none"],
             "schedule": [{"weekday": 3, "time": "19:00", "title": "社課", "venue": "活動中心"}]},
        ]
        pages = self.render(entries, [])
        self.assertEqual(ROBOTS_RE.findall(pages["empty"]), ["noindex,follow"])
        self.assertIn("尚未從這個來源收錄到活動", pages["empty"])  # 頁面內容與追蹤按鈕照舊
        self.assertIn('data-org-id="empty"', pages["empty"])
        self.assertEqual(ROBOTS_RE.findall(pages["weekly"]), [])


class LegacyEventIndexSignalTests(unittest.TestCase):
    def test_pages_no_longer_built_from_data_stay_reachable_but_noindex(self):
        structured = json.dumps({"name": "舊活動", "startDate": "2026-05-01T10:00:00+08:00"}, ensure_ascii=False)
        legacy = ('<html><head><title>舊</title><link rel="canonical" href="x"></head><body><h1>舊</h1>'
                  f'<script type="application/ld+json">{structured}</script></body></html>')
        with tempfile.TemporaryDirectory() as tmp, patch.object(build_site, "SITE", Path(tmp)):
            for event_id in ("evt_legacy", "evt_current"):
                path = Path(tmp) / "event" / event_id / "index.html"
                path.parent.mkdir(parents=True)
                path.write_text(legacy)
            build_site.refresh_legacy_event_seo({"evt_current"})
            build_site.refresh_legacy_event_seo({"evt_current"})  # 每次建站都會重跑，不能重複插入
            page = (Path(tmp) / "event/evt_legacy/index.html").read_text()
            current = (Path(tmp) / "event/evt_current/index.html").read_text()
        self.assertEqual(ROBOTS_RE.findall(page), ["noindex,follow"])
        self.assertIn('<link rel="canonical" href="https://chumei.observe.tw/event/evt_legacy/">', page)
        self.assertEqual(current, legacy)


class SitemapIndexSignalTests(unittest.TestCase):
    def test_noindex_pages_are_left_out_of_the_sitemap(self):
        now = datetime.fromisoformat("2026-10-23T12:00:00+08:00")
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            pages = {"index.html": "<main>home</main>",
                     "org/full/index.html": "<main>活動</main>",
                     "org/empty/index.html": '<head><meta name="robots" content="noindex,follow"></head><main></main>',
                     "event/kept/index.html": "<main>活動</main>"}
            for rel, body in pages.items():
                (site / rel).parent.mkdir(parents=True, exist_ok=True)
                (site / rel).write_text(body)
            events = [{"id": "kept", "start_at": "2026-10-20T10:00:00+08:00"}]
            write_search_sitemap(site, events, ["full", "empty", "missing"], [], now, "https://example.com",
                                 state_path=Path(tmp) / "state.json")
            sitemap = (site / "sitemap.xml").read_text()
        self.assertIn("https://example.com/org/full/", sitemap)
        self.assertIn("https://example.com/event/kept/", sitemap)
        self.assertNotIn("/org/empty/", sitemap)
        self.assertNotIn("/org/missing/", sitemap)


if __name__ == "__main__":
    unittest.main()
