"""Synthetic consumer contracts for discovery timestamps; no account/provider IO."""
import copy
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import auth_server as a
import build_site as b


NOW = datetime.fromisoformat("2026-10-18T12:00:00+08:00")
LATER = datetime.fromisoformat("2026-11-18T12:00:00+08:00")
FIRST = "2026-10-10T09:00:00+08:00"
RSS_FIRST = "Sat, 10 Oct 2026 09:00:00 +0800"


def fixture(**fields):
    event = {
        "id": "evt_synthetic", "title": "Synthetic NYCU activity",
        "start_at": "2026-11-01T14:00:00+08:00",
        "end_at": "2026-12-01T17:00:00+08:00",
        "organizer": "Synthetic", "summary": "Offline fixture",
        "source": {"source_id": "nycu_life_api", "post_id": "synthetic",
                   "first_seen": FIRST, "publication_time_basis": "first_seen"},
    }
    event.update(fields)
    return event


def outputs(events, now=NOW):
    with tempfile.TemporaryDirectory() as root:
        rss_path, ics_path = Path(root) / "feed.xml", Path(root) / "feed.ics"
        # Auth and builder consumers receive the identical clock. Builder ICS
        # must pass it through to discovery validation, not reread wall time.
        with patch.object(a, "datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            custom = a._feed_rss(events, "Synthetic")
        b.write_rss(rss_path, events, "Synthetic", now=now)
        b.write_ics(ics_path, events, "Synthetic", now=now)
        return rss_path.read_text(), custom, ics_path.read_bytes()


def dates(xml):
    return [item.findtext("pubDate") for item in ElementTree.fromstring(xml).findall("./channel/item")]


class FeedDiscoveryTests(unittest.TestCase):
    def assert_discovery(self, event, expected=RSS_FIRST, stamp="20261010T010000Z"):
        original = copy.deepcopy(event)
        initial = outputs([event])
        self.assertEqual(initial, outputs([event], LATER))
        self.assertEqual(event, original)
        for rss in initial[:2]:
            self.assertEqual(dates(rss), [expected])
        for field in ("DTSTAMP", "CREATED", "LAST-MODIFIED"):
            self.assertIn(f"{field}:{stamp}".encode(), initial[2])

    def test_legacy_nycu_source_discovery_precedes_future_activity_start(self):
        self.assert_discovery(fixture())

    def test_malformed_event_discovery_falls_through_to_valid_source(self):
        self.assert_discovery(fixture(first_seen="malformed"))

    def test_future_event_discovery_falls_through_to_valid_source(self):
        self.assert_discovery(fixture(first_seen="2099-01-01T00:00:00Z"))

    def test_valid_event_discovery_retains_priority_over_source(self):
        self.assert_discovery(fixture(first_seen="2026-10-09T09:00:00+08:00"),
                              "Fri, 09 Oct 2026 09:00:00 +0800", "20261009T010000Z")

    def test_discovery_offsets_and_legacy_naive_values_normalize_to_taipei(self):
        for value in (FIRST, "2026-10-10T01:00:00Z", "2026-10-09T21:00:00-04:00",
                      "2026-10-10T09:00:00"):
            for location in ("event", "source"):
                with self.subTest(value=value, location=location):
                    event = fixture(first_seen="invalid")
                    target = event if location == "event" else event["source"]
                    target["first_seen"] = value
                    self.assert_discovery(event)

    def test_first_seen_at_alias_is_validated_before_source_selection(self):
        self.assert_discovery(fixture(first_seen="invalid", first_seen_at=FIRST))
        event = fixture(first_seen="invalid", first_seen_at="2099-01-01")
        event["source"].update(first_seen="invalid", first_seen_at=FIRST)
        self.assert_discovery(event)

    def test_unknown_discovery_omits_rss_date_and_creation_only_dtstamp_uses_start(self):
        for value in (None, "invalid", "2099-01-01T00:00:00Z"):
            with self.subTest(value=value):
                event = fixture(first_seen=value, fetched_at=FIRST, published_at=FIRST)
                event["source"].update(first_seen=value, posted_at=FIRST, fetched_at=FIRST)
                initial = outputs([event])
                self.assertEqual(initial, outputs([event], LATER))
                for rss in initial[:2]:
                    self.assertEqual(dates(rss), [None])
                self.assertIn(b"DTSTAMP:20261101T060000Z", initial[2])
                self.assertNotIn(b"CREATED:", initial[2])
                self.assertNotIn(b"LAST-MODIFIED:", initial[2])

    def test_same_clock_rejects_one_second_future_and_accepts_equal_instant(self):
        # This explicit clock is deliberately ahead of the real test-run clock.
        # Re-reading wall time in event_ics would reject otherwise valid evidence.
        now = datetime.fromisoformat("2098-01-01T12:00:00+08:00")
        event = fixture(start_at="2098-01-02", end_at="2098-01-03",
                        first_seen="2098-01-01T04:00:01Z")
        event["source"]["first_seen"] = "2098-01-01T04:00:00Z"
        rss, custom, ics = outputs([event], now)
        for xml in (rss, custom):
            self.assertEqual(dates(xml), ["Wed, 01 Jan 2098 12:00:00 +0800"])
        self.assertIn(b"CREATED:20980101T040000Z", ics)
        self.assertIn(b"DTSTAMP:20980101T040000Z", ics)


if __name__ == "__main__":
    unittest.main()
