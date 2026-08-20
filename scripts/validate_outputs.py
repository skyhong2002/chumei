"""公開輸出驗證（fail-closed）：壞掉的輸出寧可不發佈。run_pipeline 在 build 後執行。"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def fail(msg):
    print(f"VALIDATE FAIL: {msg}", file=sys.stderr)
    return 1


def main():
    errors = 0

    try:
        bundle = json.loads((SITE / "data" / "events.json").read_text())
    except Exception as e:
        return fail(f"events.json unparseable: {e}")

    events = bundle.get("events", [])
    if not events:
        errors += fail("events.json has zero events")

    ids = set()
    for e in events:
        for k in ("id", "title", "start_at", "school", "source"):
            if not e.get(k):
                errors += fail(f"event missing {k}: {e.get('id') or e.get('title')}")
                break
        if e["id"] in ids:
            errors += fail(f"duplicate event id {e['id']}")
        ids.add(e["id"])
        p = e.get("poster_image")
        if p and not (SITE / p.lstrip("/")).exists():
            errors += fail(f"poster missing on disk: {p}")
        if not (SITE / "event" / e["id"] / "index.html").exists():
            errors += fail(f"detail page missing: {e['id']}")

    for name in ("feeds/all.xml", "feeds/nthu.xml", "feeds/nycu.xml", "sitemap.xml"):
        try:
            ET.parse(SITE / name)
        except Exception as e:
            errors += fail(f"{name} unparseable: {e}")

    for name in ("feeds/all.ics", "feeds/nthu.ics", "feeds/nycu.ics"):
        txt = (SITE / name).read_text() if (SITE / name).exists() else ""
        if "BEGIN:VCALENDAR" not in txt:
            errors += fail(f"{name} not a calendar")

    api = json.loads((SITE / "api" / "events.json").read_text())
    if len(api.get("events", [])) != len(events):
        errors += fail("api/events.json count mismatch")

    if errors:
        return 1
    print(f"validate: OK ({len(events)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
