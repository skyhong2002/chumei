import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_pipeline


class RunPipelineTests(unittest.TestCase):
    def test_each_available_community_account_adds_three_instagram_slots(self):
        status = {"accounts": [
            {"label": "PRIMARY", "available": True, "exhausted": False},
            {"label": "COMMUNITY-ONE", "available": True, "exhausted": False},
            {"label": "COMMUNITY-TWO", "available": True, "exhausted": False},
            {"label": "COMMUNITY-EMPTY", "available": True, "exhausted": True},
        ]}
        self.assertEqual(run_pipeline.instagram_batch_size(status), 11)


if __name__ == "__main__":
    unittest.main()
