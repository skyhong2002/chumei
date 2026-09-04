#!/usr/bin/env python3
"""Fetch public organization Stories without using a Chumei-owned IG account.

The actor's free-plan ceiling is small, so each pipeline run scans only the
most active due profiles and stops while a protected Apify credit reserve
remains for the existing Facebook collector.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

from apify_pool import (APIFY_BASE, choose_token, pool_status, record_run)
from chumei_lib import AVATAR_DIR, INBOX_DIR, ROOT, read_sources_csv
from fetch_facebook import apify_request, usage_usd
from fetch_stories import (MEDIA_DIR, STORIES_STATE, refresh_story_output)
from ig_schedule import (adaptive_interval_hours, load_schedule, mark_failure,
                         mark_success, save_schedule)
from source_status import record_api_call, record_fetch


ACTOR_ID = "intropix/instagram-stories-scraper"
SCHEDULE_STATE = ROOT / "state" / "instagram_apify_stories_schedule.json"
DEFAULT_RESERVE_USD = 10.0
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}


def historical_post_times() -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    path = INBOX_DIR / "rsshub.jsonl"
    if not path.exists():
        return values
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except (TypeError, ValueError):
                continue
            source_id = str(item.get("source_id") or "")
            if source_id.startswith("ig_") and item.get("posted_at"):
                values[source_id.removeprefix("ig_")].append(item["posted_at"])
    return values


def ranked_usernames(usernames: list[str], history: dict[str, list[str]], *, now=None):
    now = time.time() if now is None else float(now)
    intervals = {
        username: adaptive_interval_hours(
            history.get(username, [])[-12:], now=now, minimum=12, maximum=168
        )
        for username in usernames
    }
    return sorted(usernames, key=lambda username: (intervals[username], username)), intervals


def select_active_due(usernames: list[str], intervals: dict[str, float], state: dict,
                      limit: int, *, now=None, force=False) -> list[str]:
    """Prefer frequently publishing accounts instead of fair-but-slow seeding."""
    now = time.time() if now is None else float(now)
    accounts = state.get("accounts") or {}
    due = [
        username for username in usernames
        if force or float((accounts.get(username) or {}).get("next_eligible") or 0) <= now
    ]
    due.sort(key=lambda username: (
        intervals[username],
        float((accounts.get(username) or {}).get("next_eligible") or 0),
        float((accounts.get(username) or {}).get("last_attempt") or 0),
        username,
    ))
    return due[:limit]


def run_actor(token: str, usernames: list[str], max_results: int):
    actor_api_id = ACTOR_ID.replace("/", "~")
    run = apify_request(
        "POST", f"/acts/{actor_api_id}/runs", token,
        params={"memory": 4096, "timeout": 300, "restartOnError": "false"},
        body={"usernames": usernames, "maxResults": max_results},
    ).get("data", {})
    run_id = run.get("id")
    if not run_id:
        raise RuntimeError("Apify Story actor did not return a run id")
    deadline = time.monotonic() + 345
    while run.get("status") not in TERMINAL_STATUSES:
        if time.monotonic() > deadline:
            raise RuntimeError(f"timed out waiting for Apify Story run {run_id}")
        time.sleep(3)
        run = apify_request("GET", f"/actor-runs/{run_id}", token, timeout=30).get("data", {})
    if run.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Apify Story run {run_id} ended with {run.get('status')}")
    dataset_id = run.get("defaultDatasetId")
    items = apify_request(
        "GET", f"/datasets/{dataset_id}/items", token,
        params={"format": "json", "clean": "true", "limit": max_results},
    ) if dataset_id else []
    outcome = {}
    store_id = run.get("defaultKeyValueStoreId")
    if store_id:
        response = requests.get(
            f"{APIFY_BASE}/key-value-stores/{store_id}/records/OUTPUT",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30,
        )
        if response.ok:
            outcome = response.json()
    return run, items if isinstance(items, list) else [], outcome


def _video_frame(content: bytes, destination: Path) -> bool:
    with tempfile.TemporaryDirectory(prefix="chumei-story-") as directory:
        source = Path(directory) / "story.mp4"
        source.write_bytes(content)
        result = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(source),
             "-frames:v", "1", "-vf", "scale='min(720,iw)':-2", str(destination)],
            capture_output=True,
        )
        return result.returncode == 0 and destination.exists()


def save_media(item: dict) -> str | None:
    story_id = str(item.get("story_pk") or "").strip()
    media_url = str(item.get("media_url") or "").strip()
    if not story_id or not media_url:
        return None
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    destination = MEDIA_DIR / f"{story_id}.jpg"
    if destination.exists():
        return f"/assets/stories/{story_id}.jpg"
    try:
        response = requests.get(media_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        if item.get("media_type") == "video":
            if not _video_frame(response.content, destination):
                return None
        else:
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            image.thumbnail((720, 1280))
            image.save(destination, "JPEG", quality=82)
        return f"/assets/stories/{story_id}.jpg"
    except Exception as exc:
        print(f"story media {story_id}: {str(exc)[:100]}", file=sys.stderr)
        destination.unlink(missing_ok=True)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", help="comma-separated usernames")
    parser.add_argument("--max-accounts", type=int, default=5)
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--reserve-usd", type=float, default=DEFAULT_RESERVE_USD)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.max_accounts < 1 or not 1 <= args.max_results <= 10:
        parser.error("--max-accounts must be positive and --max-results must be 1..10")

    quota = pool_status(refresh=True)
    if float(quota.get("remainingUsd") or 0) <= args.reserve_usd:
        refresh_story_output()
        print(f"stories (Apify): skipped; protected reserve US${args.reserve_usd:.2f}")
        return 0

    rows = [
        row for row in read_sources_csv("ig_accounts.csv")
        if row.get("active", "true").lower() not in {"false", "link"}
        and row.get("org_type", "").lower() in {"club", "department", "official"}
    ]
    if args.accounts:
        wanted = {value.strip().lstrip("@") for value in args.accounts.split(",") if value.strip()}
        rows = [row for row in rows if row["username"].strip().lstrip("@") in wanted]
    metadata = {row["username"].strip().lstrip("@"): row for row in rows}
    ranked, intervals = ranked_usernames(list(metadata), historical_post_times())
    schedule = load_schedule(SCHEDULE_STATE)
    selected = (
        ranked[:args.max_accounts] if args.accounts else
        select_active_due(ranked, intervals, schedule, args.max_accounts, force=args.force)
    )
    if not selected:
        refresh_story_output()
        print("stories (Apify): no accounts due")
        return 0

    try:
        label, token, _ = choose_token(refresh=False)
        run, items, outcome = run_actor(token, selected, args.max_results)
    except RuntimeError as exc:
        for username in selected:
            mark_failure(schedule, username, base_hours=6, cap_hours=48)
            record_fetch(f"story:{username}", backend="Apify Stories", ok=False, error=exc)
        save_schedule(SCHEDULE_STATE, schedule)
        print(f"stories (Apify): ERROR {exc}", file=sys.stderr)
        return 1

    if outcome.get("outcome") == "denied":
        reason = outcome.get("reason") or "free-tier request denied"
        for username in selected:
            mark_failure(schedule, username, base_hours=12, cap_hours=48)
            record_fetch(f"story:{username}", backend="Apify Stories", ok=False, error=reason)
        save_schedule(SCHEDULE_STATE, schedule)
        print(f"stories (Apify): {reason}; will retry later")
        return 0

    state = json.loads(STORIES_STATE.read_text()) if STORIES_STATE.exists() else {}
    added = 0
    counts = defaultdict(int)
    for item in items:
        username = str(item.get("username") or "").strip().lstrip("@")
        story_id = str(item.get("story_pk") or "").strip()
        row = metadata.get(username)
        if not row or not story_id:
            continue
        counts[username] += 1
        if story_id in state:
            continue
        media = save_media(item)
        if not media:
            continue
        taken_at = str(item.get("taken_at") or datetime.now(timezone.utc).isoformat())
        state[story_id] = {
            "username": username,
            "avatar": (f"/assets/avatars/ig_{username}.jpg"
                       if (AVATAR_DIR / f"ig_{username}.jpg").exists() else None),
            "name": row.get("name") or username,
            "school": row.get("school") or "other",
            "taken_at": taken_at,
            "expires_at": item.get("expiring_at"),
            "is_video": item.get("media_type") == "video",
            "media": media,
            "ig_url": f"https://www.instagram.com/stories/{username}/{story_id}/",
        }
        added += 1

    failed = set(outcome.get("failed_targets") or [])
    for username in selected:
        if username in failed:
            mark_failure(schedule, username, base_hours=24, cap_hours=168)
            record_fetch(f"story:{username}", backend="Apify Stories", ok=False,
                         error=(outcome.get("failed_target_reasons") or {}).get(username, {}))
            continue
        mark_success(schedule, username, interval_hours=intervals[username], jitter_hours=1)
        record_fetch(f"story:{username}", backend="Apify Stories", ok=True,
                     items=counts[username])
    save_schedule(SCHEDULE_STATE, schedule)
    live, expired, _ = refresh_story_output(state)
    cost = usage_usd(run)
    record_run(label, cost_usd=cost, source_count=len(selected), ok=True)
    record_api_call("Apify", operation="instagram story actor", source_count=len(selected),
                    request_count=0, ok=True, cost_usd=cost)
    print(f"stories (Apify): +{added}, {live} visible, pruned {expired}; "
          f"scanned={len(selected)}, cost={cost if cost is not None else 'unreported'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
