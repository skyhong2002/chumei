"""IG fetcher：透過 RSSHub／Instaloader 抓公開貼文。

節制原則：持久化帳號排程、小批次、隨機等待與指數退避（IG cookie 額度是共用資源）。
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

from chumei_lib import (SeenState, TZ_TAIPEI, append_inbox, load_env, now_iso,
                        read_sources_csv, ROOT)
from ig_schedule import (clear_global_rate_limit, is_rate_limited, load_schedule,
                         mark_failure, mark_success, save_schedule, select_due,
                         set_global_rate_limit)
from source_status import record_api_call, record_fetch

RAW_SOURCE = "rsshub"
ERROR_LOG = ROOT / "state" / "seen" / "instagram_errors.jsonl"
SCHEDULE_STATE = ROOT / "state" / "instagram_profile_schedule.json"


def strip_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def rsshub_error(response):
    """Turn RSSHub's HTML error page into a useful, stable exception."""
    if response.status_code < 400:
        return None
    match = re.search(
        r"Error Message:\s*<br\s*/?>\s*<code[^>]*>(.*?)</code>",
        response.text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    detail = strip_html(match.group(1)) if match else ""
    if detail:
        return RuntimeError(f"RSSHub: {detail} (HTTP {response.status_code})")
    return requests.HTTPError(
        f"RSSHub HTTP {response.status_code} for {response.url}", response=response
    )


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
    resp = requests.get(f"{base}/instagram/2/user/{username}", params={"limit": limit,
                        }, timeout=(10, 45))
    error = rsshub_error(resp)
    if error:
        raise error
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


class AutoBackend:
    """Per-run RSSHub circuit breaker with Instaloader fallback."""

    def __init__(self, base):
        self.base = base
        self.rsshub_open = False
        self.last_attempts = []

    def fetch(self, username, limit):
        self.last_attempts = []
        if not self.rsshub_open:
            try:
                result = fetch_rsshub(self.base, username, limit)
                self.last_attempts.append(("RSSHub", True))
                return result
            except Exception as e:
                self.last_attempts.append(("RSSHub", False))
                # A failed shared route is unlikely to recover for the next
                # account seconds later. Probe again on the next launchd run.
                self.rsshub_open = True
                print(f"    rsshub unavailable ({str(e)[:60]}); circuit open for this batch",
                      file=sys.stderr)
        try:
            result = fetch_instaloader(username, limit)
        except Exception:
            self.last_attempts.append(("Instaloader", False))
            raise
        self.last_attempts.append(("Instaloader", True))
        return result


def log_error(username, err):
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), "username": username, "error": str(err)[:300]}, ensure_ascii=False) + "\n")


