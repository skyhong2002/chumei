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


def fetch_rsshub(base, username, limit):
    """回傳 (avatar_url, posts)。"""
    resp = requests.get(f"{base}/instagram/2/user/{username}", params={"limit": limit}, timeout=90)
    resp.raise_for_status()
    if b"<rss" not in resp.content[:200]:
        raise RuntimeError(f"non-RSS response ({resp.status_code})")
    m_av = re.search(r"<image><url>([^<]+)</url>", resp.text)
    return (html.unescape(m_av.group(1)) if m_av else None), list(parse_feed(resp.text))


_instaloader_session = None
USERID_CACHE = ROOT / "state" / "ig_userids.json"


def _instaloader_context():
    global _instaloader_session
    if _instaloader_session is None:
        from fetch_stories import load_session
        _instaloader_session = load_session()
    return _instaloader_session


def _resolve_userid(L, username):
    """userid 快取與 fetch_stories 共用；缺的用 topsearch 補，最後才退到 Profile（商業帳號會 400）。"""
    cache = json.loads(USERID_CACHE.read_text()) if USERID_CACHE.exists() else {}
    if cache.get(username):
        return cache[username]
    uid = None
    try:
        d = L.context.get_json("web/search/topsearch/", params={"query": username})
        hit = next((x["user"] for x in d.get("users", []) if x["user"]["username"].lower() == username.lower()), None)
        uid = int(hit["pk"]) if hit else None
    except Exception:
        pass
    if uid is None:
        import instaloader
        uid = instaloader.Profile.from_username(L.context, username).userid
    cache[username] = uid
    USERID_CACHE.parent.mkdir(parents=True, exist_ok=True)
    USERID_CACHE.write_text(json.dumps(cache))
    return uid


def _item_images(item, max_images=2):
    nodes = item.get("carousel_media") or [item]
    out = []
    for node in nodes[:max_images]:
        cands = (node.get("image_versions2") or {}).get("candidates") or []
        if cands:
            out.append(cands[0]["url"])
    return out


def fetch_instaloader(username, limit):
    """走 app 端點 api/v1/feed/user/<id>（同一組 cookie）；置頂貼文會排在前面，跳過後依時間取最新 limit 篇。

    不用 Profile.from_username：商業／專業帳號在 web_profile_info 會回
    「ig_business_category_subvertical has been deleted」400（instaloader 上游問題）。
    回傳 (avatar_url, posts)。
    """
    L = _instaloader_context()
    uid = _resolve_userid(L, username)
    data = L.context.get_iphone_json(f"api/v1/feed/user/{uid}/", {"count": limit + 4})
    items = [it for it in data.get("items", []) if it.get("code") and not it.get("timeline_pinned_user_ids")]
    items.sort(key=lambda it: it.get("taken_at") or 0, reverse=True)
    posts = []
    for it in items[:limit]:
        caption = ((it.get("caption") or {}).get("text") or "").strip()
        posts.append({
            "post_id": it["code"],
            "url": f"https://www.instagram.com/p/{it['code']}/",
            "posted_at": datetime.fromtimestamp(it.get("taken_at") or 0, timezone.utc).isoformat(timespec="seconds"),
            "text": caption or "（純圖片貼文，內容見海報）",
            "images": _item_images(it),
        })
    avatar = (data.get("user") or (items[0].get("user") if items else {}) or {}).get("profile_pic_url")
    return avatar, posts


def fetch_account(backend, base, username, limit):
    if backend == "rsshub":
        return fetch_rsshub(base, username, limit)
    if backend == "instaloader":
        return fetch_instaloader(username, limit)
    try:
        return fetch_rsshub(base, username, limit)
    except Exception as e:
        print(f"    rsshub failed ({str(e)[:60]}), falling back to instaloader", file=sys.stderr)
        return fetch_instaloader(username, limit)


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
    ap.add_argument("--backend", choices=["auto", "rsshub", "instaloader"],
                    help="預設讀 CHUMEI_IG_BACKEND，再預設 auto")
    ap.add_argument("--dry-run", action="store_true", help="只印出抓到的貼文，不寫 inbox／seen-state／頭貼")
    args = ap.parse_args()

    env = load_env()
    base = env.get("CHUMEI_RSSHUB_BASE", "http://127.0.0.1:1200")
    backend = args.backend or env.get("CHUMEI_IG_BACKEND", "auto")
    rows = [r for r in read_sources_csv("ig_accounts.csv") if r.get("active", "true").lower() not in ("false", "link")]
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
            avatar_url, posts = fetch_account(backend, base, username, args.limit)
            if args.dry_run:
                print(f"[{i+1}/{len(rows)}] @{username}: {len(posts)} posts"
                      + f"{' (avatar ok)' if avatar_url else ''}")
                for p in posts:
                    print(f"    {p['post_id']} {p['posted_at'][:10]} {'NEW' if not seen.has(source_id, p['post_id']) else 'seen'} "
                          f"{p['text'][:50].replace(chr(10), ' ')!r} img={len(p['images'])}")
                continue
            if avatar_url:
                from chumei_lib import save_avatar
                save_avatar(f"ig_{username}", avatar_url)
            fresh = []
            for p in posts:
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
