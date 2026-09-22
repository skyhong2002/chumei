"""公開輸出驗證（fail-closed）：壞掉的輸出寧可不發佈。run_pipeline 在 build 後執行。"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from site_paths import build_site_dir

SITE = build_site_dir()


def fail(msg):
    print(f"VALIDATE FAIL: {msg}", file=sys.stderr)
    return 1


def validate_browser_indexes(site, events):
    errors = 0
    try:
        current = json.loads((site / "data/events-index.json").read_text())
        archive = json.loads((site / "data/events-archive.json").read_text())
        current_ids = [e["id"] for e in current["events"]]
        archive_ids = [e["id"] for e in archive["events"]]
        if len(set(current_ids + archive_ids)) != len(current_ids + archive_ids):
            errors += fail("browser indexes contain duplicate events")
        if set(current_ids + archive_ids) != {e["id"] for e in events}:
            errors += fail("browser indexes do not cover the full event dataset")
        if current.get("archive_count") != len(archive_ids) or current.get("archive_url") != "/data/events-archive.json":
            errors += fail("browser index archive metadata mismatch")
        if current.get("generated_at") != archive.get("generated_at"):
            errors += fail("browser indexes belong to different builds")
        from check_browser_budget import check
        if not check(site):
            errors += fail("browser event index exceeds download budget; see docs/browser-performance.md")
    except Exception as exc:
        errors += fail(f"browser indexes invalid: {exc}")
    return errors



def validate_quality_report(site, bundle):
    try:
        report = json.loads((site / "api/data-quality.json").read_text())
        if report.get("generated_at") != bundle.get("generated_at"):
            return fail("data quality report belongs to a different build")
        items = report["items"]
        if report["counts"]["queued_events"] != len(items) or len({r["id"] for r in items}) != len(items):
            return fail("data quality queue count mismatch or duplicate ids")
        event_ids = {e["id"] for e in bundle["events"]}
        if any(r.get("event_url") and r["id"] not in event_ids for r in items):
            return fail("data quality queue links to unpublished event")
        if not (site / "quality/index.html").exists():
            return fail("data quality page missing")
        for metric in report["coverage"].values():
            if not 0 <= metric["available"] <= metric["total"]:
                return fail("data quality coverage invalid")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return fail(f"data quality report invalid: {exc}")
    return 0


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
        cover = e.get("cover_image")
        if not cover:
            errors += fail(f"event missing cover image: {e['id']}")
        elif not (SITE / cover.lstrip("/")).exists():
            errors += fail(f"cover missing on disk: {cover}")
        if not (SITE / "event" / e["id"] / "index.html").exists():
            errors += fail(f"detail page missing: {e['id']}")

    errors += validate_browser_indexes(SITE, events)
    errors += validate_quality_report(SITE, bundle)

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
    if api != bundle:
        errors += fail("api/events.json content mismatch")

    try:
        status = json.loads((SITE / "api" / "status.json").read_text())
        sources = status.get("sources", [])
        if not sources:
            errors += fail("api/status.json has zero sources")
        if status.get("counts", {}).get("sources") != len(sources):
            errors += fail("api/status.json source count mismatch")
        required = {"id", "name", "backend", "lastAttempt", "lastSuccess", "nextDue", "targetIntervalHours"}
        for source in sources:
            if required - set(source):
                errors += fail(f"status source missing fields: {source.get('id')}")
                break
        if "token" in json.dumps(status).lower():
            errors += fail("api/status.json may expose a token field")
        if not (SITE / "status" / "index.html").exists():
            errors += fail("status page missing")
    except Exception as e:
        errors += fail(f"api/status.json unparseable: {e}")

    for name in ("data/map/campuses.geojson", "data/map/buildings.geojson"):
        try:
            geo = json.loads((SITE / name).read_text())
            if geo.get("type") != "FeatureCollection" or not geo.get("features"):
                errors += fail(f"{name} has no map features")
        except Exception as e:
            errors += fail(f"{name} unparseable: {e}")

    if errors:
        return 1
    print(f"validate: OK ({len(events)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
