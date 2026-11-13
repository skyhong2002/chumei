#!/usr/bin/env python3
"""Assemble one blind review round.

  python3 docs/design-review/tools/make_round.py ROUND NEW_SET_DIR [BRIEF] [REFERENCE_SET_DIR]

ROUND is a label such as 1, c1 (council) or m9 (rounds shot on sky-mini).
Numeric labels get an r prefix (r1); labels that start with a letter are used
as is (m9). BRIEF defaults to brief.md, which never changes after round 1.
CM_HOST (default sky-mini) is recorded with the mapping; every set in one
round must be shot on that host.

Copies the fixed baseline set, this round's new set and the fixed reference
set into $CM_REVIEW/rounds/<label>/{A,B,C} in random order, plus a
byte-identical copy of brief.md. The A/B/C mapping is written outside the
review folder, to $CM_REVIEW/private/<label>.json.
"""
import hashlib
import os
import json
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ.get('CM_REVIEW', '/tmp/cm-review'))
DOCS = Path(__file__).resolve().parents[1]
HOST = os.environ.get('CM_HOST', 'sky-mini')


def round_label(number):
    return number if number[:1].isalpha() else f'r{number}'


def main():
    number, new_set = sys.argv[1], Path(sys.argv[2])
    brief = DOCS / (sys.argv[3] if len(sys.argv) > 3 else 'brief.md')
    reference = Path(sys.argv[4]) if len(sys.argv) > 4 else ROOT / 'sets/reference'
    sets = {'baseline': ROOT / 'sets/baseline', 'new': new_set, 'reference': reference}
    labels = ['A', 'B', 'C']
    random.SystemRandom().shuffle(labels)
    mapping = dict(zip(labels, sets))
    out = ROOT / 'rounds' / round_label(number)
    if out.exists():
        shutil.rmtree(out)
    for label, name in mapping.items():
        target = out / label
        target.mkdir(parents=True)
        for image in sorted(sets[name].glob('*.png')):
            shutil.copy2(image, target / image.name)
    shutil.copy2(brief, out / 'brief.md')
    digest = hashlib.sha256(brief.read_bytes()).hexdigest()
    private = ROOT / 'private'
    private.mkdir(parents=True, exist_ok=True)
    (private / f'{round_label(number)}.json').write_text(json.dumps({'round': number, 'host': HOST, 'mapping': mapping, 'new': str(new_set), 'brief': brief.name, 'briefSha256': digest}, indent=2))
    print(out, digest)


if __name__ == '__main__':
    main()
