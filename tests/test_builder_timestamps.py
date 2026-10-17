"""Synthetic, credential-free builder regressions for observation/publication time."""
import copy
from contextlib import ExitStack, contextmanager
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site as b


FIRST = "2026-10-10T09:00:00+08:00"
NOW = "2026-10-18T12:00:00+08:00"
LATER = "2026-11-18T12:00:00+08:00"
PUBLISHED = "2026-10-01T08:00:00+08:00"


def event(pid="past", start="2026-10-12T14:00:00+08:00", **fields):
    result = {
        "id": "evt_" + pid, "title": "Synthetic " + pid,
        "start_at": start, "end_at": "2099-12-31T17:00:00+08:00",
        "first_seen": FIRST, "fetched_at": NOW,
        "summary": "Synthetic fixture", "school": "nycu", "campus": "nycu-guangfu",
        "organizer": "NYCU LIFE", "organizer_type": "official", "category": "演講",
        "source": {"source_id": "nycu_life_api", "post_id": pid,
                   "platform": "api", "url": "https://example.invalid/" + pid},
    }
    result.update(fields)
    return result


def legacy_inbox(ev, **fields):
    result = {**ev["source"], "source_name": "NYCU LIFE", "raw_source": "nycu-life-api",
              "posted_at": ev["start_at"], "fetched_at": FIRST,
              "school": "nycu", "text": ev["title"], "images": []}
    result.update(fields)
    return result


@contextmanager
def clock_at(value):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime.fromisoformat(value)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    with patch.object(b, "datetime", FixedClock), patch.object(b, "now_iso", return_value=value):
        yield


class BuilderTimestampTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.site = self.root / "site"
        (self.root / "state/extraction").mkdir(parents=True)
        (self.root / "data/sources").mkdir(parents=True)
        self.site.mkdir()
        self.inbox = []
        self.stack.enter_context(patch.object(b, "ROOT", self.root))
        self.stack.enter_context(patch.object(b, "SITE", self.site))
        self.stack.enter_context(patch.object(b, "EXTRACT_DIR", self.root / "state/extraction"))
        self.stack.enter_context(patch("chumei_lib.iter_inbox", side_effect=lambda: iter(self.inbox)))
        self.stack.enter_context(patch("chumei_lib.AVATAR_DIR", self.root / "avatars"))
        self.stack.enter_context(patch("chumei_lib.save_avatar"))
        self.stack.enter_context(patch.object(b, "cache_post_image", return_value=None))
        self.stack.enter_context(patch.object(b, "local_image_size", return_value=None))
        self.stack.enter_context(patch.object(b, "load_recurrings", return_value={}))
        self.stack.enter_context(patch.object(b, "read_sources_csv", side_effect=lambda name: [
            {"name": "NYCU LIFE", "school": "nycu", "source_id": "nycu_life_api",
             "url": "https://example.invalid/life"}
        ] if name == "bulletin_sources.csv" else []))

    def outputs(self, events, clock):
        with clock_at(clock):
            b.attach_source_post_times(events)
            posts = b.build_posts_data(events)
            entries = b.build_sources_data(events)
            b.org_pages(entries, events)
            b.write_rss(self.site / "feed.xml", events, "Synthetic")
            b.write_ics(self.site / "feed.ics", events, "Synthetic")
        return {
            "posts": posts, "entries": entries,
            "org": (self.site / "org" / str(entries[0]["id"]) / "index.html").read_text(),
            "rss": (self.site / "feed.xml").read_text(),
            "ics": (self.site / "feed.ics").read_bytes(),
        }

    def test_legacy_past_and_future_starts_never_become_publication(self):
        events = [event(), event("future", "2026-11-01T14:00:00+08:00")]
        self.inbox = [legacy_inbox(ev) for ev in events]
        original_inbox = copy.deepcopy(self.inbox)
        first = self.outputs(copy.deepcopy(events), NOW)
        # The formerly future start is now past; a refreshed structured fetched_at
        # and another build clock must not manufacture a new posting/discovery.
        for ev in events:
            ev["fetched_at"] = LATER
        second_events = copy.deepcopy(events)
        second = self.outputs(second_events, LATER)
        self.assertEqual(first, second)
        self.assertEqual(self.inbox, original_inbox)
        self.assertEqual({p["post_id"] for p in first["posts"]}, {"past", "future"})
        for post in first["posts"]:
            self.assertEqual(post["posted_at"], FIRST)
            self.assertEqual(post["fetched_at"], FIRST)
            self.assertEqual(post["publication_time_basis"], "first_seen")
            self.assertIsNone(post["published_at"])
        for ev in second_events:
            self.assertEqual(ev["source"]["posted_at"], FIRST)
            self.assertEqual(ev["source"]["publication_time_basis"], "first_seen")
            self.assertIsNone(ev["source"]["published_at"])
        self.assertEqual(first["entries"][0]["updated"], FIRST)
        self.assertIn('org-post-date">10/10', first["org"])
        self.assertNotIn('org-post-date">10/12', first["org"])
        self.assertIn(b"CREATED:20261010T010000Z", first["ics"])

    def test_real_structured_publication_wins_over_legacy_inbox(self):
        for location in ("source", "event"):
            with self.subTest(location=location):
                ev = event()
                target = ev["source"] if location == "source" else ev
                target.update(published_at="2026-10-01T00:00:00Z", publication_time_basis="source")
                ev["source"]["posted_at"] = PUBLISHED
                self.inbox = [legacy_inbox(ev, published_at="2026-10-02T08:00:00+08:00")]
                result = self.outputs([ev], NOW)
                self.assertEqual(ev["source"]["posted_at"], PUBLISHED)
                self.assertEqual(ev["source"]["published_at"], PUBLISHED)
                self.assertEqual(ev["source"]["publication_time_basis"], "source")
                self.assertEqual(result["posts"][0]["posted_at"], PUBLISHED)
                self.assertEqual(result["posts"][0]["first_seen"], FIRST)
                self.assertEqual(result["posts"][0]["publication_time_basis"], "source")
                self.assertEqual(result["entries"][0]["updated"], PUBLISHED)
                self.assertIn('org-post-date">10/1', result["org"])

    def test_timezone_less_and_future_nycu_publication_use_discovery(self):
        for published in ("2026-10-01", "2026-10-01T08:00:00", "2099-01-01T00:00:00Z", "invalid"):
            with self.subTest(published=published):
                ev = event(published_at=published, publication_time_basis="source")
                self.inbox = [legacy_inbox(ev)]
                with clock_at(NOW):
                    b.attach_source_post_times([ev])
                    post = b.build_posts_data([ev])[0]
                self.assertEqual(post["posted_at"], FIRST)
                self.assertEqual(post["publication_time_basis"], "first_seen")
                self.assertIsNone(ev["source"]["published_at"])

    def test_legacy_nycu_without_structured_first_seen_uses_original_inbox_observation(self):
        ev = event(first_seen=None)
        self.inbox = [legacy_inbox(ev)]
        result = self.outputs([ev], NOW)
        self.assertEqual(result["posts"][0]["posted_at"], FIRST)
        self.assertEqual(ev["source"]["first_seen"], FIRST)
        self.assertIn(b"CREATED:20261010T010000Z", result["ics"])
        self.assertIn("Sat, 10 Oct 2026 09:00:00 +0800", result["rss"])

    def test_structured_only_post_uses_publication_or_discovery_never_start(self):
        for known in (False, True):
            with self.subTest(known=known), clock_at(NOW):
                ev = event(published_at=PUBLISHED if known else None)
                post = b.build_posts_data([ev])[0]
                self.assertEqual(post["posted_at"], PUBLISHED if known else FIRST)
                self.assertEqual(post["fetched_at"], FIRST)
                self.assertEqual(post["publication_time_basis"], "source" if known else "first_seen")

    def test_generic_structured_source_is_not_overwritten_and_alts_keep_own_evidence(self):
        ev = event()
        ev["source"].update(source_id="fb_test", posted_at=PUBLISHED, custom="keep")
        ev["alt_posts"] = [{"source_id": "nycu_life_api", "post_id": "alt", "platform": "api"}]
        self.inbox = [
            {"source_id": "fb_test", "post_id": "past", "posted_at": FIRST, "fetched_at": NOW},
            {"source_id": "nycu_life_api", "post_id": "alt", "posted_at": ev["start_at"],
             "fetched_at": "2026-10-11T09:00:00+08:00"},
        ]
        with clock_at(NOW):
            b.attach_source_post_times([ev])
        self.assertEqual(ev["source"]["posted_at"], PUBLISHED)
        self.assertEqual(ev["source"]["publication_time_basis"], "source")
        self.assertEqual(ev["source"]["custom"], "keep")
        self.assertEqual(ev["alt_posts"][0]["posted_at"], "2026-10-11T09:00:00+08:00")
        self.assertEqual(ev["alt_posts"][0]["publication_time_basis"], "first_seen")

    def test_unknown_time_has_no_created_or_rss_date_and_rebuild_is_identical(self):
        ev = event(first_seen=None)
        ev["fetched_at"] = NOW  # mutable structured fetch is not discovery evidence
        first = self.outputs([copy.deepcopy(ev)], NOW)
        ev["fetched_at"] = LATER
        second = self.outputs([ev], LATER)
        self.assertEqual(first, second)
        self.assertEqual(first["posts"][0]["posted_at"], "")
        self.assertEqual(first["posts"][0]["publication_time_basis"], "unknown")
        self.assertNotIn("updated", first["entries"][0])
        self.assertNotIn(b"CREATED:", first["ics"])
        self.assertNotIn(b"LAST-MODIFIED:", first["ics"])
        self.assertIn(b"DTSTAMP:20261012T060000Z", first["ics"])
        self.assertNotIn("pubDate", first["rss"])

    def test_record_first_seen_survives_retry_and_existing_event_timestamp_wins(self):
        cache = self.root / "state/extraction/test.json"
        historical = "2026-09-01T09:00:00+08:00"
        legacy = event("legacy")
        legacy.pop("first_seen")
        preserved = event("preserved", first_seen=historical)
        def write_cache(retried):
            cache.write_text(json.dumps({"post": {
                "first_seen": FIRST, "ts": retried, "events": [legacy, preserved],
            }}))
        write_cache(NOW)
        initial = b.load_events()
        first = self.outputs(initial, NOW)
        write_cache(LATER)
        retried = b.load_events()
        self.assertEqual([e["first_seen"] for e in retried], [FIRST, historical])
        self.assertEqual(first, self.outputs(retried, LATER))

    def test_legacy_cache_without_record_first_seen_retains_ts_fallback(self):
        ev = event()
        ev.pop("first_seen")
        (self.root / "state/extraction/test.json").write_text(json.dumps({
            "post": {"ts": FIRST, "events": [ev]},
        }))
        self.assertEqual(b.load_events()[0]["first_seen"], FIRST)

    def test_nycu_seen_state_fills_missing_event_time_without_overwriting_it(self):
        (self.root / "state/seen").mkdir()
        (self.root / "state/seen/nycu-life-api.json").write_text(json.dumps({
            "nycu_life_api\tpast": FIRST, "nycu_life_api\texisting": NOW,
        }))
        missing = event()
        missing.pop("first_seen")
        (self.root / "state/nycu_life_activities.json").write_text(json.dumps([missing, event("existing")]))
        self.assertEqual([ev["first_seen"] for ev in b.load_events()], [FIRST, FIRST])

    def test_inbox_only_nycu_legacy_time_is_rejected_even_when_past(self):
        for start in ("2026-10-12T14:00:00+08:00", "2026-11-01T14:00:00+08:00"):
            post = legacy_inbox(event(start=start))
            for clock in (NOW, LATER):
                self.assertEqual(b.post_publication_time(post, clock), FIRST)
                self.assertEqual(b.post_time_details(post, clock)["publication_time_basis"], "first_seen")
        for post in ({}, {"posted_at": "invalid"}, {"posted_at": "2099-01-01"}):
            self.assertEqual(b.post_publication_time(post, NOW), "")


if __name__ == "__main__":
    unittest.main()
