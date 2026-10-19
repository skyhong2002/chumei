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
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_site as b
import auth_server as a


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
    with patch.object(b, "datetime", FixedClock), patch.object(b, "now_iso", return_value=value), \
            patch.object(a, "datetime", FixedClock):
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
            custom_rss = a._feed_rss(events, "Synthetic")
            custom_ics = a._feed_ics(events, "Synthetic", "https://example.invalid/feed.ics")
            with patch.object(a, "_events_by_id", return_value={e["id"]: e for e in events}):
                personal_ics = a._calendar_ics([e["id"] for e in events], "Synthetic owner")
        return {
            "posts": posts, "entries": entries,
            "org": (self.site / "org" / str(entries[0]["id"]) / "index.html").read_text(),
            "rss": (self.site / "feed.xml").read_text(),
            "ics": (self.site / "feed.ics").read_bytes(),
            "custom_rss": custom_rss, "custom_ics": custom_ics, "personal_ics": personal_ics,
        }

    def assert_final_evidence(self, result, events, has_inbox=True):
        for post in result["posts"] + [e["source"] for e in events]:
            self.assertEqual(post["posted_at"], PUBLISHED)
            self.assertEqual(post["published_at"], PUBLISHED)
            self.assertEqual(post["first_seen"], FIRST)
            self.assertEqual(post["publication_time_basis"], "source")
        self.assertEqual(result["entries"][0]["updated"], PUBLISHED)
        if has_inbox:
            self.assertIn('org-post-date">10/1', result["org"])
        else:
            self.assertNotIn('org-post-date', result["org"])
        for rss in (result["rss"], result["custom_rss"]):
            self.assertEqual([item.findtext("pubDate") for item in
                              ElementTree.fromstring(rss).findall("./channel/item")],
                             ["Sat, 10 Oct 2026 09:00:00 +0800"] * len(events))
        for ics in (result["ics"].decode(), result["custom_ics"], result["personal_ics"]):
            for field in ("DTSTAMP", "CREATED", "LAST-MODIFIED"):
                stamps = [line for line in ics.splitlines() if line.startswith(field + ":")]
                self.assertEqual(stamps, [field + ":20261010T010000Z"] *
                                 (len(events) + (field == "LAST-MODIFIED")))

    def test_invalid_primary_source_does_not_mask_valid_event_across_consumers(self):
        for bad in ("malformed", "2099-01-01T00:00:00Z"):
            for inbox_publication in (None, "", "2026-10-03T09:00:00+08:00"):
                with self.subTest(bad=bad, inbox_publication=inbox_publication):
                    ev = event(start="2026-11-01T12:00:00+08:00", published_at=PUBLISHED)
                    ev["source"].update(published_at=bad, first_seen=bad)
                    self.inbox = [] if inbox_publication is None else [legacy_inbox(
                        ev, published_at=inbox_publication, fetched_at="2026-10-11T09:00:00+08:00")]
                    original_inbox = copy.deepcopy(self.inbox)
                    # Consumers must work independently, before source attachment
                    # has had an opportunity to sanitize their input.
                    with clock_at(NOW):
                        direct_posts = b.build_posts_data([ev])
                        direct_entries = b.build_sources_data([ev])
                        b.org_pages(direct_entries, [ev])
                        direct_html = (self.site / "org" / str(direct_entries[0]["id"]) / "index.html").read_text()
                    initial_events = [copy.deepcopy(ev)]
                    result = self.outputs(initial_events, NOW)
                    self.assert_final_evidence(result, initial_events, has_inbox=inbox_publication is not None)
                    self.assertEqual(result["posts"], direct_posts)
                    self.assertEqual(result["entries"], direct_entries)
                    self.assertEqual(result["org"], direct_html)
                    self.assertEqual(self.inbox, original_inbox)
                    self.assertEqual(result, self.outputs([copy.deepcopy(ev)], LATER))
                    self.assertEqual(result, self.outputs(initial_events, NOW))

    def test_duplicate_records_validate_before_merging_in_either_order(self):
        for bad in ("malformed", "2099-01-01T00:00:00Z"):
            for reverse in (False, True):
                with self.subTest(bad=bad, reverse=reverse):
                    invalid = event(first_seen=bad, published_at=bad)
                    invalid["source"].update(first_seen=bad, first_seen_at=bad,
                                             published_at=bad, custom="keep")
                    valid = event(first_seen=bad, first_seen_at=FIRST, published_at=PUBLISHED)
                    valid["id"] = "evt_same_post_second_activity"
                    events = [invalid, valid][::(-1 if reverse else 1)]
                    self.inbox = [legacy_inbox(invalid, published_at="2026-10-03T09:00:00+08:00",
                                               fetched_at="2026-10-11T09:00:00+08:00")]
                    result = self.outputs(events, NOW)
                    self.assert_final_evidence(result, events)
                    self.assertEqual(b.event_post_records(events, NOW)[("nycu_life_api", "past")]["custom"], "keep")

    def test_generic_duplicate_legacy_times_keep_basis_and_discovery_separate(self):
        for bad in ("malformed", "2099-01-01T00:00:00Z"):
            for basis in ("source", "first_seen", "unknown"):
                with self.subTest(bad=bad, basis=basis):
                    invalid = event(first_seen=bad, published_at=bad)
                    invalid["source"].update(source_id="fb_test", posted_at=bad,
                                             publication_time_basis=basis)
                    valid = copy.deepcopy(invalid)
                    valid["source"].update(posted_at=PUBLISHED, first_seen_at=FIRST,
                                           publication_time_basis="source")
                    records = b.event_post_records([invalid, valid], NOW)
                    record = b.post_time_details({}, NOW, records[("fb_test", "past")])
                    self.assertEqual(record["published_at"], PUBLISHED)
                    self.assertEqual(record["first_seen"], FIRST)
                    self.assertEqual(record["publication_time_basis"], "source")

    def test_alternate_invalid_evidence_never_inherits_primary_event_times(self):
        for bad in ("malformed", "2099-01-01T00:00:00Z"):
            for own_publication in (None, "", "2026-10-03T09:00:00+08:00"):
                with self.subTest(bad=bad, own_publication=own_publication), clock_at(NOW):
                    ev = event(published_at=PUBLISHED)
                    alt = {"source_id": "nycu_life_api", "post_id": "alt", "platform": "api",
                           "first_seen": bad, "published_at": bad, "posted_at": ev["start_at"]}
                    ev["alt_posts"] = [alt]
                    self.inbox = [] if own_publication is None else [{
                        **alt, "published_at": own_publication, "fetched_at": "2026-10-11T09:00:00+08:00"}]
                    original = copy.deepcopy(ev)
                    records = b.event_post_records([ev], NOW)
                    self.assertEqual(ev, original)
                    self.assertFalse(records[("nycu_life_api", "alt")]["published_at"])
                    self.assertEqual(records[("nycu_life_api", "alt")]["first_seen"], "")
                    b.attach_source_post_times([ev])
                    self.assertEqual(ev["source"]["published_at"], PUBLISHED)
                    self.assertEqual(alt["published_at"], own_publication or None)
                    self.assertEqual(alt["first_seen"], "" if own_publication is None else "2026-10-11T09:00:00+08:00")
                    self.assertEqual(alt["publication_time_basis"], "unknown" if own_publication is None
                                     else "source" if own_publication else "first_seen")

    def test_duplicate_publication_retains_explicit_priority_and_own_legacy_basis(self):
        legacy = event()
        legacy["source"].update(source_id="fb_test", posted_at="2026-10-03T09:00:00+08:00")
        explicit = copy.deepcopy(legacy)
        explicit["published_at"] = PUBLISHED
        for events in ([legacy, explicit], [explicit, legacy]):
            with self.subTest(order=[bool(ev.get("published_at")) for ev in events]):
                record = b.event_post_records(events, NOW)[("fb_test", "past")]
                self.assertEqual(record["published_at"], PUBLISHED)
        for basis in ("first_seen", "unknown"):
            with self.subTest(basis=basis):
                discovery = copy.deepcopy(legacy)
                discovery["source"]["publication_time_basis"] = basis
                unknown = copy.deepcopy(legacy)
                unknown["source"]["posted_at"] = "invalid"
                record = b.post_time_details({}, NOW, b.event_post_records([unknown, discovery], NOW)[("fb_test", "past")])
                self.assertIsNone(record["published_at"])
                self.assertEqual(record["first_seen"], FIRST)
                self.assertEqual(record["publication_time_basis"], "first_seen")

    def test_inbox_nycu_identity_still_rejects_structured_legacy_posted_at(self):
        ev = event()
        ev["source"].update(source_id="legacy_api", posted_at=PUBLISHED)
        self.inbox = [legacy_inbox(ev)]  # raw_source alone identifies the adapter
        with clock_at(NOW):
            b.attach_source_post_times([ev])
            post = b.build_posts_data([ev])[0]
        self.assertIsNone(ev["source"]["published_at"])
        self.assertEqual(ev["source"]["publication_time_basis"], "first_seen")
        self.assertIsNone(post["published_at"])
        self.assertEqual(post["posted_at"], FIRST)

    def test_evidence_index_uses_supplied_clock_and_preserves_valid_source_priority(self):
        ev = event(first_seen="2098-01-01T12:00:00+08:00", published_at="2098-01-01T12:00:00+08:00")
        ev["source"].update(first_seen="2098-01-01T04:00:01Z", published_at="2098-01-01T04:00:01Z")
        with patch.object(b, "now_iso", side_effect=AssertionError("must use supplied clock")):
            record = b.event_post_records([ev], "2098-01-01T12:00:00+08:00")[("nycu_life_api", "past")]
        self.assertEqual(record["first_seen"], "2098-01-01T12:00:00+08:00")
        self.assertEqual(record["published_at"], "2098-01-01T12:00:00+08:00")
        ev.update(first_seen="2026-10-11T09:00:00+08:00", published_at="2026-10-03T09:00:00+08:00")
        ev["source"].update(first_seen=FIRST, published_at=PUBLISHED)
        record = b.event_post_records([ev], NOW)[("nycu_life_api", "past")]
        self.assertEqual(record["first_seen"], FIRST)
        self.assertEqual(record["published_at"], PUBLISHED)

    def test_publication_timezone_provenance_survives_index_and_all_consumers(self):
        for identity in ("source_id", "structured_raw_source", "inbox_raw_source", "generic"):
            for location in ("source", "event"):
                for raw in ("2026-10-01", "2026-10-01T08:00:00",
                            "2026-10-01T00:00:00Z", PUBLISHED):
                    for inbox_publication in ("", "2026-10-03T09:00:00+08:00", "2026-10-03T09:00:00"):
                        with self.subTest(identity=identity, location=location, raw=raw,
                                          inbox_publication=inbox_publication):
                            ev = event(start="2026-11-01T12:00:00+08:00")
                            sid = "nycu_life_api" if identity == "source_id" else "legacy_api"
                            ev["source"].update(source_id=sid, custom="keep")
                            if identity == "structured_raw_source":
                                ev["source"]["raw_source"] = "nycu-life-api"
                            (ev["source"] if location == "source" else ev)["published_at"] = raw
                            inbox = legacy_inbox(ev, published_at=inbox_publication,
                                                 fetched_at="2026-10-11T09:00:00+08:00")
                            if identity == "generic":
                                inbox.pop("raw_source")
                                inbox["posted_at"] = ""  # explicit publication alone
                            self.inbox = [inbox]
                            original = copy.deepcopy(ev)
                            original_inbox = copy.deepcopy(self.inbox)
                            structured = {**ev["source"], "first_seen": FIRST, "published_at": raw}
                            direct = b.post_time_details(inbox, NOW, structured)
                            aware = raw in ("2026-10-01T00:00:00Z", PUBLISHED)
                            expected_publication = (
                                ("2026-10-01T00:00:00+08:00" if len(raw) == 10 else PUBLISHED)
                                if aware or identity == "generic" else
                                "2026-10-03T09:00:00+08:00" if inbox_publication.endswith("+08:00") else None)
                            expected = {"posted_at": expected_publication or FIRST,
                                        "published_at": expected_publication, "first_seen": FIRST,
                                        "publication_time_basis": "source" if expected_publication else "first_seen"}
                            self.assertEqual(direct, expected)
                            with patch.object(b, "now_iso", side_effect=AssertionError("use supplied clock")):
                                indexed = b.event_post_records([ev], NOW)[(sid, "past")]
                                self.assertEqual(b.post_time_details(inbox, NOW, indexed), direct)
                            self.assertEqual(ev, original)
                            registry = [{"name": "NYCU LIFE", "school": "nycu", "source_id": sid,
                                         "url": "https://example.invalid/life"}]
                            with patch.object(b, "read_sources_csv", side_effect=lambda name:
                                              registry if name == "bulletin_sources.csv" else []):
                                with clock_at(NOW):
                                    posts = b.build_posts_data([ev])
                                    entries = b.build_sources_data([ev])
                                    b.org_pages(entries, [ev])
                                    html = (self.site / "org" / str(entries[0]["id"]) / "index.html").read_text()
                                result = self.outputs([ev], NOW)
                                self.assertEqual(result["posts"], posts)
                                self.assertEqual(result["entries"], entries)
                                self.assertEqual(result["org"], html)
                                self.assertEqual(result, self.outputs([copy.deepcopy(original)], LATER))
                                self.assertEqual(result, self.outputs([ev], NOW))
                            for record in (posts[0], ev["source"]):
                                self.assertEqual({key: record[key] for key in direct}, direct)
                                self.assertNotIn("_published_at_candidates", record)
                                self.assertNotIn("_nycu_publication", record)
                            self.assertEqual(ev["source"]["custom"], "keep")
                            self.assertEqual(entries[0]["updated"], direct["posted_at"])
                            day = datetime.fromisoformat(direct["posted_at"]).day
                            self.assertIn(f'org-post-date">10/{day}', html)
                            for rss in (result["rss"], result["custom_rss"]):
                                self.assertEqual(ElementTree.fromstring(rss).findtext("./channel/item/pubDate"),
                                                 "Sat, 10 Oct 2026 09:00:00 +0800")
                            for ics in (result["ics"].decode(), result["custom_ics"], result["personal_ics"]):
                                for field in ("DTSTAMP", "CREATED", "LAST-MODIFIED"):
                                    self.assertIn(field + ":20261010T010000Z", ics)
                            self.assertEqual(self.inbox, original_inbox)

    def test_late_nycu_identity_keeps_aware_event_fallback_and_alternate_ownership(self):
        for raw in ("2026-10-01", "2026-10-01T08:00:00", "invalid", "2099-01-01T00:00:00Z"):
            with self.subTest(raw=raw), clock_at(NOW):
                ev = event(published_at="2026-10-01T00:00:00Z")
                ev["source"].update(source_id="legacy_api", published_at=raw)
                alt = {**ev["source"], "post_id": "alternate"}
                ev["alt_posts"] = [alt]
                self.inbox = [legacy_inbox(ev, published_at="2026-10-03T09:00:00+08:00"),
                              {**alt, "raw_source": "nycu-life-api", "fetched_at": FIRST,
                               "published_at": ""}]
                records = b.event_post_records([ev], NOW)
                self.assertEqual(b.post_time_details(self.inbox[0], NOW,
                                                    records[("legacy_api", "past")])["published_at"], PUBLISHED)
                b.attach_source_post_times([ev])
                self.assertEqual(ev["source"]["published_at"], PUBLISHED)
                self.assertIsNone(alt["published_at"])
                self.assertEqual(alt["publication_time_basis"], "first_seen")

    def test_duplicate_nycu_identity_revalidates_all_raw_publication_candidates(self):
        for fallback_location in (None, "event", "duplicate"):
            for reverse in (False, True):
                with self.subTest(fallback_location=fallback_location, reverse=reverse):
                    naive = event(published_at="2026-10-01T00:00:00Z" if fallback_location == "event" else None)
                    naive["source"].update(source_id="src", raw_source="old-adapter",
                                            published_at="2026-09-01T08:00:00")
                    identity = event()
                    identity["source"].update(source_id="src", raw_source="nycu-life-api")
                    if fallback_location == "duplicate":
                        identity["source"]["published_at"] = "2026-10-01T00:00:00Z"
                    events = [naive, identity][::(-1 if reverse else 1)]
                    original = copy.deepcopy(events)
                    records = b.event_post_records(events, NOW)
                    resolved = b.post_time_details({}, NOW, records[("src", "past")])
                    self.assertEqual(resolved["published_at"], PUBLISHED if fallback_location else None)
                    self.assertEqual(resolved["posted_at"], PUBLISHED if fallback_location else FIRST)
                    self.assertEqual(resolved["publication_time_basis"], "source" if fallback_location else "first_seen")
                    self.assertEqual(events, original)

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

    def test_load_events_validates_event_record_and_seen_fallback_candidates(self):
        seen = self.root / "state/seen"
        seen.mkdir()
        for bad in ("malformed", "2099-01-01T00:00:00Z"):
            for alias in (None, "2026-10-09T09:00:00+08:00"):
                with self.subTest(bad=bad, alias=alias):
                    (self.root / "state/nycu_life_activities.json").write_text(json.dumps([
                        event(first_seen=bad, first_seen_at=alias),
                    ]))
                    (seen / "nycu-life-api.json").write_text(json.dumps({"nycu_life_api\tpast": FIRST}))
                    (self.root / "state/extraction/test.json").write_text(json.dumps({
                        "valid_record": {"first_seen": FIRST, "ts": NOW,
                                         "events": [event("record", first_seen=bad, first_seen_at=alias)]},
                        "legacy_record": {"first_seen": bad, "ts": FIRST,
                                          "events": [event("legacy", first_seen=bad, first_seen_at=alias)]},
                        "unknown": {"first_seen": bad, "ts": bad,
                                    "events": [event("unknown", first_seen=bad)]},
                    }))
                    with patch.object(b, "now_iso", side_effect=AssertionError("must use supplied clock")):
                        loaded = b.load_events(now=NOW)
                    self.assertEqual([ev["first_seen"] for ev in loaded], [alias or FIRST] * 3 + [""])

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
