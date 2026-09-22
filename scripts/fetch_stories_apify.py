#!/usr/bin/env python3
"""Fetch public organization Stories without using a Chumei-owned IG account.

The actor grants every free-plan Apify account 40 result items per day, at
most 10 items and 10 scanned profiles per run. Each pipeline invocation
therefore rotates through the token pool: every run takes a fresh batch of due
profiles on the account with the most allowance left today, spread across the
day so live Stories are caught before they expire. Runs still charge the
account's monthly credit, so each account's daily Story spend is capped at
half of its evenly paced remaining credit; the Facebook collector's own
pacing takes the rest.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

from apify_pool import (APIFY_BASE, STORY_DAILY_RESULT_LIMIT, STORY_RUN_RESULT_LIMIT,
                        STORY_RUN_TARGET_LIMIT, choose_story_token, pool_status,
                        record_run, record_story_run, story_runs_available)
from chumei_lib import AVATAR_DIR, INBOX_DIR, ROOT, read_sources_csv
from fetch_facebook import apify_request, usage_usd
from fetch_stories import (MEDIA_DIR, STORIES_STATE, refresh_story_output)
from ig_schedule import (adaptive_interval_hours, load_schedule, mark_failure,
                         mark_success, save_schedule)
from source_status import record_api_call, record_fetch


ACTOR_ID = "intropix/instagram-stories-scraper"
SCHEDULE_STATE = ROOT / "state" / "instagram_apify_stories_schedule.json"
PIPELINE_RUNS_PER_DAY = 8  # launchd pipeline cadence is every 3 hours
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


def attempted_targets(selected: list[str], outcome: dict) -> list[str]:
    """Return the usernames the actor actually scanned.

    The free-plan guard caps profiles per run; usernames past ``granted_targets``
    are reported as "not attempted" and must stay due instead of being marked
    as scanned with zero Stories.
    """
    granted = outcome.get("granted_targets")
    if isinstance(granted, int) and 0 <= granted < len(selected):
        return selected[:granted]
    return list(selected)


def auto_max_runs(status: dict) -> int:
    """Spread today's remaining pool allowance evenly over the pipeline cadence."""
    return max(1, math.ceil(story_runs_available(status) / PIPELINE_RUNS_PER_DAY))


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
    parser.add_argument("--max-accounts", type=int, default=STORY_RUN_TARGET_LIMIT,
                        help=f"profiles per actor run (free plan scans at most {STORY_RUN_TARGET_LIMIT})")
    parser.add_argument("--max-results", type=int, default=STORY_RUN_RESULT_LIMIT)
    parser.add_argument("--max-runs", type=int, default=0,
                        help="actor runs this invocation (0 = spread today's pool allowance over the day)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.max_accounts < 1 or not 1 <= args.max_results <= STORY_RUN_RESULT_LIMIT or args.max_runs < 0:
        parser.error(f"--max-accounts must be positive, --max-results 1..{STORY_RUN_RESULT_LIMIT}, "
                     "--max-runs non-negative")
    batch = min(args.max_accounts, STORY_RUN_TARGET_LIMIT)

    quota = pool_status(refresh=True)
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
    max_runs = 1 if args.accounts else (args.max_runs or auto_max_runs(quota))

    state = json.loads(STORIES_STATE.read_text()) if STORIES_STATE.exists() else {}
    attempted: set[str] = set()
    exhausted_labels: set[str] = set()
    added = scanned = runs_done = 0
    total_cost = 0.0
    stop_reason = ""
    while runs_done < max_runs:
        if args.accounts:
            selected = ranked[:batch]
        else:
            due = [username for username in ranked if username not in attempted]
            selected = select_active_due(due, intervals, schedule, batch, force=args.force)
        if not selected:
            stop_reason = "no more accounts due"
            break
        try:
            label, token, _, allowance = choose_story_token(refresh=False, exclude=exhausted_labels)
        except RuntimeError as exc:
            stop_reason = str(exc)
            break
        try:
            run, items, outcome = run_actor(token, selected, min(args.max_results, allowance))
        except RuntimeError as exc:
            for username in selected:
                mark_failure(schedule, username, base_hours=6, cap_hours=48)
                record_fetch(f"story:{username}", backend="Apify Stories", ok=False, error=exc)
            save_schedule(SCHEDULE_STATE, schedule)
            record_run(label, cost_usd=None, source_count=len(selected), ok=False)
            print(f"stories (Apify): ERROR {exc}", file=sys.stderr)
            return 1

        if outcome.get("outcome") == "denied":
            reason = outcome.get("reason") or "free-tier request denied"
            record_story_run(label, delivered=0, denied_reason=reason)
            exhausted_labels.add(label)
            print(f"stories (Apify): {label} denied ({reason}); trying another account")
            continue

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

        scanned_now = attempted_targets(selected, outcome)
        failed = set(outcome.get("failed_targets") or [])
        for username in scanned_now:
            if username in failed:
                mark_failure(schedule, username, base_hours=24, cap_hours=168)
                record_fetch(f"story:{username}", backend="Apify Stories", ok=False,
                             error=(outcome.get("failed_target_reasons") or {}).get(username, {}))
                continue
            mark_success(schedule, username, interval_hours=intervals[username], jitter_hours=1)
            record_fetch(f"story:{username}", backend="Apify Stories", ok=True,
                         items=counts[username])
        attempted.update(selected)
        save_schedule(SCHEDULE_STATE, schedule)
        delivered = len(items) if items else int(outcome.get("delivered") or 0)
        cost = usage_usd(run)
        budget = record_story_run(label, delivered=delivered, cost_usd=cost)
        total_cost += cost or 0.0
        record_run(label, cost_usd=cost, source_count=len(scanned_now), ok=True)
        record_api_call("Apify", operation="instagram story actor", source_count=len(scanned_now),
                        request_count=0, ok=True, cost_usd=cost)
        scanned += len(scanned_now)
        runs_done += 1
        print(f"stories (Apify): run {runs_done}/{max_runs} on {label}: delivered={delivered}, "
              f"scanned={len(scanned_now)}/{len(selected)}, cost={cost if cost is not None else 'unreported'}, "
              f"today {budget['results']}/{STORY_DAILY_RESULT_LIMIT} items, US${budget['costUsd']:.3f}")

    live, expired, _ = refresh_story_output(state)
    suffix = f"; stopped: {stop_reason}" if stop_reason and runs_done < max_runs else ""
    print(f"stories (Apify): +{added}, {live} visible, pruned {expired}; "
          f"runs={runs_done}, scanned={scanned}, cost={total_cost:.4f}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
