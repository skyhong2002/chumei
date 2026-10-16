"""Chumei and Harmonica must share one logged-out Instagram budget per host."""

import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ig_public_host


class HostPacingTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "host.json"
        self.waits = []

    def turn(self):
        return ig_public_host.wait_turn(path=self.path, gap=10, sleep=self.waits.append)

    def test_queries_from_any_collector_are_spaced_on_one_timeline(self):
        self.assertTrue(self.turn())
        self.assertTrue(self.turn())
        self.assertTrue(self.turn())
        # The second and third reservations queue behind the first, even
        # though nobody actually slept in this test.
        self.assertEqual(len(self.waits), 2)
        self.assertAlmostEqual(self.waits[0], 10, delta=1)
        self.assertAlmostEqual(self.waits[1], 20, delta=1)

    def test_a_refusal_blocks_every_collector_and_is_never_shortened(self):
        until = ig_public_host.report_block("harmonica", path=self.path, seconds=3600)
        self.assertFalse(self.turn())
        self.assertEqual(ig_public_host.report_block("chumei", path=self.path, seconds=60), until)
        self.assertAlmostEqual(ig_public_host.blocked_until(self.path), time.time() + 3600, delta=5)

    def test_expired_block_allows_queries_again(self):
        ig_public_host.report_block("chumei", path=self.path, seconds=-1)
        self.assertTrue(self.turn())


if __name__ == "__main__":
    unittest.main()
