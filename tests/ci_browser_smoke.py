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


def main():
    site = Path(sys.argv[1]).resolve()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(site)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for viewport in ({'width': 1280, 'height': 900}, {'width': 390, 'height': 844}):
                context = browser.new_context(viewport=viewport, service_workers='block')
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
    print('Desktop/mobile browser smoke passed: six pages, search, same-time venues, no JS errors.')


if __name__ == '__main__':
    main()
