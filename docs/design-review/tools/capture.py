#!/usr/bin/env python3
"""Photograph every state in states.py at both sizes, one browser at a time.

  python3 capture.py site http://127.0.0.1:8411 OUT_DIR --session-file BUILD/session.txt [--only ID-substring]
  python3 capture.py references OUT_DIR

Waits while load1 > 10 before each state. FONTCONFIG/fonts: the host must have
Noto Sans CJK TC installed so Chinese renders the same in every set.
"""
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from states import NOW, REFERENCES, SIZES, STATES

DATA_PATTERN = '**/data/*.json'
STATUS_PATTERN = '**/api/status.json'
IPHONE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 '
             '(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1')


def wait_for_load(limit=10.0):
    while os.getloadavg()[0] > limit:
        print(f'load1 {os.getloadavg()[0]:.1f} > {limit}; waiting', flush=True)
        time.sleep(30)


def emptied(body):
    data = json.loads(body)
    if isinstance(data, dict):
        return {k: ([] if isinstance(v, list) else v) for k, v in data.items()}
    return [] if isinstance(data, list) else data


def route_data(page, mode):
    def handle(route):
        if mode == 'loading':
            return  # never answers
        if mode == 'error':
            return route.fulfill(status=500, content_type='application/json', body='{"error":"Server error."}')
        response = route.fetch()
        return route.fulfill(response=response, body=json.dumps(emptied(response.text()), ensure_ascii=False))
    page.route(DATA_PATTERN, handle)
    page.route(STATUS_PATTERN, handle)


def settle(page, max_height):
    height = min(page.evaluate('document.documentElement.scrollHeight'), max_height * 2)
    for y in range(0, height, 600):
        page.evaluate(f'window.scrollTo(0, {y})')
        page.wait_for_timeout(100)
    page.evaluate('window.scrollTo(0, 0)')
    try:
        page.wait_for_load_state('networkidle', timeout=8000)
    except Exception:
        pass
    page.evaluate('''() => Promise.all([...document.images].filter((img) => !img.complete).map((img) =>
        new Promise((done) => { img.onload = img.onerror = done; setTimeout(done, 4000); })))''')
    page.wait_for_timeout(500)


def shoot(page, file, size, state):
    top = 0
    if state.get('anchor'):
        top = page.evaluate('''(selector) => {
            const node = document.querySelector(selector);
            const header = document.querySelector('.site-header');
            const sticky = header && ['sticky', 'fixed'].includes(getComputedStyle(header).position) ? header.offsetHeight : 0;
            return node ? Math.round(Math.max(0, node.getBoundingClientRect().top + window.scrollY - 24 - sticky)) : 0;
        }''', state['anchor'])
    if state.get('viewport_only'):
        page.evaluate(f'window.scrollTo(0, {top})')
        page.wait_for_timeout(300)
        return page.screenshot(path=file)
    full = page.evaluate('document.documentElement.scrollHeight')
    height = max(size['height'], min(full - top, size['max_height']))
    page.set_viewport_size({'width': size['width'], 'height': int(min(height, max(full - top, size['height'])))})
    page.wait_for_timeout(800)
    page.evaluate(f'window.scrollTo(0, {top})')
    page.wait_for_timeout(300)
    return page.screenshot(path=file)


def capture_site(base, out, session_token, only):
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.fromisoformat(NOW)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for size_name, size in SIZES.items():
            for state in [st for st in STATES if not only or only in st['id']]:
                if os.environ.get('RESUME') and (out / f"{state['id']}_{size_name}.png").exists():
                    continue  # resume a capture the host interrupted
                wait_for_load()
                context = browser.new_context(
                    viewport={'width': size['width'], 'height': size['height']}, device_scale_factor=size['scale'],
                    is_mobile=size['mobile'], has_touch=size['mobile'], user_agent=IPHONE_UA if size['mobile'] else None,
                    color_scheme='light', locale='zh-TW', timezone_id='Asia/Taipei',
                    reduced_motion='reduce', service_workers='block')
                if state.get('session') == 'in':
                    context.add_cookies([{'name': 'chumei_session', 'value': session_token, 'url': base}])
                if state.get('theme') == 'light':
                    context.add_init_script("try{localStorage.setItem('theme','light')}catch(e){}")
                page = context.new_page()
                page.clock.set_fixed_time(now)
                if state.get('data'):
                    route_data(page, state['data'])
                try:
                    page.goto(base + state['path'], wait_until='domcontentloaded' if state.get('data') == 'loading' else 'networkidle', timeout=60000)
                except Exception as error:
                    print(state['id'], 'goto', str(error).splitlines()[0])
                if state.get('data') == 'loading':
                    page.wait_for_timeout(1500)
                else:
                    page.wait_for_timeout(500)
                    for selector in state.get('click', []):
                        try:
                            page.locator(selector).first.click(timeout=5000)
                        except Exception as error:
                            print(state['id'], 'click failed', selector, str(error).splitlines()[0])
                        page.wait_for_timeout(400)
                    if state.get('type'):
                        page.keyboard.type(state['type'])
                        page.wait_for_timeout(800)
                    if not state.get('viewport_only'):
                        settle(page, size['max_height'])
                file = out / f"{state['id']}_{size_name}.png"
                shoot(page, str(file), size, state)
                print(file, flush=True)
                context.close()
        browser.close()


def capture_references(out):
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for size_name, size in SIZES.items():
            for ref in REFERENCES:
                wait_for_load()
                context = browser.new_context(
                    viewport={'width': size['width'], 'height': size['height']}, device_scale_factor=size['scale'],
                    is_mobile=size['mobile'], has_touch=size['mobile'], locale=ref.get('locale', 'en-US'),
                    timezone_id='Asia/Taipei', user_agent=IPHONE_UA if size['mobile'] else
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
                page = context.new_page()
                try:
                    page.goto(ref['url'], wait_until='domcontentloaded', timeout=45000)
                except Exception as error:
                    print(ref['id'], 'goto', str(error).splitlines()[0])
                page.wait_for_timeout(8000)
                for name in ('Reject All', 'Reject all', 'Accept All', 'Accept all', 'Accept', 'Got it', '接受', '同意', '我知道了'):
                    button = page.get_by_role('button', name=name, exact=True)
                    if button.count():
                        button.first.click(timeout=2000)
                        break
                settle(page, size['max_height'])
                file = out / f"{ref['id']}_{size_name}.png"
                shoot(page, str(file), size, {})
                print(file, flush=True)
                context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['site', 'references'])
    parser.add_argument('args', nargs='+')
    parser.add_argument('--session-file', type=Path)
    parser.add_argument('--only')
    a = parser.parse_args()
    if a.mode == 'site':
        base, out = a.args
        capture_site(base.rstrip('/'), Path(out), a.session_file.read_text().strip() if a.session_file else '', a.only)
    else:
        capture_references(Path(a.args[0]))


if __name__ == '__main__':
    main()
