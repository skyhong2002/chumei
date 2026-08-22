import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bot_core
from chumei_lib import TZ_TAIPEI

# 2026-08-22 是週六
NOW = datetime(2026, 8, 22, 15, 0, tzinfo=TZ_TAIPEI)

LABELS = {
    "school": {"nthu": "清大", "nycu": "陽明交大", "both": "清大×交大", "external": "校外"},
    "campus": {"nthu-main": "清大校本部", "nycu-guangfu": "交大光復校區",
               "nycu-yangming": "陽明校區", "online": "線上", "other": "其他地點"},
    "org": {"club": "社團"},
}


def event(eid, title, start, **overrides):
    e = {"id": eid, "title": title, "start_at": start, "all_day": False,
         "school": "nthu", "campus": "nthu-main", "venue": "工程一館",
         "organizer": "測試社", "category": "演講", "summary": "", "description": ""}
    e.update(overrides)
    return e


EVENTS = [
    event("evt_a", "今晚演講", "2026-08-22T19:00:00+08:00"),
    event("evt_b", "週日市集", "2026-08-23T10:00:00+08:00",
          school="nycu", campus="nycu-guangfu", category="市集", organizer="交大熱舞社"),
    event("evt_c", "下週三工作坊", "2026-08-26T14:00:00+08:00",
          school="both", category="工作坊"),
    event("evt_d", "上個月的活動", "2026-07-01T10:00:00+08:00"),
    event("evt_e", "全天展覽", "2026-08-23T00:00:00+08:00", all_day=True, category="展覽"),
]

SOURCES = [
    {"id": 42, "name": "交大熱舞社", "school": "nycu", "events": 3, "sids": ["ig_dance"]},
    {"id": 7, "name": "清大登山社", "school": "nthu", "events": 0, "sids": []},
]


class BotCoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "events.json").write_text(json.dumps(
            {"generated_at": NOW.isoformat(), "labels": LABELS, "events": EVENTS},
            ensure_ascii=False))
        (root / "sources.json").write_text(json.dumps(
            {"entries": SOURCES}, ensure_ascii=False))
        self._orig = bot_core.EVENTS_PATH, bot_core.SOURCES_PATH
        bot_core.EVENTS_PATH = root / "events.json"
        bot_core.SOURCES_PATH = root / "sources.json"
        bot_core._CACHE.clear()

    def tearDown(self):
        bot_core.EVENTS_PATH, bot_core.SOURCES_PATH = self._orig
        bot_core._CACHE.clear()
        self.tmp.cleanup()

    # ---- 解析 ----

    def test_parse_no_spaces(self):
        q = bot_core.parse_query("這週末清大演講", NOW)
        self.assertEqual(q["time"][2], "這週末")
        self.assertEqual(q["school"], "nthu")
        self.assertEqual(q["category"], "演講")
        self.assertEqual(q["keyword"], "")

    def test_parse_synonyms_and_campus(self):
        q = bot_core.parse_query("陽明 講座", NOW)
        self.assertEqual(q["campus"], "nycu-yangming")
        self.assertIsNone(q["school"])
        self.assertEqual(q["category"], "演講")

    def test_parse_yangming_jiaoda_is_school(self):
        q = bot_core.parse_query("陽明交大", NOW)
        self.assertEqual(q["school"], "nycu")
        self.assertIsNone(q["campus"])

    def test_parse_keyword_remainder(self):
        q = bot_core.parse_query("下週 熱舞社", NOW)
        self.assertEqual(q["time"][2], "下週")
        self.assertEqual(q["keyword"], "熱舞社")

    def test_parse_help(self):
        self.assertTrue(bot_core.parse_query("", NOW)["help"])
        self.assertTrue(bot_core.parse_query("/start", NOW)["help"])
        self.assertTrue(bot_core.parse_query("說明", NOW)["help"])

    def test_time_ranges(self):
        start, end, _ = bot_core._time_range("今天", NOW)
        self.assertEqual((start.day, end.day), (22, 23))
        start, end, _ = bot_core._time_range("這週末", NOW)  # 週六下午問 → 今天起算
        self.assertEqual((start.day, end.day), (22, 24))
        start, end, _ = bot_core._time_range("下週", NOW)
        self.assertEqual((start.day, end.day), (24, 31))

    # ---- 搜尋 ----

    def test_search_today(self):
        hits = bot_core.search(bot_core.parse_query("今天", NOW), NOW)
        self.assertEqual([e["id"] for e in hits], ["evt_a"])

    def test_search_school_includes_both(self):
        hits = bot_core.search(bot_core.parse_query("清大", NOW), NOW)
        self.assertEqual([e["id"] for e in hits], ["evt_a", "evt_e", "evt_c"])

    def test_search_default_excludes_past(self):
        hits = bot_core.search(bot_core.parse_query("活動", NOW), NOW)
        self.assertNotIn("evt_d", [e["id"] for e in hits])

    def test_search_keyword_matches_organizer(self):
        hits = bot_core.search(bot_core.parse_query("熱舞社", NOW), NOW)
        self.assertEqual([e["id"] for e in hits], ["evt_b"])

    # ---- 回覆 ----

    def test_answer_events(self):
        r = bot_core.answer("這週末", NOW)
        self.assertEqual(r["kind"], "events")
        self.assertIn("3 場", r["title"])
        # 依開始時間排序：evt_a（六 19:00）→ evt_e（日 全天 00:00）→ evt_b（日 10:00）
        self.assertEqual(r["events"][0]["when"], "8/22（六）19:00")
        self.assertEqual(r["events"][1]["when"], "8/23（日）")  # 全天不顯示時間
        self.assertIn("交大光復校區", r["events"][2]["where"])

    def test_answer_org_fallback(self):
        r = bot_core.answer("登山社", NOW)
        self.assertEqual(r["kind"], "org")
        self.assertIn("/org/7/", r["text"])

    def test_answer_empty(self):
        r = bot_core.answer("量子詠春拳", NOW)
        self.assertEqual(r["kind"], "empty")

    def test_answer_help(self):
        r = bot_core.answer("help", NOW)
        self.assertEqual(r["kind"], "help")
        self.assertIn("chumei.observe.tw", r["text"])


if __name__ == "__main__":
    unittest.main()
