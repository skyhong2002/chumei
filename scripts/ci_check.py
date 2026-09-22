"""Run a credential-free check of tracked files in a disposable checkout.

Never builds in site/, reads a developer's state/, or runs the scraping pipeline.
Python child processes block non-loopback network access even when tests regress.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]


def fixture(root):
    now = datetime.now(timezone(timedelta(hours=8))).replace(microsecond=0)
    events = []
    for index, (title, start, end, venue) in enumerate([
        ('CI 同名說明會', now + timedelta(days=1), now + timedelta(days=1, hours=1), '台達館 B05'),
        ('CI 同名說明會', now + timedelta(days=1), now + timedelta(days=1, hours=1), '物理館 B1-019'),
        ('CI 進行中展覽', now - timedelta(days=1), now + timedelta(days=1), '圖書館'),
        ('CI 歷史活動', now - timedelta(days=90), now - timedelta(days=90, hours=-1), '圖書館'),
    ]):
        events.append({
            'id': f'evt_{index:012x}', 'title': title, 'summary': title + '：離線建站測試資料。',
            'description': '合成資料；不會抓取、發布通知或使用正式帳號。',
            'start_at': start.isoformat(), 'end_at': end.isoformat(), 'all_day': False,
            'school': 'nthu', 'campus': 'nthu-main', 'venue': venue,
            'organizer': 'CI 測試單位', 'organizer_type': 'club', 'category': '演講',
            'source': {'source_id': 'ig_nthu_dsc', 'post_id': f'ci_{0 if index < 2 else index}',
                       'url': f'https://example.com/ci/{index}', 'platform': 'instagram',
                       'name': 'CI 測試單位'},
            'extraction': {'confidence': 1, 'needs_review': False},
            'registration_required': False, 'price': '免費',
        })
    (root / 'state').mkdir()
    (root / 'state/nycu_life_activities.json').write_text(json.dumps(events, ensure_ascii=False))
    inbox = root / 'data/feeds/inbox'
    inbox.mkdir(parents=True)
    # A full column is needed to exercise nested scrolling. Keep the event-backed
    # post at the bottom: its absolute screen-reader labels exposed deck overflow.
    post_texts = [
        'CI 同名說明會', '籃球友誼賽開放報名，歡迎同學組隊參加。', '吉他社成果演出，週末一起欣賞音樂。',
        '圖書館推出新書展示，探索不同文化觀點。', '登山團出發前說明裝備與路線規劃。',
        '手作陶藝體驗課程分享捏塑與上釉技巧。', '程式設計讀書會討論資料結構練習題。',
        '攝影展記錄校園四季景色和人文故事。', '志工招募協助社區長者學習手機操作。',
        '電影欣賞交流會邀請大家分享觀後心得。', '天文觀測夜帶你認識星座與望遠鏡。',
        '生態導覽尋訪步道上的植物和鳥類。', '舞蹈工作坊從基礎律動開始練習。',
        '烘焙同好交換餅乾食譜與製作經驗。', '游泳訓練介紹暖身動作及水中安全。',
        '桌遊聚會準備策略挑戰和合作任務。',
    ]
    (inbox / 'ci.jsonl').write_text(''.join(json.dumps({
        'source_id': 'ig_nthu_dsc', 'source_name': 'CI 測試單位', 'platform': 'instagram',
        'raw_source': 'ci', 'school': 'nthu', 'org_type': 'club', 'post_id': f'ci_{index}',
        'url': f'https://example.com/ci/{index}',
        'posted_at': (now - timedelta(minutes=60 - index)).isoformat(),
        'fetched_at': (now - timedelta(minutes=20 - index)).isoformat(),
        'text': post_texts[index],
        'images': [],
    }, ensure_ascii=False) + '\n' for index in range(len(post_texts))))


def main():
    with tempfile.TemporaryDirectory(prefix='chumei-ci-') as temporary:
        root = Path(temporary)
        paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        for name in filter(None, paths):
            if name in ('.env', '.env.apify') or name.startswith(('state/', 'data/feeds/', 'published/')):
                raise RuntimeError(f'Private/generated file unexpectedly tracked: {name}')
            source, target = ROOT / name, root / name
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        (root / '.venv').symlink_to(Path(sys.prefix), target_is_directory=True)
        fixture(root)
        env = {key: value for key, value in os.environ.items()
               if not (key.startswith(('CHUMEI_', 'APIFY_', 'TELEGRAM_', 'LINE_', 'GOOGLE_', 'GITHUB_', 'GH_'))
                       or key in ('VAPID_PRIVATE_KEY', 'OPENAI_API_KEY'))}
        env.update(CHUMEI_BUILD_OFFLINE='1', PYTHONPATH=str(root / 'tests/ci_network_guard'))
        def run(*command):
            subprocess.run(command, cwd=root, env=env, check=True)
        run(sys.executable, '-m', 'compileall', '-q', 'scripts', 'tests')
        for path in (root / 'site/assets').glob('*.js'):
            run('node', '--check', str(path))
        run(sys.executable, 'scripts/publish_site.py', '--offline')
        # Point artifact-level SEO assertions at the release built above.
        run(sys.executable, '-c', '''import sys, unittest
from pathlib import Path
sys.path.insert(0, 'tests')
suite = unittest.defaultTestLoader.discover('tests')
sys.modules['test_seo'].SITE = Path('published/current').resolve()
result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())''')
        run(sys.executable, 'tests/ci_browser_smoke.py', str(root / 'published/current'))
        # The validation gate must reject real corruption, not just pass a happy fixture.
        release = root / 'published/current'
        env['CHUMEI_BUILD_DIR'] = str(release)
        page = release / 'event/evt_000000000000/index.html'
        page.write_text(page.read_text().replace('rel="canonical"', 'rel="broken-canonical"'))
        seo_probe = subprocess.run([sys.executable, '-c', """import sys, unittest
from pathlib import Path
sys.path.insert(0, 'tests')
import test_seo
test_seo.SITE = Path('published/current').resolve()
suite = unittest.defaultTestLoader.loadTestsFromName('test_seo.SEOOutputTests.test_every_page_has_queryless_canonical_and_preview_metadata')
raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())"""],
            cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if seo_probe.returncode == 0 or b'FAIL: test_every_page' not in seo_probe.stderr:
            raise RuntimeError('Missing canonical unexpectedly passed SEO checks')
        data = release / 'data/events.json'
        data.write_text('{invalid JSON')
        result = subprocess.run([sys.executable, 'scripts/validate_outputs.py'], cwd=root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0 or b'events.json unparseable' not in result.stderr:
            raise RuntimeError('Corrupted event data unexpectedly passed validation')
        print('CI passed: isolated release, unit/JS tests, SEO, browser smoke, invalid-data/SEO rejection.')


if __name__ == '__main__':
    main()
