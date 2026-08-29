import collections
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site


class AttachGeoTests(unittest.TestCase):
    def test_generic_gym_name_stays_on_known_campus(self):
        venues = build_site.load_venues()
        events = [
            {"campus": "nthu-main", "venue": "體育館2F（全）"},
            {"campus": "nycu-guangfu", "venue": "體育館2F（全）"},
        ]

        self.assertEqual(build_site.attach_geo(events, venues), 2)
        self.assertEqual(events[0]["campus"], "nthu-main")
        self.assertEqual(events[0]["geo"]["name"], "新體育館")
        self.assertEqual(events[1]["campus"], "nycu-guangfu")
        self.assertEqual(events[1]["geo"]["name"], "體育館")

    def test_all_registered_cross_campus_names_respect_the_known_campus(self):
        venues = build_site.load_venues()
        by_key = collections.defaultdict(list)
        for row in venues:
            for key in [row["name"], *row["aliases"]]:
                by_key[key].append(row)

        collisions = {
            key: rows for key, rows in by_key.items()
            if len({row["campus"] for row in rows}) > 1
        }
        self.assertIn("體育館", collisions)
        self.assertIn("工程一館", collisions)
        self.assertIn("學生活動中心", collisions)

        for key, rows in collisions.items():
            for row in rows:
                with self.subTest(venue=key, campus=row["campus"]):
                    event = {"campus": row["campus"], "venue": key}
                    build_site.attach_geo([event], venues)
                    self.assertEqual(event["campus"], row["campus"])
                    self.assertEqual(event["geo"]["name"], row["name"])

    def test_unregistered_name_cannot_jump_from_a_known_campus(self):
        event = {"campus": "nthu-main", "venue": "綜合球館"}

        build_site.attach_geo([event], build_site.load_venues())

        self.assertEqual(event["campus"], "nthu-main")
        self.assertTrue(event["geo"]["approximate"])
        self.assertEqual(
            (event["geo"]["lat"], event["geo"]["lng"]),
            build_site.CAMPUS_GEO["nthu-main"],
        )

    def test_unique_venue_can_fill_an_unknown_campus(self):
        event = {"campus": None, "venue": "旺宏館"}

        build_site.attach_geo([event], build_site.load_venues())

        self.assertEqual(event["campus"], "nthu-main")
        self.assertEqual(event["geo"]["name"], "總圖書館")


class OrgDisplayNameTests(unittest.TestCase):
    def test_school_and_campus_prefixes(self):
        self.assertEqual(build_site.org_display_name("口琴社", "nthu"), "清大口琴社")
        self.assertEqual(
            build_site.org_display_name("竹韻口琴社", "nycu", "guangfu"),
            "交大竹韻口琴社",
        )
        self.assertEqual(
            build_site.org_display_name("揚鳴口琴社", "nycu", "yangming"),
            "陽明揚鳴口琴社",
        )

    def test_offices_and_full_school_names_are_normalized(self):
        self.assertEqual(build_site.org_display_name("教務處", "nthu"), "清大教務處")
        self.assertEqual(
            build_site.org_display_name("國立陽明交通大學皮藝社", "nycu", "yangming"),
            "陽明皮藝社",
        )
        self.assertEqual(
            build_site.org_display_name("陽明交大圖書館", "nycu"),
            "陽明交大圖書館",
        )

    def test_joint_and_external_names(self):
        self.assertEqual(
            build_site.org_display_name("清大交大聯合柔道社", "both"),
            "清交聯合柔道社",
        )
        self.assertEqual(build_site.org_display_name("新竹市文化局", "external"), "新竹市文化局")


class StoryDisplayNameTests(unittest.TestCase):
    def test_school_prefixes_are_hidden(self):
        self.assertEqual(build_site.story_display_name("陽明交大竹韻口琴社"), "竹韻口琴社")
        self.assertEqual(build_site.story_display_name("清大教育心理與諮商學系"), "教育心理與諮商學系")
        self.assertEqual(build_site.story_display_name("國立清華大學學生會"), "學生會")
        self.assertEqual(build_site.story_display_name("交大電子競技社"), "電子競技社")

    def test_non_school_name_and_empty_fallback_are_preserved(self):
        self.assertEqual(build_site.story_display_name("陽明愛杏管弦樂團"), "陽明愛杏管弦樂團")
        self.assertEqual(build_site.story_display_name("國立清華大學"), "國立清華大學")


