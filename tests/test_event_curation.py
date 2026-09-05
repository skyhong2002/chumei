import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site as b
from event_curation import is_period_event, merge_reviewed_events, write_merged_event_pages


def event(eid, start="2026-09-02T00:00:00+08:00", end="2026-09-07T23:59:59+08:00", **fields):
    return {"id": eid, "title": eid, "start_at": start, "end_at": end, "all_day": True,
            "school": "nthu", "source": {"source_id": "ig_test", "post_id": eid, "platform": "instagram", "url": "https://example.com/" + eid},
            "extraction": {"confidence": .9}, **fields}


class CurationTests(unittest.TestCase):
    def test_only_explicit_ids_merge_and_every_source_survives(self):
        events = [event("a"), event("b"), event("other-session")]
        rows = [{"event_id": "b", "canonical_id": "a"}]
        out = merge_reviewed_events(events, rows)
        self.assertEqual([e["id"] for e in out], ["a", "other-session"])
        self.assertEqual(out[0]["alt_posts"][0]["post_id"], "b")
        self.assertEqual(out[0]["merged_event_ids"], ["b"])
        self.assertEqual(merge_reviewed_events(out, rows), out)

    def test_missing_target_keeps_original(self):
        self.assertEqual(len(merge_reviewed_events([event("a")], [{"event_id": "a", "canonical_id": "absent"}])), 1)

    def test_known_curation_keeps_camp_and_interview_separate(self):
        rows = b.read_sources_csv("event_merges.csv")
        ids = sorted({r[k] for r in rows for k in ("event_id", "canonical_id")})
        out = merge_reviewed_events([event(eid) for eid in ids])
        self.assertEqual(len(out), 2)
        self.assertEqual(sorted(1 + len(e["alt_posts"]) for e in out), [5, 11])

    def test_alias_page_points_to_canonical_and_preserves_source(self):
        out = merge_reviewed_events([event("a"), event("b")], [{"event_id": "b", "canonical_id": "a"}])
        with tempfile.TemporaryDirectory() as tmp:
            write_merged_event_pages(out, Path(tmp), "https://chumei.observe.tw")
            page = (Path(tmp) / "event/b/index.html").read_text()
            self.assertIn('rel="canonical" href="https://chumei.observe.tw/event/a/"', page)
            self.assertIn('content="0;url=/event/a/"', page)
            self.assertEqual(out[0]["alt_sources"], ["https://example.com/b"])

    def test_period_and_overnight_sessions(self):
        self.assertTrue(is_period_event(event("period")))
        self.assertTrue(is_period_event(event("expo", all_day=False)))
        self.assertFalse(is_period_event(event("night", "2026-09-02T22:00:00+08:00", "2026-09-03T02:00:00+08:00", all_day=False)))
        self.assertFalse(is_period_event(event("single", end=None)))
        self.assertFalse(is_period_event(event("day", end="2026-09-02T23:59:59+08:00")))

    def test_ssr_keeps_ongoing_period_and_removes_finished_period(self):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 6, 12, tzinfo=b.TZ_TAIPEI)
        events = [event("interview"), event("camp", end="2026-09-05T23:59:59+08:00"),
                  event("exhibition", "2026-08-01T00:00:00+08:00", "2026-10-10T23:59:59+08:00"),
                  event("talk", "2026-09-06T19:00:00+08:00", "2026-09-06T21:00:00+08:00", all_day=False)]
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            for path, marker in (("events", "ssr-events"), ("calendar", "ssr-cal")):
                (site / path).mkdir()
                (site / path / "index.html").write_text(f'<!-- {marker} --><!-- /{marker} -->')
            with mock.patch.object(b, "SITE", site), mock.patch.object(b, "datetime", FixedDateTime):
                b.prerender_events(copy.deepcopy(events))
                b.prerender_calendar(copy.deepcopy(events))
            listing = (site / "events/index.html").read_text()
            calendar = (site / "calendar/index.html").read_text()
            self.assertIn("期間活動", listing)
            self.assertIn("定時活動", listing)
            self.assertIn('/event/interview/', listing)
            self.assertNotIn('/event/camp/', listing)
            self.assertIn('9/2–9/7', listing)
            self.assertEqual(calendar.count('/event/exhibition/'), 2)  # 跨月每月一次
            self.assertEqual(calendar.count('/event/interview/'), 1)
            self.assertNotIn('/event/camp/', calendar)


if __name__ == "__main__":
    unittest.main()
