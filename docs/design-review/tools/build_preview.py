#!/usr/bin/env python3
"""Build one version of the site against the frozen fixture, in isolation.

  python3 docs/design-review/tools/build_preview.py REF OUT
      REF  a git ref (baseline: main) or WORKTREE for the current checkout
      OUT  e.g. /tmp/cm-review/builds/baseline

Copies REF's tracked files to OUT/src, adds the fixture from prepare_fixture.py
(state/, data/feeds/inbox/, cached images, mocked stories) and runs the normal
build steps with the clock started at the snapshot time and every non-loopback
connection blocked. Runs under nice (and ionice on Linux) and waits while the
host is busy (hostload.py: load1 > CM_MAX_LOAD or memory below CM_MIN_MEM_GIB). The
repository's own state/, data/feeds/ and published/ are never read or written.
"""
import os
import shutil
import subprocess
import sys
import tarfile
import io
import time
from pathlib import Path

from hostload import low_priority, wait_for_load

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[2]
REVIEW = Path(os.environ.get('CM_REVIEW', '/tmp/cm-review'))
NOW = os.environ.get('CHUMEI_PREVIEW_NOW', '2026-11-12T15:30:00+08:00')
PYTHON = os.environ.get('CM_PYTHON', str(REVIEW / 'venv/bin/python'))
STEPS = ('build_map_data.py', 'build_site.py', 'build_status_page.py')


def export(ref, src):
    if ref == 'WORKTREE':
        names = subprocess.check_output(['git', 'ls-files', '-z', '-co', '--exclude-standard'], cwd=REPO).decode().split('\0')
        for name in filter(None, names):
            source = REPO / name
            if source.is_file() and not name.startswith(('state/', 'data/feeds/', 'published/')):
                (src / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, src / name)
    else:
        archive = subprocess.check_output(['git', 'archive', '--format=tar', ref], cwd=REPO)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(src, filter='data')
    for private in ('.env', '.env.apify'):
        (src / private).unlink(missing_ok=True)


def main():
    ref, out = sys.argv[1], Path(sys.argv[2])
    src = out / 'src'
    if out.exists():
        shutil.rmtree(out)
    src.mkdir(parents=True)
    export(ref, src)
    fixture = REVIEW / 'fixture'
    shutil.copytree(fixture / 'state', src / 'state', dirs_exist_ok=True)
    shutil.copytree(fixture / 'data', src / 'data', dirs_exist_ok=True)
    shutil.copytree(fixture / 'site', src / 'site', dirs_exist_ok=True)
    (src / 'site/data').mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture / 'stories.json', src / 'site/data/stories.json')
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('CHUMEI_', 'APIFY_', 'TELEGRAM_', 'LINE_', 'GOOGLE_', 'GITHUB_', 'GH_', 'OPENAI_'))}
    env.update(CHUMEI_BUILD_OFFLINE='1', CHUMEI_PREVIEW_NOW=NOW, CHUMEI_BUILD_DIR=str(src / 'site'),
               PYTHONPATH=str(TOOLS / 'frozen'), TZ='Asia/Taipei')
    for step in STEPS:
        wait_for_load()
        started = time.monotonic()
        subprocess.run(low_priority([PYTHON, str(src / 'scripts' / step)]),
                       cwd=src, env=env, check=True, stdout=subprocess.DEVNULL if step != 'build_site.py' else None)
        print(f'{step}: {time.monotonic() - started:.0f}s', flush=True)
    # The status page reads its data client-side; use the public snapshot so it is not empty.
    snapshot = REVIEW / 'data/status.json'
    if snapshot.exists():
        (src / 'site/api').mkdir(exist_ok=True)
        shutil.copy2(snapshot, src / 'site/api/status.json')
    print('built', src / 'site')


if __name__ == '__main__':
    main()
