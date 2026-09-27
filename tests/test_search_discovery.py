import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from search_discovery import build_search_pages, write_search_sitemap


def _sitemap_dates(site):
    root = ET.parse(site / 'sitemap.xml').getroot()
    return {x[0].text: x[1].text for x in root if len(x) > 1}


class SearchDiscoveryTests(unittest.TestCase):
    def test_recent_sitemap_keeps_ongoing_old_start_and_stable_lastmod(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / 'site'
            state = Path(tmp) / 'state' / 'sitemap-state.json'
            events = [dict(id='old', start_at='2017-01-01'),
                      dict(id='recent', start_at='2026-09-20'),
                      dict(id='long', start_at='2020-01-01', end_at='2027-01-01')]
            for path in ('index.html', 'event/old/index.html', 'event/recent/index.html', 'event/long/index.html'):
                p = site / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('<main>Activity<section class="org-more">a</section></main>')
            (site / '.sitemap-state.json').write_text('{}')
            now = datetime.fromisoformat('2026-09-28T00:00:00.123456+08:00')
            write_search_sitemap(site, events, [], [], now, 'https://example.com', state_path=state)
            first = (site / 'sitemap.xml').read_bytes()
            self.assertNotIn(b'/event/old/', first)
            self.assertIn(b'/event/long/', first)
            self.assertIn(b'/event/recent/', first)
            self.assertTrue((site / 'event/old/index.html').exists())
            # 狀態只存在網站根目錄之外；舊版寫進網站根目錄的檔案要清掉。
            self.assertTrue(state.exists())
            self.assertFalse((site / '.sitemap-state.json').exists())
            self.assertEqual(_sitemap_dates(site)['https://example.com/event/recent/'], '2026-09-28T00:00:00+08:00')

            # 換一天重建：內容沒變，lastmod 不動；同單位其他活動增減也不算更新。
            later = now.replace(day=29)
            (site / 'event/long/index.html').write_text('<main>Activity<section class="org-more">b</section></main>')
            write_search_sitemap(site, events, [], [], later, 'https://example.com', state_path=state)
            self.assertEqual(first, (site / 'sitemap.xml').read_bytes())

            (site / 'event/recent/index.html').write_text('<main>Updated venue</main>')
            write_search_sitemap(site, events, [], [], later, 'https://example.com', state_path=state)
            dates = _sitemap_dates(site)
            self.assertEqual(dates['https://example.com/event/recent/'], '2026-09-29T00:00:00+08:00')
            self.assertEqual(dates['https://example.com/event/long/'], '2026-09-28T00:00:00+08:00')

    def test_hubs_filter_school_and_category_and_links_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / 'events').mkdir()
            (site / 'index.html').write_text(
                '<title>x</title><h1 class="sr-only">竹梅</h1><section>stories</section>\n  <div class="feed-tabs-row"></div>')
            (site / 'events/index.html').write_text('<h1>活動</h1>')
            now = datetime.fromisoformat('2026-09-28T00:00:00+08:00')
            events = [dict(id='nthu-talk', start_at='2026-10-01', school='nthu', category='演講'),
                      dict(id='nycu-show', start_at='2026-10-02', school='nycu', category='表演'),
                      dict(id='past', start_at='2020-01-01', school='nthu', category='演講'),
                      dict(id='exhibit', start_at='2026-09-01', end_at='2026-12-01', all_day=True,
                           school='nthu', category='展覽')]
            shell = lambda title, desc, content, canonical: canonical + content
            for _ in range(2):
                build_search_pages(site, events, now, 'https://example.com', shell, lambda e: e['id'])
            nthu = (site / 'events/nthu/index.html').read_text()
            self.assertIn('nthu-talk', nthu)
            self.assertNotIn('nycu-show', nthu)
            self.assertNotIn('past', nthu)
            # 進行中的長期展覽另列「期間活動」，排在定時活動之後。
            self.assertLess(nthu.index('定時活動 · 1 場'), nthu.index('nthu-talk'))
            self.assertLess(nthu.index('nthu-talk'), nthu.index('期間活動 · 1 場'))
            self.assertLess(nthu.index('期間活動 · 1 場'), nthu.index('exhibit'))
            self.assertIn('href="/events/nthu/" aria-current="page"', nthu)
            self.assertNotIn('nycu-show', (site / 'events/talks/index.html').read_text())
            home = (site / 'index.html').read_text()
            self.assertEqual(home.count('<!-- search-entry-links -->'), 1)
            # 首頁入口列在限動列之後、河道工具列之前；不動 sr-only 標題。
            self.assertLess(home.index('stories</section>'), home.index('class="feed-hubs"'))
            self.assertLess(home.index('class="feed-hubs"'), home.index('feed-tabs-row'))
            self.assertIn('<title>清大、陽明交大活動與講座｜竹梅活動觀測站</title>', home)
            self.assertEqual((site / 'events/index.html').read_text().count('class="feed-hubs"'), 1)
