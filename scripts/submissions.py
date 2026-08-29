"""連結回報（登入者投稿）共用層：URL 正規化／分類、SQLite 儲存。

auth_server 負責收件與顯示，process_submissions 負責審核與落地；兩邊共用這裡的
SubmissionStore（與帳號同一個 sqlite 檔）與狀態定義。
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DAILY_LIMIT = 10
MAX_ATTEMPTS = 3
MAX_URL_LENGTH = 2000
MAX_NOTE_LENGTH = 300

# status → (使用者看到的標籤, 是否為最終狀態)
STATUS_LABELS = {
    "pending": "待處理",
    "processing": "審核中",
    "accepted": "已收錄，等待上線",
    "published": "已上線",
    "existing": "已收錄",
    "not_event": "未辨識出活動",
    "source_suggested": "帳號已列入評估",
    "manual": "待人工確認",
    "rejected": "不收錄",
    "error": "處理失敗",
}
OPEN_STATUSES = {"pending", "processing", "accepted"}

TRACKING_PARAMS = {"igsh", "igshid", "igsi", "fbclid", "mibextid", "ref", "rdid", "share_id", "s", "t", "xmt"}
HOST_ALIASES = {
    "instagram.com": "www.instagram.com",
    "m.facebook.com": "www.facebook.com",
    "facebook.com": "www.facebook.com",
    "web.facebook.com": "www.facebook.com",
    "mbasic.facebook.com": "www.facebook.com",
    "threads.com": "www.threads.net",
    "www.threads.com": "www.threads.net",
    "threads.net": "www.threads.net",
    "mobile.twitter.com": "x.com",
    "twitter.com": "x.com",
    "www.x.com": "x.com",
}


def _now() -> int:
    return int(time.time())


def normalize_url(raw: str | None) -> str | None:
    """清掉追蹤參數與 fragment、統一主機別名；不合法回傳 None。"""
    value = (raw or "").strip()
    if not value:
        return None
    if not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    if len(value) > MAX_URL_LENGTH:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host or "." not in host or any(ch.isspace() for ch in value):
        return None
    host = HOST_ALIASES.get(host, host)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    path = re.sub(r"/{2,}", "/", parts.path) or "/"
    if path != "/" and not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return urlunsplit(("https", host, path, urlencode(query), ""))


def classify_url(url: str) -> dict:
    """回傳 {"kind": ..., "platform": ..., "handle": ..., "post_id": ...}。

    kind: ig_post / ig_profile / fb_post / fb_page / fb_group / threads_post /
          threads_profile / x_post / x_profile / chumei / web
    """
    parts = urlsplit(url)
    host, path = parts.hostname or "", parts.path
    if host.endswith("chumei.observe.tw"):
        return {"kind": "chumei", "platform": "web", "handle": None, "post_id": None}
    if host == "www.instagram.com":
        m = re.match(r"^/(?:p|reel|reels|tv)/([\w-]+)/?", path)
        if m:
            return {"kind": "ig_post", "platform": "instagram", "handle": None, "post_id": m.group(1)}
        m = re.match(r"^/([\w.]+)/?(?:$|(?:p|reel|reels|tagged|followers|following)/?$)", path)
        if m and m.group(1) not in {"explore", "accounts", "stories", "direct"}:
            return {"kind": "ig_profile", "platform": "instagram", "handle": m.group(1).lower(), "post_id": None}
    if host == "www.facebook.com":
        if path.startswith("/groups/"):
            return {"kind": "fb_group", "platform": "facebook", "handle": None, "post_id": None}
        m = re.match(r"^/events/(\d+)", path)
        if m:
            return {"kind": "fb_post", "platform": "facebook", "handle": None, "post_id": "event_" + m.group(1)}
        m = re.match(r"^/([\w.]+)/posts/(\w+)", path)
        if m:
            return {"kind": "fb_post", "platform": "facebook", "handle": m.group(1).lower(), "post_id": m.group(2)}
        if re.match(r"^/(share|photo|photos|watch|reel|story\.php|permalink\.php)", path) or "fbid=" in parts.query:
            return {"kind": "fb_post", "platform": "facebook", "handle": None, "post_id": None}
        if path == "/profile.php":
            pid = dict(parse_qsl(parts.query)).get("id")
            return {"kind": "fb_page", "platform": "facebook", "handle": pid, "post_id": None}
        m = re.match(r"^/([\w.-]+)/?$", path)
        if m:
            return {"kind": "fb_page", "platform": "facebook", "handle": m.group(1).lower(), "post_id": None}
    if host == "www.threads.net":
        m = re.match(r"^/@([\w.]+)/post/([\w-]+)", path)
        if m:
            return {"kind": "threads_post", "platform": "threads", "handle": m.group(1).lower(), "post_id": m.group(2)}
        m = re.match(r"^/@([\w.]+)/?$", path)
        if m:
            return {"kind": "threads_profile", "platform": "threads", "handle": m.group(1).lower(), "post_id": None}
    if host == "x.com":
        m = re.match(r"^/(\w+)/status/(\d+)", path)
        if m:
            return {"kind": "x_post", "platform": "twitter", "handle": m.group(1).lower(), "post_id": m.group(2)}
        m = re.match(r"^/(\w+)/?$", path)
        if m and m.group(1) not in {"home", "explore", "search", "i"}:
            return {"kind": "x_profile", "platform": "twitter", "handle": m.group(1).lower(), "post_id": None}
    return {"kind": "web", "platform": "web", "handle": None, "post_id": None}


def new_submission_id() -> str:
    return "sub_" + secrets.token_hex(6)


class SubmissionStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL DEFAULT '',
                    event_url TEXT,
                    verdict TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    resolved_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS submissions_user_created
                    ON submissions(user_id, created_at);
                CREATE INDEX IF NOT EXISTS submissions_status
                    ON submissions(status, created_at);
                CREATE INDEX IF NOT EXISTS submissions_url ON submissions(url);
                """
            )

    def count_today(self, user_id: str, now: int | None = None) -> int:
        now = now or _now()
        with self._connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE user_id = ? AND created_at > ?",
                (user_id, now - 86400),
            ).fetchone()[0]

    def find_by_url(self, url: str) -> dict | None:
        """同一個連結若已有非「不收錄／失敗」的紀錄，回傳最新那筆。"""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM submissions WHERE url = ? AND status NOT IN ('rejected', 'error') "
                "ORDER BY created_at DESC LIMIT 1",
                (url,),
            ).fetchone()
        return dict(row) if row else None

    def create(self, user_id: str, url: str, note: str = "") -> dict:
        now = _now()
        record = {
            "id": new_submission_id(),
            "user_id": user_id,
            "url": url,
            "note": (note or "").strip()[:MAX_NOTE_LENGTH],
            "status": "pending",
            "reason": "",
            "event_url": None,
            "verdict": None,
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
            "resolved_at": None,
        }
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO submissions(id, user_id, url, note, status, reason, event_url, verdict, "
                "attempts, created_at, updated_at, resolved_at) "
                "VALUES (:id, :user_id, :url, :note, :status, :reason, :event_url, :verdict, "
                ":attempts, :created_at, :updated_at, :resolved_at)",
                record,
            )
        return record

    def list_for_user(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM submissions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_recent(self, limit: int = 50) -> list[dict]:
        """所有人的回報，公開狀態頁用（呼叫端負責隱藏 user_id／note）。"""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM submissions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def list_by_status(self, statuses, limit: int = 20) -> list[dict]:
        marks = ",".join("?" for _ in statuses)
        with self._connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM submissions WHERE status IN ({marks}) ORDER BY created_at LIMIT ?",
                (*statuses, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, submission_id: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
        return dict(row) if row else None

    def update(self, submission_id: str, status: str, reason: str = "", *,
               event_url: str | None = None, verdict: str | None = None,
               bump_attempts: bool = False) -> None:
        now = _now()
        final = status not in OPEN_STATUSES
        with self._connection() as conn:
            conn.execute(
                "UPDATE submissions SET status = ?, reason = ?, event_url = COALESCE(?, event_url), "
                "verdict = COALESCE(?, verdict), attempts = attempts + ?, updated_at = ?, "
                "resolved_at = CASE WHEN ? THEN ? ELSE resolved_at END WHERE id = ?",
                (status, reason[:500], event_url, verdict, 1 if bump_attempts else 0, now,
                 final, now, submission_id),
            )
