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


if __name__ == "__main__":
    unittest.main()
