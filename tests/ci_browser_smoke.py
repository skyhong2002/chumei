"""Exercise the built static site in desktop and mobile Chromium without outbound I/O."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def check_feed_layout(page):
    page.wait_for_selector('body.feed-locked .feed-cols')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Homepage overflows viewport'
    if page.viewport_size['width'] < 700:
        return  # Mobile uses one overview column.
    deck = page.locator('.feed-cols')
    assert deck.locator('.feed-col').count() == 3
    if deck.evaluate('(el) => el.scrollWidth > el.clientWidth + 2'):
        next_button = page.locator('.deck-next')
        # Exercise the keyboard-accessible control, including narrow desktops
        # where reaching the last column takes more than one step.
        for _ in range(4):
            if next_button.is_disabled():
                break
            next_button.focus()
            next_button.press('Enter')
            page.wait_for_function('''() => {
                const deck = document.querySelector('.feed-cols');
                return deck.scrollLeft > 0;
            }''')
            page.wait_for_timeout(400)  # Allow smooth horizontal scrolling to settle.
        assert next_button.is_disabled(), 'Last column is unreachable through deck navigation'
    summary = deck.locator('.feed-col').nth(2).locator('.col-picker > summary')
    bounds = summary.bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= page.viewport_size['width']
    summary.focus()
    summary.press('Enter')
    search = deck.locator('.feed-col').nth(2).locator('.col-picker[open] .cf-q')
    search.wait_for(state='visible')
    summary.press('Tab')
    assert search.evaluate('(el) => el === document.activeElement'), 'Filter search is not keyboard reachable'
    assert search.evaluate('''(el) => {
        const panel = el.closest('.col-picker-menu'), r = panel.getBoundingClientRect();
        const input = el.getBoundingClientRect();
        return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight
            && document.elementFromPoint(input.x + input.width / 2, input.y + input.height / 2) === el;
    }'''), 'Filter popover is clipped or outside viewport'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Open filter overflows viewport'
    summary.press('Enter')


def main():
    site = Path(sys.argv[1]).resolve()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(site)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for viewport in ({'width': width, 'height': 900} for width in (390, 1024, 1440, 1920)):
                context = browser.new_context(viewport=viewport, service_workers='block')
                # Populate every desktop column from the small CI fixture too:
                # an empty last column cannot expose escaped positioned content.
                context.add_init_script("localStorage.setItem('chumei-cols', JSON.stringify("
                                        "[{t:'feed',school:'all'}, {t:'feed',school:'all'},"
                                        " {t:'feed',school:'all'}]));")
                def route(request):
                    parsed = urlparse(request.request.url)
                    if parsed.netloc != urlparse(origin).netloc:
                        request.abort()
                    elif parsed.path.startswith(('/auth/', '/push/')):
                        request.fulfill(status=200, content_type='application/json', body=json.dumps({
                            'user': None, 'authenticated': False, 'following': [], 'going': [], 'counts': {},
                        }))
                    else:
                        request.continue_()
                context.route('**/*', route)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                for path in ('/', '/events/', '/source/', '/subscribe/', '/status/', '/event/evt_000000000000/'):
                    response = page.goto(origin + path, wait_until='networkidle')
                    assert response.status == 200, (path, response.status)
                    assert page.locator('h1').first.is_visible(), path
                    if path == '/':
                        check_feed_layout(page)
                page.goto(origin + '/events/', wait_until='networkidle')
                page.locator('#search').fill('CI 同名說明會')
                page.wait_for_function("document.querySelectorAll('a[href=\"/event/evt_000000000000/\"]').length > 0")
                assert page.locator('a[href="/event/evt_000000000001/"]').count() > 0
                assert not errors, errors
                context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print('Browser smoke passed at 390/1024/1440/1920px: six pages, search, same-time venues, '
          'contained deck, keyboard navigation/filter popovers, no JS errors.')


if __name__ == '__main__':
    main()
