import json
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import auth_server
import build_site
from event_time import event_has_not_ended

NOW = datetime.fromisoformat("2026-09-23T12:00:00+08:00")
CASES = [
    ({"start_at": "2026-08-10", "end_at": "2026-10-11", "all_day": True}, True),
    ({"start_at": "2026-08-05", "end_at": "2026-12-06", "all_day": True}, True),
    ({"start_at": "2026-09-23", "end_at": "2026-09-23"}, True),
    ({"start_at": "2026-09-22", "end_at": "2026-09-22", "all_day": True}, False),
    ({"start_at": "2026-09-23T00:00:00+08:00", "end_at": "2026-09-23T00:00:00+08:00", "all_day": True}, True),
    ({"start_at": "2026-09-22T23:00:00+08:00", "end_at": "2026-09-23T13:00:00+08:00"}, True),
    ({"start_at": "2026-09-22T23:00:00+08:00", "end_at": "2026-09-23T12:00:00+08:00"}, False),
    ({"start_at": "2026-09-22T22:00:00-04:00", "end_at": "2026-09-23T01:00:00-04:00"}, True),
    ({"start_at": "2026-09-23T01:00:00Z", "end_at": "2026-09-23T03:59:59Z"}, False),
    ({"start_at": "2026-09-23T09:00:00"}, True),
    ({"start_at": "2026-09-22T09:00:00"}, False),
    ({"start_at": "2026-09-22T22:00:00-07:00"}, True),
    ({"start_at": "2026-09-24"}, True),
    ({"start_at": "invalid"}, False),
    ({"start_at": "2026-09-23", "end_at": "invalid"}, True),
    ({"start_at": "2026-09-23", "end_at": "2026-09-22"}, True),
]


def events():
    return [dict(e, id=f"evt_{i}", title=f"Event {i}", organizer="Test") for i, (e, _) in enumerate(CASES)]


class EventTimeTests(unittest.TestCase):
    def test_inclusive_dates_exclusive_instants_and_missing_end(self):
        for event, expected in CASES:
            with self.subTest(event=event):
                self.assertEqual(event_has_not_ended(event, NOW), expected)
        midnight = datetime.fromisoformat("2026-09-24T00:00:00+08:00")
        self.assertFalse(event_has_not_ended({"start_at": "2026-09-23"}, midnight))
        self.assertFalse(event_has_not_ended({"start_at": "2026-09-22", "end_at": "2026-09-23"}, midnight))

    @unittest.skipUnless(shutil.which("node"), "node required for browser predicate parity")
    def test_browser_and_python_lifetime_rules_match(self):
        source = (ROOT / "site/assets/app.js").read_text()
        helper = source.split("  function eventHasNotEnded", 1)[1].split("  function ongoingLabel", 1)[0]
        program = "function eventHasNotEnded" + helper + "\nconsole.log(JSON.stringify(" + json.dumps([e for e, _ in CASES]) + ".map(e => eventHasNotEnded(e, new Date('2026-09-23T12:00:00+08:00')))));"
        actual = json.loads(subprocess.check_output(["node", "-e", program], text=True))
        self.assertEqual(actual, [expected for _, expected in CASES])

    def test_general_and_custom_feeds_keep_same_unfinished_events(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "all.ics"
            build_site.write_ics(path, events(), "General", now=NOW)
            general = path.read_text()
        with mock.patch.object(auth_server, "datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            custom = auth_server._feed_ics(events(), "Custom", "https://example.test/feed.ics")
        for i, (_, expected) in enumerate(CASES):
            uid = f"UID:evt_{i}@chumei.observe.tw"
            self.assertEqual(uid in general, expected)
            self.assertEqual(uid in custom, expected)

    def test_account_profile_classification_and_private_calendar_history(self):
        fixtures = [events()[0], events()[3]]
        byid = {e["id"]: e for e in fixtures}
        with mock.patch.object(auth_server, "_events_by_id", return_value=byid), mock.patch.object(auth_server, "datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            account = auth_server._going_html(list(byid))
            upcoming, past = account.split('<details class="account-past">')
            self.assertIn("Event 0", upcoming)
            self.assertNotIn("Event 3", upcoming)
            self.assertIn("Event 3", past)
            public = auth_server._profile_html({"id": "u1", "handle": "tester", "profile_public": True}, None, [], list(byid))
            self.assertIn("Event 0", public)
            self.assertNotIn("Event 3", public)
            self.assertIn("<strong>1</strong> 場會去", public)
            history = auth_server._calendar_ics(list(byid))
            self.assertIn("UID:evt_0@", history)
            self.assertIn("UID:evt_3@", history)


if __name__ == "__main__":
    unittest.main()
