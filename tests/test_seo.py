import re
import unittest
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
BASE_URL = "https://chumei.observe.tw"


class SEOParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts = []
        self.h1_parts = []
        self._in_title = False
        self._h1 = None
        self.meta = {}
        self.canonicals = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._h1 = []
        elif tag == "meta":
            key = attrs.get("name") or attrs.get("property")
            if key:
                self.meta[key] = attrs.get("content", "").strip()
        elif tag == "link" and attrs.get("rel") == "canonical":
            self.canonicals.append(attrs.get("href", "").strip())

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1" and self._h1 is not None:
            self.h1_parts.append("".join(self._h1).strip())
            self._h1 = None

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if self._h1 is not None:
            self._h1.append(data)

    @property
    def title(self):
        return "".join(self.title_parts).strip()

    @property
    def h1(self):
        return self.h1_parts[0] if self.h1_parts else ""


def parse_pages():
    pages = []
    for path in sorted(SITE.rglob("index.html")):
        parser = SEOParser()
        parser.feed(path.read_text())
        pages.append((path, parser))
    return pages


class SEOOutputTests(unittest.TestCase):
    def test_about_links_nycu_life_team_to_its_current_site(self):
        source = (SITE / "about" / "index.html").read_text()
        self.assertIn(
            '<a href="https://nycu.life/" rel="noopener">NYCU LIFE 數碼寶貝社</a>',
            source,
        )

    def test_about_special_thanks_matches_current_services(self):
        source = (SITE / "about" / "index.html").read_text()
        section = source.split("<h2>特別感謝</h2>", 1)[1].split("<h2>關於我</h2>", 1)[0]
        self.assertIn('<a href="/status/">系統狀態</a>', section)
        self.assertIn('<a href="https://nycu.life/" rel="noopener">NYCU LIFE 團隊</a>', section)
        self.assertIn("Instagram 限時動態、Instagram 貼文備援與 Facebook 公開貼文抓取", section)
        self.assertIn("Threads 與 X 公開貼文抓取", section)
        self.assertNotIn("Instaloader", section)
        self.assertNotIn("NYCU LIFE</a>（社團）", section)

    def test_every_shell_uses_the_same_footer_links(self):
        expected = [
            "/", "/", "/events/", "/calendar/", "/stories/", "/notify/",
            "/submit/", "/subscribe/", "/source/", "/status/", "/about/",
            "/account/",
        ]
        checked = 0
        for path in sorted(SITE.rglob("index.html")):
            source = path.read_text()
            if 'class="site-header"' not in source:
                continue
            with self.subTest(path=path.relative_to(SITE)):
                self.assertEqual(source.count('class="fab"'), 1)
                footers = re.findall(
                    r'<footer class="site-footer">(.*?)</footer>', source, re.S
                )
                if path == SITE / "index.html":
                    self.assertEqual(footers, [])
                    continue
                self.assertEqual(len(footers), 1)
                self.assertEqual(re.findall(r'href="([^"]+)"', footers[0]), expected)
            checked += 1
        self.assertGreater(checked, 5)

    def test_every_page_has_queryless_canonical_and_preview_metadata(self):
        pages = parse_pages()
        # A clean checkout tracks the six static shells; a built production tree also includes
        # event/source/org pages. The same contract applies to whichever pages are present.
        self.assertGreater(len(pages), 5)
        for path, page in pages:
            with self.subTest(path=path.relative_to(SITE)):
                self.assertEqual(len(page.canonicals), 1)
                canonical = page.canonicals[0]
                self.assertTrue(canonical.startswith(BASE_URL + "/"), canonical)
                self.assertNotIn("?", canonical)
                self.assertNotIn("#", canonical)
                self.assertTrue(page.title)
                self.assertTrue(page.h1)
                self.assertTrue(page.meta.get("description"))
                self.assertEqual(page.meta.get("og:title"), page.title)
                self.assertEqual(page.meta.get("og:description"), page.meta.get("description"))
                self.assertEqual(page.meta.get("og:url"), canonical)
                self.assertTrue(page.meta.get("og:image"))
                self.assertEqual(page.meta.get("twitter:title"), page.title)
                self.assertEqual(page.meta.get("twitter:description"), page.meta.get("description"))

    def test_title_h1_and_preview_description_are_unique_per_page(self):
        pages = parse_pages()
        for label, getter in (
            ("title", lambda page: page.title),
            ("h1", lambda page: page.h1),
            ("description", lambda page: page.meta.get("description", "")),
        ):
            seen = defaultdict(list)
            for path, page in pages:
                seen[getter(page)].append(str(path.relative_to(SITE)))
            duplicates = {value: paths for value, paths in seen.items() if len(paths) > 1}
            self.assertFalse(duplicates, f"duplicate {label}: {list(duplicates.items())[:8]}")

    def test_query_variants_update_content_but_not_canonical(self):
        source = (SITE / "assets" / "app.js").read_text()
        self.assertIn('new URLSearchParams(location.search)', source)
        self.assertIn('base.h1 + "｜" + context', source)
        self.assertIn('base.description + "目前條件：" + context', source)
        self.assertIn('canonicalHref = canonicalHref.split("?", 1)[0].split("#", 1)[0]', source)
        self.assertGreaterEqual(len(re.findall(r"pageSEO\.refresh\(", source)), 5)

    def test_logged_in_navigation_uses_profile_avatar_and_handle(self):
        app = (SITE / "assets" / "app.js").read_text()
        css = (SITE / "assets" / "site.css").read_text()
        self.assertIn('label.textContent = handle ? "@" + handle : "帳號"', app)
        self.assertIn('avatar.className = "nav-account-avatar"', app)
        self.assertIn("var avatarUrl = String(user.avatarUrl || \"\")", app)
        self.assertIn('img.referrerPolicy = "no-referrer"', app)
        self.assertIn("return a.desktopOrder - b.desktopOrder", app)
        self.assertIn('form.action = "/auth/logout"', app)
        self.assertIn('form.className = "nav-logout"', app)
        self.assertIn('button.innerHTML = svg("logout", "mi") + "<span>登出</span>"', app)
        self.assertIn('{ href: "/status/", label: "系統狀態", icon: "status" }', app)
        self.assertIn("[data-account-link]", app)
        self.assertIn(".nav-account-avatar {", css)
        self.assertIn(".nav-account-entry { margin-top: auto; }", css)
        self.assertIn(".nav-more-menu .nav-logout button {", css)
        self.assertIn(".footer-nav {", css)
        self.assertIn(".footer-nav section {", css)


if __name__ == "__main__":
    unittest.main()
