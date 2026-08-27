"""OAuth-only account service for Chumei.

NYCU handles credentials and consent. Chumei stores only a local user mapping
and opaque browser sessions; it never receives or stores a school password.

Public routes (Caddy proxies /auth/*, /account*, /submit* to this service):
  GET  /account/              account/login page
  GET  /auth/{provider}/start     begin Authorization Code + PKCE flow (nycu / google)
  GET  /auth/{provider}/callback  exchange code and create/login local account
  GET  /auth/me               current session
  GET  /auth/follows          public counts plus current user's follows
  POST /auth/follows/sync     merge browser-local follows after login
  PUT  /auth/follows/{org_id} follow one organization
  DELETE /auth/follows/{org_id} unfollow one organization
  GET  /auth/submissions      current user's link reports
  POST /auth/submissions      report a link (JSON or form; login required)
  POST /auth/logout           revoke local session
  GET  /auth/health           runtime/configuration status
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import secrets
import sqlite3
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

import requests
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from build_site import page_shell
from chumei_lib import ROOT, load_env
from submissions import (
    DAILY_LIMIT,
    MAX_NOTE_LENGTH,
    STATUS_LABELS,
    SubmissionStore,
    classify_url,
    normalize_url,
)


PORT = 8324
NYCU_AUTHORIZE_URL = "https://id.nycu.edu.tw/o/authorize/"
NYCU_TOKEN_URL = "https://id.nycu.edu.tw/o/token/"
NYCU_PROFILE_URL = "https://id.nycu.edu.tw/api/profile/"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SESSION_COOKIE = "chumei_session"
EVENT_ID_RE = re.compile(r"evt_[0-9a-f]{6,32}")
OAUTH_STATE_COOKIE = "chumei_oauth_state"
SESSION_AGE_SECONDS = 30 * 24 * 60 * 60
OAUTH_STATE_AGE_SECONDS = 10 * 60


def _now() -> int:
    return int(time.time())


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _safe_return_to(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/account/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return "/account/"
    return value


def _normalize_follow_orgs(values) -> list[dict]:
    """Keep a bounded, deduplicated list of public organization identifiers."""
    if not isinstance(values, list):
        return []
    out: list[dict] = []
    seen: set[int] = set()
    for value in values[:500]:
        if isinstance(value, dict):
            raw_id = value.get("id")
            raw_name = value.get("name")
        else:
            raw_id = value
            raw_name = ""
        if isinstance(raw_id, bool):
            continue
        try:
            org_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if org_id <= 0 or org_id > 1_000_000_000 or org_id in seen:
            continue
        name = str(raw_name or "").strip()[:80]
        out.append({"id": org_id, "name": name})
        seen.add(org_id)
    return out


@dataclass(frozen=True)
class AuthConfig:
    client_id: str
    client_secret: str
    google_client_id: str = ""
    google_client_secret: str = ""
    public_base_url: str = "https://chumei.observe.tw"
    database_path: Path = ROOT / "state" / "auth.sqlite3"
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "AuthConfig":
        env = load_env()
        client_id = env.get("CHUMEI_NYCU_OAUTH_CLIENT_ID", "").strip()
        client_secret = env.get("CHUMEI_NYCU_OAUTH_CLIENT_SECRET", "").strip()
        if not client_id:
            client_id = _keychain_value("tw.observe.chumei.nycu-oauth-client-id")
        if not client_secret:
            client_secret = _keychain_value("tw.observe.chumei.nycu-oauth-secret")
        google_client_id = env.get("CHUMEI_GOOGLE_OAUTH_CLIENT_ID", "").strip()
        google_client_secret = env.get("CHUMEI_GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
        if not google_client_id:
            google_client_id = _keychain_value("tw.observe.chumei.google-oauth-client-id")
        if not google_client_secret:
            google_client_secret = _keychain_value("tw.observe.chumei.google-oauth-secret")
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            public_base_url=env.get(
                "CHUMEI_AUTH_PUBLIC_BASE_URL", "https://chumei.observe.tw"
            ).rstrip("/"),
            database_path=Path(
                env.get("CHUMEI_AUTH_DATABASE", ROOT / "state" / "auth.sqlite3")
            ),
            cookie_secure=env.get("CHUMEI_AUTH_COOKIE_SECURE", "true").lower()
            not in {"0", "false", "no"},
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url}/auth/nycu/callback"

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_base_url}/auth/google/callback"


def _keychain_value(service: str) -> str:
    """Read a deployment credential without placing it in .env or logs."""
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                "chumei",
                "-s",
                service,
                "-w",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""


class AuthStore:
    def __init__(self, path: Path, directory_path: Path | None = None):
        self.path = Path(path)
        self.directory_path = Path(directory_path) if directory_path else ROOT / "site" / "data" / "sources.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _directory_names(self) -> dict[int, str]:
        try:
            payload = json.loads(self.directory_path.read_text())
            return {
                int(entry["id"]): str(entry["name"])
                for entry in payload.get("entries", [])
                if entry.get("id") is not None and entry.get("name")
            }
        except (OSError, ValueError, TypeError):
            return {}

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    email TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_identities (
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    email TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (provider, subject)
                );
                CREATE INDEX IF NOT EXISTS oauth_identities_user_id
                    ON oauth_identities(user_id);
                CREATE TABLE IF NOT EXISTS user_org_follows (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    org_id INTEGER NOT NULL,
                    org_name TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, org_id)
                );
                CREATE INDEX IF NOT EXISTS user_org_follows_org_id
                    ON user_org_follows(org_id);
                CREATE TABLE IF NOT EXISTS user_event_going (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    event_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, event_id)
                );
                CREATE INDEX IF NOT EXISTS user_event_going_event_id
                    ON user_event_going(event_id);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_expires_at
                    ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    code_verifier TEXT NOT NULL,
                    return_to TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )
            columns = {r[1] for r in conn.execute("PRAGMA table_info(oauth_states)")}
            if "link_user_id" not in columns:
                conn.execute("ALTER TABLE oauth_states ADD COLUMN link_user_id TEXT")

    def cleanup(self, now: int | None = None) -> None:
        now = now or _now()
        with self._connection() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            conn.execute(
                "DELETE FROM oauth_states WHERE created_at <= ?",
                (now - OAUTH_STATE_AGE_SECONDS,),
            )

    def put_oauth_state(
        self, state: str, verifier: str, return_to: str, link_user_id: str | None = None
    ) -> None:
        now = _now()
        self.cleanup(now)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO oauth_states(state_hash, code_verifier, return_to, created_at, link_user_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (_hash_token(state), verifier, _safe_return_to(return_to), now, link_user_id),
            )

    def consume_oauth_state(self, state: str) -> sqlite3.Row | None:
        state_hash = _hash_token(state)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT code_verifier, return_to, created_at, link_user_id FROM oauth_states "
                "WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            conn.execute("DELETE FROM oauth_states WHERE state_hash = ?", (state_hash,))
        if not row or row["created_at"] <= _now() - OAUTH_STATE_AGE_SECONDS:
            return None
        return row

    def get_or_create_user(self, provider: str, subject: str, email: str | None) -> dict:
        now = _now()
        display_name = (email or subject).split("@", 1)[0][:80] or "竹梅使用者"
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT u.id, u.display_name, u.email
                FROM oauth_identities i
                JOIN users u ON u.id = i.user_id
                WHERE i.provider = ? AND i.subject = ?
                """,
                (provider, subject),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE oauth_identities SET email = ?, updated_at = ? "
                    "WHERE provider = ? AND subject = ?",
                    (email, now, provider, subject),
                )
                conn.execute(
                    "UPDATE users SET email = COALESCE(?, email), updated_at = ? WHERE id = ?",
                    (email, now, row["id"]),
                )
                return dict(row)

            user_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users(id, display_name, email, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, display_name, email, now, now),
            )
            conn.execute(
                "INSERT INTO oauth_identities(provider, subject, user_id, email, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (provider, subject, user_id, email, now, now),
            )
            return {"id": user_id, "display_name": display_name, "email": email}

    def identities_for_user(self, user_id: str) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT provider, subject, email FROM oauth_identities "
                "WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def link_identity(self, user_id: str, provider: str, subject: str, email: str | None) -> str:
        """把 (provider, subject) 綁到 user_id。回傳 ok / merged / already。

        若該身分已屬於另一個使用者，把對方的追蹤、參加、回報與 session
        全部搬過來再刪除對方（merged）。
        """
        now = _now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT user_id FROM oauth_identities WHERE provider = ? AND subject = ?",
                (provider, subject),
            ).fetchone()
            if row and row["user_id"] == user_id:
                conn.execute(
                    "UPDATE oauth_identities SET email = ?, updated_at = ? "
                    "WHERE provider = ? AND subject = ?",
                    (email, now, provider, subject),
                )
                return "already"
            if row:
                other_id = row["user_id"]
                conn.execute(
                    "UPDATE OR IGNORE user_org_follows SET user_id = ? WHERE user_id = ?",
                    (user_id, other_id),
                )
                conn.execute(
                    "UPDATE OR IGNORE user_event_going SET user_id = ? WHERE user_id = ?",
                    (user_id, other_id),
                )
                conn.execute(
                    "UPDATE sessions SET user_id = ? WHERE user_id = ?", (user_id, other_id)
                )
                conn.execute(
                    "UPDATE oauth_identities SET user_id = ?, email = ?, updated_at = ? "
                    "WHERE user_id = ?",
                    (user_id, email, now, other_id),
                )
                has_submissions = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'submissions'"
                ).fetchone()
                if has_submissions:
                    conn.execute(
                        "UPDATE submissions SET user_id = ? WHERE user_id = ?",
                        (user_id, other_id),
                    )
                conn.execute(
                    "UPDATE users SET email = COALESCE(email, ?), updated_at = ? WHERE id = ?",
                    (email, now, user_id),
                )
                conn.execute("DELETE FROM users WHERE id = ?", (other_id,))
                return "merged"
            conn.execute(
                "INSERT INTO oauth_identities(provider, subject, user_id, email, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (provider, subject, user_id, email, now, now),
            )
            conn.execute(
                "UPDATE users SET email = COALESCE(email, ?), updated_at = ? WHERE id = ?",
                (email, now, user_id),
            )
            return "ok"

    def unlink_identity(self, user_id: str, provider: str) -> bool:
        """解除某個 provider 的綁定；至少要留下一種登入方式。"""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT provider FROM oauth_identities WHERE user_id = ?", (user_id,)
            ).fetchall()
            kept = [r["provider"] for r in rows if r["provider"] != provider]
            if len(kept) == len(rows) or not kept:
                return False
            conn.execute(
                "DELETE FROM oauth_identities WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )
            return True

    def create_session(self, user_id: str) -> str:
        raw = secrets.token_urlsafe(32)
        now = _now()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (_hash_token(raw), user_id, now, now + SESSION_AGE_SECONDS),
            )
        return raw

    def session_user(self, raw_token: str | None) -> dict | None:
        if not raw_token:
            return None
        now = _now()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.display_name, u.email, i.provider, i.subject
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                JOIN oauth_identities i ON i.user_id = u.id
                WHERE s.token_hash = ? AND s.expires_at > ?
                ORDER BY i.created_at
                LIMIT 1
                """,
                (_hash_token(raw_token), now),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (_hash_token(raw_token),)
            )

    def merge_user_follows(self, user_id: str, orgs: list[dict]) -> None:
        """Union browser-local follows into a user's durable follow list."""
        now = _now()
        with self._connection() as conn:
            for org in orgs:
                conn.execute(
                    """
                    INSERT INTO user_org_follows(
                        user_id, org_id, org_name, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, org_id) DO UPDATE SET
                        org_name = CASE
                            WHEN excluded.org_name <> '' THEN excluded.org_name
                            ELSE user_org_follows.org_name
                        END,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, org["id"], org["name"], now, now),
                )

    def set_user_follow(
        self, user_id: str, org_id: int, org_name: str, following: bool
    ) -> None:
        now = _now()
        with self._connection() as conn:
            if following:
                conn.execute(
                    """
                    INSERT INTO user_org_follows(
                        user_id, org_id, org_name, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, org_id) DO UPDATE SET
                        org_name = CASE
                            WHEN excluded.org_name <> '' THEN excluded.org_name
                            ELSE user_org_follows.org_name
                        END,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, org_id, org_name, now, now),
                )
            else:
                conn.execute(
                    "DELETE FROM user_org_follows WHERE user_id = ? AND org_id = ?",
                    (user_id, org_id),
                )

    def follow_snapshot(self, user_id: str | None = None) -> dict:
        directory_names = self._directory_names()
        with self._connection() as conn:
            following = []
            if user_id:
                following = [
                    {"id": row["org_id"], "name": directory_names.get(row["org_id"], row["org_name"])}
                    for row in conn.execute(
                        "SELECT org_id, org_name FROM user_org_follows "
                        "WHERE user_id = ? ORDER BY created_at, org_id",
                        (user_id,),
                    )
                ]
            counts = {
                str(row["org_id"]): row["followers"]
                for row in conn.execute(
                    "SELECT org_id, COUNT(*) AS followers FROM user_org_follows "
                    "GROUP BY org_id"
                )
            }
            summary = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT user_id) AS accounts,
                    COUNT(*) AS follows,
                    COUNT(DISTINCT org_id) AS organizations
                FROM user_org_follows
                """
            ).fetchone()
        return {
            "following": following,
            "counts": counts,
            "summary": {
                "accounts": summary["accounts"],
                "follows": summary["follows"],
                "organizations": summary["organizations"],
            },
        }

    def set_user_event(self, user_id: str, event_id: str, going: bool) -> None:
        """標記／取消「我要去」。"""
        with self._connection() as conn:
            if going:
                conn.execute(
                    "INSERT INTO user_event_going(user_id, event_id, created_at) "
                    "VALUES (?, ?, ?) ON CONFLICT(user_id, event_id) DO NOTHING",
                    (user_id, event_id, _now()),
                )
            else:
                conn.execute(
                    "DELETE FROM user_event_going WHERE user_id = ? AND event_id = ?",
                    (user_id, event_id),
                )

    def event_snapshot(self, user_id: str | None = None) -> dict:
        """公開的每場活動參加人數＋目前使用者標記過的場次。"""
        with self._connection() as conn:
            going = []
            if user_id:
                going = [
                    row["event_id"]
                    for row in conn.execute(
                        "SELECT event_id FROM user_event_going "
                        "WHERE user_id = ? ORDER BY created_at, event_id",
                        (user_id,),
                    )
                ]
            counts = {
                row["event_id"]: row["people"]
                for row in conn.execute(
                    "SELECT event_id, COUNT(*) AS people FROM user_event_going "
                    "GROUP BY event_id"
                )
            }
            summary = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT user_id) AS accounts,
                    COUNT(*) AS marks,
                    COUNT(DISTINCT event_id) AS events
                FROM user_event_going
                """
            ).fetchone()
        return {
            "going": going,
            "counts": counts,
            "summary": {
                "accounts": summary["accounts"],
                "marks": summary["marks"],
                "events": summary["events"],
            },
        }


