"""IG 限時動態 fetcher：instaloader ＋ bamboo-rsshub 的 IG session cookie。

- userid 解析走 topsearch（快取 state/ig_userids.json，每輪最多解析 --resolve-limit 個）。
- get_stories 批量查詢所有 userid（instaloader 內部分批），一輪只花個位數請求。
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

USERID_CACHE = ROOT / "state" / "ig_userids.json"
STORIES_STATE = ROOT / "state" / "stories.json"
MEDIA_DIR = ROOT / "site" / "assets" / "stories"
OUT = ROOT / "site" / "data" / "stories.json"


def load_session():
    import instaloader
    cookie = subprocess.run(["docker", "exec", "bamboo-rsshub", "printenv", "IG_COOKIE"],
                            capture_output=True, text=True).stdout.strip()
    kv = dict(re.findall(r"(\w+)=([^;]+)", cookie))
    if "sessionid" not in kv:
        raise RuntimeError("IG_COOKIE 裡沒有 sessionid（bamboo-rsshub 容器沒跑？）")
    L = instaloader.Instaloader(quiet=True)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolve-limit", type=int, default=15, help="這一輪最多解析幾個新 userid")
    ap.add_argument("--check", action="store_true", help="只驗證 session")
    args = ap.parse_args()

    L = load_session()
    me = L.test_login()
    print(f"session ok (@{me})")
    if args.check:
        return 0

    rows = [r for r in read_sources_csv("ig_accounts.csv") if r.get("active", "true").lower() != "false"]
    meta = {r["username"].strip().lstrip("@"): r for r in rows}
    cache = resolve_userids(L, rows, args.resolve_limit)
    uid_to_name = {v: k for k, v in cache.items() if v}
    userids = list(uid_to_name)
    if not userids:
        print("no userids resolved yet")
        return 0

    state = json.loads(STORIES_STATE.read_text()) if STORIES_STATE.exists() else {}
    now = datetime.now(timezone.utc)
    n_new = 0
    for story in L.get_stories(userids=userids):
        username = story.owner_username
        row = meta.get(username, {})
        for item in story.get_items():
            key = str(item.mediaid)
            if key in state:
                continue
            media = save_media(item)
            if not media:
                continue
            taken = item.date_utc.replace(tzinfo=timezone.utc)
            state[key] = {
                "username": username,
                "name": row.get("name") or username,
                "school": row.get("school") or "other",
                "taken_at": taken.isoformat(timespec="seconds"),
                "expires_at": (taken + timedelta(hours=24)).isoformat(timespec="seconds"),
                "is_video": item.is_video,
                "media": media,
                "ig_url": f"https://www.instagram.com/stories/{username}/{item.mediaid}/",
            }
            n_new += 1

    # 過期清理：顯示期 24h，媒體多留一天後刪檔
    active, expired = {}, []
    for key, s in state.items():
        exp = datetime.fromisoformat(s["expires_at"])
        if exp > now:
            active[key] = s
        elif exp < now - timedelta(hours=24):
            expired.append(key)
        else:
            active[key] = {**s, "archived": True}
    for key in expired:
        p = ROOT / "site" / state[key]["media"].lstrip("/")
        p.unlink(missing_ok=True)
        state.pop(key)

    STORIES_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0))
    live = {k: v for k, v in active.items() if not v.get("archived")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": now_iso(),
        "stories": sorted(live.values(), key=lambda s: s["taken_at"], reverse=True),
    }, ensure_ascii=False))
    print(f"stories: +{n_new} new, {len(live)} active, pruned {len(expired)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
