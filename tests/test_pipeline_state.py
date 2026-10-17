"""Real child-process races against temporary local state; no external services."""
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pipeline_state import LockBusy, atomic_json, file_lock, merge_json, read_json


def merge_worker(path, prefix, start):
    start.wait(10)
    for index in range(20):
        merge_json(path, {f"{prefix}-{index}": {"events": [], "attempts": index}})


def hold_lock(path, ready, release):
    with file_lock(path):
        ready.set()
        release.wait(10)


def extraction_worker(directory, ready, release, calls):
    import extract_events as x
    from test_extraction_retry import item
    x.EXTRACT_DIR = Path(directory) / "extraction"
    x.GATEWAY_STATE = Path(directory) / "gateway.json"
    x.load_env = lambda: {"CHUMEI_LLM_API_KEY": "fixture-only"}
    x.iter_inbox = lambda: iter([item()])

    def reply(*args, **kwargs):
        calls.put("request")
        ready.set()
        if not release.wait(10):
            raise RuntimeError("test did not release worker")
        return '{"events":[]}', "fixture-model"

    x.call_llm = reply
    sys.argv = ["extract_events.py", "--workers", "1"]
    raise SystemExit(x.main())


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.ctx = multiprocessing.get_context("spawn")
        self.children = []
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for process in self.children:
            if process.is_alive():
                process.terminate()
            process.join(10)

    def start(self, target, *args):
        process = self.ctx.Process(target=target, args=args)
        self.children.append(process)
        process.start()
        return process

    def test_concurrent_merge_keeps_all_history_and_json_readable(self):
        path = self.root / "source.json"
        history = {"historical-event": {"events": [{"id": "past"}], "first_seen": "2020-01-01"}}
        atomic_json(path, history)
        start = self.ctx.Event()
        first = self.start(merge_worker, path, "a", start)
        second = self.start(merge_worker, path, "b", start)
        start.set()
        for _ in range(200):
            self.assertIn("historical-event", json.loads(path.read_text()))
        for process in [first, second]:
            process.join(15)
            self.assertEqual(process.exitcode, 0)
        result = read_json(path)
        self.assertEqual(len(result), 41)
        self.assertEqual(result["historical-event"], history["historical-event"])
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.assertFalse(list(self.root.glob(".*.tmp")))

    def test_failed_atomic_replace_preserves_old_file_and_cleans_temporary(self):
        path = self.root / "cache.json"
        atomic_json(path, {"old": 1})
        with mock.patch("pipeline_state.os.replace", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                atomic_json(path, {"new": 2})
        self.assertEqual(read_json(path), {"old": 1})
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_os_lock_excludes_second_process_and_is_released_after_death(self):
        path = self.root / "job.lock"
        ready, release = self.ctx.Event(), self.ctx.Event()
        process = self.start(hold_lock, path, ready, release)
        self.assertTrue(ready.wait(10))
        with self.assertRaises(LockBusy):
            with file_lock(path, blocking=False):
                self.fail("lock was acquired twice")
        process.terminate()
        process.join(10)
        with file_lock(path, blocking=False):
            self.assertTrue(path.exists())

    def test_competing_extractors_make_one_provider_attempt(self):
        ready, release = self.ctx.Event(), self.ctx.Event()
        calls = self.ctx.Queue()
        first = self.start(extraction_worker, self.root, ready, release, calls)
        self.assertTrue(ready.wait(10))
        second = self.start(extraction_worker, self.root, ready, release, calls)
        second.join(10)
        self.assertEqual(second.exitcode, 0)
        release.set()
        first.join(10)
        self.assertEqual(first.exitcode, 0)
        self.assertEqual(calls.get(timeout=2), "request")
        self.assertTrue(calls.empty())
        self.assertEqual(read_json(self.root / "extraction/fixture.json")["one"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
