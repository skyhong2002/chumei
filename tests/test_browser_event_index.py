"""Browser index must preserve browsing/search without loading source metadata."""
import copy
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_site
import validate_outputs
import check_browser_budget


class BrowserEventIndexTests(unittest.TestCase):
    def test_partition_covers_all_events_and_keeps_ongoing_and_timezone_boundary(self):
        events = [
            {'id': 'past', 'start_at': '2026-08-20T12:00:00+08:00'},
            {'id': 'current', 'start_at': '2026-09-01T12:00:00+08:00'},
            {'id': 'ongoing', 'start_at': '2026-08-01T12:00:00+08:00', 'end_at': '2026-10-01T12:00:00+08:00'},
            {'id': 'overseas', 'start_at': '2026-08-31T23:00:00-07:00'},
            {'id': 'future', 'start_at': '2027-01-01T12:00:00+08:00'},
        ]
        for e in events:
            e.update(title='title', summary='searchable summary', description='notification keywords', category='演講', source={'post_id': 'large'}, extraction={'needs_review': True, 'raw': 'large'})
        original = copy.deepcopy(events)
        bundle = {'events': events, 'generated_at': 'now', 'labels': {}}
        index, archive = build_site.browser_event_bundles(bundle, date(2026, 9, 23))
        self.assertEqual({e['id'] for e in index['events']}, {'current', 'ongoing', 'overseas', 'future'})
        self.assertEqual([e['id'] for e in archive['events']], ['past'])
        self.assertEqual(index['archive_count'], 1)
        self.assertEqual(index['categories'], ['演講'])
        self.assertEqual(events, original)
        for e in index['events'] + archive['events']:
            self.assertEqual(e['summary'], 'searchable summary')
            self.assertEqual(e['description'], 'notification keywords')
            self.assertNotIn('source', e)
            self.assertEqual(e['extraction'], {'needs_review': True})
        with tempfile.TemporaryDirectory() as directory:
            old_site = build_site.SITE
            try:
                build_site.SITE = Path(directory)
                (build_site.SITE / 'data').mkdir()
                build_site.write_browser_event_bundles(bundle)
                self.assertEqual(validate_outputs.validate_browser_indexes(build_site.SITE, events), 0)
                archive_path = build_site.SITE / 'data/events-archive.json'
                archive_path.write_text(json.dumps({'events': []}))
                self.assertGreater(validate_outputs.validate_browser_indexes(build_site.SITE, events), 0)
                build_site.write_browser_event_bundles(bundle)
                for name in ('events-index', 'events-archive'):
                    self.assertIn('events', json.loads((build_site.SITE / 'data' / (name + '.json')).read_text()))
            finally:
                build_site.SITE = old_site

    def test_budget_fails_closed_and_allows_explicit_positive_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / 'data').mkdir()
            (site / 'data/events-index.json').write_text(json.dumps({'events': []}))
            with mock.patch.dict(os.environ, {'CHUMEI_BROWSER_INDEX_MAX_BYTES': '1'}):
                self.assertFalse(check_browser_budget.check(site))
            with mock.patch.dict(os.environ, {'CHUMEI_BROWSER_INDEX_MAX_BYTES': '1000', 'CHUMEI_BROWSER_INDEX_MAX_GZIP_BYTES': '1000'}):
                self.assertTrue(check_browser_budget.check(site))
            with mock.patch.dict(os.environ, {'CHUMEI_BROWSER_INDEX_MAX_BYTES': '0'}):
                with self.assertRaises(ValueError):
                    check_browser_budget.check(site)

    def test_archive_loader_retries_deduplicates_and_preserves_order(self):
        subprocess.run(['node', str(ROOT / 'tests' / 'event_index_ui.cjs')], cwd=ROOT, check=True)


if __name__ == '__main__':
    unittest.main()