# 節流基準（2026-09-02）：IG 對抓取帳號發出 scraping_warning。當時 24h／4 批 ≈ 每天
# 324 次 profile 請求，而 RSSHub 每次都會 POST 一次 ig_sso_users 重新驗證 session，
# 正是被判定為自動化的模式。48h／2 批把量砍半（≈160 次/日），代價是新貼文的發現
# 從「1 天內」變「2 天內」。要調快之前先想清楚：IG 下一次不是警告，是停用。
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", help="逗號分隔，只抓這些 username")
    ap.add_argument("--limit", type=int, default=5, help="每帳號抓最新幾篇")
    ap.add_argument("--sleep", type=float, help="相容舊參數：固定帳號間隔秒數")
    ap.add_argument("--sleep-min", type=float, default=25, help="帳號間最短等待秒數")
    ap.add_argument("--sleep-max", type=float, default=45, help="帳號間最長等待秒數")
    ap.add_argument("--batch-size", type=int, default=10, help="每小批帳號數")
    ap.add_argument("--batches", type=int, default=2, help="每輪最多跑幾個小批")
    ap.add_argument("--batch-buffer-min", type=float, default=300, help="小批間最短緩衝秒數")
    ap.add_argument("--batch-buffer-max", type=float, default=480, help="小批間最長緩衝秒數")
    ap.add_argument("--account-interval-hours", type=float, default=48,
                    help="同一帳號成功後至少間隔幾小時再抓")
    ap.add_argument("--max-accounts", type=int, default=0,
                    help="覆寫這一輪帳號上限（0=使用 batch-size × batches）")
    ap.add_argument("--backend", choices=["auto", "rsshub", "instaloader"],
                    help="預設讀 CHUMEI_IG_BACKEND，再預設 auto")
    ap.add_argument("--force", action="store_true", help="忽略帳號排程與全域冷卻，僅供人工診斷")
    ap.add_argument("--dry-run", action="store_true", help="只印出抓到的貼文，不寫 inbox／seen-state／頭貼")
    args = ap.parse_args()

    if args.batch_size < 1 or args.batches < 1:
        ap.error("batch-size and batches must be positive")
    if min(args.sleep_min, args.sleep_max, args.batch_buffer_min, args.batch_buffer_max) < 0:
        ap.error("sleep and batch buffer values must not be negative")
    if args.sleep is not None and args.sleep < 0:
        ap.error("sleep must not be negative")

    env = load_env()
    base = env.get("CHUMEI_RSSHUB_BASE", "http://127.0.0.1:1200")
    backend = args.backend or env.get("CHUMEI_IG_BACKEND", "auto")
    if backend not in {"auto", "rsshub", "instaloader"}:
        ap.error(f"invalid CHUMEI_IG_BACKEND: {backend}")
    rows = [r for r in read_sources_csv("ig_accounts.csv") if r.get("active", "true").lower() not in ("false", "link")]
    if args.accounts:
        wanted = set(args.accounts.split(","))
        rows = [r for r in rows if r["username"] in wanted]
    row_by_username = {r["username"].strip().lstrip("@"): r for r in rows}
    schedule = load_schedule(SCHEDULE_STATE)
    now_ts = time.time()
    cooldown = schedule.get("global_cooldown_until", 0)
    if cooldown > now_ts and not args.force:
        print(f"instagram: cooling down until {datetime.fromtimestamp(cooldown, TZ_TAIPEI).isoformat(timespec='minutes')}")
        return 0
    maximum = args.max_accounts or args.batch_size * args.batches
    selected = (list(row_by_username) if args.accounts else
                select_due(list(row_by_username), schedule, maximum, now=now_ts, force=args.force))
    if args.max_accounts:
        selected = selected[:args.max_accounts]
    rows = [row_by_username[u] for u in selected]
    if not rows:
        print("instagram: no accounts due")
        return 0

    if args.sleep is not None:
        args.sleep_min = args.sleep_max = args.sleep
    if args.sleep_min > args.sleep_max or args.batch_buffer_min > args.batch_buffer_max:
        ap.error("sleep/batch buffer minimum must not exceed maximum")
    print(f"instagram schedule: {len(rows)}/{len(row_by_username)} accounts, "
          f"{args.batch_size} per batch, account wait {args.sleep_min:g}-{args.sleep_max:g}s, "
          f"batch buffer {args.batch_buffer_min:g}-{args.batch_buffer_max:g}s")

    seen = SeenState(RAW_SOURCE)
    total_new, failed = 0, 0
    auto_backend = AutoBackend(base) if backend == "auto" else None
    for i, row in enumerate(rows):
        if i and i % args.batch_size == 0:
            wait = random.uniform(args.batch_buffer_min, args.batch_buffer_max)
            print(f"batch buffer: {wait:.0f}s", flush=True)
            time.sleep(wait)
        username = row["username"].strip().lstrip("@")
        source_id = f"ig_{username}"
        source_key = f"instagram:{username}"
        attempt_backend = backend
        try:
            if auto_backend:
                avatar_url, posts = auto_backend.fetch(username, args.limit)
                attempt_backend = auto_backend.last_attempts[-1][0] if auto_backend.last_attempts else "auto"
            else:
                avatar_url, posts = fetch_account(backend, base, username, args.limit)
                attempt_backend = "RSSHub" if backend == "rsshub" else "Instaloader"
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
            mark_success(schedule, username, interval_hours=args.account_interval_hours,
                         jitter_hours=3)
            clear_global_rate_limit(schedule)
            save_schedule(SCHEDULE_STATE, schedule)
            attempts = auto_backend.last_attempts if auto_backend else [(attempt_backend, True)]
            for service, ok in attempts:
                record_api_call(service, operation="instagram profile", ok=ok)
            record_fetch(source_key, backend=attempt_backend, ok=True, items=len(posts))
            print(f"[{i+1}/{len(rows)}] @{username}: +{n}")
        except Exception as e:
            failed += 1
            if not args.dry_run:
                if auto_backend:
                    for service, ok in auto_backend.last_attempts:
                        record_api_call(service, operation="instagram profile", ok=ok)
                    attempt_backend = auto_backend.last_attempts[-1][0] if auto_backend.last_attempts else "auto"
                else:
                    attempt_backend = "RSSHub" if backend == "rsshub" else "Instaloader"
                    record_api_call(attempt_backend, operation="instagram profile", ok=False)
                record_fetch(source_key, backend=attempt_backend, ok=False, error=e)
                log_error(username, e)
                mark_failure(schedule, username)
            print(f"[{i+1}/{len(rows)}] @{username}: ERROR {str(e)[:120]}", file=sys.stderr)
            if is_rate_limited(e):
                if not args.dry_run:
                    until = set_global_rate_limit(schedule)
                    save_schedule(SCHEDULE_STATE, schedule)
                    until_text = datetime.fromtimestamp(until, TZ_TAIPEI).isoformat(timespec="minutes")
                    print(f"instagram rate-limited; stopping batch, cooldown until {until_text}",
                          file=sys.stderr)
                return 1
            if not args.dry_run:
                save_schedule(SCHEDULE_STATE, schedule)
        if i < len(rows) - 1:
            time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    print(f"done: {total_new} new items, {failed} failures / {len(rows)} accounts")
    return 0 if failed < max(1, len(rows) // 2) else 1


if __name__ == "__main__":
    sys.exit(main())
