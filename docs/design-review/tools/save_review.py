#!/usr/bin/env python3
"""Save one reviewer's raw output and its scores.

  python3 save_review.py ROUND REVIEWER TRANSCRIPT.jsonl [--note TEXT]

Takes the reviewer's last assistant message verbatim from its transcript,
reads the private A/B/C mapping for the round, and writes
results/r<ROUND>-<REVIEWER>.md (raw text unedited, mapping revealed after the
review) plus a row in results/scores.json (mean of the 12 category scores).
"""
import argparse
import json
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
PRIVATE = Path('/tmp/cm-review/private')


def last_text(transcript):
    # Stream the file: reviewer transcripts embed every screenshot and run to
    # hundreds of MB, so reading them whole can exhaust a busy host's memory.
    text = None
    with transcript.open(encoding='utf-8') as lines:
        for line in lines:
            if '"type":"assistant"' not in line or '"type":"text"' not in line:
                continue
            text = _text_of(line) or text
    return text


def _text_of(line):
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        return None
    message = item.get('message') or {}
    if item.get('type') != 'assistant' or message.get('role') != 'assistant':
        return None
    parts = [c.get('text', '') for c in message.get('content', []) if isinstance(c, dict) and c.get('type') == 'text']
    return ''.join(parts) if ''.join(parts).strip() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('round')
    parser.add_argument('reviewer')
    parser.add_argument('transcript', type=Path)
    parser.add_argument('--note', default='')
    a = parser.parse_args()
    raw = last_text(a.transcript)
    mapping = json.loads((PRIVATE / f'r{a.round}.json').read_text())
    blob = re.findall(r'```json\s*(\{.*?\})\s*```', raw, re.S)[-1]
    scores = json.loads(blob)
    means = {mapping['mapping'][label]: round(sum(v['scores'].values()) / len(v['scores']), 2) for label, v in scores.items()}
    header = (f"# Round {a.round} blind review: {a.reviewer}\n\n"
              f"- Brief: `brief.md`, SHA-256 `{mapping['briefSha256']}`\n"
              f"- Mapping (revealed after the review): " + ', '.join(f"**{k} = {v}**" for k, v in mapping['mapping'].items()) + "\n"
              f"- New set: `{mapping['new']}`\n"
              f"- Mean of 12 scores: " + ', '.join(f"{k} {v}" for k, v in means.items()) + "\n"
              + (f"- Note: {a.note}\n" if a.note else '') +
              "\nRaw reviewer output below, unedited.\n\n---\n\n")
    out = DOCS / 'results' / f'r{a.round}-{a.reviewer}.md'
    out.write_text(header + raw.strip() + '\n')
    table = DOCS / 'results' / 'scores.json'
    rows = json.loads(table.read_text()) if table.exists() else []
    rows = [r for r in rows if not (r['round'] == a.round and r['reviewer'] == a.reviewer)]
    by_set = {mapping['mapping'][label]: v['scores'] for label, v in scores.items()}
    rows.append({'round': a.round, 'reviewer': a.reviewer, 'means': means, 'scores': by_set, 'note': a.note})
    table.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + '\n')
    print(out, means)


if __name__ == '__main__':
    main()
