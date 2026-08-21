import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import publish_telegram as telegram


def event(event_id="evt_new", start="2026-08-25T14:00:00+08:00", **overrides):
    value = {
        "id": event_id,
        "title": "A < B & 活動",
        "start_at": start,
        "all_day": False,
        "school": "both",
        "campus": "nycu-guangfu",
        "venue": "工程館",
        "organizer": "測試主辦",
        "summary": "公開資訊 & 注意事項",
        "status": "published",
        "first_seen": "2026-08-21T12:00:00+08:00",
        "extraction": {"needs_review": False},
    }
    value.update(overrides)
    return value


class PublisherTests(unittest.TestCase):
    def test_initialize_baselines_only_upcoming_events(self):
        state = telegram.initialize_state(
            [event(), event("evt_old", "2026-08-19T10:00:00+08:00")],
            today="2026-08-21",
        )
        self.assertEqual(set(state["sent"]), {"evt_new"})
        self.assertIn("baselined_at", state["sent"]["evt_new"])

    def test_pending_excludes_sent_past_and_rejected(self):
        events = [
            event(),
            event("evt_sent"),
            event("evt_old", "2026-08-19T10:00:00+08:00"),
            event("evt_rejected", status="rejected"),
        ]
        pending = telegram.pending_events(events, {"sent": {"evt_sent": {}}}, today="2026-08-21")
        self.assertEqual([item["id"] for item in pending], ["evt_new"])

    def test_format_event_escapes_html_and_includes_location(self):
        text = telegram.format_event(event())
        self.assertIn("A &lt; B &amp; 活動", text)
        self.assertIn("交大光復校區 ・ 工程館", text)
        self.assertNotIn("A < B", text)

    def test_review_warning(self):
        text = telegram.format_event(event(extraction={"needs_review": True}))
        self.assertIn("以原始公告為準", text)

    def test_silent_hours(self):
        self.assertTrue(telegram.is_silent_hour(datetime(2026, 8, 21, 23, tzinfo=timezone.utc)))
        self.assertFalse(telegram.is_silent_hour(datetime(2026, 8, 21, 12, tzinfo=timezone.utc)))

    def test_atomic_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telegram.json"
            expected = {"version": 1, "sent": {"evt_new": {"message_id": 7}}}
            telegram.save_state(expected, path)
            self.assertEqual(telegram.load_state(path), expected)
            self.assertFalse(path.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