class PostCampusTests(unittest.TestCase):
    def test_directory_campus_wins_over_event_venue(self):
        self.assertEqual(
            build_site.post_campus(
                {"campus": "guangfu", "name": "交大竹韻口琴社"},
                [{"campus": "nycu-yangming"}],
            ),
            "guangfu",
        )

    def test_school_wide_source_uses_unambiguous_event_campus(self):
        self.assertEqual(
            build_site.post_campus(
                {"campus": None, "name": "陽明交大圖書館"},
                [{"campus": "nycu-yangming"}, {"campus": "online"}],
            ),
            "yangming",
        )

    def test_mixed_school_wide_source_stays_unassigned(self):
        self.assertIsNone(
            build_site.post_campus(
                {"campus": None, "name": "陽明交大圖書館"},
                [{"campus": "nycu-guangfu"}, {"campus": "nycu-yangming"}],
            )
        )

    def test_feed_label_uses_nycu_campus(self):
        self.assertEqual(
            build_site._feed_school_label({"school": "nycu", "campus": "guangfu"}),
            "交大",
        )
        self.assertEqual(
            build_site._feed_school_label({"school": "nycu", "campus": "yangming"}),
            "陽明",
        )
        self.assertEqual(build_site._feed_school_label({"school": "nthu"}), "清大")


class SourceTableTests(unittest.TestCase):
    def test_follow_is_the_default_sort_header(self):
        entry = {
            "id": 1,
            "name": "清大測試社",
            "school": "nthu",
            "campus": None,
            "kind": "club",
            "category": None,
            "links": [],
            "events": 0,
            "updated": None,
            "avatar": None,
        }

        rendered = build_site.source_table_html([entry])

        self.assertIn('class="src-th src-th-follow src-th-on" data-sort="follow">追蹤 ↓</button>', rendered)
        self.assertNotIn('data-sort="events">收錄 ↓</button>', rendered)


class RelatedEventsTests(unittest.TestCase):
    @staticmethod
    def event(event_id, title, start_at, campus="nycu-guangfu", venue=None, category="市集", org_id=None):
        return {
            "id": event_id,
            "title": title,
            "start_at": start_at,
            "campus": campus,
            "venue": venue,
            "category": category,
            "org_id": org_id,
        }

    def test_social_expo_page_lists_other_booths_but_not_unrelated_same_time_event(self):
        parent = self.event(
            "parent", "2026 陽明交大社團博覽會", "2026-09-09T17:30:00+08:00", org_id=1)
        art = self.event(
            "art", "交大美術社｜9/9 圖書館前社博攤位", "2026-09-09T17:30:00+08:00",
            venue="圖書館前", org_id=2)
        dog = self.event(
            "dog", "汪汪社社團博覽會攤位", "2026-09-09T17:30:00+08:00",
            venue="工程三館前 40 號攤位", org_id=3)
        unrelated = self.event(
            "talk", "半導體職涯講座", "2026-09-09T17:30:00+08:00",
            venue="工程三館", category="演講", org_id=4)
        other_campus = self.event(
            "yangming", "陽明瑜珈社社團博覽會攤位", "2026-08-31T11:00:00+08:00",
            campus="nycu-yangming", org_id=5)

        related = build_site.related_events(parent, [parent, art, dog, unrelated, other_campus])

        self.assertEqual([event["id"] for event, _ in related], ["art", "dog"])
        self.assertTrue(all(reason == "同場社博" for _, reason in related))

    def test_same_organizer_is_left_to_existing_more_from_organizer_section(self):
        first = self.event("first", "Conversation Circle 秋季開幕場", "2026-09-22T12:00:00+08:00", org_id=8)
        second = self.event("second", "Conversation Circle 秋季第二場", "2026-10-13T12:00:00+08:00", org_id=8)

        self.assertEqual(build_site.related_events(first, [first, second]), [])

    def test_detail_page_renders_relation_reason_and_disclaimer(self):
        event = self.event("parent", "社團博覽會", "2026-09-09T17:30:00+08:00")
        event.update({
            "end_at": None, "all_day": False, "school": "nycu", "summary": "社團博覽會",
            "description": "", "organizer": "課外組", "organizer_type": "official", "reg": None,
            "price": None, "fee": None, "registration_url": None, "registration_deadline": None,
            "source": {"url": "https://example.com/post"}, "extraction": {"needs_review": False},
        })
        booth = self.event("booth", "美術社社博攤位", "2026-09-09T17:30:00+08:00")

        rendered = build_site.detail_page(event, related=[(booth, "同場社博")])

        self.assertIn("可能相關的活動", rendered)
        self.assertIn("實際關係以主辦單位公告為準", rendered)
        self.assertIn("美術社社博攤位", rendered)
        self.assertIn("同場社博", rendered)


if __name__ == "__main__":
    unittest.main()
