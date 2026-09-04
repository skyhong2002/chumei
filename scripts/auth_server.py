"""OAuth-only account service for Chumei.

NYCU handles credentials and consent. Chumei stores only a local user mapping
and opaque browser sessions; it never receives or stores a school password.

Public routes (Caddy proxies /auth/*, /account*, /submit*, /@* to this service):
  GET  /@{handle}             public profile (display name, follows, going events)
  GET  /account/              account settings / login page
  GET  /auth/{provider}/start     begin Authorization Code + PKCE flow (nycu / google)
  GET  /auth/{provider}/callback  exchange code and create/login local account
  GET  /auth/me               current session
  GET  /auth/follows          public counts plus current user's follows
  POST /auth/follows/sync     merge browser-local follows after login
  PUT  /auth/follows/{org_id} follow one organization
  DELETE /auth/follows/{org_id} unfollow one organization
  GET  /auth/submissions      current user's link reports
  POST /auth/submissions      report a link (JSON or form; login required)
  GET  /contribute/           Apify community contribution dashboard
  GET/POST /auth/apify-contributions  list or register encrypted Apify tokens
  POST /auth/logout           revoke local session
  GET  /auth/health           runtime/configuration status
"""

from __future__ import annotations

import base64
import hashlib
import hmac
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
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlparse

import requests
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Route

from apify_contributions import (
    MAX_ACCOUNT_NAME_LENGTH,
    MAX_ACCOUNTS_PER_USER,
    PRIORITY_BONUS_PER_ACCOUNT,
    active_count as apify_active_count,
    dashboard as apify_dashboard,
    disable as disable_apify_contribution,
    encryption_available as apify_encryption_available,
    ensure_schema as ensure_apify_schema,
    register as register_apify_contribution,
    rename as rename_apify_contribution,
    user_rows as apify_user_rows,
    verify_token as verify_apify_token,
)
from build_site import event_ics, ics_calendar, page_shell
from chumei_lib import ROOT, load_env
from submissions import (
    DAILY_LIMIT,
    MAX_NOTE_LENGTH,
    STATUS_LABELS,
    SubmissionStore,
    classify_url,
    normalize_url,
)
from source_status import source_registry


PORT = 8324
NYCU_AUTHORIZE_URL = "https://id.nycu.edu.tw/o/authorize/"
NYCU_TOKEN_URL = "https://id.nycu.edu.tw/o/token/"
NYCU_PROFILE_URL = "https://id.nycu.edu.tw/api/profile/"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SESSION_COOKIE = "chumei_session"
# 活動 ID 除了歷史的 hex digest，也包含官方來源命名空間（例如 evt_nyculife_xxx）。
# 僅允許小寫英數與底線，總長度最多 64 字元。
EVENT_ID_RE = re.compile(r"evt_[a-z0-9_]{6,60}")
HANDLE_RE = re.compile(r"[a-z0-9_]{3,20}")
RESERVED_HANDLES = {
    "admin", "chumei", "account", "submit", "contribute", "auth", "about", "event", "org", "source"
}
OAUTH_STATE_COOKIE = "chumei_oauth_state"
SESSION_AGE_SECONDS = 30 * 24 * 60 * 60
OAUTH_STATE_AGE_SECONDS = 10 * 60
FETCH_REQUEST_DAILY_LIMIT = 5
SAVED_FEED_LIMIT = 10
SAVED_FEED_NAME_MAX = 40
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_CACHE_SECONDS = 5 * 60

CATEGORY_FILTERS = {
    "talk": "演講", "workshop": "工作坊", "show": "表演", "expo": "展覽",
    "contest": "比賽", "camp": "營隊", "recruit": "徵才", "market": "市集",
    "sport": "運動", "social": "聚會", "other": "其他",
}
CAMPUS_FILTERS = {
    "nthu-main": "清大校本部", "nthu-nanda": "清大南大",
    "nycu-guangfu": "交大光復", "nycu-boai": "交大博愛",
    "nycu-yangming": "陽明校區", "online": "線上", "other": "其他地點",
}
ORGANIZER_FILTERS = {
    "official": "校方", "department": "系所", "club": "社團", "external": "校外",
}
SCHOOL_FILTERS = {"all": "清交", "nthu": "清大", "nycu": "陽明交大"}


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


