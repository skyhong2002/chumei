"""IG 限時動態 fetcher：instaloader ＋ bamboo-rsshub 的 IG session cookie。

- userid 解析走 topsearch（快取 state/ig_userids.json，每輪最多解析 --resolve-limit 個）。
- get_stories 每輪只查一批最多 48 個 userid，launchd 跨輪輪替。
- 媒體立即下載到 site/assets/stories/（IG CDN 連結很快過期），縮到 720px。
- 限動 24 小時過期：輸出 site/data/stories.json 只含未過期項目；過期 48h 後刪媒體。
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from chumei_lib import load_env, now_iso, read_sources_csv, ROOT, TZ_TAIPEI
from ig_schedule import (clear_global_rate_limit, is_rate_limited, load_schedule,
                         mark_failure, mark_success, save_schedule, select_due,
                         set_global_rate_limit)
from source_status import record_api_call, record_fetch

USERID_CACHE = ROOT / "state" / "ig_userids.json"
STORIES_STATE = ROOT / "state" / "stories.json"
MEDIA_DIR = ROOT / "site" / "assets" / "stories"
OUT = ROOT / "site" / "data" / "stories.json"
SCHEDULE_STATE = ROOT / "state" / "instagram_stories_schedule.json"
STORY_DISPLAY_HOURS = 48
STORY_MEDIA_GRACE_HOURS = 24


def load_session():
    import instaloader
    cookie = subprocess.run(["docker", "exec", "bamboo-rsshub", "printenv", "IG_COOKIE"],
                            capture_output=True, text=True).stdout.strip()
    kv = dict(re.findall(r"(\w+)=([^;]+)", cookie))
    if "sessionid" not in kv:
        raise RuntimeError("IG_COOKIE 裡沒有 sessionid（bamboo-rsshub 容器沒跑？）")
    # Application-level scheduling owns long retries.  Do not multiply a
    # denied request into three immediate attempts inside Instaloader.
    L = instaloader.Instaloader(quiet=True, max_connection_attempts=1,
                               request_timeout=45, fatal_status_codes=[401, 429])
    L.load_session(kv.get("ds_user_id", "ig"), {k: kv[k] for k in ("sessionid", "csrftoken", "ds_user_id", "mid") if k in kv})
    return L


def resolve_userids(L, rows, limit):
    cache = json.loads(USERID_CACHE.read_text()) if USERID_CACHE.exists() else {}
    resolved = 0
    for r in rows:
        u = r["username"].strip().lstrip("@")
        if u in cache or resolved >= limit:
            continue
        try:
            d = L.context.get_json("web/search/topsearch/", params={"query": u})
            hit = next((x["user"] for x in d.get("users", []) if x["user"]["username"].lower() == u.lower()), None)
            cache[u] = int(hit["pk"]) if hit else None  # None = 找不到，別再重查
            print(f"  resolve @{u} -> {cache[u]}")
        except Exception as e:
            print(f"  resolve @{u} FAIL {str(e)[:80]}", file=sys.stderr)
        resolved += 1
        time.sleep(3)
    USERID_CACHE.parent.mkdir(parents=True, exist_ok=True)
    USERID_CACHE.write_text(json.dumps(cache))
    return cache


def save_media(item):
    """下載限動縮圖（影片也存縮圖）→ 720px JPEG。回傳相對路徑或 None。"""
    import io
    from PIL import Image
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    dest = MEDIA_DIR / f"{item.mediaid}.jpg"
    if dest.exists():
        return f"/assets/stories/{item.mediaid}.jpg"
    try:
        r = requests.get(item.url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((720, 1280))
        im.save(dest, "JPEG", quality=82)
        return f"/assets/stories/{item.mediaid}.jpg"
    except Exception as e:
        print(f"  media fail {item.mediaid}: {str(e)[:80]}", file=sys.stderr)
        return None


def story_lifecycle(taken_at, now):
    """Return (live|archived|expired, display expiry) for a saved story."""
    taken = datetime.fromisoformat(taken_at)
    expires = taken + timedelta(hours=STORY_DISPLAY_HOURS)
    if expires > now:
        return "live", expires
    if expires < now - timedelta(hours=STORY_MEDIA_GRACE_HOURS):
        return "expired", expires
    return "archived", expires


def refresh_story_output(state=None, now=None):
    """Migrate expiry, prune media, and regenerate the public story payload."""
    state = (json.loads(STORIES_STATE.read_text()) if STORIES_STATE.exists() else {}) if state is None else state
    now = datetime.now(timezone.utc) if now is None else now
    live, expired = {}, []
    for key, story in state.items():
        lifecycle, expires = story_lifecycle(story["taken_at"], now)
        # This also migrates items saved with the former 24-hour display time.
        story["expires_at"] = expires.isoformat(timespec="seconds")
        if lifecycle == "live":
            live[key] = story
        elif lifecycle == "expired":
            expired.append(key)
    for key in expired:
        media = state[key].get("media")
        if media:
            (ROOT / "site" / media.lstrip("/")).unlink(missing_ok=True)
        state.pop(key)

    STORIES_STATE.parent.mkdir(parents=True, exist_ok=True)
    STORIES_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0))
    from chumei_lib import AVATAR_DIR
    for story in live.values():
        if not story.get("avatar"):
            candidate = AVATAR_DIR / f"ig_{story['username']}.jpg"
            if candidate.exists():
                story["avatar"] = f"/assets/avatars/ig_{story['username']}.jpg"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": now_iso(),
        "stories": sorted(live.values(), key=lambda story: story["taken_at"], reverse=True),
    }, ensure_ascii=False))
    return len(live), len(expired), state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolve-limit", type=int, default=15, help="這一輪最多解析幾個新 userid")
    ap.add_argument("--batch-size", type=int, default=48, help="每輪最多查幾個帳號（IG 單次最多 50）")
    ap.add_argument("--accounts", help="逗號分隔，只查這些 username")
    ap.add_argument("--account-interval-hours", type=float, default=18,
                    help="同一帳號至少間隔幾小時再查")
    ap.add_argument("--force", action="store_true", help="忽略帳號排程與全域冷卻，僅供人工診斷")
    ap.add_argument("--check", action="store_true", help="只驗證 session")
    args = ap.parse_args()

    if not 1 <= args.batch_size <= 50:
        ap.error("batch-size must be between 1 and 50")

    schedule = load_schedule(SCHEDULE_STATE)
    now_ts = time.time()
    cooldown = schedule.get("global_cooldown_until", 0)
    if cooldown > now_ts and not (args.force or args.check):
        live_count, expired_count, _ = refresh_story_output()
        print(f"stories: cooling down until {datetime.fromtimestamp(cooldown, TZ_TAIPEI).isoformat(timespec='minutes')}")
        print(f"stories output: {live_count} visible, pruned {expired_count}")
        return 0

    L = load_session()
    try:
        me = L.test_login()
    except Exception as e:
        me = None
        print(f"session check failed: {str(e)[:120]}", file=sys.stderr)
    if not me:
        print("session invalid: Instagram web login is not authenticated", file=sys.stderr)
        if args.check:
            return 1
        until = set_global_rate_limit(schedule)
        save_schedule(SCHEDULE_STATE, schedule)
        refresh_story_output()
        print(f"stories: global cooldown until {datetime.fromtimestamp(until, TZ_TAIPEI).isoformat(timespec='minutes')}",
              file=sys.stderr)
        return 1
    print(f"session ok (@{me})")
    if args.check:
        return 0

    rows = [r for r in read_sources_csv("ig_accounts.csv") if r.get("active", "true").lower() not in ("false", "link")]
    if args.accounts:
        wanted = {value.strip().lstrip("@") for value in args.accounts.split(",") if value.strip()}
        rows = [r for r in rows if r["username"].strip().lstrip("@") in wanted]
    meta = {r["username"].strip().lstrip("@"): r for r in rows}
    selected = (list(meta)[:args.batch_size] if args.accounts else
                select_due(list(meta), schedule, args.batch_size, now=now_ts, force=args.force))
    if not selected:
        live_count, expired_count, _ = refresh_story_output()
        print("stories: no accounts due")
        print(f"stories output: {live_count} visible, pruned {expired_count}")
        return 0
    selected_rows = [meta[u] for u in selected]
    print(f"stories batch: {len(selected)}/{len(rows)} accounts")
    cache = resolve_userids(L, selected_rows, args.resolve_limit)
    userids = [cache[u] for u in selected if cache.get(u)]
    unresolved = [u for u in selected if not cache.get(u)]
    for username in unresolved:
        mark_failure(schedule, username, base_hours=24, cap_hours=168, jitter_hours=6)
        record_fetch(f"story:{username}", backend="Instaloader", ok=False, error="Instagram userid unresolved")
    if not userids:
        print("no userids resolved yet")
        save_schedule(SCHEDULE_STATE, schedule)
        return 1

    state = json.loads(STORIES_STATE.read_text()) if STORIES_STATE.exists() else {}
    now = datetime.now(timezone.utc)
    n_new = 0
    try:
        for story in L.get_stories(userids=userids):
            try:
                username = story.owner_username
                row = meta.get(username, {})
                items = list(story.get_items())
            except Exception as e:  # 單一帳號的 reel 資料異常（過期/API 不一致）不影響整輪
                print(f"  story fetch fail (owner {getattr(story, 'owner_id', '?')}): {str(e)[:80]}", file=sys.stderr)
                continue
            for item in items:
                key = str(item.mediaid)
                if key in state:
                    continue
                media = save_media(item)
                if not media:
                    continue
                taken = item.date_utc.replace(tzinfo=timezone.utc)
                from chumei_lib import AVATAR_DIR
                av = f"/assets/avatars/ig_{username}.jpg" if (AVATAR_DIR / f"ig_{username}.jpg").exists() else None
                state[key] = {
                    "username": username,
                    "avatar": av,
                    "name": row.get("name") or username,
                    "school": row.get("school") or "other",
                    "taken_at": taken.isoformat(timespec="seconds"),
                    "expires_at": (taken + timedelta(hours=STORY_DISPLAY_HOURS)).isoformat(timespec="seconds"),
                    "is_video": item.is_video,
                    "media": media,
                    "ig_url": f"https://www.instagram.com/stories/{username}/{item.mediaid}/",
                }
                n_new += 1
    except Exception as e:
        record_api_call("Instaloader", operation="instagram stories", source_count=len(userids), ok=False)
        for username in selected:
            record_fetch(f"story:{username}", backend="Instaloader", ok=False, error=e)
        until = set_global_rate_limit(schedule)
        save_schedule(SCHEDULE_STATE, schedule)
        reason = "rate-limited" if is_rate_limited(e) else "batch failed"
        print(f"stories {reason}; stopped batch, cooldown until "
              f"{datetime.fromtimestamp(until, TZ_TAIPEI).isoformat(timespec='minutes')}", file=sys.stderr)
        refresh_story_output(state)
        raise

    for username in selected:
        if not cache.get(username):
            continue
        mark_success(schedule, username, interval_hours=args.account_interval_hours, jitter_hours=3)
        record_fetch(f"story:{username}", backend="Instaloader", ok=True)
    record_api_call("Instaloader", operation="instagram stories", source_count=len(userids), ok=True)
    clear_global_rate_limit(schedule)
    save_schedule(SCHEDULE_STATE, schedule)

    live_count, expired_count, _ = refresh_story_output(state, now)
    print(f"stories: +{n_new} new, {live_count} visible, pruned {expired_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
