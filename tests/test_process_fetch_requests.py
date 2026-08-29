import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import process_fetch_requests as processor


class PriorityFetchProcessorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "auth.sqlite3"
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "CREATE TABLE source_fetch_requests (id TEXT PRIMARY KEY,user_id TEXT,source_id TEXT,"
                "source_name TEXT,source_kind TEXT,status TEXT,reason TEXT DEFAULT '',"
                "next_attempt_at INTEGER DEFAULT 0,created_at INTEGER,updated_at INTEGER)"
            )
            conn.execute(
                "INSERT INTO source_fetch_requests VALUES "
                "('fetch_1','user_1','instagram:test','Test','instagram_profile','processing','',0,1,1)"
            )

    def tearDown(self):
        self.tempdir.cleanup()

    def _status(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(
                "SELECT status,reason,next_attempt_at FROM source_fetch_requests WHERE id='fetch_1'"
            ).fetchone()

    def test_instagram_global_cooldown_is_never_bypassed(self):
        source = {"id": "instagram:test", "kind": "instagram_profile", "username": "test", "sourceId": "ig_test"}
        request = {"id": "fetch_1", "source_id": "instagram:test"}
        with patch.object(processor, "cooldown_until", return_value=2000), patch.object(processor.time, "time", return_value=1000):
            outcome = processor.process_one(self.db, request, {source["id"]: source})
        self.assertEqual(outcome, "deferred")
        status, reason, next_attempt = self._status()
        self.assertEqual(status, "deferred")
        self.assertIn("全域冷卻", reason)
        self.assertEqual(next_attempt, 2060)

    def test_apify_exhaustion_defers_without_starting_subprocess(self):
        source = {"id": "facebook:test", "kind": "facebook", "username": "test", "sourceId": "fb_test"}
        request = {"id": "fetch_1", "source_id": "facebook:test"}
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE source_fetch_requests SET source_id='facebook:test'")
        with patch.object(processor, "apify_quota", return_value={"available": True, "exhausted": True, "cycleEnd": None}), patch.object(processor.subprocess, "run") as run:
            outcome = processor.process_one(self.db, request, {source["id"]: source})
        self.assertEqual(outcome, "deferred")
        run.assert_not_called()
        self.assertIn("Apify", self._status()[1])

    def test_commands_are_scoped_to_registered_source(self):
        command = processor.command_for({
            "kind": "threads", "username": "nthu_official", "sourceId": "threads_nthu_official"
        })
        self.assertEqual(command[:5], ["fetch_social.py", "--platform", "threads", "--accounts", "nthu_official"])
        self.assertIsNone(processor.command_for({"kind": "unknown", "username": "x", "sourceId": "x"}))


if __name__ == "__main__":
    unittest.main()
