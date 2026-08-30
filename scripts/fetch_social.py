"""Threads / X fetcher：透過本機 RSSHub 抓公開貼文。

讀 data/sources/social_accounts.csv（platform = threads | x）。
與 fetch_instagram 同節制原則：每帳號 limit 5、帳號間 sleep；
帳號級滾動排程（--max-accounts 每輪一小批），單帳號間隔 ~20h。
"""

import argparse
import json
import random
import re
import sys
import time

import requests

from chumei_lib import SeenState, append_inbox, load_env, now_iso, read_sources_csv, ROOT
from fetch_instagram import rsshub_error, strip_html
from ig_schedule import load_schedule, mark_failure, mark_success, save_schedule, select_due
from source_status import record_api_call, record_fetch

RAW_SOURCE = "rsshub-social"
ERROR_LOG = ROOT / "state" / "seen" / "social_errors.jsonl"
SCHEDULE_STATE = ROOT / "state" / "social_schedule.json"

ROUTES = {
    "threads": "/threads/{u}",
    "x": "/twitter/user/{u}",
}

POST_ID_RES = {
    "threads": re.compile(r"/(?:post|t)/([\w-]+)"),
    "x": re.compile(r"/status/(\d+)"),
}


def parse_feed(xml_text, platform):
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    from datetime import timezone

    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        get = lambda tag: (item.findtext(tag) or "").strip()
        desc = get("description")
        images = re.findall(r'<img[^>]+src="([^"]+)"', desc)
        import html as _html
        images = [_html.unescape(u) for u in images]
        link = get("link")
        m = POST_ID_RES[platform].search(link)
        post_id = m.group(1) if m else (get("guid") or link)
        try:
            posted_at = parsedate_to_datetime(get("pubDate")).astimezone(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            posted_at = now_iso()
        yield {
            "post_id": post_id,
            "url": link,
            "posted_at": posted_at,
            "text": strip_html(desc) or get("title") or "（純圖片貼文，內容見海報）",
            "images": images,
        }


def log_error(platform, username, err):
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), "platform": platform, "username": username,
                            "error": str(err)[:300]}, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", help="逗號分隔 username")
    ap.add_argument("--platform", choices=["threads", "x"], help="只抓這個平台")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--sleep", type=float, default=8.0)
    ap.add_argument("--max-accounts", type=int, default=0,
                    help="這一輪最多抓幾個帳號（0=全部；配 launchd 每 3h 滾動）")
    ap.add_argument("--account-interval-hours", type=float, default=20,
                    help="同一帳號至少間隔幾小時再抓")
    args = ap.parse_args()

    env = load_env()
    base = env.get("CHUMEI_RSSHUB_BASE", "http://127.0.0.1:1200")
    rows = [r for r in read_sources_csv("social_accounts.csv")
            if r.get("active", "true").lower() not in ("false", "link") and r["platform"] in ROUTES]
    if args.platform:
        rows = [r for r in rows if r["platform"] == args.platform]
    if args.accounts:
        wanted = set(args.accounts.split(","))
        rows = [r for r in rows if r["username"] in wanted]

    schedule = load_schedule(SCHEDULE_STATE)
    if not args.accounts:
        by_key = {f"{r['platform']}:{r['username'].strip().lstrip('@')}": r for r in rows}
        due = select_due(list(by_key), schedule, args.max_accounts or len(by_key), now=time.time())
        rows = [by_key[key] for key in due]
        if not rows:
            print("social: no accounts due")
            return 0
        print(f"social schedule: {len(rows)}/{len(by_key)} accounts")

    seen = SeenState(RAW_SOURCE)
    total_new, failed = 0, 0
    for i, row in enumerate(rows):
        platform, username = row["platform"], row["username"].strip().lstrip("@")
        source_id = f"{platform}_{username}"
        schedule_key = f"{platform}:{username}"
        try:
            url = base + ROUTES[platform].format(u=username)
            resp = requests.get(url, params={"limit": args.limit}, timeout=90)
            error = rsshub_error(resp)
            if error:
                raise error
            resp.raise_for_status()
            if b"<rss" not in resp.content[:200]:
                raise RuntimeError(f"non-RSS response ({resp.status_code})")
            posts = list(parse_feed(resp.text, platform))[: args.limit]
            import html as _html
            m_av = re.search(r"<image><url>([^<]+)</url>", resp.text)
            if m_av:
                from chumei_lib import save_avatar
                save_avatar(f"{platform}_{username}", _html.unescape(m_av.group(1)))
            fresh = []
            for p in posts:
                if seen.has(source_id, p["post_id"]):
                    continue
                fresh.append({
                    "source_id": source_id,
                    "source_name": row.get("name") or username,
                    "platform": platform,
                    "raw_source": RAW_SOURCE,
                    "school": row.get("school") or "other",
                    "org_type": row.get("org_type") or "club",
                    "fetched_at": now_iso(),
                    **p,
                })
                seen.add(source_id, p["post_id"])
            n = append_inbox(RAW_SOURCE, fresh)
            seen.save()
            total_new += n
            record_api_call("RSSHub", operation=platform, ok=True)
            record_fetch(f"{platform}:{username}", backend="RSSHub", ok=True, items=len(posts))
            mark_success(schedule, schedule_key, interval_hours=args.account_interval_hours, jitter_hours=3)
            save_schedule(SCHEDULE_STATE, schedule)
            print(f"[{i+1}/{len(rows)}] {platform}/@{username}: +{n}")
        except Exception as e:
            failed += 1
            record_api_call("RSSHub", operation=platform, ok=False)
            record_fetch(f"{platform}:{username}", backend="RSSHub", ok=False, error=e)
            log_error(platform, username, e)
            mark_failure(schedule, schedule_key)
            save_schedule(SCHEDULE_STATE, schedule)
            print(f"[{i+1}/{len(rows)}] {platform}/@{username}: ERROR {str(e)[:100]}", file=sys.stderr)
        if i < len(rows) - 1:
            time.sleep(args.sleep + random.uniform(0, 3))

    print(f"done: {total_new} new items, {failed} failures / {len(rows)} accounts")
    return 0 if failed < max(1, len(rows) // 2) else 1


if __name__ == "__main__":
    sys.exit(main())
