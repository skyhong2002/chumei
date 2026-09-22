import re
import copy
import sys
import unittest
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
BASE_URL = "https://chumei.observe.tw"
sys.path.insert(0, str(ROOT / "scripts"))

import build_site


class SEOParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts = []
        self.h1_parts = []
        self._in_title = False
        self._h1 = None
        self.meta = {}
        self.canonicals = []
        self.redirect = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._h1 = []
        elif tag == "meta":
            if attrs.get("http-equiv", "").lower() == "refresh":
                self.redirect = attrs.get("content")
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


class EventVenueSEOTests(unittest.TestCase):
    def event(self, event_id, start, campus, venue, **extra):
        return {
            "id": event_id,
            "title": "聯電2026校園人才發展計畫暨研發替代役說明會",
            "start_at": start, "campus": campus, "venue": venue,
            "organizer": "聯華電子（聯電）", "extraction": {}, **extra,
        }

    def render(self, event, with_time=True):
        page = SEOParser()
        page.feed(build_site.detail_page(event, with_time=with_time))
        return page

    def test_same_title_time_different_venues_keep_unique_pages(self):
        events = [
            self.event("evt_37717d19a7db", "2026-09-30T12:10:00+08:00", "nthu-main", "台達館 B05"),
            self.event("evt_90291e8ab873", "2026-09-30T12:10:00+08:00", "other", "自強校區電機系館 1F"),
            self.event("evt_81086527cfda", "2026-10-20T12:10:00+08:00", "nthu-main", "物理館 B1-019"),
            self.event("evt_b3c8914bd8bb", "2026-10-20T12:10:00+08:00", "other", "資管大樓 IEC6019"),
        ]
        original = copy.deepcopy(events)
        pages = [self.render(event) for event in events]
        for attr in ("title", "h1"):
            self.assertEqual(len({getattr(page, attr) for page in pages}), 4)
        self.assertEqual(len({page.meta["description"] for page in pages}), 4)
        for event, page in zip(events, pages):
            with self.subTest(event=event["id"]):
                self.assertIn(event["venue"], page.title)
                self.assertIn(event["venue"], page.h1)
                self.assertIn(event["venue"], page.meta["description"])
                self.assertIn("12:10", page.h1)
                self.assertEqual(page.canonicals, [f"{BASE_URL}/event/{event['id']}/"])
                self.assertIsNone(page.redirect)
                for prefix in ("og", "twitter"):
                    self.assertEqual(page.meta[f"{prefix}:title"], page.title)
                    self.assertEqual(page.meta[f"{prefix}:description"], page.meta["description"])
        self.assertEqual(events, original)

    def test_all_day_sessions_with_same_venue_use_campus(self):
        events = [self.event(f"evt_{campus}", "2026-09-30T00:00:00+08:00", campus, "活動中心", all_day=True)
                  for campus in ("nthu-main", "nycu-guangfu")]
        pages = [self.render(event) for event in events]
        self.assertNotEqual(pages[0].h1, pages[1].h1)
        for event, page in zip(events, pages):
            self.assertIn(build_site.CAMPUS_LABEL[event["campus"]], page.h1)
            self.assertNotIn("00:00", page.h1)

    def test_long_organizer_does_not_hide_venue_in_preview(self):
        event = self.event("evt_long", "2026-09-30T12:10:00+08:00", "nthu-main", "台達館 B05",
                           organizer="主辦單位" * 100)
        self.assertIn(event["venue"], self.render(event).meta["description"])

    def test_unique_title_keeps_compact_heading_and_missing_venue_is_valid(self):
        event = self.event("evt_unique", "2026-09-30T12:10:00+08:00", "nthu-main", "台達館 B05")
        self.assertEqual(self.render(event, with_time=False).h1,
                         event["title"] + "｜2026 年 9 月 30 日")
        event.update(campus=None, venue=None)
        self.assertEqual(self.render(event).h1, event["title"] + "｜2026 年 9 月 30 日 12:10")


class SEOOutputTests(unittest.TestCase):
    def test_about_links_nycu_life_team_to_its_current_site(self):
        source = (SITE / "about" / "index.html").read_text()
        self.assertIn(
            '<a href="https://nycu.life/" rel="noopener">NYCU LIFE 數碼寶貝社</a>',
            source,
        )

    def test_about_uses_working_contact_email(self):
        source = (SITE / "about" / "index.html").read_text()
        self.assertIn(
            '<a href="mailto:sky.cs14@nycu.edu.tw">sky.cs14@nycu.edu.tw</a>',
            source,
        )
        self.assertNotIn("chumei@observe.tw", source)

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
                if page.redirect:
                    # 合併舊頁的標題應與主活動一致；驗證確實轉向既存的主頁且不收錄舊頁。
                    self.assertIn("noindex", page.meta.get("robots", ""))
                    self.assertTrue(page.redirect.startswith("0;url=/event/"))
                    target = page.redirect.split("0;url=", 1)[1]
                    self.assertTrue((SITE / target.lstrip("/") / "index.html").exists())
                    self.assertEqual(page.canonicals, [BASE_URL + target])
                    continue
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
