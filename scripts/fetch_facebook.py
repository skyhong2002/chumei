#!/usr/bin/env python3
"""Fetch recent public Facebook page posts through one batched Apify actor run."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

from chumei_lib import SeenState, append_inbox, load_env, now_iso, read_sources_csv


ACTOR_ID = "apify/facebook-posts-scraper"
APIFY_BASE = "https://api.apify.com/v2"
RAW_SOURCE = "apify"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
FALLBACK_TEXT = "（純圖片貼文，內容見海報）"


def page_url(page: str) -> str:
    page = page.strip()
    if page.startswith(("http://", "https://")):
        return page
    return f"https://www.facebook.com/{page.strip('/')}/"


def page_slug(page: str) -> str:
    value = page.strip()
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if parts and parts[0].lower() == "profile.php":
            value = parse_qs(parsed.query).get("id", [""])[0]  # profile.php?id=N → N
        elif parts and parts[0].lower() == "groups" and len(parts) > 1:
            value = "groups-" + parts[1]  # FB 社團：保留識別名，避免所有 group 撞在 fb_groups
        elif parts and parts[0].lower() in {"people", "p", "pages"} and len(parts) > 1:
            value = parts[-1]
        elif parts:
            value = parts[0]
        else:
            value = parse_qs(parsed.query).get("id", [""])[0]
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip("/@ "))
    return value.lower().strip("_") or "facebook_page"


def parse_time(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return now_iso()
    if raw.isdigit():
        stamp = int(raw)
        if stamp > 10_000_000_000:
            stamp //= 1000
        return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = parsedate_to_datetime(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat(timespec="seconds")


def first(item: dict, names: tuple[str, ...]):
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return ""


def post_url(item: dict) -> str:
    return str(first(item, ("url", "postUrl", "facebookUrl", "permalink", "link", "topLevelUrl"))).strip()


def post_id(item: dict, url: str) -> str:
    direct = str(first(item, ("postId", "id", "post_id", "legacyId", "shortCode"))).strip()
    if direct:
        return direct
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("fbid", [""])[0]
    if query_id:
        return query_id
    match = re.search(r"/(?:posts|reels?|videos)/([^/?#]+)", parsed.path)
    return match.group(1) if match else url


def image_urls(value) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        if value.startswith(("http://", "https://")) and (
            "fbcdn.net" in value or re.search(r"\.(?:jpe?g|png|webp|gif)(?:[?#]|$)", value, re.I)
        ):
            found.append(value)
    elif isinstance(value, list):
        for child in value:
            found.extend(image_urls(child))
    elif isinstance(value, dict):
        for key in ("image", "imageUrl", "image_url", "url", "thumbnail", "thumbnailUrl", "displayUrl", "mediaUrl"):
            found.extend(image_urls(value.get(key)))
        for key in ("attachments", "media", "images", "photos"):
            found.extend(image_urls(value.get(key)))
    return list(dict.fromkeys(found))


def source_for(item: dict, sources: list[dict]) -> dict | None:
    searchable = json.dumps(item, ensure_ascii=False).casefold()
    for source in sources:
        if page_slug(source["page"]).casefold() in searchable:
            return source
    for source in sources:
        name = (source.get("name") or "").strip().casefold()
        if name and name in searchable:
            return source
    return sources[0] if len(sources) == 1 else None


def normalize(item: dict, source: dict) -> dict:
    url = post_url(item)
    pid = post_id(item, url)
    if not url or not pid:
        raise ValueError("actor item has no Facebook post URL/id")
    text = str(first(item, ("text", "message", "caption", "content", "description", "title"))).strip()
    images = image_urls(item)
    return {
        "source_id": f"fb_{page_slug(source['page'])}",
        "source_name": source.get("name") or page_slug(source["page"]),
        "platform": "facebook",
        "raw_source": RAW_SOURCE,
        "school": source.get("school") or "external",
        "org_type": source.get("org_type") or "external",
        "post_id": pid,
        "url": url,
        "posted_at": parse_time(first(item, ("time", "timestamp", "date", "createdAt", "created_time", "publishedAt"))),
        "text": text or FALLBACK_TEXT,
        "images": images,
        "image_url": images[0] if images else None,
        "fetched_at": now_iso(),
    }


def apify_request(method: str, path: str, token: str, *, params=None, body=None, timeout=60):
    try:
        response = requests.request(
            method,
            APIFY_BASE + path,
            params=params,
            json=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "ChumeiFacebookFetcher/1.0",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Apify request failed ({type(exc).__name__})") from exc
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Apify HTTP {response.status_code}: {response.text[:1000]}") from exc
    return response.json() if response.content else {}


def run_actor(token: str, sources: list[dict], limit: int) -> tuple[dict, list[dict]]:
    actor_api_id = ACTOR_ID.replace("/", "~")
    run = apify_request(
        "POST",
        f"/acts/{actor_api_id}/runs",
        token,
        params={"maxItems": max(1, len(sources) * limit), "memory": 1024, "timeout": 300, "restartOnError": "false"},
        body={"startUrls": [{"url": page_url(source["page"])} for source in sources], "resultsLimit": limit, "captionText": False},
    ).get("data", {})
    run_id = run.get("id")
    if not run_id:
        raise RuntimeError(f"Apify did not return a run id: {run}")

    deadline = time.monotonic() + 345
    while run.get("status") not in TERMINAL_STATUSES:
        if time.monotonic() > deadline:
            raise RuntimeError(f"timed out waiting for Apify run {run_id}; status={run.get('status')}")
        time.sleep(3)
        run = apify_request("GET", f"/actor-runs/{run_id}", token, timeout=30).get("data", {})

    if run.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Apify run {run_id} ended with {run.get('status')}: {run.get('statusMessage', '')}")
    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError(f"Apify run {run_id} returned no dataset")
    items = apify_request(
        "GET", f"/datasets/{dataset_id}/items", token,
        params={"format": "json", "clean": "true", "limit": max(1, len(sources) * limit)},
    )
    return run, items if isinstance(items, list) else []


def usage_usd(run: dict):
    for value in (run.get("usageTotalUsd"), run.get("usageUsd"), run.get("costUsd"), (run.get("usage") or {}).get("totalUsd")):
        if isinstance(value, (int, float)):
            return float(value)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", help="comma-separated page usernames or Facebook URLs")
    parser.add_argument("--limit", type=int, default=5, help="latest posts per page (default: 5)")
    parser.add_argument("--max-pages-per-run", type=int, default=0, help="maximum pages in this batch (0 = all)")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    sources = [row for row in read_sources_csv("fb_pages.csv") if row.get("active", "true").strip().lower() != "false"]
    if args.pages:
        wanted = {page_slug(value) for value in args.pages.split(",") if value.strip()}
        sources = [row for row in sources if page_slug(row.get("page", "")) in wanted]
    if args.max_pages_per_run > 0:
        sources = sources[:args.max_pages_per_run]
    if not sources:
        print("no active Facebook pages selected", file=sys.stderr)
        return 1

    token = load_env().get("APIFY_TOKEN", "").strip()
    if not token:
        print("APIFY_TOKEN is missing from .env/environment", file=sys.stderr)
        return 1

    try:
        run, raw_items = run_actor(token, sources, args.limit)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    seen = SeenState(RAW_SOURCE)
    fresh = []
    actor_errors = 0
    unmatched = 0
    for raw in raw_items:
        if raw.get("error") and not post_url(raw):
            actor_errors += 1
            continue
        source = source_for(raw, sources)
        if source is None:
            unmatched += 1
            continue
        try:
            item = normalize(raw, source)
        except (TypeError, ValueError):
            actor_errors += 1
            continue
        if seen.has(item["source_id"], item["post_id"]):
            continue
        fresh.append(item)
        seen.add(item["source_id"], item["post_id"])

    written = append_inbox(RAW_SOURCE, fresh)
    seen.save()
    cost = usage_usd(run)
    cost_text = f"${cost:.6f}" if cost is not None else "not reported"
    print(
        f"done: {written} new items from {len(sources)} pages; "
        f"dataset={len(raw_items)}, actor_errors={actor_errors}, unmatched={unmatched}, "
        f"run_id={run.get('id')}, usage={cost_text}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
