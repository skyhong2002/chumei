import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_site
import data_quality as quality
import validate_outputs

NOW = datetime.fromisoformat("2026-09-23T12:00:00+08:00")


def event(eid="evt_test", **overrides):
    return {"id": eid, "title": "活動", "start_at": "2026-09-24T10:00:00+08:00",
            "campus": "other", "venue": "台北活動中心", "geo": {"lat": 25, "lng": 121},
            "source": {"url": "https://example.org/event"}, "extraction": {}, **overrides}


class DataQualityTests(unittest.TestCase):
    def test_scope_rank_ongoing_and_undated_without_claiming_unverified_time(self):
        records = [event("later", start_at="2026-10-30", venue=None),
                   event("old", start_at="2026-01-01", venue=None),
                   event("ongoing", start_at="2026-09-01", end_at="2026-09-25", venue=None),
                   event("undated", start_at=None, extraction={"unverified_times": {"start_at": "2026-09-24T12:00:00-07:00"}})]
        report = quality.build_quality_report(records, NOW.isoformat(), NOW)
        self.assertEqual([r["id"] for r in report["items"]], ["ongoing", "undated", "later"])
        self.assertIsNone(report["items"][1]["event_url"])
        self.assertEqual(report["counts"]["active_events"], 2)
        self.assertEqual(report["counts"]["undated_events"], 1)

    def test_missing_field_does_not_claim_source_omission(self):
        e = event(venue=None, geo=None, registration_required=True)
        original = copy.deepcopy(e)
        issues = quality.event_quality_issues(e)
        self.assertEqual({i["code"] for i in issues}, {"missing_venue", "missing_geo", "missing_registration_url"})
        self.assertTrue(all(i["review_status"] == "unverified" for i in issues))
        self.assertEqual(e, original)

    def test_review_requires_known_field_status_and_public_evidence(self):
        e = event(venue=None)
        quality.apply_quality_reviews([e], [{"event_id": e["id"], "field": "venue", "status": "source_not_provided"}])
        self.assertNotIn("data_quality_review", e)
        quality.apply_quality_reviews([e], [{"event_id": e["id"], "field": "venue", "status": "not_extracted", "evidence_url": "https://example.org/announcement", "note": "公告第二段有場地"}])
        issue = quality.event_quality_issues(e)[0]
        self.assertEqual(issue["review_status"], "not_extracted")
        self.assertIn("尚未正確擷取", issue["reason"])

    def test_coverage_excludes_online_and_approximate_from_exact(self):
        events = [event("online", campus="online", venue=None, geo=None),
                  event("approx", geo={"lat": 25, "lng": 121, "approximate": True}, registration_required=True),
                  event("exact", registration_required=True, registration_url="https://example.org/register"),
                  event("unsafe", registration_required=True, registration_url="javascript:alert(1)")]
        report = quality.build_quality_report(events, NOW.isoformat(), NOW)
        self.assertEqual(report["coverage"]["venue"], {"available": 3, "total": 3})
        self.assertEqual(report["coverage"]["exact_location"], {"available": 2, "total": 3})
        self.assertEqual(report["coverage"]["registration_link"], {"available": 1, "total": 3})
        self.assertNotIn("online", [r["id"] for r in report["items"]])

    def test_unknown_category_and_timezone_are_actionable(self):
        e = event(category_original="學術", category_normalization={"recognized": False},
                  extraction={"needs_review": True, "review_reason": "source timezone unknown"})
        self.assertEqual({i["code"] for i in quality.event_quality_issues(e)}, {"unknown_category", "unverified_time"})

    def test_historical_unknown_category_remains_visible_without_polluting_coverage(self):
        e = event(start_at="2026-01-01", category_normalization={"recognized": False})
        report = quality.build_quality_report([e], NOW.isoformat(), NOW)
        self.assertEqual(report["items"][0]["priority"], "historical_review")
        self.assertEqual(report["counts"]["active_events"], 0)
        self.assertEqual(report["coverage"]["venue"]["total"], 0)

    def test_unknown_venue_never_retains_precise_marker(self):
        for venue in [None, "場地另行通知", "TBA"]:
            with self.subTest(venue=venue):
                e = event(venue=venue, campus="nthu-main")
                build_site.attach_geo([e], [])
                self.assertTrue(e["geo"]["approximate"])
                self.assertIn("約略位置", e["geo"]["name"])
        external = event(venue=None)
        build_site.attach_geo([external], [])
        self.assertNotIn("geo", external)

    def test_render_escapes_untrusted_text_and_unsafe_source(self):
        report = quality.build_quality_report([event(title='<img src=x onerror="alert(1)">', venue=None,
                                                     source={"url": "javascript:alert(1)"})], NOW.isoformat(), NOW)
        rendered = quality.render_quality_page(report, lambda title, description, content, **kw: content)
        self.assertNotIn('<img src=x', rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn("GitHub", rendered)
        self.assertIn("尚無來源連結", rendered)
        self.assertIn("來源尚未核對", rendered)

    def test_output_validation_rejects_stale_snapshot_or_unpublished_link(self):
        events = [event(venue=None)]
        report = quality.build_quality_report(events, NOW.isoformat(), NOW)
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            quality.write_quality_report(site, report, lambda title, description, content, **kw: content)
            bundle = {"generated_at": NOW.isoformat(), "events": events}
            self.assertEqual(validate_outputs.validate_quality_report(site, bundle), 0)
            self.assertEqual(validate_outputs.validate_quality_report(site, {**bundle, "generated_at": "old"}), 1)
            self.assertEqual(validate_outputs.validate_quality_report(site, {**bundle, "events": []}), 1)


if __name__ == "__main__":
    unittest.main()
