"""Source screenshots run with JavaScript disabled; page tweaks must not wait on page events."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import render_source_covers as rsc


class HidePageChromeTests(unittest.TestCase):
    def test_hides_header_without_javascript(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright unavailable")
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except Exception as exc:
                self.skipTest(f"chromium unavailable: {exc}")
            try:
                # Same JS-off context as safe_outbound.secure_browser_context; add_style_tag hangs here.
                context = browser.new_context(java_script_enabled=False, offline=True)
                page = context.new_page()
                page.set_content("<header>site</header><nav>menu</nav><div id='changeWidh'>body</div>")
                rsc._hide_page_chrome(page)
                display = page.evaluate("s => [...document.querySelectorAll(s)].map(e => getComputedStyle(e).display)",
                                        "header, nav, #changeWidh")
                self.assertEqual(display, ["none", "none", "block"])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
