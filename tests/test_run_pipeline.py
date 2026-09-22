import sys
import unittest
import tempfile
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_pipeline


class RunPipelineTests(unittest.TestCase):
    def test_skip_fetch_uses_atomic_publisher_after_extraction(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(run_pipeline, "STATE", Path(td) / "pipeline.json"), \
             mock.patch.object(sys, "argv", ["run_pipeline.py", "--skip-fetch"]), \
             mock.patch.object(run_pipeline, "run_step", return_value=True) as step:
            self.assertEqual(run_pipeline.run_pipeline(), 0)
        self.assertEqual(step.call_args_list, [
            mock.call("extract", ["extract_events.py"]),
            mock.call("publish", ["publish_site.py"]),
        ])

    def test_extraction_failure_does_not_publish(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(run_pipeline, "STATE", Path(td) / "pipeline.json"), \
             mock.patch.object(sys, "argv", ["run_pipeline.py", "--skip-fetch"]), \
             mock.patch.object(run_pipeline, "run_step", return_value=False) as step:
            self.assertEqual(run_pipeline.run_pipeline(), 1)
        step.assert_called_once_with("extract", ["extract_events.py"])

    def test_each_available_community_account_adds_three_instagram_slots(self):
        status = {"accounts": [
            {"label": "PRIMARY", "available": True, "exhausted": False},
            {"label": "COMMUNITY-ONE", "available": True, "exhausted": False},
            {"label": "COMMUNITY-TWO", "available": True, "exhausted": False},
            {"label": "COMMUNITY-EMPTY", "available": True, "exhausted": True},
        ]}
        self.assertEqual(run_pipeline.instagram_batch_size(status), 11)

    def test_claimed_configured_accounts_also_add_slots(self):
        status = {"accounts": [
            {"label": "PRIMARY", "community": True, "available": True, "exhausted": False},
            {"label": "SKYNTNU", "community": True, "available": True, "exhausted": False},
        ]}
        self.assertEqual(run_pipeline.instagram_batch_size(status), 11)


if __name__ == "__main__":
    unittest.main()
