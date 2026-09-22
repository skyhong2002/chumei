"""Check build output budgets without fetching anything: python scripts/check_browser_budget.py [site]."""
import gzip
import json
import os
from pathlib import Path
import sys


def check(site):
    raw = (site / 'data' / 'events-index.json').read_bytes()
    bundle = json.loads(raw)
    limits = {
        'decoded_bytes': int(os.environ.get('CHUMEI_BROWSER_INDEX_MAX_BYTES', '1500000')),
        'gzip_bytes': int(os.environ.get('CHUMEI_BROWSER_INDEX_MAX_GZIP_BYTES', '300000')),
    }
    if any(value <= 0 for value in limits.values()):
        raise ValueError('Browser index budgets must be positive byte counts')
    sizes = {'decoded_bytes': len(raw), 'gzip_bytes': len(gzip.compress(raw))}
    print(json.dumps({'events': len(bundle['events']), **sizes, 'limits': limits}))
    return all(sizes[key] <= limit for key, limit in limits.items())


if __name__ == '__main__':
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'site'
    sys.exit(0 if check(site) else 1)
