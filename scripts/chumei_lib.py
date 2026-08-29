"""共用工具：.env 載入、inbox 寫入、seen-state 去重。所有 fetcher 共用。"""

import csv
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = ROOT / "data" / "feeds" / "inbox"
SEEN_DIR = ROOT / "state" / "seen"
SOURCES_DIR = ROOT / "data" / "sources"
TZ_TAIPEI = timezone(timedelta(hours=8))


def load_env():
    env = {}
    for path in (ROOT / ".env", ROOT / ".env.apify"):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    merged = dict(env)
    merged.update({
        k: v for k, v in os.environ.items()
        if k.startswith("CHUMEI_") or k == "APIFY_TOKEN" or k.startswith("APIFY_TOKEN_")
    })
    return merged


def now_iso():
    return datetime.now(TZ_TAIPEI).isoformat(timespec="seconds")


def read_sources_csv(name):
    path = SOURCES_DIR / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [row for row in csv.DictReader(f)]


class SeenState:
    """seen-state 去重。鍵為 "source_id\\tpost_id"。"""

    def __init__(self, raw_source):
        SEEN_DIR.mkdir(parents=True, exist_ok=True)
        self.path = SEEN_DIR / f"{raw_source}.json"
        self.data = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def has(self, source_id, post_id):
        return f"{source_id}\t{post_id}" in self.data

    def add(self, source_id, post_id):
        self.data[f"{source_id}\t{post_id}"] = now_iso()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=0))
        tmp.replace(self.path)


REQUIRED_FIELDS = [
    "source_id", "source_name", "platform", "raw_source", "school",
    "org_type", "post_id", "url", "posted_at", "text", "fetched_at",
]


def append_inbox(raw_source, items):
    """驗證並 append inbox JSONL；回傳寫入筆數。呼叫端自行先用 SeenState 過濾。"""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = INBOX_DIR / f"{raw_source}.jsonl"
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for it in items:
            missing = [k for k in REQUIRED_FIELDS if not it.get(k)]
            if missing:
                raise ValueError(f"inbox item missing {missing}: {str(it)[:200]}")
            it.setdefault("images", [])
            it.setdefault("image_url", it["images"][0] if it.get("images") else None)
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
            n += 1
    return n


AVATAR_DIR = ROOT / "site" / "assets" / "avatars"


def save_avatar(key, url, max_age_days=7):
    """存單位頭貼（256px JPEG）到 site/assets/avatars/<key>.jpg。新鮮就跳過。"""
    import io
    import time
    try:
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        dest = AVATAR_DIR / f"{key}.jpg"
        if dest.exists() and time.time() - dest.stat().st_mtime < max_age_days * 86400:
            return True
        import requests
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (chumei.observe.tw)"},
                         allow_redirects=True)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):
            return dest.exists()
        from PIL import Image
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((256, 256))
        im.save(dest, "JPEG", quality=85)
        return True
    except Exception:
        return (AVATAR_DIR / f"{key}.jpg").exists()


def iter_inbox():
    """迭代所有 inbox 項目。"""
    if not INBOX_DIR.exists():
        return
    for path in sorted(INBOX_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
