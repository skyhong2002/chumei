"""Real child-process races against temporary local state; no external services."""
import json
import multiprocessing
from pathlib import Path
import queue
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


def extraction_worker(directory, ready, release, calls, phase="provider", prompt_version=3):
    import extract_events as x
    from test_extraction_retry import item
    x.EXTRACT_DIR = Path(directory) / "extraction"
    x.GATEWAY_STATE = Path(directory) / "gateway.json"
    x.PROMPT_VERSION = prompt_version
    x.load_env = lambda: {"CHUMEI_LLM_API_KEY": "fixture-only"}
    x.iter_inbox = lambda: iter([item()])

    def reply(*args, **kwargs):
        calls.put("request")
        ready.set()
        if not release.wait(10):
            raise RuntimeError("test did not release worker")
        return '{"events":[]}', "fixture-model"

    x.chat_json = reply
    if phase == "reservation":
        write = x.atomic_json

        def reserve(path, data):
            write(path, data)
            calls.put("reservation")
            ready.set()
            if not release.wait(10):
                raise RuntimeError("test did not release reservation")

        x.atomic_json = reserve
    sys.argv = ["extract_events.py", "--workers", "1"]
    raise SystemExit(x.main())


def submission_circuit_worker(path, begin, done, calls):
    """Real submission provider boundary publishing a shared circuit."""
    import process_submissions as s
    import requests
    s.GATEWAY_STATE = Path(path)
    s.load_schema = lambda _: {}

    def reply(*args, **kwargs):
        calls.put("submission-review")
        raise requests.Timeout("synthetic timeout")

    s.chat_json = reply
    if not begin.wait(10):
        raise RuntimeError("test did not begin submission review")
    try:
        s._review({}, "synthetic", "synthetic", Path("fixture"), "fixture")
    except RuntimeError:
        pass
    done.set()


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.ctx = multiprocessing.get_context("spawn")
        self.children = []
        self.child_inputs = []  # Keep semaphore owners alive until spawn unpickles.
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for process in self.children:
            if process.is_alive():
                process.terminate()
            process.join(10)

    def start(self, target, *args):
        self.child_inputs.append(args)
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

    def test_submission_opens_circuit_while_extractor_is_running(self):
        import argparse
        import extract_events as x
        from extraction_retry import gateway_blocked
        from test_extraction_retry import item
        begin, done = self.ctx.Event(), self.ctx.Event()
        calls = self.ctx.Queue()
        gateway = self.root / "gateway.json"
        child = self.start(submission_circuit_worker, gateway, begin, done, calls)

        def reply(*args, **kwargs):
            begin.set()
            self.assertTrue(done.wait(10))
            self.assertTrue(gateway_blocked(read_json(gateway)))
            return '{"events":[]}', "fixture-model"

        with mock.patch.multiple(x, EXTRACT_DIR=self.root / "extraction", GATEWAY_STATE=gateway,
                                 load_env=lambda: {"CHUMEI_LLM_API_KEY": "fixture-only"}), \
             mock.patch.object(x, "iter_inbox", return_value=iter([item(str(i)) for i in range(6)])), \
             mock.patch.object(x, "chat_json", side_effect=reply) as provider:
            self.assertEqual(x.extract(argparse.Namespace(source=None, limit=0, workers=1,
                                                          retry_errors=False)), 0)
        child.join(10)
        self.assertEqual(child.exitcode, 0)
        provider.assert_called_once()
        self.assertEqual(calls.get(timeout=2), "submission-review")
        self.assertEqual(len(read_json(self.root / "extraction/fixture.json")), 1)

    def test_repeated_provider_death_charges_four_attempts_across_prompt_changes(self):
        path = self.root / "extraction/fixture.json"
        history = {"events": [{"id": "past"}], "prompt_version": 0,
                   "first_seen": "2020-01-01T00:00:00+00:00"}
        atomic_json(path, {"one": history, "unrelated": {"events": []}})
        calls = self.ctx.Queue()
        for attempt in range(1, 5):
            ready, release = self.ctx.Event(), self.ctx.Event()
            child = self.start(extraction_worker, self.root, ready, release, calls, "provider", attempt)
            self.assertTrue(ready.wait(10))
            self.assertEqual(calls.get(timeout=2), "request")
            child.terminate()
            child.join(10)
            cache = read_json(path)
            pending = cache["one"]
            self.assertEqual(pending["attempts"], attempt)
            self.assertTrue(pending["in_progress"])
            self.assertEqual(pending["events"], history["events"])
            self.assertEqual(pending["first_seen"], history["first_seen"])
            self.assertIn("unrelated", cache)
            # Even a prompt upgrade must honor a dead request's cooldown.
            blocked = self.start(extraction_worker, self.root, self.ctx.Event(), self.ctx.Event(),
                                 calls, "provider", 100 + attempt)
            blocked.join(10)
            self.assertEqual(blocked.exitcode, 0)
            self.assertEqual(read_json(path)["one"]["attempts"], attempt)
            # Advance only this synthetic cooldown, never reset the attempt count.
            cache["one"]["retry_after"] = "2020-01-01T00:00:00+00:00"
            atomic_json(path, cache)
        fifth = self.start(extraction_worker, self.root, self.ctx.Event(), self.ctx.Event(),
                           calls, "provider", 999)
        fifth.join(10)
        self.assertEqual(fifth.exitcode, 0)
        with self.assertRaises(queue.Empty):
            calls.get(timeout=0.1)
        self.assertEqual(read_json(path)["one"]["attempts"], 4)

    def test_death_after_reservation_before_provider_retains_ambiguous_attempt(self):
        ready, release = self.ctx.Event(), self.ctx.Event()
        calls = self.ctx.Queue()
        first = self.start(extraction_worker, self.root, ready, release, calls, "reservation")
        self.assertTrue(ready.wait(10))
        self.assertEqual(calls.get(timeout=2), "reservation")
        first.terminate()
        first.join(10)
        path = self.root / "extraction/fixture.json"
        cache = read_json(path)
        self.assertEqual(cache["one"]["attempts"], 1)
        self.assertTrue(cache["one"]["in_progress"])
        blocked = self.start(extraction_worker, self.root, self.ctx.Event(), self.ctx.Event(), calls)
        blocked.join(10)
        self.assertEqual(blocked.exitcode, 0)
        cache["one"]["retry_after"] = "2020-01-01T00:00:00+00:00"
        atomic_json(path, cache)
        next_release = self.ctx.Event()
        next_release.set()
        second = self.start(extraction_worker, self.root, self.ctx.Event(), next_release, calls)
        second.join(10)
        self.assertEqual(second.exitcode, 0)
        self.assertEqual(calls.get(timeout=2), "request")
        result = read_json(path)["one"]
        self.assertEqual(result["attempts"], 2)
        self.assertNotIn("error", result)
        self.assertNotIn("in_progress", result)


if __name__ == "__main__":
    unittest.main()
