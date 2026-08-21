"""IG fetcher：透過本機 RSSHub 的 /instagram/2/user/:username route 抓公開貼文。

節制原則：每帳號 limit 5、帳號間 sleep、一天跑一輪就好（IG cookie 帳號的額度是共用資源）。
"""

import argparse
import html
import json
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from chumei_lib import SeenState, append_inbox, load_env, now_iso, read_sources_csv, ROOT

RAW_SOURCE = "rsshub"
ERROR_LOG = ROOT / "state" / "seen" / "instagram_errors.jsonl"


def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        get = lambda tag: (item.findtext(tag) or "").strip()
        desc = get("description")
        images = [html.unescape(u) for u in re.findall(r'<img[^>]+src="([^"]+)"', desc)]
        link = get("link")
        m = re.search(r"instagram\.com/(?:p|reel|tv)/([\w-]+)", link)
        post_id = m.group(1) if m else link
        pub = get("pubDate")
        try:
            posted_at = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            posted_at = now_iso()
        yield {
            "post_id": post_id,
            "url": link,
            "posted_at": posted_at,
            "text": strip_html(desc) or get("title") or "（純圖片貼文，內容見海報）",
            "images": images,
        }


def log_error(username, err):
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), "username": username, "error": str(err)[:300]}, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", help="逗號分隔，只抓這些 username")
    ap.add_argument("--limit", type=int, default=5, help="每帳號抓最新幾篇")
    ap.add_argument("--sleep", type=float, default=8.0, help="帳號間隔秒數")
    ap.add_argument("--max-accounts", type=int, default=0, help="這一輪最多處理幾個帳號（0=全部）")
    args = ap.parse_args()

    env = load_env()
    base = env.get("CHUMEI_RSSHUB_BASE", "http://127.0.0.1:1200")
    rows = [r for r in read_sources_csv("ig_accounts.csv") if r.get("active", "true").lower() != "false"]
    if args.accounts:
        wanted = set(args.accounts.split(","))
        rows = [r for r in rows if r["username"] in wanted]
    if args.max_accounts:
        rows = rows[: args.max_accounts]

    seen = SeenState(RAW_SOURCE)
    total_new, failed = 0, 0
    for i, row in enumerate(rows):
        username = row["username"].strip().lstrip("@")
        source_id = f"ig_{username}"
        try:
            resp = requests.get(f"{base}/instagram/2/user/{username}", params={"limit": args.limit}, timeout=90)
            resp.raise_for_status()
            if b"<rss" not in resp.content[:200]:
                raise RuntimeError(f"non-RSS response ({resp.status_code})")
            m_av = re.search(r"<image><url>([^<]+)</url>", resp.text)
            if m_av:
                from chumei_lib import save_avatar
                save_avatar(f"ig_{username}", html.unescape(m_av.group(1)))
            fresh = []
            for p in parse_feed(resp.text):
                if seen.has(source_id, p["post_id"]):
                    continue
                fresh.append({
                    "source_id": source_id,
                    "source_name": row.get("name") or username,
                    "platform": "instagram",
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
            print(f"[{i+1}/{len(rows)}] @{username}: +{n}")
        except Exception as e:
            failed += 1
            log_error(username, e)
            print(f"[{i+1}/{len(rows)}] @{username}: ERROR {str(e)[:120]}", file=sys.stderr)
        if i < len(rows) - 1:
            time.sleep(args.sleep + random.uniform(0, 3))

    print(f"done: {total_new} new items, {failed} failures / {len(rows)} accounts")
    return 0 if failed < max(1, len(rows) // 2) else 1


if __name__ == "__main__":
    sys.exit(main())
