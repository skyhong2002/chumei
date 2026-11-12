#!/usr/bin/env python3
"""Turn a public data snapshot into an isolated build fixture (run once per hill climb).

  python3 docs/design-review/tools/prepare_fixture.py /tmp/cm-review

Reads <root>/data/{events,posts}.json (downloaded from the public site's
/data/), writes <root>/fixture/state/nycu_life_activities.json,
<root>/fixture/data/feeds/inbox/snapshot.jsonl and caches the images those
records reference under <root>/fixture/site/assets/. Instagram stories are
mocked: four placeholder cards drawn locally, never real story media. Nothing
here touches state/, data/feeds/, published/ or any production service.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

PUBLIC = 'https://chumei.observe.tw'
UA = {'User-Agent': 'design-review-fixture/1.0'}


def fetch(path, dest):
    if dest.exists():
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(PUBLIC + path, headers=UA), timeout=20) as r:
            dest.write_bytes(r.read())
        time.sleep(0.05)
        return True
    except Exception as error:  # a missing image is fine; the build falls back
        print('miss', path, error)
        return False


def mock_stories(root, now):
    from PIL import Image, ImageDraw
    from datetime import datetime, timedelta
    out = root / 'fixture/site/assets/stories'
    out.mkdir(parents=True, exist_ok=True)
    taken = datetime.fromisoformat(now)
    rows = [('mock_story_a', '示意社團 A', 'nthu', (124, 58, 237)), ('mock_story_b', '示意社團 B', 'nycu', (14, 116, 144)),
            ('mock_story_b', '示意社團 B', 'nycu', (8, 145, 178)), ('mock_story_c', '示意單位 C', 'nthu', (190, 24, 93)),
            ('mock_story_d', '示意單位 D', 'nycu', (202, 138, 4))]
    stories = []
    for index, (user, name, school, colour) in enumerate(rows):
        image = Image.new('RGB', (720, 1280), colour)
        draw = ImageDraw.Draw(image)
        for y in range(0, 1280, 160):
            draw.rectangle([0, y, 720, y + 70], fill=tuple(min(255, c + 30) for c in colour))
        path = out / f'mock-{index}.jpg'
        image.save(path, 'JPEG', quality=80)
        at = taken - timedelta(hours=2 + index * 5)
        stories.append({'username': user, 'avatar': None, 'name': name, 'school': school,
                        'taken_at': at.isoformat(timespec='seconds'),
                        'expires_at': (at + timedelta(hours=48)).isoformat(timespec='seconds'),
                        'is_video': False, 'media': f'/assets/stories/mock-{index}.jpg',
                        'ig_url': 'https://example.com/mock-story'})
    stories.sort(key=lambda s: s['taken_at'], reverse=True)
    (root / 'fixture/stories.json').write_text(json.dumps({'generated_at': now, 'stories': stories}, ensure_ascii=False))


def main():
    root = Path(sys.argv[1])
    data, fixture = root / 'data', root / 'fixture'
    bundle = json.loads((data / 'events.json').read_text())
    events, now = bundle['events'], bundle['generated_at']
    posts = json.loads((data / 'posts.json').read_text())['posts']
    (fixture / 'state').mkdir(parents=True, exist_ok=True)
    keep = ('id', 'title', 'summary', 'description', 'start_at', 'end_at', 'all_day', 'campus', 'venue', 'school',
            'organizer', 'organizer_type', 'category', 'registration_url', 'registration_deadline', 'price',
            'source', 'poster_image', 'extraction', 'status', 'first_seen', 'image_kind', 'cover_image', 'lat', 'lng',
            'speakers', 'target', 'source_timezone')
    clean = [{k: e[k] for k in keep if k in e} for e in events]
    (fixture / 'state/nycu_life_activities.json').write_text(json.dumps(clean, ensure_ascii=False))
    inbox = fixture / 'data/feeds/inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    with (inbox / 'snapshot.jsonl').open('w') as out:
        for p in posts:
            out.write(json.dumps({
                'source_id': p['source_id'], 'post_id': p['post_id'], 'source_name': p.get('source_name'),
                'platform': p.get('platform'), 'raw_source': 'snapshot', 'school': p.get('school'),
                'org_type': p.get('org_type'), 'url': p.get('url'), 'posted_at': p.get('posted_at'),
                'fetched_at': p.get('first_seen') or p.get('fetched_at'), 'text': p.get('text') or '',
                'images': [PUBLIC + p['image']] if p.get('image') else [],
            }, ensure_ascii=False) + '\n')
    assets = fixture / 'site'
    wanted = {p['image'] for p in posts if p.get('image')}
    recent = [e for e in events if (e.get('end_at') or e['start_at']) >= '2026-09-01']
    for e in recent:
        for key in ('poster_image', 'cover_image'):
            if (e.get(key) or '').startswith('/assets/'):
                wanted.add(e[key])
    for path in sorted(wanted):
        fetch(path, assets / path.lstrip('/'))
    mock_stories(root, now)
    print(f'{len(clean)} events, {len(posts)} posts, {len(wanted)} images, clock {now}')


if __name__ == '__main__':
    main()
