#!/usr/bin/env python3
"""Read-only preview of one build from build_preview.py, for screenshots.

  CHUMEI_PREVIEW_NOW=2026-11-12T15:30:00+08:00 PYTHONPATH=docs/design-review/tools/frozen \
    /tmp/cm-review/venv/bin/python docs/design-review/tools/preview_server.py OUT PORT

Serves OUT/src/site like Caddy does (static files, /404.html on misses) and
mounts that build's own auth service on its routes (/auth/*, /account*,
/submit*, /contribute*, /@*). The auth database lives in OUT/src/state and is
seeded with one fictional account; its session token is written to
OUT/session.txt for capture.mjs. OAuth providers are configured with dummy
client IDs so the login buttons render, but no login flow is ever followed.
Web Push endpoints are mocked. Nothing outside OUT is read or written.
"""
import json
import mimetypes
import os
import sys
from pathlib import Path

OUT = Path(sys.argv[1]).resolve()
PORT = int(sys.argv[2])
SRC = OUT / 'src'
SITE = SRC / 'site'
sys.path.insert(0, str(SRC / 'scripts'))
os.chdir(SRC)
for key in [k for k in os.environ if k.startswith('CHUMEI_') and k != 'CHUMEI_PREVIEW_NOW']:
    del os.environ[key]
os.environ['CHUMEI_BUILD_DIR'] = str(SITE)

import uvicorn  # noqa: E402
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse  # noqa: E402

import auth_server  # noqa: E402  (this build's own copy)

AUTH_PREFIXES = ('/auth/', '/account', '/submit', '/contribute', '/@', '/feeds/custom.', '/feeds/s/')
ASSET_SUFFIXES = ('.js', '.css', '.json', '.xml', '.ics', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico', '.woff', '.woff2', '.map')


def seed(store, submissions):
    user = store.get_or_create_user('google', 'preview-user', 'mei.lin@example.com', display_name='林小美')
    sources = json.loads((SITE / 'data/sources.json').read_text())['entries']
    for entry in [e for e in sources if e.get('events')][:3]:
        store.set_user_follow(user['id'], entry['id'], entry['name'], True)
    events = json.loads((SITE / 'data/events.json').read_text())['events']
    upcoming = [e for e in events if e['start_at'] >= os.environ.get('CHUMEI_PREVIEW_NOW', '')]
    for event in upcoming[:2]:
        store.set_user_event(user['id'], event['id'], True)
    if not submissions.list_for_user(user['id']):
        submissions.create(user['id'], 'https://www.instagram.com/example_club/', '新成立的社團帳號，每週有社課公告')
    return store.create_session(user['id'])


def main():
    config = auth_server.AuthConfig(
        client_id='preview-nycu', client_secret='preview-secret', google_client_id='preview-google',
        google_client_secret='preview-secret', feed_signing_key='preview-feed-key',
        public_base_url=f'http://127.0.0.1:{PORT}', database_path=SRC / 'state/auth.sqlite3', cookie_secure=False)
    store = auth_server.AuthStore(config.database_path)
    submissions = auth_server.SubmissionStore(config.database_path)
    auth_server.crawl_schedule_snapshot = lambda *a, **k: {'sources': []}
    auth_app = auth_server.create_app(config, store=store, submissions=submissions)
    (OUT / 'session.txt').write_text(seed(store, submissions))

    def static(path):
        target = (SITE / path.lstrip('/')).resolve()
        if SITE.resolve() not in target.parents and target != SITE.resolve():
            return None
        if target.is_dir():
            target = target / 'index.html'
        return target if target.is_file() else None

    async def push(scope, receive, send):
        path = scope['path']
        if path == '/push/config':
            body = {'ok': True, 'publicKey': 'BPreviewOnlyPublicKeyNotUsedForDelivery000000000000000000000000000000000000000000000000'}
        elif path == '/push/stats':
            body = {'ok': True, 'subscribers': 128, 'total': 128}
        else:
            body = {'ok': True, 'subscribed': False}
        await JSONResponse(body)(scope, receive, send)

    async def app(scope, receive, send):
        if scope['type'] != 'http':
            return await auth_app(scope, receive, send)
        path = scope['path']
        if path.startswith(AUTH_PREFIXES):
            return await auth_app(scope, receive, send)
        if path.startswith('/push/'):
            return await push(scope, receive, send)
        found = static(path)
        if found:
            media = mimetypes.guess_type(found.name)[0] or 'application/octet-stream'
            return await FileResponse(found, media_type=media, headers={'Cache-Control': 'no-store'})(scope, receive, send)
        if path.startswith(('/assets/', '/data/', '/api/', '/feeds/')) or path.endswith(ASSET_SUFFIXES):
            return await PlainTextResponse('Not found', status_code=404)(scope, receive, send)
        return await FileResponse(SITE / '404.html', status_code=404, media_type='text/html')(scope, receive, send)

    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')


if __name__ == '__main__':
    main()
