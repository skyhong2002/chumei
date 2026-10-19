import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import chumei_lib
import fetch_nycu_life as life
from pipeline_state import atomic_json, read_json


def activity(pid="future", **kwargs):
    return {"publicId": pid, "title": {"zhTW": "Fixture activity"},
            "summary": {"zhTW": "Synthetic description"}, "startAt": "2027-02-01T12:00:00+08:00",
            "endAt": "2027-02-01T13:00:00+08:00", "canonicalUrl": f"https://example.org/{pid}", **kwargs}


class LifeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.patches = [mock.patch.object(chumei_lib, "SEEN_DIR", self.root / "seen"),
                        mock.patch.object(chumei_lib, "INBOX_DIR", self.root / "inbox"),
                        mock.patch.object(life, "STRUCTURED", self.root / "activities.json"),
                        mock.patch.object(life, "record_fetch"),
                        mock.patch.object(life.requests, "get")]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def fetch(self, rows, now):
        life.requests.get.return_value.json.return_value = {"data": rows}
        with mock.patch.object(life, "now_iso", return_value=now):
            life.main()
        return read_json(life.STRUCTURED)

    def test_event_start_is_never_used_as_publication_or_discovery(self):
        now = "2026-10-18T09:00:00+08:00"
        result = self.fetch([activity()], now)[0]
        post = next(chumei_lib.iter_inbox())
        self.assertEqual(post["posted_at"], now)
        self.assertEqual(post["first_seen"], now)
        self.assertEqual(post["publication_time_basis"], "first_seen")
        self.assertIsNone(post["published_at"])
        self.assertEqual(result["start_at"], "2027-02-01T12:00:00+08:00")
        self.assertEqual(result["first_seen"], now)
        later = self.fetch([activity()], "2026-10-19T09:00:00+08:00")[0]
        self.assertEqual(later["first_seen"], now)
        self.assertEqual(later["fetched_at"], "2026-10-19T09:00:00+08:00")
        self.assertEqual(len(list(chumei_lib.iter_inbox())), 1)

    def test_known_publication_is_distinct_from_first_seen(self):
        published, fetched = "2026-10-10T09:00:00+08:00", "2026-10-18T09:00:00+08:00"
        result = self.fetch([activity(publishedAt=published)], fetched)[0]
        self.assertEqual(result["published_at"], published)
        self.assertEqual(result["first_seen"], fetched)
        self.assertEqual(result["source"]["posted_at"], published)
        self.assertEqual(next(chumei_lib.iter_inbox())["publication_time_basis"], "source")

    def test_missing_api_rows_and_unknown_local_fields_are_retained(self):
        historical = {"id": "evt_nyculife_past", "title": "History", "start_at": "2020-01-01T00:00:00+08:00",
                      "source": {"post_id": "past"}, "first_seen": "2019-01-01T00:00:00+08:00"}
        atomic_json(life.STRUCTURED, [historical])
        result = self.fetch([activity()], "2026-10-18T09:00:00+08:00")
        self.assertIn(historical, result)
        # A successful empty snapshot also cannot erase the archive.
        self.assertEqual(self.fetch([], "2026-10-19T09:00:00+08:00"), result)

    def test_legacy_seen_timestamp_is_retained_and_future_publication_is_ignored(self):
        first = "2026-09-01T08:00:00+08:00"
        atomic_json(self.root / "seen/nycu-life-api.json", {"nycu_life_api\tfuture": first})
        result = self.fetch([activity(publishedAt="2027-01-01T00:00:00+08:00")],
                            "2026-10-18T09:00:00+08:00")[0]
        self.assertEqual(result["first_seen"], first)
        self.assertEqual(result["source"]["posted_at"], first)
        self.assertIsNone(result["published_at"])

    def test_refresh_preserves_local_geocode_and_other_unowned_fields(self):
        existing = self.fetch([activity()], "2026-10-18T09:00:00+08:00")
        existing[0]["geo"] = {"lat": 24.8, "lng": 121.0, "name": "Fixture user venue"}
        existing[0]["curation_note"] = "Fixture user correction"
        atomic_json(life.STRUCTURED, existing)
        updated = self.fetch([activity(title={"zhTW": "Updated fixture title"})],
                             "2026-10-19T09:00:00+08:00")[0]
        self.assertEqual(updated["geo"], existing[0]["geo"])
        self.assertEqual(updated["curation_note"], existing[0]["curation_note"])
        self.assertEqual(updated["title"], "Updated fixture title")


if __name__ == "__main__":
    unittest.main()
