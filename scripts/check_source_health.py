#!/usr/bin/env python3
"""Check a published local status snapshot without fetching or modifying anything."""
import argparse
import json
from pathlib import Path

from site_paths import published_site_dir
from source_status import SNAPSHOT_MAX_AGE_HOURS, assess_health


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=published_site_dir() / 'api/status.json')
    parser.add_argument('--max-age-hours', type=float, default=SNAPSHOT_MAX_AGE_HOURS)
    args = parser.parse_args(argv)
    if args.max_age_hours <= 0:
        parser.error('--max-age-hours must be positive')
    try:
        payload = json.loads(args.snapshot.read_text(encoding='utf-8'))
        result = assess_health(payload, max_age_hours=args.max_age_hours)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        result = {'status': 'degraded', 'issues': ['snapshot_unreadable'], 'detail': str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
