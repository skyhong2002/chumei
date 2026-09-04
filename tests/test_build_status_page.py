import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_status_page


class BuildStatusPageTests(unittest.TestCase):
    def test_status_ui_describes_current_instagram_collectors(self):
        script = build_status_page.SCRIPT
        self.assertIn("'Instagram public'", script)
        self.assertIn("'Apify Stories'", script)
        self.assertIn("'NYCU Open Data'", script)
        self.assertIn("12 小時到 14 天", script)
        self.assertNotIn("RSSHub → Instaloader", script)
        self.assertNotIn("共用 RSSHub 登入", script)

    def test_apify_quota_is_labeled_as_shared(self):
        self.assertIn("Instagram／Facebook 共用 Apify 額度", build_status_page.SCRIPT)
        self.assertIn('href="/contribute/"', build_status_page.SCRIPT)

    def test_apify_promotion_is_separate_from_the_recurring_limit(self):
        self.assertIn("temporaryCreditUsd", build_status_page.SCRIPT)
        self.assertIn("已用／固定月額", build_status_page.SCRIPT)
        self.assertIn("含臨時贈額", build_status_page.SCRIPT)
        self.assertIn("本期已用盡", build_status_page.SCRIPT)


if __name__ == "__main__":
    unittest.main()
