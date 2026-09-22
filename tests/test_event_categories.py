"""Category aliases must survive ingestion and match the same feed/Bot filters."""
import json
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import auth_server
import bot_core
import build_site
import extract_events
import fetch_nycu_life
import mcp_server
from chumei_lib import TZ_TAIPEI
from event_categories import CAT_SLUG, SLUG_CAT, normalize_event_category


class EventCategoryTests(unittest.TestCase):
    def event(self, category):
        return {"id": "evt_test123", "title": "測試", "category": category,
                "start_at": "2026-10-01T10:00:00+08:00", "school": "nycu",
                "campus": "nycu-guangfu", "source": {"source_id": "nycu_life_api"},
                "extraction": {"needs_review": False, "confidence": 1}}

    def test_aliases_and_slug_preserve_original_and_provenance(self):
        for source, category in [("講座", "演講"), ("社交", "聚會"), ("競賽", "比賽"), ("talk", "演講")]:
            event = self.event(source)
            out = normalize_event_category(event)
            self.assertEqual(out["category"], category)
            self.assertEqual(out["category_original"], source)
            self.assertEqual(out["source"], event["source"])
            self.assertFalse(out["extraction"]["needs_review"])
            self.assertEqual(event["category"], source)
            self.assertEqual(normalize_event_category(out), out)

    def test_unknown_not_discarded_or_guessed_as_talk(self):
        for category in ["學術", "新類別", "", None]:
            event = self.event(category)
            out = normalize_event_category(event)
            self.assertEqual(out["category"], "其他")
            self.assertEqual(out["category_original"], category)
            self.assertFalse(out["category_normalization"]["recognized"])
            self.assertTrue(out["extraction"]["needs_review"])
            self.assertEqual(out["extraction"]["category_review_reason"], "unknown_category")
            self.assertFalse(event["extraction"]["needs_review"])
            self.assertEqual(normalize_event_category(out), out)

    def test_old_build_cache_normalizes_both_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "state" / "nycu_life_activities.json").write_text(json.dumps([self.event("社交")]))
            cache = root / "extraction"
            cache.mkdir()
            (cache / "source.json").write_text(json.dumps({"post": {"events": [self.event("講座"), self.event("學術")]}}))
            with mock.patch.object(build_site, "ROOT", root), mock.patch.object(build_site, "EXTRACT_DIR", cache):
                events = build_site.load_events()
            self.assertEqual([e["category"] for e in events], ["聚會", "演講", "其他"])
            self.assertTrue(events[-1]["extraction"]["needs_review"])

    def test_feed_and_bot_find_old_talk_alias_and_unknown_in_other(self):
        events = [self.event("講座"), {**self.event("學術"), "id": "evt_unknown"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            path.write_text(json.dumps({"events": events}))
            with mock.patch.object(bot_core, "EVENTS_PATH", path), mock.patch.object(bot_core, "_CACHE", {}):
                now = datetime(2026, 9, 23, tzinfo=TZ_TAIPEI)
                hits = bot_core.search(bot_core.parse_query("演講", now), now)
                self.assertEqual([e["id"] for e in hits], ["evt_test123"])
                self.assertEqual(hits[0]["category"], "演講")
                others = bot_core.search(bot_core.parse_query("其他", now), now)
                self.assertEqual([e["id"] for e in others], ["evt_unknown"])
                self.assertTrue(others[0]["extraction"]["needs_review"])
        talk = auth_server._normalize_feed_rule({"categories": ["talk"]})
        other = auth_server._normalize_feed_rule({"categories": ["other"]})
        self.assertTrue(auth_server._event_matches_feed(events[0], talk))
        self.assertFalse(auth_server._event_matches_feed(events[0], other))
        self.assertTrue(auth_server._event_matches_feed(events[1], other))

    def test_mcp_reads_legacy_alias_and_accepts_alias_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.json"
            path.write_text(json.dumps({"events": [self.event("講座"), self.event("學術")]}))
            with mock.patch.object(mcp_server, "EVENTS_PATH", path), mock.patch.object(mcp_server, "_CACHE", {}):
                events = mcp_server.load_events()["events"]
            self.assertEqual([e["category"] for e in events], ["演講", "其他"])
            self.assertTrue(events[1]["extraction"]["needs_review"])
            self.assertEqual(mcp_server._norm_category("講座"), "演講")
            self.assertEqual(mcp_server._norm_category("talk"), "演講")
            with self.assertRaises(ValueError):
                mcp_server._norm_category("學術")

    def test_generated_ics_uses_canonical_category(self):
        event = normalize_event_category(self.event("講座"))
        self.assertIn("CATEGORIES:演講", build_site.event_ics(event))

    def test_extraction_normalizes_alias_without_network(self):
        item = {"source_id": "test", "post_id": "123", "school": "nycu", "source_name": "測試",
                "org_type": "official", "platform": "web", "url": "https://example.com/post",
                "text": "測試", "posted_at": "2026-09-23T10:00:00+08:00"}
        for category in ["講座", "學術"]:
            ev = {**self.event(category), "confidence": 1, "source_timezone": "Asia/Taipei"}
            with mock.patch.object(extract_events, "call_llm", return_value=json.dumps({"events": [ev]})):
                out = extract_events.process_item({}, item, None, {})[2]["events"][0]
            self.assertEqual(out["category"], "演講" if category == "講座" else "其他")
            self.assertEqual(out["category_original"], category)

    def test_nycu_ingress_normalizes_without_live_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "activities.json"
            response = mock.Mock()
            response.json.return_value = {"data": [{"publicId": "abc", "category": "社交"}]}
            with mock.patch.object(fetch_nycu_life.requests, "get", return_value=response), \
                 mock.patch.object(fetch_nycu_life, "SeenState"), \
                 mock.patch.object(fetch_nycu_life, "append_inbox"), \
                 mock.patch.object(fetch_nycu_life, "record_fetch"), \
                 mock.patch.object(fetch_nycu_life, "STRUCTURED", dest):
                fetch_nycu_life.main()
            out = json.loads(dest.read_text())[0]
            self.assertEqual(out["category"], "聚會")
            self.assertEqual(out["category_original"], "社交")

    def test_schema_and_subscription_labels_align(self):
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "scripts/extract_schema.json").read_text())
        self.assertEqual(schema["properties"]["events"]["items"]["properties"]["category"]["enum"], list(CAT_SLUG))
        page = (root / "site/subscribe/index.html").read_text()
        self.assertEqual(json.loads(re.search(r"var CAT=(\{[^;]+\});", page)[1]), SLUG_CAT)
        self.assertEqual(auth_server.CATEGORY_FILTERS, SLUG_CAT)


if __name__ == "__main__":
    unittest.main()
