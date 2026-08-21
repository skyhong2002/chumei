import json
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
        "original_text": "第一段原文。\n\n第二段有 <標籤> & 符號。",
        "source_name": "清大藝術與設計學系",
        "source_platform": "facebook",
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
        pending = telegram.pending_events(
            events,
            {"sent": {"evt_sent": {"sent_at": "2026-08-21T12:00:00+08:00"}}},
            today="2026-08-21",
        )
        self.assertEqual([item["id"] for item in pending], ["evt_new"])

    def test_pending_resumes_incomplete_multipart_delivery(self):
        pending = telegram.pending_events(
            [event()],
            {"sent": {"evt_new": {"started_at": "2026-08-21T12:00:00+08:00", "message_ids": [7]}}},
            today="2026-08-21",
        )
        self.assertEqual([item["id"] for item in pending], ["evt_new"])

    def test_format_event_escapes_html_and_includes_location(self):
        text = telegram.format_event(event())
        self.assertIn("A &lt; B &amp; 活動", text)
        self.assertIn("交大光復校區 ・ 工程館", text)
        self.assertIn("國立清華大學藝術與設計學系 (Facebook)", text)
        self.assertIn("<blockquote expandable>", text)
        self.assertIn("第二段有 &lt;標籤&gt; &amp; 符號。", text)
        self.assertNotIn("A < B", text)

    def test_review_warning(self):
        text = telegram.format_event(event(extraction={"needs_review": True}))
        self.assertIn("以原始公告為準", text)

    def test_long_original_text_is_fully_split(self):
        original = ("第一段 " * 800) + "最後一句"
        messages = telegram.format_event_messages(event(original_text=original))
        self.assertGreater(len(messages), 1)
        rendered = "".join(messages)
        self.assertIn("第一段", rendered)
        self.assertIn("最後一句", rendered)
        self.assertTrue(all(len(message) < 4096 for message in messages))

    def test_source_and_detail_buttons(self):
        buttons = telegram.event_buttons(event(source={"url": "https://example.com/source"}))
        row = buttons["inline_keyboard"][0]
        self.assertEqual([button["text"] for button in row], ["活動詳情", "原始來源"])
        self.assertEqual(row[1]["url"], "https://example.com/source")

    def test_send_event_disables_preview_and_records_each_part(self):
        client = telegram.TelegramClient("token", "@channel")
        calls = []
        recorded = []

        def fake_call(method, payload, attempts=2):
            calls.append((method, payload, attempts))
            return {"message_id": len(calls)}

        client.call = fake_call
        client.send_event(
            event(source={"url": "https://example.com/source"}),
            on_sent=lambda message, index, total: recorded.append((message["message_id"], index, total)),
        )
        self.assertEqual(calls[0][0], "sendMessage")
        self.assertEqual(calls[0][1]["reply_markup"]["inline_keyboard"][0][1]["text"], "原始來源")
        self.assertEqual(calls[0][1]["link_preview_options"], {"is_disabled": True})
        self.assertEqual(recorded, [(1, 0, 1)])

    def test_load_original_texts_uses_newest_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed.jsonl"
            rows = [
                {"source_id": "source", "post_id": "post", "text": "舊文", "fetched_at": "2026-08-20"},
                {"source_id": "source", "post_id": "post", "text": "新文", "fetched_at": "2026-08-21"},
            ]
            path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows))
            self.assertEqual(telegram.load_original_texts(Path(directory))[("source", "post")], "新文")

    def test_source_context_uses_inbox_name_and_platform(self):
        values = [event(source={"source_id": "source", "post_id": "post", "platform": "web"})]
        telegram.attach_source_context(values, {
            ("source", "post"): {
                "text": "原始內容",
                "source_name": "陽明交大圖書館",
                "platform": "facebook",
            }
        })
        self.assertEqual(values[0]["original_text"], "原始內容")
        self.assertEqual(values[0]["source_name"], "陽明交大圖書館")
        self.assertIn("國立陽明交通大學圖書館 (Facebook)", telegram.format_event(values[0]))

    def test_bulletin_source_name_is_readable(self):
        value = event(
            source_name="交大公告-演講課程",
            source_platform="bulletin",
        )
        self.assertIn("國立陽明交通大學校園公告－演講課程 (官方網站)", telegram.format_event(value))

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
