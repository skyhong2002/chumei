#!/usr/bin/env python3
"""Fetch Instagram posts without using an Instagram account.

The zero-cost logged-out endpoint is tried first. If Instagram blocks that
server IP, a small Apify profile batch is used while at least US$10 of the
existing free credit pool remains reserved for Facebook collection.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from apify_pool import choose_token, pool_status, record_run
from chumei_lib import (ROOT, SeenState, append_inbox, load_env, now_iso,
                        read_sources_csv, save_avatar)
from fetch_facebook import apify_request, usage_usd
from fetch_instagram import PUBLIC_SCHEDULE_STATE, fetch_public_web
from ig_schedule import (adaptive_interval_hours, is_rate_limited, load_schedule,
                         mark_failure, mark_success, save_schedule, select_due)
from source_status import record_api_call, record_fetch


ACTOR_ID = "apify/instagram-profile-scraper"
RAW_SOURCE = "rsshub"  # Preserve the existing seen/inbox namespace across providers.
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
DEFAULT_RESERVE_USD = 10.0


def normalize_profile(item: dict, limit: int) -> tuple[str, str | None, list[dict]]:
    username = str(item.get("username") or "").strip().lstrip("@")
    posts = []
    candidates = [raw for raw in (item.get("latestPosts") or []) if not raw.get("isPinned")]
    if not candidates:
        candidates = list(item.get("latestPosts") or [])
    candidates.sort(key=lambda raw: str(raw.get("timestamp") or ""), reverse=True)
    for raw in candidates[:limit]:
        post_id = str(raw.get("shortCode") or raw.get("shortcode") or "").strip()
        if not post_id:
            continue
        images = raw.get("images") if isinstance(raw.get("images"), list) else []
        images = [value for value in images[:2] if isinstance(value, str) and value.startswith("http")]
        if not images and str(raw.get("displayUrl") or "").startswith("http"):
            images = [raw["displayUrl"]]
        posted_at = str(raw.get("timestamp") or "").strip()
        if not posted_at:
            posted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        posts.append({
            "post_id": post_id,
            "url": raw.get("url") or f"https://www.instagram.com/p/{post_id}/",
            "posted_at": posted_at,
            "text": str(raw.get("caption") or "").strip() or "（純圖片貼文，內容見海報）",
            "images": images,
        })
    avatar = item.get("profilePicUrlHD") or item.get("profilePicUrl")
    return username, avatar, posts


def run_actor(token: str, usernames: list[str]):
    actor_id = ACTOR_ID.replace("/", "~")
    run = apify_request(
        "POST", f"/acts/{actor_id}/runs", token,
        params={"maxItems": len(usernames), "memory": 1024, "timeout": 300,
                "restartOnError": "false"},
        body={"usernames": usernames, "includeAboutSection": False},
    ).get("data", {})
    run_id = run.get("id")
    if not run_id:
        raise RuntimeError("Apify Instagram profile actor did not return a run id")
    deadline = time.monotonic() + 345
    while run.get("status") not in TERMINAL_STATUSES:
        if time.monotonic() > deadline:
            raise RuntimeError(f"timed out waiting for Apify profile run {run_id}")
        time.sleep(3)
        run = apify_request("GET", f"/actor-runs/{run_id}", token, timeout=30).get("data", {})
    if run.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Apify profile run {run_id} ended with {run.get('status')}")
    dataset_id = run.get("defaultDatasetId")
    items = apify_request(
        "GET", f"/datasets/{dataset_id}/items", token,
        params={"format": "json", "clean": "true", "limit": len(usernames)},
    ) if dataset_id else []
    return run, items if isinstance(items, list) else []


def ingest(username: str, avatar: str | None, posts: list[dict], row: dict,
           seen: SeenState) -> int:
    if avatar:
        save_avatar(f"ig_{username}", avatar)
    source_id = f"ig_{username}"
    fresh = []
    for post in posts:
        if seen.has(source_id, post["post_id"]):
            continue
        fresh.append({
            "source_id": source_id,
            "source_name": row.get("name") or username,
            "platform": "instagram",
            "raw_source": RAW_SOURCE,
            "school": row.get("school") or "other",
            "org_type": row.get("org_type") or "club",
            "fetched_at": now_iso(),
            **post,
        })
        seen.add(source_id, post["post_id"])
    return append_inbox(RAW_SOURCE, fresh)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", help="comma-separated usernames")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-accounts", type=int, default=5)
    parser.add_argument("--reserve-usd", type=float, default=DEFAULT_RESERVE_USD)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.limit < 1 or args.max_accounts < 1:
        parser.error("--limit and --max-accounts must be positive")

    rows = [
        row for row in read_sources_csv("ig_accounts.csv")
        if row.get("active", "true").lower() not in {"false", "link"}
    ]
    if args.accounts:
        wanted = {value.strip().lstrip("@") for value in args.accounts.split(",") if value.strip()}
        rows = [row for row in rows if row["username"].strip().lstrip("@") in wanted]
    metadata = {row["username"].strip().lstrip("@"): row for row in rows}
    schedule = load_schedule(PUBLIC_SCHEDULE_STATE)
    selected = (
        list(metadata)[:args.max_accounts] if args.accounts else
        select_due(list(metadata), schedule, args.max_accounts, force=args.force)
    )
    if not selected:
        print("instagram public: no accounts due")
        return 0

    seen = SeenState(RAW_SOURCE)
    resolved: dict[str, tuple[str | None, list[dict], str]] = {}
    fallback = []
    public_base = load_env().get("CHUMEI_IG_PUBLIC_BASE", "https://www.instagram.com")
    direct_open = float(schedule.get("direct_cooldown_until") or 0) > time.time()
    for username in selected:
        if direct_open:
            fallback.append(username)
            continue
        try:
            avatar, posts = fetch_public_web(public_base, username, args.limit)
            resolved[username] = (avatar, posts, "Instagram public web")
        except Exception as exc:
            fallback.append(username)
            if is_rate_limited(exc):
                schedule["direct_cooldown_until"] = time.time() + 24 * 3600
                direct_open = True
            print(f"@{username}: logged-out endpoint unavailable ({str(exc)[:80]})")

    actor_run = None
    actor_label = None
    if fallback:
        quota = pool_status(refresh=True)
        if float(quota.get("remainingUsd") or 0) > args.reserve_usd:
            try:
                actor_label, token, _ = choose_token(refresh=False)
                actor_run, items = run_actor(token, fallback)
                for item in items:
                    username, avatar, posts = normalize_profile(item, args.limit)
                    if username in metadata:
                        resolved[username] = (avatar, posts, "Apify Instagram")
            except RuntimeError as exc:
                print(f"Apify Instagram fallback failed: {exc}", file=sys.stderr)
        else:
            print(f"Apify Instagram skipped; protected reserve US${args.reserve_usd:.2f}")

    total = 0
    failures = 0
    for username in selected:
        result = resolved.get(username)
        if not result:
            failures += 1
            mark_failure(schedule, username, base_hours=12, cap_hours=72)
            record_fetch(f"instagram:{username}", backend="Instagram public", ok=False,
                         error="no unauthenticated provider available within free-credit reserve")
            continue
        avatar, posts, backend = result
        total += ingest(username, avatar, posts, metadata[username], seen)
        interval = adaptive_interval_hours([post.get("posted_at") for post in posts])
        mark_success(schedule, username, interval_hours=interval, jitter_hours=3)
        record_fetch(f"instagram:{username}", backend=backend, ok=True, items=len(posts))
        record_api_call(backend, operation="instagram profile", ok=True)
        print(f"@{username}: {len(posts)} posts via {backend}; next ~{interval:g}h")
    seen.save()
    save_schedule(PUBLIC_SCHEDULE_STATE, schedule)
    if actor_run is not None and actor_label is not None:
        cost = usage_usd(actor_run)
        record_run(actor_label, cost_usd=cost, source_count=len(fallback), ok=True)
        record_api_call("Apify", operation="instagram profile actor", source_count=len(fallback),
                        request_count=0, ok=True, cost_usd=cost)
        print(f"Apify Instagram cost: {cost if cost is not None else 'unreported'}")
    print(f"instagram public: +{total}, failures={failures}/{len(selected)}")
    return 0 if failures < len(selected) else 1


if __name__ == "__main__":
    sys.exit(main())
