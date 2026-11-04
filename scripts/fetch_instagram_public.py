#!/usr/bin/env python3
"""Fetch Instagram posts without using an Instagram account.

The zero-cost logged-out web query is tried first, paced host-wide together
with Harmonica (see ``ig_public_host``). When Instagram rate-limits this
server IP, the rest of the batch falls back to a small Apify profile run paid
from the Instagram share of the pool's daily credit.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone

import ig_public_host
from apify_pool import (SOURCE_COST_ESTIMATE_USD, budget_stretch, choose_token, pool_status,
                        record_run, round_budget_usd)
from chumei_lib import (ROOT, SeenState, append_inbox, load_env, now_iso,
                        read_sources_csv, save_avatar)
from fetch_facebook import apify_request, usage_usd
from fetch_instagram import PUBLIC_SCHEDULE_STATE, PublicWebClient
from ig_schedule import (adaptive_interval_hours, is_rate_limited, load_schedule,
                         mark_failure, mark_success, save_schedule, select_due)
from source_status import record_api_call, record_fetch


ACTOR_ID = "apify/instagram-profile-scraper"
RAW_SOURCE = "rsshub"  # Preserve the existing seen/inbox namespace across providers.
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
DIRECT_MAX_CONSECUTIVE_FAILURES = 3


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


def profile_unavailable(item: dict) -> str | None:
    """Why a profile actor item carries no readable posts, or None if it is usable.

    The actor answers a missing profile with an item like
    ``{"error": "not_found", "errorDescription": "Profile does not exist"}``.
    Treating that as an empty success hid renamed cohort accounts for weeks.
    An existing profile with zero posts is still a real (empty) success.
    """
    error = str(item.get("error") or "").strip()
    if error:
        description = str(item.get("errorDescription") or "").strip()
        if error == "not_found":
            return f"not_found: {description or 'Profile does not exist'}（帳號可能已改名或刪除）"
        if "restricted" in error.lower():
            return f"restricted: {error}（帳號受限，無法讀取貼文）"
        return f"{error}: {description}".rstrip(": ")
    if item.get("private") and not item.get("latestPosts"):
        return "private: 帳號已轉為私人，無法讀取貼文"
    return None


def wanted_daily_fetches(schedule: dict, metadata: dict) -> float:
    """Fetches per day the activity-based (unstretched) intervals ask for."""
    accounts = schedule.get("accounts") or {}
    total = 0.0
    for username in metadata:
        account = accounts.get(username) or {}
        hours = account.get("wanted_interval_hours") or account.get("interval_hours") or 168
        total += 24 / max(1.0, float(hours))
    return total


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
    env = load_env()
    client = PublicWebClient(env.get("CHUMEI_IG_PUBLIC_BASE", "https://www.instagram.com"),
                             env.get("CHUMEI_IG_PROFILE_POSTS_DOC_ID"))
    schedule.pop("direct_cooldown_until", None)  # superseded by the host-wide block
    direct_open = False
    consecutive_failures = 0
    direct_failed = set()
    for username in selected:
        if direct_open or not ig_public_host.wait_turn():
            direct_open = True
            fallback.append(username)
            continue
        try:
            avatar, posts = client.fetch(username, args.limit)
            resolved[username] = (avatar, posts, "Instagram public web")
            consecutive_failures = 0
        except Exception as exc:
            fallback.append(username)
            if not is_rate_limited(exc):
                direct_failed.add(username)
            consecutive_failures += 1
            print(f"@{username}: logged-out endpoint unavailable ({str(exc)[:80]})")
            if is_rate_limited(exc):
                ig_public_host.report_block("chumei")
                direct_open = True
            elif consecutive_failures >= DIRECT_MAX_CONSECUTIVE_FAILURES:
                # Repeated non-rate-limit failures point at the query itself
                # (for example a rotated doc id); stop spending requests on it.
                direct_open = True
    if direct_open:
        print(f"instagram public: direct path paused; {len(fallback)} accounts left for Apify")

    actor_run = None
    actor_label = None
    batch = []
    quota = None
    unavailable: dict[str, str] = {}
    if fallback:
        quota = pool_status(refresh=True)
        budget = round_budget_usd("instagram", quota)
        affordable = math.floor(budget / SOURCE_COST_ESTIMATE_USD["instagram"])
        batch = fallback[:affordable]
        if batch:
            try:
                actor_label, token, _ = choose_token(refresh=False)
                actor_run, items = run_actor(token, batch)
                for item in items:
                    username, avatar, posts = normalize_profile(item, args.limit)
                    if username not in metadata:
                        continue
                    problem = profile_unavailable(item)
                    if problem:
                        unavailable[username] = problem
                    else:
                        resolved[username] = (avatar, posts, "Apify Instagram")
            except RuntimeError as exc:
                print(f"Apify Instagram fallback failed: {exc}", file=sys.stderr)
        if len(batch) < len(fallback):
            print(f"Apify Instagram: {len(fallback) - len(batch)} accounts wait for the "
                  f"Instagram share of Apify credit (US${budget:.3f} this round)")

    # Paid fetches follow the Instagram share of the credit: when the activity-
    # based intervals ask for more than it pays for, all of them stretch alike.
    stretch = 1.0
    if any(result[2] == "Apify Instagram" for result in resolved.values()):
        quota = quota or pool_status(refresh=False)
        stretch = budget_stretch(quota, "instagram", daily_fetches=wanted_daily_fetches(schedule, metadata))
        if stretch > 1:
            print(f"Apify Instagram: intervals x{stretch:g} to fit the Instagram credit share")

    total = 0
    failures = 0
    for username in selected:
        if username in unavailable:
            failures += 1
            # A missing, private or restricted profile will not come back soon;
            # retry rarely so a renamed account does not keep spending credit.
            mark_failure(schedule, username, base_hours=72, cap_hours=336)
            record_fetch(f"instagram:{username}", backend="Apify Instagram", ok=False,
                         error=unavailable[username])
            print(f"@{username}: {unavailable[username]}")
            continue
        result = resolved.get(username)
        if not result:
            failures += 1
            tried = username in batch or username in direct_failed
            if tried:
                mark_failure(schedule, username, base_hours=12, cap_hours=72)
            # Accounts no provider could try stay due, so the next round takes them first.
            record_fetch(f"instagram:{username}", backend="Instagram public", ok=False,
                         error="no unauthenticated provider available within the Instagram Apify credit share")
            continue
        avatar, posts, backend = result
        total += ingest(username, avatar, posts, metadata[username], seen)
        wanted = adaptive_interval_hours([post.get("posted_at") for post in posts])
        interval = round(wanted * stretch, 1) if backend == "Apify Instagram" else wanted
        mark_success(schedule, username, interval_hours=interval, jitter_hours=3)
        schedule["accounts"].setdefault(username, {})["wanted_interval_hours"] = wanted
        record_fetch(f"instagram:{username}", backend=backend, ok=True, items=len(posts))
        record_api_call(backend, operation="instagram profile", ok=True)
        print(f"@{username}: {len(posts)} posts via {backend}; next ~{interval:g}h")
    seen.save()
    save_schedule(PUBLIC_SCHEDULE_STATE, schedule)
    if actor_run is not None and actor_label is not None:
        cost = usage_usd(actor_run)
        record_run(actor_label, consumer="instagram", cost_usd=cost, source_count=len(batch), ok=True)
        record_api_call("Apify", operation="instagram profile actor", source_count=len(batch),
                        request_count=0, ok=True, cost_usd=cost)
        print(f"Apify Instagram cost: {cost if cost is not None else 'unreported'}")
    print(f"instagram public: +{total}, failures={failures}/{len(selected)}")
    return 0 if failures < len(selected) else 1


if __name__ == "__main__":
    sys.exit(main())
