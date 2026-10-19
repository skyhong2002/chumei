import sys
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_status_page


class BuildStatusPageTests(unittest.TestCase):
    def test_status_ui_describes_current_instagram_collectors(self):
        script = build_status_page.SCRIPT
        self.assertIn("'Instagram public'", script)
        self.assertIn("'Instagram Stories'", script)
        self.assertIn("公開端點優先 · Apify 帳號池備援", script)
        self.assertIn("免費限動檢視網站優先 · Apify 帳號池備援", script)
        self.assertIn("Apify 帳號池 · 批次抓取", script)
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

    def test_apify_allocation_lists_every_consumer_including_facebook(self):
        script = build_status_page.SCRIPT
        for text in ("每日額度平均分配", "'Facebook 粉專'", "'Instagram 限時動態'",
                     "'Instagram 貼文備援'", "spent30dUsd", "保障"):
            self.assertIn(text, script)
        self.assertNotIn("US$10", script)

    def test_priority_controls_and_quota_updates(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "status_page_ui.cjs")],
            input=build_status_page.SCRIPT.replace("<script>", "").replace("</script>", ""),
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
