"""Offline regression cases verified against Luma JSON-LD on 2026-09-23."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_site as b
import extract_events as x
import publish_push as push
from event_curation import write_merged_event_pages


def event(eid='test', **kw):
    result = {'id': eid, 'title': '資訊矽友交流會', 'summary': '', 'description': '',
              'start_at': '2026-09-25T16:00:00-07:00', 'end_at': '2026-09-25T20:00:00-07:00',
              'source_timezone': 'America/Los_Angeles', 'all_day': False,
              'campus': 'other', 'venue': 'San Jose', 'school': 'nycu',
              'organizer': '資訊系友會', 'organizer_type': 'department', 'category': '聚會',
              'registration_url': 'https://luma.com/nycuaa-1ipo', 'registration_deadline': None,
              'status': 'published', 'confidence': .99,
              'source': {'source_id': 'fb_csnctu', 'post_id': eid, 'platform': 'facebook',
                         'url': 'https://example.com/' + eid},
              'extraction': {'confidence': .99, 'needs_review': False}}
    result.update(kw)
    return result


class TimezoneTests(unittest.TestCase):
    def process(self, ev):
        item = {'source_id': 'fb_test', 'post_id': '123', 'school': 'nycu',
                'source_name': '校友會', 'org_type': 'department', 'platform': 'facebook',
                'url': 'https://example.com/post', 'text': '活動於 9/25 舉辦',
                'posted_at': '2026-09-21T06:28:00+00:00'}
        with mock.patch.object(x, 'call_llm', return_value=json.dumps({'events': [ev]})):
            return x.process_item({}, item, None, {})[2]['events'][0]

    def test_valid_overseas_time_preserves_instant_and_source_zone(self):
        out = self.process(event())
        self.assertEqual(out['start_at'], '2026-09-26T07:00:00+08:00')
        self.assertEqual(out['end_at'], '2026-09-26T11:00:00+08:00')
        self.assertEqual(out['source_timezone'], 'America/Los_Angeles')
        self.assertEqual(out['status'], 'published')

    def test_unknown_overseas_zone_is_recoverable_review_not_calendar_instant(self):
        out = self.process(event(source_timezone=None, start_at='2026-09-25T16:00:00+08:00'))
        self.assertEqual(out['status'], 'review')
        self.assertIsNone(out['start_at'])
        self.assertIsNone(out['end_at'])
        self.assertIn('timezone unknown', out['extraction']['review_reason'])
        self.assertEqual(out['extraction']['unverified_times']['start_at'], '2026-09-25T16:00:00+08:00')
        self.assertEqual(b.event_ics(out), '')

    def test_local_campus_default_is_not_affected_by_foreign_speaker(self):
        out = self.process(event(source_timezone=None, campus='nthu-main', venue='清大旺宏館',
                                 title='美國矽谷教授演講', start_at='2026-09-25T16:00:00+08:00',
                                 end_at='2026-09-25T18:00:00+08:00'))
        self.assertEqual(out['status'], 'published')
        self.assertEqual(out['source_timezone'], 'Asia/Taipei')
        self.assertEqual(out['start_at'], '2026-09-25T16:00:00+08:00')

    def test_online_explicit_taiwan_zone_is_published(self):
        out = self.process(event(campus='online', source_timezone='Asia/Taipei',
                                 start_at='2026-09-25T16:00:00+08:00', end_at=None))
        self.assertEqual(out['status'], 'published')

    def test_taiwan_institutional_online_default_records_provenance(self):
        out = self.process(event(campus='online', venue='Zoom', source_timezone=None,
                                 start_at='2026-09-25T16:00:00+08:00', end_at=None))
        self.assertEqual(out['status'], 'published')
        self.assertEqual(out['source_timezone'], 'Asia/Taipei')
        self.assertEqual(out['extraction']['timezone_basis'], 'taiwan-school-online-source')

    def test_foreign_zone_hint_blocks_online_fallback_but_foreign_speaker_does_not(self):
        item = {'school': 'nycu', 'org_type': 'department', 'text': '美國教授 Zoom 線上演講'}
        ev = event(campus='online', venue='Zoom', source_timezone=None,
                   start_at='2026-09-25T16:00:00+08:00', end_at=None)
        self.assertIsNone(x.check_source_timezone(dict(ev), item))
        for text in ['09:00 PDT', '09:00 美國加州時間', '09:00 UTC-7', '09:00 Pacific Time']:
            with self.subTest(text=text):
                self.assertIsNotNone(x.check_source_timezone(dict(ev), {**item, 'text': text}))
        self.assertIsNotNone(x.check_source_timezone(dict(ev), {**item, 'school': 'external'}))

    def test_dst_offsets_and_nonexistent_local_time(self):
        for iso, valid in [('2026-09-25T16:00:00-07:00', True),
                           ('2026-01-25T16:00:00-08:00', True),
                           ('2026-09-25T16:00:00+08:00', False),
                           ('2026-01-25T16:00:00-07:00', False),
                           ('2026-03-08T02:30:00-08:00', False),
                           ('2026-11-01T01:30:00-07:00', True),
                           ('2026-11-01T01:30:00-08:00', True)]:
            with self.subTest(iso=iso):
                reason = x.check_source_timezone(event(start_at=iso, end_at=None))
                self.assertEqual(reason is None, valid, reason)

    def test_explicit_numeric_offset_and_missing_or_invalid_offset(self):
        self.assertIsNone(x.check_source_timezone(event(source_timezone='-07:00')))
        for zone, st in [('-25:00', '2026-09-25T16:00:00-07:00'),
                         ('America/Los_Angeles', '2026-09-25T16:00:00'),
                         ('Mars/Base', '2026-09-25T16:00:00-07:00')]:
            self.assertIsNotNone(x.check_source_timezone(event(source_timezone=zone, start_at=st)))

    def test_ics_and_google_calendar_convert_the_instant(self):
        ev = event()
        ics = b.event_ics(ev)
        self.assertIn('DTSTART;TZID=Asia/Taipei:20260926T070000', ics)
        self.assertIn('DTEND;TZID=Asia/Taipei:20260926T110000', ics)
        page = b.detail_page(ev)
        self.assertIn('dates=20260926T070000/20260926T110000', page)
        self.assertIn('2026 年 9 月 26 日', page)
        self.assertEqual(b.fmt_dt(ev['start_at']), '2026/9/26（六） 07:00')
        self.assertEqual(b.event_ics(event(start_at='2026-09-25T16:00:00')), '')

    def test_all_day_dates_remain_civil_dates(self):
        ev = event(start_at='2026-09-25T00:00:00-07:00', end_at='2026-09-26T00:00:00-07:00', all_day=True)
        x.normalize_event_times(ev)
        ics = b.event_ics(ev)
        self.assertIn('DTSTART;VALUE=DATE:20260925', ics)
        self.assertIn('DTEND;VALUE=DATE:20260927', ics)

    def test_curated_sources_merge_and_old_link_and_reminder_survive(self):
        events = [event('evt_9015433fcfe0', start_at='2026-09-25T16:00:00+08:00'),
                  event('evt_05a9433e4a6e', start_at='2026-09-26T07:00:00+08:00'),
                  event('evt_490332813616', title='Taiwan Tech Summit 2026',
                        registration_url='https://luma.com/fum0o6xh', start_at='2026-09-26T09:00:00+08:00')]
        with mock.patch.object(b, '_post_norm_texts', return_value={}):
            events = b.dedupe(b.apply_overrides(events))
        self.assertEqual(len(events), 2)
        by_id = {e['id']: e for e in events}
        meet = by_id['evt_05a9433e4a6e']
        summit = by_id['evt_490332813616']
        self.assertEqual(meet['start_at'], '2026-09-26T07:00:00+08:00')
        self.assertEqual(summit['start_at'], '2026-09-27T00:00:00+08:00')
        self.assertEqual(summit['end_at'], '2026-09-27T09:00:00+08:00')
        self.assertEqual(meet['alt_posts'][0]['post_id'], 'evt_9015433fcfe0')
        with tempfile.TemporaryDirectory() as tmp:
            write_merged_event_pages(events, Path(tmp), b.BASE_URL)
            page = (Path(tmp) / 'event/evt_9015433fcfe0/index.html').read_text()
            self.assertIn('content="0;url=/event/evt_05a9433e4a6e/"', page)
        plan = push.reminders_for({'dev': {'user_id': 'u'}}, events,
                                 {'u': ['evt_9015433fcfe0', 'evt_05a9433e4a6e']}, {}, today=date(2026, 9, 25))
        self.assertEqual(len(plan), 1)
        self.assertIn('9/26', plan[0][3]['body'])
        self.assertIn('07:00', plan[0][3]['body'])
        self.assertEqual(plan[0][1], 'evt_05a9433e4a6e')
        self.assertEqual(push.reminders_for({'dev': {'user_id': 'u'}}, events,
                         {'u': ['evt_05a9433e4a6e']},
                         {'reminders': {'u:evt_9015433fcfe0': {}}},
                         today=date(2026, 9, 25)), [])


if __name__ == '__main__':
    unittest.main()