class NYCUOAuthClient:
    def __init__(self, http=requests):
        self.http = http

    def exchange_code(self, config: AuthConfig, code: str, verifier: str) -> str:
        response = self.http.post(
            NYCU_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.redirect_uri,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code_verifier": verifier,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("NYCU token response did not contain access_token")
        return access_token

    def profile(self, access_token: str) -> tuple[str, str | None]:
        response = self.http.get(
            NYCU_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        subject = payload.get("username")
        email = payload.get("email")
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("NYCU profile response did not contain username")
        if not isinstance(email, str) or "@" not in email:
            email = None
        return subject.strip(), email


class GoogleOAuthClient:
    """Google OpenID Connect（Authorization Code + PKCE）；用 userinfo 端點拿 sub 與 email。"""

    def __init__(self, http=requests):
        self.http = http

    def exchange_code(self, config: AuthConfig, code: str, verifier: str) -> str:
        response = self.http.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.google_redirect_uri,
                "client_id": config.google_client_id,
                "client_secret": config.google_client_secret,
                "code_verifier": verifier,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Google token response did not contain access_token")
        return access_token

    def profile(self, access_token: str) -> tuple[str, str | None]:
        response = self.http.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        subject = payload.get("sub")
        email = payload.get("email")
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Google userinfo response did not contain sub")
        if not isinstance(email, str) or "@" not in email:
            email = None
        return subject.strip(), email


def _error_page(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    body = _account_html(None, False, False, title=title, message=message)
    return HTMLResponse(body, status_code=status_code)


SUBMIT_NOTICES = {
    "ok": ("已收到，系統會在幾分鐘到一小時內判讀這個連結。", False),
    "dup": ("這個連結已經有人回報過了，下面可以看到它的狀態。", False),
    "invalid": ("看起來不是有效的網址，請貼完整的 http(s) 連結。", True),
    "self": ("這已經是竹梅站內的頁面囉，請貼原始貼文或公告的連結。", True),
    "limit": (f"一天最多回報 {DAILY_LIMIT} 個連結，明天再來吧。", True),
}


EVENTS_DATA_PATH = ROOT / "site" / "data" / "events.json"
_events_cache: dict = {"mtime": None, "byid": {}}


def _events_by_id() -> dict:
    """帳號頁把「我要去」的 event_id 對回標題／日期；以 mtime 快取整份 events.json。"""
    try:
        mtime = EVENTS_DATA_PATH.stat().st_mtime
    except OSError:
        return _events_cache["byid"]
    if _events_cache["mtime"] != mtime:
        try:
            data = json.loads(EVENTS_DATA_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            return _events_cache["byid"]
        _events_cache["byid"] = {e["id"]: e for e in data.get("events", []) if e.get("id")}
        _events_cache["mtime"] = mtime
    return _events_cache["byid"]


def _fmt_time(ts: int | None) -> str:
    if not ts:
        return ""
    return time.strftime("%m/%d %H:%M", time.localtime(ts))


def _submission_item_html(it: dict, mine: bool) -> str:
    status = it.get("status") or "pending"
    label = STATUS_LABELS.get(status, status)
    url = it["url"]
    short = html.escape(url.replace("https://", "").replace("www.", "")[:72] + ("…" if len(url) > 80 else ""))
    reason = html.escape(it.get("reason") or "")
    link = ""
    if it.get("event_url"):
        link = f' <a class="submit-result" href="{html.escape(it["event_url"])}">查看→</a>'
    note = ""
    if mine and it.get("note"):
        note = f'<p class="submit-note">備註：{html.escape(it["note"])}</p>'
    return (
        f'<li class="submit-item is-{html.escape(status)}{" is-mine" if mine else ""}">'
        f'<div class="submit-item-head"><span class="submit-status">{html.escape(label)}</span>'
        + ('<span class="submit-mine">你回報的</span>' if mine else "")
        + f'<time>{_fmt_time(it.get("created_at"))}</time></div>'
        f'<a class="submit-url" href="{html.escape(url)}" rel="noopener nofollow" target="_blank">{short}</a>'
        + (f'<p class="submit-reason">{reason}{link}</p>' if reason or link else "")
        + note + "</li>"
    )


def _submissions_html(items: list[dict], notice: str | None, user_id: str | None, nycu_ok: bool, google_ok: bool) -> str:
    alert = ""
    if notice in SUBMIT_NOTICES:
        text, is_error = SUBMIT_NOTICES[notice]
        alert = f'<p class="submit-notice{" is-error" if is_error else ""}" role="status">{html.escape(text)}</p>'
    rows = [
        _submission_item_html(it, bool(user_id) and it.get("user_id") == user_id)
        for it in items
    ]
    listing = (
        f'<ul class="submit-list">{"".join(rows)}</ul>'
        if rows
        else '<p class="submit-empty">還沒有人回報過連結。</p>'
    )
    if user_id:
        form = f"""
        <form method="post" action="/auth/submissions" class="submit-form">
          <label class="submit-label" for="submit-url">連結</label>
          <input id="submit-url" class="submit-input" type="url" name="url" required inputmode="url" placeholder="https://www.instagram.com/p/…" autocomplete="off">
          <label class="submit-label" for="submit-note">備註（選填，只有你和站長看得到）</label>
          <input id="submit-note" class="submit-input" type="text" name="note" maxlength="{MAX_NOTE_LENGTH}" placeholder="例如：主辦是清大天文社、活動在 9/20">
          <button class="btn btn-primary account-action" type="submit">送出</button>
        </form>"""
    elif nycu_ok or google_ok:
        btns = []
        if nycu_ok:
            btns.append('<a class="btn btn-primary account-action" href="/auth/nycu/start?return_to=/submit/">登入後回報連結</a>')
        if google_ok:
            btns.append('<a class="btn account-action" href="/auth/google/start?return_to=/submit/">用 Google 登入</a>')
        form = "".join(btns)
    else:
        form = ""
    return f"""
        <p class="eyebrow">回報連結</p>
        <h2>看到活動，貼連結給竹梅</h2>
        <p>IG／FB／Threads 貼文、公告頁或報名表都可以。系統會自動判讀是不是清交相關的活動：是新活動就收錄，已經有的就幫你對上，不確定的會留給人工看。每個連結的處理狀態都公開在下面。</p>
        {alert}
        {form}
        <h3 class="submit-list-title">最近的回報</h3>
        {listing}
    """


def _submit_page_html(items: list[dict], notice: str | None, user: dict | None, nycu_ok: bool, google_ok: bool) -> str:
    inner = _submissions_html(items, notice, user["id"] if user else None, nycu_ok, google_ok)
    content = f"""
<section class="account-page">
  <div class="hero">
    <h1>回報活動</h1>
    <p>幫竹梅補上漏掉的活動。處理進度公開，已收錄的會直接連到活動頁。</p>
  </div>
  <section class="account-card submit-card" id="submit">{inner}</section>
</section>
"""
    return page_shell(
        "回報活動｜竹梅活動觀測站",
        "把活動貼文或公告的連結回報給竹梅，系統會自動判讀收錄。",
        content,
        canonical="https://chumei.observe.tw/submit/",
    )


def _going_html(going_ids: list[str]) -> str:
    byid = _events_by_id()
    today = time.strftime("%Y-%m-%d")
    upcoming, past = [], []
    for eid in going_ids:
        ev = byid.get(eid)
        if not ev:
            continue
        start = str(ev.get("start_at") or "")[:10]
        (upcoming if start >= today else past).append((start, ev))
    upcoming.sort(key=lambda p: p[0])
    past.sort(key=lambda p: p[0], reverse=True)

    def row(start: str, ev: dict) -> str:
        date = f"{start[5:7]}/{start[8:10]}" if len(start) == 10 else "——"
        org = html.escape(ev.get("organizer") or "")
        eid = html.escape(ev["id"])
        ev_title = html.escape(ev.get("title") or "未命名活動")
        return (f'<li><time>{date}</time><a href="/event/{eid}/">{ev_title}</a>'
                + (f'<span class="account-event-org">{org}</span>' if org else "")
                + "</li>")

    parts = []
    if upcoming:
        parts.append('<ul class="account-events">' + "".join(row(*p) for p in upcoming) + "</ul>")
    else:
        parts.append('<p class="account-empty">還沒有標記要去的活動。到<a href="/events/">活動總覽</a>按 ✓，它們就會出現在這裡。</p>')
    if past:
        parts.append(f'<details class="account-past"><summary>已結束（{len(past)} 場）</summary>'
                     '<ul class="account-events">' + "".join(row(*p) for p in past) + "</ul></details>")
    return "".join(parts)


def _account_html(
    user: dict | None,
    nycu_ok: bool,
    google_ok: bool,
    *,
    title: str = "帳號",
    message: str | None = None,
    following: list[dict] | None = None,
    going_ids: list[str] | None = None,
    my_submissions: list[dict] | None = None,
    identities: list[dict] | None = None,
) -> str:
    sections = []
    if user:
        idents = identities or []
        if not idents:
            idents = [{"provider": user.get("provider") or "nycu",
                       "subject": user.get("subject") or "",
                       "email": user.get("email")}]
        by_provider = {i["provider"]: i for i in idents}
        can_unlink = len(idents) > 1

        def unlink_form(provider: str) -> str:
            if not can_unlink:
                return ""
            return (f'<form method="post" action="/auth/unlink" class="account-unlink">'
                    f'<input type="hidden" name="provider" value="{provider}">'
                    f'<button type="submit">解除綁定</button></form>')

        rows = []
        nycu = by_provider.get("nycu")
        if nycu:
            rows.append(f'<div><dt>學校帳號</dt><dd>{html.escape(nycu.get("subject") or "")}'
                        f'{unlink_form("nycu")}</dd></div>')
        elif nycu_ok:
            rows.append('<div><dt>學校帳號</dt><dd><a class="account-bind" '
                        'href="/auth/nycu/start?link=1">綁定陽明交大 OAuth →</a></dd></div>')
        if nycu and not by_provider.get("google") and user.get("email"):
            rows.append(f'<div><dt>Email</dt><dd>{html.escape(user["email"])}</dd></div>')
        google = by_provider.get("google")
        if google:
            g_label = html.escape(google.get("email") or google.get("subject") or "")
            rows.append(f'<div><dt>Google</dt><dd>{g_label}{unlink_form("google")}</dd></div>')
        elif google_ok:
            rows.append('<div><dt>Google</dt><dd><a class="account-bind" '
                        'href="/auth/google/start?link=1">綁定 Google 帳號 →</a></dd></div>')

        if "nycu" in by_provider and "google" in by_provider:
            status_line = "已綁定學校與 Google 帳號"
        elif "google" in by_provider:
            status_line = "已使用 Google 帳號登入"
        else:
            status_line = "已使用陽明交大 OAuth 登入"
        bind_hint = ("" if can_unlink else
                     '<p class="account-hint">綁定另一種登入方式後，用哪個帳號登入都會回到同一份追蹤與回報。</p>')
        sections.append(f"""<section class="account-card">
        <div class="account-status"><span class="account-dot"></span>{status_line}</div>
        <h2>{html.escape(user.get('display_name') or '竹梅使用者')}</h2>
        <dl>{''.join(rows)}</dl>
        {bind_hint}
        <form method="post" action="/auth/logout"><button class="btn account-action" type="submit">登出</button></form>
        </section>""")

        follows = following or []
        if follows:
            chips = []
            for org in follows:
                name = html.escape(org.get("name") or f"單位 {org['id']}")
                chips.append(f'<a class="account-chip" href="/org/{org["id"]}/">{name}</a>')
            follow_body = f'<div class="account-chips">{"".join(chips)}</div>'
        else:
            follow_body = '<p class="account-empty">還沒有追蹤任何單位。在貼文、活動卡或單位頁按 🔔 就會出現在這裡。</p>'
        sections.append(f"""<section class="account-card account-section">
        <h2>追蹤的單位{f'<span class="account-count">{len(follows)}</span>' if follows else ''}</h2>
        {follow_body}
        <p class="account-links"><a href="/source/">找更多單位 →</a><a href="/notify/">通知設定 →</a></p>
        </section>""")

        sections.append(f"""<section class="account-card account-section">
        <h2>我要去的活動</h2>
        {_going_html(going_ids or [])}
        </section>""")

        subs = my_submissions or []
        if subs:
            sub_body = ('<ul class="submit-list">'
                        + "".join(_submission_item_html(it, True) for it in subs)
                        + "</ul>")
        else:
            sub_body = '<p class="account-empty">還沒有回報過連結。看到竹梅漏掉的活動，貼個連結就能幫大家補上。</p>'
        sections.append(f"""<section class="account-card account-section">
        <h2>我的回報</h2>
        {sub_body}
        <p class="account-links"><a href="/submit/">回報新連結 →</a></p>
        </section>""")
    elif nycu_ok or google_ok:
        nycu_btn = ('<a class="btn btn-primary account-action" href="/auth/nycu/start">使用陽明交大 OAuth 登入</a>'
                    if nycu_ok else "")
        google_btn = ('<a class="btn account-action" href="/auth/google/start">使用 Google 帳號登入</a>'
                      if google_ok else "")
        sections.append(f"""<section class="account-card">
        <p class="eyebrow">OAuth-only account</p>
        <h2>登入竹梅</h2>
        <p>陽明交大成員請走學校單一入口；清大朋友、校友與其他人可用 Google 帳號登入。竹梅不會取得或儲存你的密碼。</p>
        {nycu_btn}
        {google_btn}
        <p class="privacy-note">登入只取得穩定的帳號識別與 Email，用來記住你的追蹤、參加標記與<a href="/submit/">回報的連結</a>。</p>
        </section>""")
    else:
        sections.append("""<section class="account-card">
        <p class="eyebrow">OAuth-only account</p>
        <h2>登入功能設定中</h2>
        <p>OAuth Client 尚未完成設定，請稍後再試。</p>
        <span class="btn btn-primary account-action disabled" aria-disabled="true">登入竹梅</span>
        </section>""")

    alert = f'<div class="account-alert">{html.escape(message)}</div>' if message else ""
    lede = "" if message else "<p>登入身分、追蹤的單位、要去的活動與回報進度都在這裡。</p>"
    content = f"""
<section class="account-page">
  <div class="hero">
    <h1>{html.escape(title)}</h1>
    {lede}
  </div>
  {alert}
  {"".join(sections)}
</section>
"""
    return page_shell(
        f"{title}｜竹梅活動觀測站",
        "管理你的竹梅帳號：登入、追蹤單位、參加標記與回報。",
        content,
        canonical="https://chumei.observe.tw/account/",
    )


def create_app(
    config: AuthConfig | None = None,
    store: AuthStore | None = None,
    oauth_client: NYCUOAuthClient | None = None,
    submissions: SubmissionStore | None = None,
    google_oauth_client: "GoogleOAuthClient | None" = None,
) -> Starlette:
    config = config or AuthConfig.from_env()
    store = store or AuthStore(config.database_path)
    oauth_client = oauth_client or NYCUOAuthClient()
    google_oauth_client = google_oauth_client or GoogleOAuthClient()
    submissions = submissions or SubmissionStore(config.database_path)

    providers = {
        "nycu": {
            "client": oauth_client,
            "authorize_url": NYCU_AUTHORIZE_URL,
            "scope": "profile",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "configured": config.configured,
            "extra": {},
            "cancel_msg": "陽明交大未授權登入，帳號沒有建立。",
            "fail_msg": "無法向陽明交大完成身分驗證，請稍後再試。",
            "unconfigured_msg": "NYCU OAuth Client 尚未完成設定。",
        },
        "google": {
            "client": google_oauth_client,
            "authorize_url": GOOGLE_AUTHORIZE_URL,
            "scope": "openid email",
            "client_id": config.google_client_id,
            "redirect_uri": config.google_redirect_uri,
            "configured": config.google_configured,
            "extra": {"prompt": "select_account"},
            "cancel_msg": "Google 未授權登入，帳號沒有建立。",
            "fail_msg": "無法向 Google 完成身分驗證，請稍後再試。",
            "unconfigured_msg": "Google OAuth Client 尚未完成設定。",
        },
    }

    LINK_MESSAGES = {
        "ok": "綁定完成！之後用學校或 Google 帳號登入，都會回到同一個竹梅帳號。",
        "merged": "綁定完成，另一個帳號的追蹤、參加標記與回報都合併進來了。",
        "already": "這兩個帳號原本就綁在一起了。",
        "unlinked": "已解除綁定。",
        "unlink_fail": "至少要保留一種登入方式，無法解除綁定。",
    }

    async def account(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        kwargs = {}
        if user:
            kwargs = {
                "following": store.follow_snapshot(user["id"])["following"],
                "going_ids": store.event_snapshot(user["id"])["going"],
                "my_submissions": submissions.list_for_user(user["id"], 8),
                "identities": store.identities_for_user(user["id"]),
                "message": LINK_MESSAGES.get(request.query_params.get("link") or ""),
            }
        return HTMLResponse(
            _account_html(user, config.configured, config.google_configured, **kwargs)
        )

    async def submit_page(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        notice = request.query_params.get("submit")
        return HTMLResponse(
            _submit_page_html(
                submissions.list_recent(), notice, user,
                config.configured, config.google_configured,
            )
        )

    def submission_payload(item: dict, user: dict | None) -> dict:
        """公開欄位；備註與「是不是我回報的」只給本人。"""
        mine = bool(user) and item.get("user_id") == user["id"]
        payload = {
            "id": item["id"],
            "url": item["url"],
            "status": item["status"],
            "statusLabel": STATUS_LABELS.get(item["status"], item["status"]),
            "reason": item.get("reason") or "",
            "eventUrl": item.get("event_url"),
            "createdAt": item["created_at"],
            "updatedAt": item["updated_at"],
            "mine": mine,
        }
        if mine:
            payload["note"] = item.get("note") or ""
        return payload

    async def submissions_list(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        items = [submission_payload(i, user) for i in submissions.list_recent()]
        return JSONResponse(
            {"ok": True, "authenticated": bool(user), "submissions": items, "dailyLimit": DAILY_LIMIT}
        )

    async def submissions_create(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        wants_json = "application/json" in (request.headers.get("content-type") or "")

        def reply(code: str, item: dict | None = None, status_code: int = 200):
            if wants_json:
                body = {"ok": code in ("ok", "dup"), "code": code}
                if item:
                    body["submission"] = submission_payload(item, user)
                return JSONResponse(body, status_code=status_code)
            return RedirectResponse(f"/submit/?submit={code}#submit", 303)

        if not user:
            if wants_json:
                return JSONResponse(
                    {"ok": False, "error": "authentication required"}, status_code=401
                )
            return RedirectResponse("/submit/", 303)
        if wants_json:
            try:
                body = await request.json()
            except (json.JSONDecodeError, ValueError):
                body = {}
            body = body if isinstance(body, dict) else {}
        else:
            raw = (await request.body())[:8192].decode("utf-8", "replace")
            body = dict(parse_qsl(raw, keep_blank_values=True))
        url = normalize_url(str(body.get("url") or ""))
        if not url:
            return reply("invalid", status_code=400)
        if classify_url(url)["kind"] == "chumei":
            return reply("self", status_code=400)
        existing = submissions.find_by_url(url)
        if existing:
            return reply("dup", existing)
        if submissions.count_today(user["id"]) >= DAILY_LIMIT:
            return reply("limit", status_code=429)
        item = submissions.create(user["id"], url, str(body.get("note") or ""))
        return reply("ok", item, status_code=201)

    async def oauth_start(request: Request):
        spec = providers.get(str(request.path_params.get("provider") or ""))
        if not spec:
            return _error_page("不支援的登入方式", "沒有這個登入提供者。", 404)
        if not spec["configured"]:
            return _error_page("登入功能設定中", spec["unconfigured_msg"], 503)
        link_user_id = None
        if request.query_params.get("link"):
            link_user = store.session_user(request.cookies.get(SESSION_COOKIE))
            if not link_user:
                return _error_page("要先登入", "請先登入原本的帳號，再綁定另一種登入方式。", 401)
            link_user_id = link_user["id"]
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        return_to = _safe_return_to(request.query_params.get("return_to"))
        store.put_oauth_state(state, verifier, return_to, link_user_id=link_user_id)
        params = {
            "response_type": "code",
            "client_id": spec["client_id"],
            "redirect_uri": spec["redirect_uri"],
            "scope": spec["scope"],
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            **spec["extra"],
        }
        response = RedirectResponse(f"{spec['authorize_url']}?{urlencode(params)}", 302)
        response.set_cookie(
            OAUTH_STATE_COOKIE,
            state,
            max_age=OAUTH_STATE_AGE_SECONDS,
            secure=config.cookie_secure,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    async def oauth_callback(request: Request):
        provider_key = str(request.path_params.get("provider") or "")
        spec = providers.get(provider_key)
        if not spec:
            return _error_page("不支援的登入方式", "沒有這個登入提供者。", 404)
        provider_error = request.query_params.get("error")
        state = request.query_params.get("state") or ""
        state_cookie = request.cookies.get(OAUTH_STATE_COOKIE) or ""
        if provider_error:
            return _error_page("登入已取消", spec["cancel_msg"])
        if not state or not secrets.compare_digest(state, state_cookie):
            return _error_page("登入驗證失敗", "登入狀態已失效，請回到帳號頁重新登入。")
        state_row = store.consume_oauth_state(state)
        code = request.query_params.get("code")
        if not state_row or not code:
            return _error_page("登入驗證失敗", "授權碼或登入狀態已失效，請重新登入。")
        try:
            access_token = await run_in_threadpool(
                spec["client"].exchange_code, config, code, state_row["code_verifier"]
            )
            subject, email = await run_in_threadpool(spec["client"].profile, access_token)
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            return _error_page("登入暫時失敗", spec["fail_msg"], 502)
        link_user_id = state_row["link_user_id"]
        if link_user_id:
            current = store.session_user(request.cookies.get(SESSION_COOKIE))
            if not current or current["id"] != link_user_id:
                return _error_page("綁定失敗", "登入狀態已改變，請重新登入後再綁定一次。", 400)
            outcome = store.link_identity(current["id"], provider_key, subject, email)
            response = RedirectResponse(f"/account/?link={outcome}", 303)
            response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
            return response
        user = store.get_or_create_user(provider_key, subject, email)
        raw_session = store.create_session(user["id"])
        response = RedirectResponse(state_row["return_to"], 303)
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
        response.set_cookie(
            SESSION_COOKIE,
            raw_session,
            max_age=SESSION_AGE_SECONDS,
            secure=config.cookie_secure,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    async def me(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse({"ok": True, "authenticated": False})
        return JSONResponse(
            {
                "ok": True,
                "authenticated": True,
                "user": {
                    "id": user["id"],
                    "displayName": user["display_name"],
                    "email": user["email"],
                    "provider": user.get("provider") or "nycu",
                    "providers": [
                        i["provider"] for i in store.identities_for_user(user["id"])
                    ],
                },
            }
        )

    def follow_payload(user: dict | None) -> dict:
        snapshot = store.follow_snapshot(user["id"] if user else None)
        return {
            "ok": True,
            "authenticated": bool(user),
            **snapshot,
        }

    async def follows(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        return JSONResponse(follow_payload(user))

    def event_payload(user: dict | None) -> dict:
        snapshot = store.event_snapshot(user["id"] if user else None)
        return {"ok": True, "authenticated": bool(user), **snapshot}

    def _event_id(request: Request) -> str:
        return str(request.path_params.get("event_id") or "")[:64]

    async def events_going(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        return JSONResponse(event_payload(user))

    async def event_going_set(request: Request):
        """PUT＝我要去、DELETE＝取消；計數綁帳號，一人一場只算一次。"""
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "authentication required"}, status_code=401
            )
        event_id = _event_id(request)
        if not EVENT_ID_RE.fullmatch(event_id):
            return JSONResponse({"ok": False, "error": "invalid event id"}, status_code=400)
        store.set_user_event(user["id"], event_id, request.method == "PUT")
        return JSONResponse(event_payload(user))

    async def follows_sync(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "authentication required"}, status_code=401
            )
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)
        if not isinstance(body.get("orgs"), list):
            return JSONResponse(
                {"ok": False, "error": "orgs must be a list"}, status_code=400
            )
        store.merge_user_follows(user["id"], _normalize_follow_orgs(body["orgs"]))
        return JSONResponse(follow_payload(user))

    async def follow_add(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "authentication required"}, status_code=401
            )
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        if not isinstance(body, dict):
            body = {}
        orgs = _normalize_follow_orgs(
            [{"id": request.path_params["org_id"], "name": body.get("name", "")}]
        )
        if not orgs:
            return JSONResponse(
                {"ok": False, "error": "invalid organization"}, status_code=400
            )
        org = orgs[0]
        store.set_user_follow(user["id"], org["id"], org["name"], True)
        return JSONResponse(follow_payload(user))

    async def follow_remove(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "authentication required"}, status_code=401
            )
        orgs = _normalize_follow_orgs([request.path_params["org_id"]])
        if not orgs:
            return JSONResponse(
                {"ok": False, "error": "invalid organization"}, status_code=400
            )
        store.set_user_follow(user["id"], orgs[0]["id"], "", False)
        return JSONResponse(follow_payload(user))

    async def logout(request: Request):
        raw_session = request.cookies.get(SESSION_COOKIE)
        store.delete_session(raw_session)
        response = RedirectResponse("/account/", 303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    async def unlink(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return RedirectResponse("/account/", 303)
        form = await request.form()
        provider_key = str(form.get("provider") or "")
        if provider_key not in providers:
            return RedirectResponse("/account/", 303)
        removed = store.unlink_identity(user["id"], provider_key)
        code = "unlinked" if removed else "unlink_fail"
        return RedirectResponse(f"/account/?link={code}", 303)

    async def health(request: Request):
        return JSONResponse(
            {
                "ok": True,
                "service": "chumei-auth",
                "configured": config.configured,
                "googleConfigured": config.google_configured,
            }
        )

    app = Starlette(
        routes=[
            Route("/account", account, methods=["GET"]),
            Route("/account/", account, methods=["GET"]),
            Route("/submit", submit_page, methods=["GET"]),
            Route("/submit/", submit_page, methods=["GET"]),
            Route("/auth/{provider}/start", oauth_start, methods=["GET"]),
            Route("/auth/{provider}/callback", oauth_callback, methods=["GET"]),
            Route("/auth/me", me, methods=["GET"]),
            Route("/auth/follows", follows, methods=["GET"]),
            Route("/auth/events", events_going, methods=["GET"]),
            Route("/auth/events/{event_id}", event_going_set, methods=["PUT", "DELETE"]),
            Route("/auth/follows/sync", follows_sync, methods=["POST"]),
            Route("/auth/follows/{org_id:int}", follow_add, methods=["PUT"]),
            Route("/auth/follows/{org_id:int}", follow_remove, methods=["DELETE"]),
            Route("/auth/submissions", submissions_list, methods=["GET"]),
            Route("/auth/submissions", submissions_create, methods=["POST"]),
            Route("/auth/unlink", unlink, methods=["POST"]),
            Route("/auth/logout", logout, methods=["POST"]),
            Route("/auth/health", health, methods=["GET"]),
        ]
    )

    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Pragma", "no-cache")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; img-src 'self'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