def _safe_avatar_url(value: str | None) -> str | None:
    """Only proxy provider-supplied Google avatar URLs."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or not (hostname == "googleusercontent.com" or hostname.endswith(".googleusercontent.com"))
    ):
        return None
    return value


def _gravatar_url(email: str | None, size: int = 160) -> str | None:
    """Return a Gravatar URL that 404s when the email has no avatar."""
    if not isinstance(email, str) or "@" not in email:
        return None
    normalized = email.strip().lower()
    digest = hashlib.md5(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={size}&d=404"


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
    feed_signing_key: str = ""
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
        feed_signing_key = env.get("CHUMEI_FEED_SIGNING_KEY", "").strip()
        if not feed_signing_key:
            feed_signing_key = _keychain_value("tw.observe.chumei.feed-signing-key")
        if not feed_signing_key and client_secret:
            # Domain-separated fallback keeps deployment zero-touch while avoiding raw token storage.
            # An explicit feed key remains preferable because rotating OAuth credentials then has no effect.
            feed_signing_key = hashlib.sha256(
                ("chumei-saved-feed-v1\0" + client_secret).encode("utf-8")
            ).hexdigest()
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            google_client_id=google_client_id,
            google_client_secret=google_client_secret,
            feed_signing_key=feed_signing_key,
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
                    avatar_url TEXT,
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
                CREATE TABLE IF NOT EXISTS source_fetch_requests (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    next_attempt_at INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS source_fetch_requests_queue
                    ON source_fetch_requests(status, created_at);
                CREATE INDEX IF NOT EXISTS source_fetch_requests_user
                    ON source_fetch_requests(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS user_saved_feeds (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    public_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    rule_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS user_saved_feeds_user
                    ON user_saved_feeds(user_id, created_at, id);
                """
            )
            ensure_apify_schema(conn)
            columns = {r[1] for r in conn.execute("PRAGMA table_info(oauth_states)")}
            if "link_user_id" not in columns:
                conn.execute("ALTER TABLE oauth_states ADD COLUMN link_user_id TEXT")
            user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
            if "handle" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN handle TEXT")
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_handle ON users(handle)")
            if "calendar_token" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN calendar_token TEXT")
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS users_calendar_token ON users(calendar_token)"
                )
            if "profile_public" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN profile_public INTEGER NOT NULL DEFAULT 1")
            identity_cols = {r[1] for r in conn.execute("PRAGMA table_info(oauth_identities)")}
            if "avatar_url" not in identity_cols:
                conn.execute("ALTER TABLE oauth_identities ADD COLUMN avatar_url TEXT")
            fetch_cols = {r[1] for r in conn.execute("PRAGMA table_info(source_fetch_requests)")}
            if "next_attempt_at" not in fetch_cols:
                conn.execute("ALTER TABLE source_fetch_requests ADD COLUMN next_attempt_at INTEGER NOT NULL DEFAULT 0")
            # 舊帳號補代號：每個帳號都要有公開個人頁的網址
            for row in conn.execute(
                "SELECT id, display_name, email FROM users WHERE handle IS NULL OR handle = ''"
            ).fetchall():
                conn.execute(
                    "UPDATE users SET handle = ? WHERE id = ?",
                    (self._free_handle(conn, row["email"] or row["display_name"]), row["id"]),
                )

    @staticmethod
    def _free_handle(conn, seed: str | None) -> str:
        base = re.sub(r"[^a-z0-9_]+", "_", (seed or "").split("@", 1)[0].lower()).strip("_")[:20]
        if len(base) < 3:
            base = (base + "_user")[:20]
        if base in RESERVED_HANDLES:
            base = base[:18] + "_1"
        candidate, n = base, 1
        while conn.execute("SELECT 1 FROM users WHERE handle = ?", (candidate,)).fetchone():
            n += 1
            suffix = str(n)
            candidate = base[:20 - len(suffix)] + suffix
        return candidate

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

    @staticmethod
    def _avatar_candidates_for_user(
        conn: sqlite3.Connection, user_id: str, fallback_email: str | None = None
    ) -> list[tuple[str, str]]:
        identities = conn.execute(
            "SELECT provider, email, avatar_url FROM oauth_identities WHERE user_id = ? "
            "ORDER BY CASE provider WHEN 'google' THEN 0 ELSE 1 END, created_at",
            (user_id,),
        ).fetchall()
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(url: str | None, source: str) -> None:
            if url and url not in seen:
                candidates.append((url, source))
                seen.add(url)

        google = [i for i in identities if i["provider"] == "google"]
        nycu = [i for i in identities if i["provider"] == "nycu"]
        for identity in google:
            add(_safe_avatar_url(identity["avatar_url"]), "google")
        for identity in google:
            add(_gravatar_url(identity["email"]), "google_gravatar")
        for identity in nycu:
            add(_gravatar_url(identity["email"]), "nycu_gravatar")
        if not identities:
            add(_gravatar_url(fallback_email), "gravatar")
        return candidates

    @classmethod
    def _attach_avatar(cls, conn: sqlite3.Connection, user: dict) -> dict:
        candidates = cls._avatar_candidates_for_user(
            conn, user["id"], user.get("email")
        )
        user["_avatar_candidates"] = candidates
        if candidates:
            user["avatar_url"], user["avatar_source"] = candidates[0]
        else:
            user["avatar_url"], user["avatar_source"] = None, None
        return user

    def get_or_create_user(
        self,
        provider: str,
        subject: str,
        email: str | None,
        avatar_url: str | None = None,
    ) -> dict:
        now = _now()
        display_name = (email or subject).split("@", 1)[0][:80] or "竹梅使用者"
        avatar_url = _safe_avatar_url(avatar_url) if provider == "google" else None
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
                    "UPDATE oauth_identities SET email = ?, avatar_url = COALESCE(?, avatar_url), updated_at = ? "
                    "WHERE provider = ? AND subject = ?",
                    (email, avatar_url, now, provider, subject),
                )
                conn.execute(
                    "UPDATE users SET email = COALESCE(?, email), updated_at = ? WHERE id = ?",
                    (email, now, row["id"]),
                )
                return dict(row)

            user_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users(id, display_name, email, handle, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, display_name, email, self._free_handle(conn, email or subject), now, now),
            )
            conn.execute(
                "INSERT INTO oauth_identities(provider, subject, user_id, email, avatar_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (provider, subject, user_id, email, avatar_url, now, now),
            )
            return {"id": user_id, "display_name": display_name, "email": email}

    def identities_for_user(self, user_id: str) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT provider, subject, email, avatar_url FROM oauth_identities "
                "WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def link_identity(
        self,
        user_id: str,
        provider: str,
        subject: str,
        email: str | None,
        avatar_url: str | None = None,
    ) -> str:
        """把 (provider, subject) 綁到 user_id。回傳 ok / merged / already。

        若該身分已屬於另一個使用者，把對方的追蹤、參加、回報、Apify 貢獻與 session
        全部搬過來再刪除對方（merged）。
        """
        now = _now()
        avatar_url = _safe_avatar_url(avatar_url) if provider == "google" else None
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT user_id FROM oauth_identities WHERE provider = ? AND subject = ?",
                (provider, subject),
            ).fetchone()
            if row and row["user_id"] == user_id:
                conn.execute(
                    "UPDATE oauth_identities SET email = ?, avatar_url = COALESCE(?, avatar_url), updated_at = ? "
                    "WHERE provider = ? AND subject = ?",
                    (email, avatar_url, now, provider, subject),
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
                    "UPDATE user_saved_feeds SET user_id = ? WHERE user_id = ?",
                    (user_id, other_id),
                )
                conn.execute(
                    "UPDATE sessions SET user_id = ? WHERE user_id = ?", (user_id, other_id)
                )
                conn.execute(
                    "UPDATE apify_contributions SET user_id = ?, updated_at = ? WHERE user_id = ?",
                    (user_id, now, other_id),
                )
                conn.execute(
                    "UPDATE oauth_identities SET user_id = ?, email = ?, avatar_url = COALESCE(?, avatar_url), updated_at = ? "
                    "WHERE user_id = ?",
                    (user_id, email, avatar_url, now, other_id),
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
                "INSERT INTO oauth_identities(provider, subject, user_id, email, avatar_url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (provider, subject, user_id, email, avatar_url, now, now),
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

    def update_profile(self, user_id: str, display_name: str, handle: str, public: bool) -> str:
        """回傳 ok / handle_taken。"""
        now = _now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            taken = conn.execute(
                "SELECT 1 FROM users WHERE handle = ? AND id <> ?", (handle, user_id)
            ).fetchone()
            if taken:
                return "handle_taken"
            conn.execute(
                "UPDATE users SET display_name = ?, handle = ?, profile_public = ?, updated_at = ? "
                "WHERE id = ?",
                (display_name, handle, 1 if public else 0, now, user_id),
            )
            return "ok"

    def user_by_handle(self, handle: str) -> dict | None:
        if not handle:
            return None
        with self._connection() as conn:
            row = conn.execute(
                "SELECT id, display_name, email, handle, profile_public, created_at FROM users "
                "WHERE handle = ?",
                (handle.lower(),),
            ).fetchone()
            if not row:
                return None
            user = self._attach_avatar(conn, dict(row))
        return user

    def calendar_token(self, user_id: str, rotate: bool = False) -> str:
        """每個帳號一組私密行事曆 token；rotate=True 換新（舊連結立即失效）。"""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT calendar_token FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            token = row["calendar_token"] if row else None
            if not token or rotate:
                token = secrets.token_urlsafe(24)
                conn.execute(
                    "UPDATE users SET calendar_token = ?, updated_at = ? WHERE id = ?",
                    (token, _now(), user_id),
                )
            return token

    def user_by_calendar_token(self, token: str) -> dict | None:
        if not token:
            return None
        with self._connection() as conn:
            row = conn.execute(
                "SELECT id, display_name, handle FROM users WHERE calendar_token = ?", (token,)
            ).fetchone()
        return dict(row) if row else None

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
                SELECT u.id, u.display_name, u.email, u.handle, u.profile_public, u.created_at,
                       i.provider, i.subject
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                JOIN oauth_identities i ON i.user_id = u.id
                WHERE s.token_hash = ? AND s.expires_at > ?
                ORDER BY i.created_at
                LIMIT 1
                """,
                (_hash_token(raw_token), now),
            ).fetchone()
            if not row:
                return None
            user = self._attach_avatar(conn, dict(row))
        return user

    def delete_session(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (_hash_token(raw_token),)
            )

    @staticmethod
    def _fetch_request_payload(row: sqlite3.Row | dict) -> dict:
        item = dict(row)
        return {
            "id": item["id"], "sourceId": item["source_id"],
            "sourceName": item["source_name"], "sourceKind": item["source_kind"],
            "status": item["status"], "reason": item.get("reason") or "",
            "createdAt": item["created_at"], "updatedAt": item["updated_at"],
        }

    def fetch_requests_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM source_fetch_requests WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?", (user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._fetch_request_payload(row) for row in rows]

    def create_fetch_request(
        self, user_id: str, source: dict, daily_limit: int = FETCH_REQUEST_DAILY_LIMIT
    ) -> tuple[str, dict | None]:
        now = _now()
        day_start = now - (now % 86400)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM source_fetch_requests WHERE source_id = ? "
                "AND status IN ('pending','processing','deferred') ORDER BY created_at LIMIT 1",
                (source["id"],),
            ).fetchone()
            if existing:
                return "duplicate", self._fetch_request_payload(existing)
            used = conn.execute(
                "SELECT count(*) FROM source_fetch_requests WHERE user_id = ? AND created_at >= ?",
                (user_id, day_start),
            ).fetchone()[0]
            if used >= daily_limit:
                return "limit", None
            request_id = "fetch_" + uuid.uuid4().hex[:16]
            conn.execute(
                "INSERT INTO source_fetch_requests(id,user_id,source_id,source_name,source_kind,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,'pending',?,?)",
                (request_id, user_id, source["id"], source["name"], source["kind"], now, now),
            )
            row = conn.execute("SELECT * FROM source_fetch_requests WHERE id = ?", (request_id,)).fetchone()
        return "ok", self._fetch_request_payload(row)

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
        """加入／移除「我會去」。"""
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

    @staticmethod
    def _saved_feed_row(row: sqlite3.Row | dict) -> dict:
        item = dict(row)
        try:
            item["rule"] = json.loads(item.pop("rule_json"))
        except (json.JSONDecodeError, TypeError):
            item["rule"] = {"school": "all", "categories": [], "campuses": [],
                            "organizers": [], "followed": False}
            item.pop("rule_json", None)
        return item

    def saved_feeds_for_user(self, user_id: str) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM user_saved_feeds WHERE user_id = ? ORDER BY created_at, id",
                (user_id,),
            ).fetchall()
        return [self._saved_feed_row(row) for row in rows]

    def saved_feed_by_public_id(self, public_id: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_saved_feeds WHERE public_id = ?", (public_id,)
            ).fetchone()
        return self._saved_feed_row(row) if row else None

    def create_saved_feed(self, user_id: str, name: str, rule: dict) -> tuple[str, dict | None]:
        now = _now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute(
                "SELECT COUNT(*) FROM user_saved_feeds WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            if count >= SAVED_FEED_LIMIT:
                return "limit", None
            feed_id = "feed_" + uuid.uuid4().hex[:16]
            public_id = secrets.token_urlsafe(12)
            conn.execute(
                "INSERT INTO user_saved_feeds(id,user_id,public_id,name,rule_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (feed_id, user_id, public_id, name,
                 json.dumps(rule, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                 now, now),
            )
            row = conn.execute(
                "SELECT * FROM user_saved_feeds WHERE id = ?", (feed_id,)
            ).fetchone()
        return "ok", self._saved_feed_row(row)

    def update_saved_feed(self, user_id: str, feed_id: str, name: str, rule: dict) -> dict | None:
        with self._connection() as conn:
            changed = conn.execute(
                "UPDATE user_saved_feeds SET name = ?, rule_json = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (name, json.dumps(rule, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                 _now(), feed_id, user_id),
            ).rowcount
            row = conn.execute(
                "SELECT * FROM user_saved_feeds WHERE id = ? AND user_id = ?",
                (feed_id, user_id),
            ).fetchone() if changed else None
        return self._saved_feed_row(row) if row else None

    def delete_saved_feed(self, user_id: str, feed_id: str) -> bool:
        with self._connection() as conn:
            return bool(conn.execute(
                "DELETE FROM user_saved_feeds WHERE id = ? AND user_id = ?",
                (feed_id, user_id),
            ).rowcount)

    def rotate_saved_feed(self, user_id: str, feed_id: str) -> dict | None:
        with self._connection() as conn:
            changed = conn.execute(
                "UPDATE user_saved_feeds SET public_id = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (secrets.token_urlsafe(12), _now(), feed_id, user_id),
            ).rowcount
            row = conn.execute(
                "SELECT * FROM user_saved_feeds WHERE id = ? AND user_id = ?",
                (feed_id, user_id),
            ).fetchone() if changed else None
        return self._saved_feed_row(row) if row else None


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

    def profile(self, access_token: str) -> tuple[str, str | None, str | None]:
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
        return subject.strip(), email, None


class GoogleOAuthClient:
    """Google OpenID Connect（Authorization Code + PKCE）；取得 sub、email 與頭貼。"""

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

    def profile(self, access_token: str) -> tuple[str, str | None, str | None]:
        response = self.http.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        subject = payload.get("sub")
        email = payload.get("email")
        avatar_url = _safe_avatar_url(payload.get("picture"))
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Google userinfo response did not contain sub")
        if not isinstance(email, str) or "@" not in email:
            email = None
        return subject.strip(), email, avatar_url


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
    """帳號頁把「我會去」的 event_id 對回標題／日期；以 mtime 快取整份 events.json。"""
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


def _normalize_feed_rule(raw: object, *, allow_followed: bool = True) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("rule must be an object")
    school = str(raw.get("school") or "all")
    if school not in SCHOOL_FILTERS:
        raise ValueError("unknown school")

    def values(key: str, allowed: dict[str, str]) -> list[str]:
        source = raw.get(key) or []
        if not isinstance(source, list):
            raise ValueError(f"{key} must be a list")
        out = []
        for value in source:
            value = str(value)
            if value not in allowed:
                raise ValueError(f"unknown {key} value")
            if value not in out:
                out.append(value)
        return out

    followed_value = raw.get("followed", False)
    if not isinstance(followed_value, bool):
        raise ValueError("followed must be a boolean")
    followed = followed_value if allow_followed else False
    return {
        "school": school,
        "categories": values("categories", CATEGORY_FILTERS),
        "campuses": values("campuses", CAMPUS_FILTERS),
        "organizers": values("organizers", ORGANIZER_FILTERS),
        "followed": followed,
    }


def _feed_rule_from_query(query) -> dict:
    def csv_values(key: str) -> list[str]:
        raw = str(query.get(key) or "")[:400]
        return [value for value in raw.split(",") if value]

    return _normalize_feed_rule({
        "school": query.get("school") or "all",
        "categories": csv_values("categories"),
        "campuses": csv_values("campuses"),
        "organizers": csv_values("organizers"),
    }, allow_followed=False)


def _feed_rule_summary(rule: dict) -> str:
    parts = [SCHOOL_FILTERS[rule["school"]]]
    if rule["categories"]:
        parts.append("／".join(CATEGORY_FILTERS[v] for v in rule["categories"]))
    if rule["campuses"]:
        parts.append("／".join(CAMPUS_FILTERS[v] for v in rule["campuses"]))
    if rule["organizers"]:
        parts.append("／".join(ORGANIZER_FILTERS[v] for v in rule["organizers"]))
    if rule.get("followed"):
        parts.append("我追蹤的單位")
    if len(parts) == 1:
        parts.append("全部活動")
    return "・".join(parts)


def _event_matches_feed(event: dict, rule: dict, followed_org_ids: set[int] | None = None) -> bool:
    school = rule["school"]
    if school != "all" and event.get("school") not in (school, "both"):
        return False
    if rule["categories"]:
        category = event.get("category") or "其他"
        category_slug = next(
            (slug for slug, label in CATEGORY_FILTERS.items() if slug != "other" and label == category),
            "other",
        )
        if category_slug not in rule["categories"]:
            return False
    if rule["campuses"] and event.get("campus") not in rule["campuses"]:
        return False
    if rule["organizers"] and event.get("organizer_type") not in rule["organizers"]:
        return False
    if rule.get("followed"):
        try:
            org_id = int(event.get("org_id"))
        except (TypeError, ValueError):
            return False
        if org_id not in (followed_org_ids or set()):
            return False
    return True


def _filtered_feed_events(rule: dict, followed_org_ids: set[int] | None = None) -> list[dict]:
    return [
        event for event in _events_by_id().values()
        if _event_matches_feed(event, rule, followed_org_ids)
    ]


def _saved_feed_token(public_id: str, signing_key: str) -> str:
    if not signing_key:
        return ""
    digest = hmac.new(signing_key.encode("utf-8"), public_id.encode("ascii"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")[:24]
    return f"{public_id}.{signature}"


def _saved_feed_public_id(token: str, signing_key: str) -> str | None:
    if not signing_key or "." not in token or len(token) > 100:
        return None
    public_id, _signature = token.rsplit(".", 1)
    expected = _saved_feed_token(public_id, signing_key)
    return public_id if expected and hmac.compare_digest(token, expected) else None


def _feed_ics(events: list[dict], name: str, url: str) -> str:
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    upcoming = sorted(
        (e for e in events if str(e.get("start_at") or "")[:10] >= today),
        key=lambda e: e.get("start_at") or "",
    )
    body = "\r\n".join(filter(None, (event_ics(event) for event in upcoming)))
    return ics_calendar(
        body, f"竹梅｜{name}",
        "竹梅活動觀測站的自訂活動訂閱；修改條件後會在同一個網址自動更新。",
        url,
    )


def _feed_rss(events: list[dict], name: str) -> str:
    items = []
    for event in list(reversed(events))[:80]:
        link = f"https://chumei.observe.tw/event/{event['id']}/"
        start = str(event.get("start_at") or "")
        meta = "｜".join(
            value for value in (start[:16].replace("T", " "), event.get("venue"),
                                event.get("organizer")) if value
        )
        description = html.escape(meta + ("\n" if meta else "") + str(event.get("summary") or ""))
        pub = ""
        try:
            published = datetime.fromisoformat(str(event.get("first_seen") or start))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone(timedelta(hours=8)))
            pub = format_datetime(published)
        except (TypeError, ValueError):
            pass
        items.append(
            f"<item><title>{html.escape(str(event.get('title') or '未命名活動'))}</title>"
            f"<link>{link}</link><guid isPermaLink=\"true\">{link}</guid>"
            + (f"<pubDate>{pub}</pubDate>" if pub else "")
            + f"<description>{description}</description></item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{html.escape('竹梅｜' + name)}</title>"
        "<link>https://chumei.observe.tw/</link>"
        "<description>竹梅｜清大×交大校園活動觀測站</description><language>zh-tw</language>"
        + "".join(items) + "</channel></rss>"
    )


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
          <input id="submit-url" class="submit-input" type="url" name="url" required inputmode="url" placeholder="貼文或帳號主頁，例如 https://www.instagram.com/p/…" autocomplete="off">
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
        <p>IG／FB／Threads 貼文、公告頁或報名表都可以。系統會自動判讀是不是清交相關的活動：是新活動就收錄，已經有的就幫你對上，不確定的會留給人工看。</p>
        <p>也可以直接貼<strong>帳號主頁</strong>。確認是清交的單位、社團或校園媒體之後就會加進追蹤清單，之後的新貼文都自動收錄，不用等人工放行。</p>
        <p>每個連結的處理狀態都公開在下面。</p>
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
    <p>幫竹梅補上漏掉的活動，或還沒追蹤的帳號。處理進度公開，已收錄的會直接連到活動頁。</p>
  </div>
  <section class="account-card submit-card" id="submit">{inner}</section>
</section>
"""
    return page_shell(
        "回報活動｜竹梅活動觀測站",
        "把活動貼文、公告或帳號主頁的連結回報給竹梅，系統會自動判讀收錄。",
        content,
        canonical="https://chumei.observe.tw/submit/",
    )


def _calendar_ics(going_ids: list[str], owner: str = "") -> str:
    """「我會去」私密行事曆：所有加入過的活動（含已結束，行事曆自己會留歷史）。"""
    name = f"竹梅｜{owner} 會去的活動" if owner else "竹梅｜我會去的活動"
    desc = ("在竹梅活動觀測站加入「我會去」的活動。加入或移除後，行事曆下次同步就會更新。"
            + (f"（帳號：{owner}）" if owner else ""))
    by_id = _events_by_id()
    events = [by_id[i] for i in going_ids if i in by_id]
    events.sort(key=lambda e: e.get("start_at") or "")
    body = "\r\n".join(filter(None, (event_ics(e) for e in events)))
    return ics_calendar(body, name, desc, "https://chumei.observe.tw/account/")


def _saved_feed_payload(item: dict, config: AuthConfig) -> dict:
    token = _saved_feed_token(item["public_id"], config.feed_signing_key)
    stem = f"{config.public_base_url}/feeds/s/{token}" if token else ""
    return {
        "id": item["id"],
        "name": item["name"],
        "rule": item["rule"],
        "summary": _feed_rule_summary(item["rule"]),
        "ics": f"{stem}.ics" if stem else "",
        "rss": f"{stem}.xml" if stem else "",
        "createdAt": item["created_at"],
        "updatedAt": item["updated_at"],
    }


def _saved_feeds_html(feeds: list[dict], configured: bool) -> str:
    if not configured:
        return '<p class="account-empty">自訂訂閱服務正在設定中，既有「我會去」行事曆仍可正常使用。</p>'
    rows = []
    for feed in feeds:
        feed_id = html.escape(feed["id"])
        name = html.escape(feed["name"])
        summary = html.escape(feed["summary"])
        ics_url = html.escape(feed["ics"], quote=True)
        rss_url = html.escape(feed["rss"], quote=True)
        webcal = ics_url.replace("https://", "webcal://", 1)
        rows.append(f"""<article class="saved-feed">
          <div class="saved-feed-head"><div><strong>{name}</strong><p>{summary}</p></div>
            <a class="account-bind" href="/subscribe/?edit={feed_id}#custom">編輯 →</a></div>
          <div class="account-cal-row saved-feed-links">
            <input readonly value="{ics_url}" aria-label="{name} 行事曆網址" onclick="this.select()">
            <a class="btn" href="{webcal}">Apple 日曆</a>
            <a class="btn" href="https://calendar.google.com/calendar/render?cid={quote(webcal, safe='')}" target="_blank" rel="noopener">Google 日曆</a>
            <button class="btn saved-feed-copy" type="button" data-copy="{rss_url}">複製 RSS</button>
          </div>
          <div class="saved-feed-manage">
            <form method="post" action="/auth/saved-feeds/{feed_id}/rotate" onsubmit="return confirm('換新網址後，舊的行事曆與 RSS 訂閱會立即失效。要繼續嗎？')"><button type="submit">換新網址</button></form>
            <form method="post" action="/auth/saved-feeds/{feed_id}/delete" onsubmit="return confirm('確定刪除這組訂閱？已加入外部 App 的網址也會失效。')"><button type="submit">刪除</button></form>
          </div>
        </article>""")
    listing = "".join(rows) if rows else '<p class="account-empty">還沒有自訂訂閱。建立後可以隨時修改條件，不必重新加入行事曆。</p>'
    add_label = "再建立一組" if feeds else "建立第一組訂閱"
    return listing + f'<p class="account-links"><a href="/subscribe/#custom">{add_label} →</a></p>'


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
        parts.append('<p class="account-empty">還沒有加入「我會去」的活動。到<a href="/events/">活動總覽</a>按「我會去」，它們就會出現在這裡。</p>')
    if past:
        parts.append(f'<details class="account-past"><summary>已結束（{len(past)} 場）</summary>'
                     '<ul class="account-events">' + "".join(row(*p) for p in past) + "</ul></details>")
    return "".join(parts)


def _avatar_html(user: dict, size: str = "") -> str:
    initial = (user.get("display_name") or user.get("handle") or "竹")[:1].upper()
    avatar_url = _safe_avatar_url(user.get("avatar_url")) or (
        user.get("avatar_url")
        if str(user.get("avatar_source") or "").endswith("gravatar")
        else None
    )
    handle = str(user.get("handle") or "")
    avatar_src = f"/auth/avatar/{quote(handle, safe='')}" if avatar_url and handle else ""
    image = (
        f'<img src="{html.escape(avatar_src, quote=True)}" alt="" '
        'referrerpolicy="no-referrer" onerror="this.remove()">'
        if avatar_url else ""
    )
    return (
        f'<span class="profile-avatar{(" " + size) if size else ""}" aria-hidden="true">'
        f'{html.escape(initial)}{image}</span>'
    )


def _joined(user: dict) -> str:
    try:
        return time.strftime("%Y/%m", time.localtime(int(user.get("created_at") or 0)))
    except (TypeError, ValueError, OverflowError):
        return ""


def _follow_chips_html(follows: list[dict], owner: bool) -> str:
    if follows:
        chips = []
        for org in follows:
            name = html.escape(org.get("name") or f"單位 {org['id']}")
            chips.append(f'<a class="account-chip" href="/org/{org["id"]}/">{name}</a>')
        return f'<div class="account-chips">{"".join(chips)}</div>'
    if owner:
        return '<p class="account-empty">還沒有追蹤任何單位。在貼文、活動卡或單位頁按 🔔 就會出現在這裡。</p>'
    return '<p class="account-empty">還沒有追蹤任何單位。</p>'


def _profile_html(
    profile: dict,
    viewer: dict | None,
    following: list[dict],
    going_ids: list[str],
) -> str:
    """公開個人頁 /@handle：名稱、代號、追蹤的單位、我會去的活動。"""
    owner = bool(viewer and viewer["id"] == profile["id"])
    name = html.escape(profile.get("display_name") or "竹梅使用者")
    handle = html.escape(profile.get("handle") or "")
    joined = _joined(profile)
    byid = _events_by_id()
    today = time.strftime("%Y-%m-%d")
    upcoming_n = sum(1 for eid in going_ids
                     if eid in byid and str(byid[eid].get("start_at") or "")[:10] >= today)
    actions = ""
    if owner:
        actions = ('<div class="profile-actions">'
                   '<a class="btn account-action" href="/account/">編輯個人檔案</a>'
                   '<button class="btn account-action profile-share" type="button" '
                   f'data-url="https://chumei.observe.tw/@{handle}">分享個人頁</button></div>')
    private_note = ""
    if owner and not profile.get("profile_public"):
        private_note = '<p class="account-hint">這個個人頁目前設為不公開，只有你看得到。可在<a href="/account/">帳號設定</a>改。</p>'
    going_block = (_going_html(going_ids) if owner
                   else _going_html([eid for eid in going_ids
                                     if eid in byid and str(byid[eid].get("start_at") or "")[:10] >= today]))
    content = f"""
<section class="account-page profile-page">
  <header class="profile-head">
    {_avatar_html(profile, "lg")}
    <div class="profile-id">
      <h1>{name}</h1>
      <p class="profile-handle">@{handle}{f'<span class="profile-joined">・{joined} 加入</span>' if joined else ''}</p>
      <p class="profile-stats"><span><strong>{len(following)}</strong> 追蹤的單位</span><span><strong>{upcoming_n}</strong> 場會去</span></p>
    </div>
    {actions}
  </header>
  {private_note}
  <section class="account-card account-section">
    <h2>追蹤的單位{f'<span class="account-count">{len(following)}</span>' if following else ''}</h2>
    {_follow_chips_html(following, owner)}
  </section>
  <section class="account-card account-section">
    <h2>我會去的活動</h2>
    {going_block}
  </section>
</section>
"""
    return page_shell(
        f"{name}（@{handle}）｜竹梅活動觀測站",
        f"{name} 在竹梅追蹤的單位與會去的活動。",
        content,
        canonical=f"https://chumei.observe.tw/@{handle}",
    )


def _login_card_html(nycu_ok: bool, google_ok: bool, return_to: str = "/account/") -> str:
    if nycu_ok or google_ok:
        encoded_return = quote(_safe_return_to(return_to), safe="/")
        nycu_btn = (f'<a class="btn btn-primary account-action" href="/auth/nycu/start?return_to={encoded_return}">使用陽明交大 OAuth 登入</a>'
                    if nycu_ok else "")
        google_btn = (f'<a class="btn account-action" href="/auth/google/start?return_to={encoded_return}">使用 Google 帳號登入</a>'
                      if google_ok else "")
        return f"""<section class="account-card">
        <p class="eyebrow">OAuth-only account</p>
        <h2>登入竹梅</h2>
        <p>陽明交大成員請走學校單一入口；清大朋友、校友與其他人可用 Google 帳號登入。竹梅不會取得或儲存你的密碼。</p>
        {nycu_btn}
        {google_btn}
        <p class="privacy-note">登入只取得穩定的帳號識別與 Email，用來記住你的追蹤、參加標記與<a href="/submit/">回報的連結</a>。</p>
        </section>"""
    return """<section class="account-card">
        <p class="eyebrow">OAuth-only account</p>
        <h2>登入功能設定中</h2>
        <p>OAuth Client 尚未完成設定，請稍後再試。</p>
        <span class="btn btn-primary account-action disabled" aria-disabled="true">登入竹梅</span>
        </section>"""


def _account_html(
    user: dict | None,
    nycu_ok: bool,
    google_ok: bool,
    *,
    title: str = "帳號設定",
    message: str | None = None,
    my_submissions: list[dict] | None = None,
    identities: list[dict] | None = None,
    calendar_token: str | None = None,
    saved_feeds: list[dict] | None = None,
    saved_feeds_configured: bool = False,
    return_to: str = "/account/",
    message_ok: bool = False,
) -> str:
    """帳號設定 /account/：個人檔案、登入方式、行事曆、回報、登出。未登入＝登入頁。"""
    sections = []
    if user:
        handle = html.escape(user.get("handle") or "")
        name = html.escape(user.get("display_name") or "竹梅使用者")
        public = bool(user.get("profile_public", 1))
        # ---- 個人檔案
        sections.append(f"""<section class="account-card account-section">
        <h2>個人檔案</h2>
        <div class="profile-row">{_avatar_html(user)}<div><strong>{name}</strong><span class="profile-handle">@{handle}</span></div>
          <a class="account-bind" href="/@{handle}">查看個人頁 →</a></div>
        <form method="post" action="/auth/profile" class="account-profile-form">
          <label><span>顯示名稱</span><input name="display_name" maxlength="80" required value="{name}"></label>
          <label><span>帳號代號</span><span class="account-handle-input"><span class="at">@</span>
            <input name="handle" maxlength="20" pattern="[a-z0-9_]{{3,20}}" required autocapitalize="off" autocorrect="off"
            spellcheck="false" value="{handle}"></span></label>
          <p class="account-hint">代號限小寫英數與底線，3–20 字，全站唯一；個人頁網址是 chumei.observe.tw/@代號。</p>
          <label class="account-check"><input type="checkbox" name="public" value="1"{' checked' if public else ''}>
            <span>公開個人頁<small>其他人能看到你追蹤的單位與即將參加的活動；關掉後只有你自己看得到。</small></span></label>
          <button class="btn btn-primary account-action" type="submit">儲存</button>
        </form>
        </section>""")

        # ---- 登入方式
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
            status_line = "以 Google 帳號登入"
        else:
            status_line = "以陽明交大 OAuth 登入"
        bind_hint = ("" if can_unlink else
                     '<p class="account-hint">綁定另一種登入方式後，用哪個帳號登入都會回到同一份追蹤與回報。</p>')
        sections.append(f"""<section class="account-card account-section">
        <h2>登入方式</h2>
        <div class="account-status"><span class="account-dot"></span>{status_line}</div>
        <dl>{''.join(rows)}</dl>
        {bind_hint}
        </section>""")

        # ---- 自訂活動訂閱
        feeds = saved_feeds or []
        sections.append(f"""<section class="account-card account-section">
        <h2>我的活動訂閱{f'<span class="account-count">{len(feeds)}</span>' if feeds else ''}</h2>
        <p class="account-hint">每組訂閱都能同時提供行事曆與 RSS；修改條件後原網址會自動更新。網址等同存取權，請不要公開貼出。</p>
        {_saved_feeds_html(feeds, saved_feeds_configured)}
        </section>""")

        # ---- 我會去行事曆
        if calendar_token:
            cal_owner = user.get("handle") or user.get("display_name") or ""
            cal_name = f"竹梅｜{cal_owner} 會去的活動" if cal_owner else "竹梅｜我會去的活動"
            cal_url = f"https://chumei.observe.tw/auth/calendar/{html.escape(calendar_token)}.ics"
            webcal = cal_url.replace("https://", "webcal://", 1)
            sections.append(f"""<section class="account-card account-section">
        <h2>我會去的活動行事曆</h2>
        <p class="account-hint">把這個私密連結加到 Google／Apple 行事曆，加入「我會去」的活動會自動出現、移除也會消失（行事曆每幾小時同步一次）。</p>
        <div class="account-calendar-actions" aria-label="加入行事曆">
          <a class="btn btn-primary account-action" href="{webcal}">訂閱到 Apple 行事曆</a>
          <a class="btn account-action" href="https://calendar.google.com/calendar/render?cid={quote(webcal, safe='')}" target="_blank" rel="noopener">訂閱到 Google 日曆</a>
        </div>
        <div class="account-private-link">
          <div class="account-private-link-text">
            <span>私密訂閱連結</span>
            <code title="{cal_url}">{cal_url}</code>
          </div>
          <button class="btn saved-feed-copy" type="button" data-copy="{cal_url}">複製連結</button>
        </div>
        <p class="account-hint">Apple 行事曆會自動命名為「{html.escape(cal_name)}」；Google 日曆一律拿網址當名稱，加入後請到該行事曆的設定把名稱改成
          <code class="account-copy" title="點一下複製" onclick="navigator.clipboard&&navigator.clipboard.writeText(this.textContent)">{html.escape(cal_name)}</code>。</p>
        <form method="post" action="/auth/calendar/rotate" class="account-unlink"
          onsubmit="return confirm('換新連結後，舊連結會立即失效，要繼續嗎？')">
          <button type="submit">連結外流了？換一組新的</button>
        </form>
        </section>""")

        # ---- 回報
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

    else:
        sections.append(_login_card_html(nycu_ok, google_ok, return_to))

    alert = (f'<div class="account-alert{" ok" if message_ok else ""}">{html.escape(message)}</div>'
             if message else "")
    if message:
        lede = ""
    elif user:
        lede = "<p>個人檔案、登入方式、行事曆訂閱與回報進度。</p>"
    else:
        lede = "<p>登入後可以追蹤單位、加入「我會去」的活動、回報連結，並擁有自己的個人頁。</p>"
    page_title = title if user or title != "帳號設定" else "登入"
    logout_form = ('<form method="post" action="/auth/logout" class="account-logout account-logout-top">'
                   '<button class="btn account-action" type="submit">登出</button></form>'
                   if user else "")
    content = f"""
<section class="account-page">
  <div class="hero account-hero-row">
    <div>
      <h1>{html.escape(page_title)}</h1>
      {lede}
    </div>
    {logout_form}
  </div>
  {alert}
  {"".join(sections)}
</section>
<script>
document.addEventListener("click",function(event){{
  var button=event.target.closest(".saved-feed-copy");
  if(!button||!navigator.clipboard)return;
  var original=button.textContent;
  navigator.clipboard.writeText(button.dataset.copy).then(function(){{
    button.textContent="已複製 ✓";
    setTimeout(function(){{button.textContent=original;}},1200);
  }});
}});
</script>
"""
    return page_shell(
        f"{page_title}｜竹梅活動觀測站",
        "管理你的竹梅帳號：登入方式、個人檔案、行事曆訂閱與回報。",
        content,
        canonical="https://chumei.observe.tw/account/",
    )


def _contribution_time(value: object) -> str:
    if not value:
        return "尚無資料"
    try:
        if isinstance(value, (int, float)):
            moment = datetime.fromtimestamp(float(value), timezone.utc)
        else:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.astimezone(timezone(timedelta(hours=8))).strftime("%Y/%-m/%-d %-H:%M")
    except (TypeError, ValueError, OSError):
        return "尚無資料"


def _contribute_html(
    user: dict | None,
    public: dict,
    mine: list[dict],
    *,
    encryption_ready: bool,
    nycu_ok: bool,
    google_ok: bool,
) -> str:
    esc = html.escape
    totals = public["totals"]
    scoreboard_rows = []
    for rank, row in enumerate(public["scoreboard"], 1):
        name = esc(str(row["name"]))
        person = (
            f'<a href="/@{quote(str(row["handle"]), safe="")}">{name}</a>'
            if row.get("handle") else name
        )
        scoreboard_rows.append(
            f'<tr><td class="contrib-rank">{rank}</td><td>{person}</td>'
            f'<td>{int(row["accounts"])} / {int(row["usableAccounts"])}</td>'
            f'<td>+{int(row["priorityBonus"])}</td>'
            f'<td>US${float(row["remainingUsd"]):.2f}</td></tr>'
        )
    scoreboard_body = (
        "".join(scoreboard_rows)
        if scoreboard_rows
        else '<tr><td colspan="5" class="contrib-empty">還沒有社群貢獻，第一名等你。</td></tr>'
    )

    account_rows = []
    for row in public["accounts"]:
        name = esc(str(row["contributor"]))
        person = (
            f'<a href="/@{quote(str(row["handle"]), safe="")}">{name}</a>'
            if row.get("handle") else name
        )
        account_rows.append(
            '<article class="contrib-account">'
            f'<div><strong>{esc(str(row["accountLabel"]))}</strong>'
            f'<span>{person} · {"本期可使用" if row["usable"] else "有效貢獻（本期已用盡）"}</span></div>'
            f'<div><strong>US${float(row["remainingUsd"]):.3f}</strong><span>本期剩餘</span></div>'
            f'<div><strong>{_contribution_time(row.get("cycleEnd"))}</strong><span>額度重置</span></div>'
            '</article>'
        )
    accounts_body = "".join(account_rows) or '<p class="contrib-empty">目前沒有有效的社群帳號。</p>'

    if user:
        my_rows = []
        for row in mine:
            active = row["status"] == "active"
            state_label = (
                "有效貢獻" if active and row["usable"] else
                "有效貢獻（本期已用盡）" if active else
                "憑證已失效" if row["status"] == "invalid" else "已停止"
            )
            action = (
                f'<button type="button" class="btn contrib-disable" data-disable="{esc(row["publicId"])}">停止貢獻</button>'
                if active else '<span class="contrib-muted">已停止；重新提交同一 token 即可恢復</span>'
            )
            actions = (
                '<div class="contrib-actions">'
                f'<button type="button" class="btn" data-rename="{esc(row["publicId"])}" '
                f'data-name="{esc(row["accountLabel"])}">重新命名</button>{action}</div>'
            )
            my_rows.append(
                '<article class="contrib-my-row">'
                f'<div><strong>{esc(row["accountLabel"])}</strong>'
                f'<span>{state_label} · 本期剩餘 US${float(row["remainingUsd"]):.3f}</span></div>'
                f'<div><strong>+{int(row["priorityBonus"])}</strong><span>每日優先抓取</span></div>{actions}'
                '</article>'
            )
        my_body = "".join(my_rows) or '<p class="contrib-empty">你還沒有貢獻 Apify 帳號。</p>'
        form_disabled = "" if encryption_ready else " disabled"
        form_note = (
            "token 送到竹梅伺服器後會立即驗證並加密保存；公開頁只顯示你取的名稱與額度。"
            if encryption_ready else "伺服器的貢獻加密金鑰尚未設定，目前暫停收件。"
        )
        action = f"""
<section class="contrib-panel" id="my-contributions">
  <div class="contrib-heading"><div><p class="eyebrow">你的貢獻</p><h2>新增 Apify 帳號</h2></div><span class="contrib-rule">每個有效貢獻＝每日 +3 次優先抓取</span></div>
  <form id="contribution-form" class="contrib-form">
    <label for="apify-name">帳號名稱</label>
    <input id="apify-name" name="name" type="text" autocomplete="off" maxlength="{MAX_ACCOUNT_NAME_LENGTH}" placeholder="例如：社團帳號、MY-APIFY" required{form_disabled}>
    <label for="apify-token">Apify API token</label>
    <div class="contrib-token-row"><input id="apify-token" name="token" type="password" autocomplete="off" spellcheck="false" placeholder="apify_api_…" required{form_disabled}><button class="btn btn-primary" type="submit"{form_disabled}>驗證並貢獻</button></div>
    <p>{form_note} 每位使用者最多 {MAX_ACCOUNTS_PER_USER} 個有效帳號。</p>
    <p class="contrib-message" id="contribution-message" role="status"></p>
  </form>
  <div class="contrib-my-list">{my_body}</div>
</section>"""
    else:
        action = _login_card_html(nycu_ok, google_ok, "/contribute/")

    content = f"""
<section class="contribute-page">
  <section class="hero contrib-hero"><p class="eyebrow">Community-powered crawling</p><h1>貢獻</h1><p>替自己的 Apify Token 命名並把閒置免費額度接進竹梅，讓清大與陽明交大的 Instagram、Story 和 Facebook 公開資訊抓得更快。</p></section>
  <section class="contrib-totals" aria-label="社群貢獻總覽">
    <article><span>本期可用／有效貢獻</span><strong>{int(totals["accounts"])} / {int(totals["registeredAccounts"])}</strong></article>
    <article><span>貢獻者</span><strong>{int(totals["contributors"])}</strong></article>
    <article><span>每輪加速槽位</span><strong>+{int(totals["extraSlots"])}</strong></article>
    <article><span>本期剩餘額度</span><strong>US${float(totals["remainingUsd"]):.2f}</strong></article>
  </section>
  <section class="contrib-explain">
    <article><strong>1</strong><h2>登入後提交</h2><p>只收 Apify API token，不收密碼；伺服器先向 Apify 驗證額度。</p></article>
    <article><strong>2</strong><h2>加密加入帳號池</h2><p>token 不會出現在公開 API、排行榜、log 或 Git，只用來執行爬取 Actor。</p></article>
    <article><strong>3</strong><h2>全站一起加速</h2><p>每個有效貢獻讓貢獻者每天多 3 次優先抓取；本期仍有額度的帳號也會增加每輪抓取槽位。</p></article>
  </section>
  {action}
  <section class="contrib-grid">
    <section class="contrib-panel"><div class="contrib-heading"><div><p class="eyebrow">Scoreboard</p><h2>貢獻排行榜</h2></div></div><div class="contrib-table-wrap"><table><thead><tr><th>#</th><th>貢獻者</th><th>貢獻／本期可用</th><th>優先額度</th><th>本期剩餘</th></tr></thead><tbody>{scoreboard_body}</tbody></table></div></section>
    <section class="contrib-panel"><div class="contrib-heading"><div><p class="eyebrow">Registered pool</p><h2>已註冊帳號</h2></div><a href="/status/">查看全池狀態 →</a></div><div class="contrib-account-list">{accounts_body}</div></section>
  </section>
</section>
<style>
.contribute-page{{padding-bottom:56px}}.contrib-hero p{{max-width:760px}}.contrib-totals{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}}.contrib-totals article,.contrib-panel,.contrib-explain article{{border:1px solid var(--color-border-subtle);border-radius:var(--radius-md);background:var(--color-surface)}}.contrib-totals article{{padding:16px}}.contrib-totals span,.contrib-account span,.contrib-my-row span,.contrib-form p,.contrib-muted{{display:block;color:var(--color-text-muted);font-size:.78rem}}.contrib-totals strong{{display:block;margin-top:4px;font-size:clamp(1.55rem,3vw,2.3rem)}}.contrib-explain{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 20px}}.contrib-explain article{{padding:18px}}.contrib-explain article>strong{{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--color-surface-soft)}}.contrib-explain h2{{font-size:1rem;margin:14px 0 6px}}.contrib-explain p{{margin:0;color:var(--color-text-secondary);font-size:.84rem;line-height:1.55}}.contrib-grid{{display:grid;grid-template-columns:1.05fr .95fr;gap:12px;margin-top:12px}}.contrib-panel{{padding:18px;margin-top:12px}}.contrib-heading{{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:14px}}.contrib-heading h2{{margin:2px 0 0;font-size:1.15rem}}.contrib-heading p{{margin:0}}.contrib-heading a,.contrib-rule{{font-size:.78rem;color:var(--color-text-secondary)}}.contrib-rule{{border:1px solid var(--color-border-subtle);border-radius:var(--radius-pill);padding:5px 9px}}.contrib-form{{padding:14px;border-radius:var(--radius-md);background:var(--color-surface-soft)}}.contrib-form label{{display:block;margin:10px 0 7px;font-size:.8rem;font-weight:650}}.contrib-form label:first-child{{margin-top:0}}.contrib-token-row{{display:flex;gap:8px}}.contrib-token-row input,#apify-name{{box-sizing:border-box;min-width:0;height:42px;border:1px solid var(--color-border-strong);border-radius:var(--radius-sm);padding:0 12px;background:var(--color-canvas);color:var(--color-text-primary);font:inherit}}.contrib-token-row input{{flex:1}}#apify-name{{width:100%}}.contrib-form p{{margin:8px 0 0;line-height:1.5}}.contrib-form .contrib-message{{min-height:1.3em;color:var(--color-text-secondary)}}.contrib-my-list,.contrib-account-list{{display:grid;gap:8px;margin-top:12px}}.contrib-my-row,.contrib-account{{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:14px;padding:12px;border-top:1px solid var(--color-border-subtle)}}.contrib-account{{grid-template-columns:minmax(0,1fr) auto auto}}.contrib-account:first-child,.contrib-my-row:first-child{{border-top:0}}.contrib-account strong,.contrib-my-row strong{{display:block;font-size:.88rem}}.contrib-actions{{display:flex;gap:6px;align-items:center}}.contrib-disable{{font-size:.74rem}}.contrib-table-wrap{{overflow-x:auto}}.contrib-panel table{{width:100%;border-collapse:collapse;font-size:.82rem}}.contrib-panel th,.contrib-panel td{{padding:10px 8px;border-top:1px solid var(--color-border-subtle);text-align:left;white-space:nowrap}}.contrib-panel thead th{{border-top:0;color:var(--color-text-muted);font-size:.72rem}}.contrib-rank{{font-weight:700}}.contrib-empty{{padding:18px!important;color:var(--color-text-muted);text-align:center!important}}@media(max-width:800px){{.contrib-totals{{grid-template-columns:1fr 1fr}}.contrib-explain,.contrib-grid{{grid-template-columns:1fr}}}}@media(max-width:560px){{.contrib-token-row{{display:grid}}.contrib-my-row,.contrib-account{{grid-template-columns:1fr auto}}.contrib-actions{{grid-column:1/-1}}.contrib-my-row .contrib-disable{{width:100%}}}}
</style>
<script>
document.addEventListener('submit',async function(event){{
  if(event.target.id!=='contribution-form')return;
  event.preventDefault();
  var form=event.target,input=form.querySelector('#apify-token'),nameInput=form.querySelector('#apify-name'),message=form.querySelector('#contribution-message');
  var token=input.value.trim(),name=nameInput.value.trim(); input.value=''; message.textContent='正在向 Apify 驗證…';
  var button=form.querySelector('button[type="submit"]'); button.disabled=true;
  try{{var response=await fetch('/auth/apify-contributions',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{token:token,name:name}})}});var data=await response.json();if(!response.ok)throw new Error(data.error||'貢獻失敗');nameInput.value='';message.textContent='驗證完成，已加入社群帳號池。';setTimeout(function(){{location.reload()}},700)}}catch(error){{message.textContent=error.message;button.disabled=false}}
}});
document.addEventListener('click',async function(event){{
  var rename=event.target.closest('[data-rename]');if(rename){{var name=prompt('新的帳號名稱',rename.dataset.name||'');if(!name)return;rename.disabled=true;var renamed=await fetch('/auth/apify-contributions/'+encodeURIComponent(rename.dataset.rename),{{method:'PATCH',headers:{{'content-type':'application/json'}},body:JSON.stringify({{name:name}})}});if(renamed.ok)location.reload();else rename.disabled=false;return}}
  var button=event.target.closest('[data-disable]');if(!button)return;
  if(!confirm('停止貢獻後，竹梅會立即清除加密 token，確定嗎？'))return;
  button.disabled=true;var response=await fetch('/auth/apify-contributions/'+encodeURIComponent(button.dataset.disable),{{method:'DELETE'}});
  if(response.ok)location.reload();else button.disabled=false;
}});
</script>
"""
    return page_shell(
        "貢獻｜竹梅活動觀測站",
        "貢獻 Apify 免費額度，增加竹梅的公開資訊抓取頻率與個人優先抓取額度。",
        content,
        canonical="https://chumei.observe.tw/contribute/",
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
    avatar_cache: dict[str, tuple[float, bytes, str]] = {}
    avatar_failures: dict[str, float] = {}

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
            "scope": "openid email profile",
            "client_id": config.google_client_id,
            "redirect_uri": config.google_redirect_uri,
            "configured": config.google_configured,
            "extra": {"prompt": "select_account"},
            "cancel_msg": "Google 未授權登入，帳號沒有建立。",
            "fail_msg": "無法向 Google 完成身分驗證，請稍後再試。",
            "unconfigured_msg": "Google OAuth Client 尚未完成設定。",
        },
    }

    PROFILE_MESSAGES = {
        "ok": "已更新名稱與帳號代號。",
        "handle_taken": "這個帳號代號已經有人用了，換一個試試。",
        "bad_handle": "帳號代號只能用小寫英數與底線，3–20 字。",
        "bad_name": "顯示名稱不能空白。",
        "rotated": "已換新的行事曆連結，記得重新訂閱。",
        "feed_rotated": "已換新的自訂訂閱網址，記得在行事曆或 RSS 閱讀器重新加入。",
        "feed_deleted": "已刪除自訂訂閱，舊網址也已失效。",
    }
    OK_CODES = {"ok", "merged", "already", "unlinked", "rotated", "feed_rotated", "feed_deleted"}
    LINK_MESSAGES = {
        "ok": "綁定完成！之後用學校或 Google 帳號登入，都會回到同一個竹梅帳號。",
        "merged": "綁定完成，另一個帳號的追蹤、參加標記與回報都合併進來了。",
        "already": "這兩個帳號原本就綁在一起了。",
        "unlinked": "已解除綁定。",
        "unlink_fail": "至少要保留一種登入方式，無法解除綁定。",
    }

    async def profile_page(request: Request):
        handle = str(request.path_params.get("handle") or "")
        profile = store.user_by_handle(handle)
        viewer = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not profile or (not profile.get("profile_public") and not (viewer and viewer["id"] == profile["id"])):
            return _error_page("找不到這個個人頁", "沒有這個代號，或對方沒有公開個人頁。", 404)
        if profile["handle"] != handle:
            return RedirectResponse(f"/@{profile['handle']}", 301)
        return HTMLResponse(_profile_html(
            profile, viewer,
            store.follow_snapshot(profile["id"])["following"],
            store.event_snapshot(profile["id"])["going"],
        ))

    async def avatar_image(request: Request):
        handle = str(request.path_params.get("handle") or "").lower()
        profile = store.user_by_handle(handle)
        viewer = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not profile or (
            not profile.get("profile_public")
            and not (viewer and viewer["id"] == profile["id"])
        ):
            return Response(status_code=404)
        candidates = profile.get("_avatar_candidates") or []
        if not candidates:
            return Response(status_code=404)

        def fetch_avatar(source_url: str) -> tuple[bytes, str]:
            upstream = requests.get(
                source_url,
                headers={"User-Agent": "ChumeiAvatar/1.0"},
                timeout=10,
            )
            upstream.raise_for_status()
            content_type = (upstream.headers.get("content-type") or "").split(";", 1)[0].lower()
            if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                raise ValueError("avatar response is not an image")
            if len(upstream.content) > AVATAR_MAX_BYTES:
                raise ValueError("avatar response is too large")
            return upstream.content, content_type

        now = time.monotonic()
        for source_url, _source in candidates:
            cached = avatar_cache.get(source_url)
            if cached and cached[0] > now:
                return Response(
                    cached[1], media_type=cached[2],
                    headers={"Cache-Control": "private, max-age=300"},
                )
            if avatar_failures.get(source_url, 0) > now:
                continue
            try:
                body, content_type = await run_in_threadpool(fetch_avatar, source_url)
            except (requests.RequestException, ValueError):
                avatar_failures[source_url] = now + AVATAR_CACHE_SECONDS
                continue
            avatar_cache[source_url] = (
                now + AVATAR_CACHE_SECONDS, body, content_type
            )
            return Response(
                body, media_type=content_type,
                headers={"Cache-Control": "private, max-age=300"},
            )
        return Response(status_code=404)

    async def account(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        kwargs = {}
        if user:
            saved = [
                _saved_feed_payload(item, config)
                for item in store.saved_feeds_for_user(user["id"])
            ] if config.feed_signing_key else []
            kwargs = {
                "my_submissions": submissions.list_for_user(user["id"], 8),
                "identities": store.identities_for_user(user["id"]),
                "calendar_token": store.calendar_token(user["id"]),
                "saved_feeds": saved,
                "saved_feeds_configured": bool(config.feed_signing_key),
                "message": (LINK_MESSAGES.get(request.query_params.get("link") or "")
                            or PROFILE_MESSAGES.get(request.query_params.get("profile") or "")
                            or PROFILE_MESSAGES.get(request.query_params.get("feeds") or "")),
                "message_ok": (request.query_params.get("link") in OK_CODES
                               or request.query_params.get("profile") in OK_CODES
                               or request.query_params.get("feeds") in OK_CODES),
            }
        else:
            kwargs["return_to"] = _safe_return_to(request.query_params.get("return_to"))
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
            subject, email, avatar_url = await run_in_threadpool(
                spec["client"].profile, access_token
            )
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            return _error_page("登入暫時失敗", spec["fail_msg"], 502)
        link_user_id = state_row["link_user_id"]
        if link_user_id:
            current = store.session_user(request.cookies.get(SESSION_COOKIE))
            if not current or current["id"] != link_user_id:
                return _error_page("綁定失敗", "登入狀態已改變，請重新登入後再綁定一次。", 400)
            outcome = store.link_identity(
                current["id"], provider_key, subject, email, avatar_url
            )
            response = RedirectResponse(f"/account/?link={outcome}", 303)
            response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
            return response
        user = store.get_or_create_user(provider_key, subject, email, avatar_url)
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
                    "handle": user.get("handle"),
                    "profileUrl": f"/@{user['handle']}" if user.get("handle") else None,
                    "profilePublic": bool(user.get("profile_public", 1)),
                    "avatarUrl": (
                        f"/auth/avatar/{quote(str(user['handle']), safe='')}"
                        if user.get("avatar_url") and user.get("handle") else None
                    ),
                    "avatarSource": user.get("avatar_source"),
                    "provider": user.get("provider") or "nycu",
                    "providers": [
                        i["provider"] for i in store.identities_for_user(user["id"])
                    ],
                },
            }
        )

    async def fetch_requests(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "authentication required"}, status_code=401
            )
        contribution_count = apify_active_count(store.path, user["id"])
        priority_bonus = contribution_count * PRIORITY_BONUS_PER_ACCOUNT
        daily_limit = FETCH_REQUEST_DAILY_LIMIT + priority_bonus
        if request.method == "GET":
            return JSONResponse({
                "ok": True,
                "dailyLimit": daily_limit,
                "baseDailyLimit": FETCH_REQUEST_DAILY_LIMIT,
                "contributionBonus": priority_bonus,
                "requests": store.fetch_requests_for_user(user["id"]),
            })
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        source_id = str(body.get("sourceId") or "") if isinstance(body, dict) else ""
        if len(source_id) > 180:
            source_id = ""
        source = next((item for item in source_registry() if item["id"] == source_id), None)
        if not source:
            return JSONResponse({"ok": False, "error": "unknown source"}, status_code=400)
        code, item = store.create_fetch_request(user["id"], source, daily_limit=daily_limit)
        if code == "limit":
            return JSONResponse(
                {"ok": False, "error": "daily request limit reached", "dailyLimit": daily_limit},
                status_code=429,
            )
        return JSONResponse(
            {
                "ok": True,
                "code": code,
                "request": item,
                "dailyLimit": daily_limit,
                "contributionBonus": priority_bonus,
            },
            status_code=201 if code == "ok" else 200,
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

    def feed_payload(item: dict) -> dict:
        return _saved_feed_payload(item, config)

    def parse_feed_input(body: object) -> tuple[str, dict]:
        if not isinstance(body, dict):
            raise ValueError("invalid json")
        name = " ".join(str(body.get("name") or "").split())[:SAVED_FEED_NAME_MAX]
        rule = _normalize_feed_rule(body.get("rule"))
        if not name:
            name = _feed_rule_summary(rule)[:SAVED_FEED_NAME_MAX]
        return name, rule

    async def saved_feeds(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "authentication required"}, status_code=401
            )
        if not config.feed_signing_key:
            return JSONResponse(
                {"ok": False, "error": "saved feeds are not configured"}, status_code=503
            )
        if request.method == "GET":
            return JSONResponse({
                "ok": True,
                "limit": SAVED_FEED_LIMIT,
                "feeds": [feed_payload(item) for item in store.saved_feeds_for_user(user["id"])],
            })
        try:
            name, rule = parse_feed_input(await request.json())
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"ok": False, "error": "invalid feed"}, status_code=400)
        code, item = store.create_saved_feed(user["id"], name, rule)
        if code == "limit":
            return JSONResponse(
                {"ok": False, "error": "saved feed limit reached", "limit": SAVED_FEED_LIMIT},
                status_code=429,
            )
        return JSONResponse({"ok": True, "feed": feed_payload(item)}, status_code=201)

    async def saved_feed_item(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "authentication required"}, status_code=401
            )
        feed_id = str(request.path_params.get("feed_id") or "")
        if request.method == "DELETE":
            deleted = store.delete_saved_feed(user["id"], feed_id)
            return JSONResponse({"ok": deleted}, status_code=200 if deleted else 404)
        try:
            name, rule = parse_feed_input(await request.json())
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"ok": False, "error": "invalid feed"}, status_code=400)
        item = store.update_saved_feed(user["id"], feed_id, name, rule)
        if not item:
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        return JSONResponse({"ok": True, "feed": feed_payload(item)})

    async def saved_feed_rotate(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return RedirectResponse("/account/", 303)
        feed_id = str(request.path_params.get("feed_id") or "")
        item = store.rotate_saved_feed(user["id"], feed_id)
        if "application/json" in (request.headers.get("accept") or ""):
            return JSONResponse(
                {"ok": bool(item), "feed": feed_payload(item) if item else None},
                status_code=200 if item else 404,
            )
        return RedirectResponse("/account/?feeds=feed_rotated" if item else "/account/", 303)

    async def saved_feed_delete(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return RedirectResponse("/account/", 303)
        feed_id = str(request.path_params.get("feed_id") or "")
        deleted = store.delete_saved_feed(user["id"], feed_id)
        return RedirectResponse("/account/?feeds=feed_deleted" if deleted else "/account/", 303)

    def feed_response(fmt: str, events: list[dict], name: str, url: str) -> Response:
        if fmt == "ics":
            return Response(
                _feed_ics(events, name, url), media_type="text/calendar; charset=utf-8",
                headers={"Content-Disposition": 'inline; filename="chumei-custom.ics"'},
            )
        if fmt == "xml":
            return Response(
                _feed_rss(events, name), media_type="application/rss+xml; charset=utf-8",
                headers={"Content-Disposition": 'inline; filename="chumei-custom.xml"'},
            )
        return PlainTextResponse("not found", status_code=404)

    async def public_custom_feed(request: Request):
        try:
            rule = _feed_rule_from_query(request.query_params)
        except ValueError:
            return PlainTextResponse("invalid feed filters", status_code=400)
        name = _feed_rule_summary(rule)
        return feed_response(
            str(request.path_params.get("format") or ""),
            _filtered_feed_events(rule), name, str(request.url),
        )

    async def signed_saved_feed(request: Request):
        token = str(request.path_params.get("token") or "")
        public_id = _saved_feed_public_id(token, config.feed_signing_key)
        item = store.saved_feed_by_public_id(public_id) if public_id else None
        if not item:
            return PlainTextResponse("not found", status_code=404)
        followed = set()
        if item["rule"].get("followed"):
            followed = {
                org["id"] for org in store.follow_snapshot(item["user_id"])["following"]
            }
        return feed_response(
            str(request.path_params.get("format") or ""),
            _filtered_feed_events(item["rule"], followed), item["name"], str(request.url),
        )

    def event_payload(user: dict | None) -> dict:
        snapshot = store.event_snapshot(user["id"] if user else None)
        return {"ok": True, "authenticated": bool(user), **snapshot}

    def _event_id(request: Request) -> str:
        return str(request.path_params.get("event_id") or "")

    async def events_going(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        return JSONResponse(event_payload(user))

    async def event_going_set(request: Request):
        """PUT＝加入我會去、DELETE＝移除；計數綁帳號，一人一場只算一次。"""
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

    async def profile(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return RedirectResponse("/account/", 303)
        form = await request.form()
        display_name = " ".join(str(form.get("display_name") or "").split())[:80]
        handle = str(form.get("handle") or "").strip().lstrip("@").lower()
        public = str(form.get("public") or "") in {"1", "on", "true"}
        if not display_name:
            return RedirectResponse("/account/?profile=bad_name", 303)
        if not HANDLE_RE.fullmatch(handle) or handle in RESERVED_HANDLES:
            return RedirectResponse("/account/?profile=bad_handle", 303)
        outcome = store.update_profile(user["id"], display_name, handle, public)
        return RedirectResponse(f"/account/?profile={outcome}", 303)

    async def calendar_feed(request: Request):
        token = str(request.path_params.get("token") or "")
        user = store.user_by_calendar_token(token)
        if not user:
            return PlainTextResponse("not found", status_code=404)
        going = store.event_snapshot(user["id"])["going"]
        body = _calendar_ics(going, user.get("handle") or user.get("display_name") or "")
        return Response(
            body,
            media_type="text/calendar; charset=utf-8",
            headers={"Content-Disposition": 'inline; filename="chumei-going.ics"'},
        )

    async def calendar_rotate(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return RedirectResponse("/account/", 303)
        store.calendar_token(user["id"], rotate=True)
        return RedirectResponse("/account/?profile=rotated", 303)

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

    async def contribute_page(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        public = apify_dashboard(store.path)
        mine = apify_user_rows(store.path, user["id"]) if user else []
        return HTMLResponse(_contribute_html(
            user,
            public,
            mine,
            encryption_ready=apify_encryption_available(),
            nycu_ok=config.configured,
            google_ok=config.google_configured,
        ))

    async def apify_contributions(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if request.method == "GET":
            public = apify_dashboard(store.path)
            payload = {"ok": True, **public}
            if user:
                count = apify_active_count(store.path, user["id"])
                payload["mine"] = apify_user_rows(store.path, user["id"])
                payload["priorityBonus"] = count * PRIORITY_BONUS_PER_ACCOUNT
                payload["dailyPriorityLimit"] = (
                    FETCH_REQUEST_DAILY_LIMIT + payload["priorityBonus"]
                )
            return JSONResponse(payload)
        if not user:
            return JSONResponse(
                {"ok": False, "error": "請先登入竹梅再貢獻帳號。"}, status_code=401
            )
        if not apify_encryption_available():
            return JSONResponse(
                {"ok": False, "error": "伺服器尚未設定貢獻加密金鑰。"}, status_code=503
            )
        try:
            if int(request.headers.get("content-length") or 0) > 2048:
                raise ValueError("request too large")
            body = await request.json()
            token = str(body.get("token") or "") if isinstance(body, dict) else ""
            name = str(body.get("name") or "") if isinstance(body, dict) else ""
            quota = await run_in_threadpool(verify_apify_token, token)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            message = "Apify token 無效或已撤銷。" if status in {401, 403} else "Apify 暫時無法驗證這個 token。"
            return JSONResponse({"ok": False, "error": message}, status_code=400 if status in {401, 403} else 502)
        except requests.RequestException:
            return JSONResponse(
                {"ok": False, "error": "Apify 暫時無法連線，請稍後再試。"}, status_code=502
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return JSONResponse(
                {"ok": False, "error": "請貼上有效的 Apify API token。"}, status_code=400
            )
        try:
            code, item = register_apify_contribution(
                store.path, user["id"], token, quota, name=name
            )
        except ValueError:
            return JSONResponse(
                {"ok": False, "error": f"帳號名稱請填 1–{MAX_ACCOUNT_NAME_LENGTH} 個字。"},
                status_code=400,
            )
        except RuntimeError:
            return JSONResponse(
                {"ok": False, "error": "伺服器目前無法安全保存這個 token。"}, status_code=503
            )
        if code == "claimed":
            return JSONResponse(
                {"ok": False, "error": "這個 Apify 帳號已由另一位貢獻者註冊。"}, status_code=409
            )
        if code == "limit":
            return JSONResponse(
                {"ok": False, "error": f"每人最多 {MAX_ACCOUNTS_PER_USER} 個有效帳號。"}, status_code=429
            )
        return JSONResponse(
            {
                "ok": True,
                "code": code,
                "contribution": item,
                "priorityBonus": apify_active_count(store.path, user["id"])
                * PRIORITY_BONUS_PER_ACCOUNT,
            },
            status_code=201 if code == "created" else 200,
        )

    async def apify_contribution_item(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        if not user:
            return JSONResponse(
                {"ok": False, "error": "請先登入竹梅。"}, status_code=401
            )
        public_id = str(request.path_params.get("public_id") or "")
        if not re.fullmatch(r"apy_[a-f0-9]{10}", public_id):
            return JSONResponse({"ok": False, "error": "找不到這個貢獻。"}, status_code=404)
        if request.method == "PATCH":
            try:
                if int(request.headers.get("content-length") or 0) > 512:
                    raise ValueError("request too large")
                body = await request.json()
                name = rename_apify_contribution(
                    store.path, user["id"], public_id,
                    str(body.get("name") or "") if isinstance(body, dict) else "",
                )
            except (json.JSONDecodeError, ValueError, TypeError):
                return JSONResponse(
                    {"ok": False, "error": f"帳號名稱請填 1–{MAX_ACCOUNT_NAME_LENGTH} 個字。"},
                    status_code=400,
                )
            return JSONResponse(
                {"ok": bool(name), "accountLabel": name},
                status_code=200 if name else 404,
            )
        removed = disable_apify_contribution(store.path, user["id"], public_id)
        return JSONResponse({"ok": removed}, status_code=200 if removed else 404)

    async def health(request: Request):
        return JSONResponse(
            {
                "ok": True,
                "service": "chumei-auth",
                "configured": config.configured,
                "googleConfigured": config.google_configured,
                "savedFeedsConfigured": bool(config.feed_signing_key),
            }
        )

    app = Starlette(
        routes=[
            Route("/@{handle}", profile_page, methods=["GET"]),
            Route("/auth/avatar/{handle}", avatar_image, methods=["GET"]),
            Route("/account", account, methods=["GET"]),
            Route("/account/", account, methods=["GET"]),
            Route("/submit", submit_page, methods=["GET"]),
            Route("/submit/", submit_page, methods=["GET"]),
            Route("/contribute", contribute_page, methods=["GET"]),
            Route("/contribute/", contribute_page, methods=["GET"]),
            Route("/auth/{provider}/start", oauth_start, methods=["GET"]),
            Route("/auth/{provider}/callback", oauth_callback, methods=["GET"]),
            Route("/auth/me", me, methods=["GET"]),
            Route("/auth/fetch-requests", fetch_requests, methods=["GET", "POST"]),
            Route("/auth/apify-contributions", apify_contributions, methods=["GET", "POST"]),
            Route(
                "/auth/apify-contributions/{public_id}",
                apify_contribution_item,
                methods=["PATCH", "DELETE"],
            ),
            Route("/auth/follows", follows, methods=["GET"]),
            Route("/auth/saved-feeds", saved_feeds, methods=["GET", "POST"]),
            Route("/auth/saved-feeds/{feed_id}", saved_feed_item, methods=["PATCH", "DELETE"]),
            Route("/auth/saved-feeds/{feed_id}/rotate", saved_feed_rotate, methods=["POST"]),
            Route("/auth/saved-feeds/{feed_id}/delete", saved_feed_delete, methods=["POST"]),
            Route("/auth/events", events_going, methods=["GET"]),
            Route("/auth/events/{event_id}", event_going_set, methods=["PUT", "DELETE"]),
            Route("/auth/follows/sync", follows_sync, methods=["POST"]),
            Route("/auth/follows/{org_id:int}", follow_add, methods=["PUT"]),
            Route("/auth/follows/{org_id:int}", follow_remove, methods=["DELETE"]),
            Route("/auth/submissions", submissions_list, methods=["GET"]),
            Route("/auth/submissions", submissions_create, methods=["POST"]),
            Route("/auth/unlink", unlink, methods=["POST"]),
            Route("/auth/profile", profile, methods=["POST"]),
            Route("/auth/calendar/rotate", calendar_rotate, methods=["POST"]),
            Route("/auth/calendar/{token}.ics", calendar_feed, methods=["GET"]),
            Route("/feeds/custom.{format}", public_custom_feed, methods=["GET"]),
            Route("/feeds/s/{token}.{format}", signed_saved_feed, methods=["GET"]),
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
