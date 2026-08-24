"""OAuth-only account service for Chumei.

NYCU handles credentials and consent. Chumei stores only a local user mapping
and opaque browser sessions; it never receives or stores a school password.

Public routes (Caddy proxies /auth/* and /account* to this service):
  GET  /account/              account/login page
  GET  /auth/nycu/start       begin Authorization Code + PKCE flow
  GET  /auth/nycu/callback    exchange code and create/login local account
  GET  /auth/me               current session
  POST /auth/logout           revoke local session
  GET  /auth/health           runtime/configuration status
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import secrets
import sqlite3
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from build_site import page_shell
from chumei_lib import ROOT, load_env


PORT = 8324
NYCU_AUTHORIZE_URL = "https://id.nycu.edu.tw/o/authorize/"
NYCU_TOKEN_URL = "https://id.nycu.edu.tw/o/token/"
NYCU_PROFILE_URL = "https://id.nycu.edu.tw/api/profile/"
SESSION_COOKIE = "chumei_session"
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


@dataclass(frozen=True)
class AuthConfig:
    client_id: str
    client_secret: str
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
        return cls(
            client_id=client_id,
            client_secret=client_secret,
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
    def redirect_uri(self) -> str:
        return f"{self.public_base_url}/auth/nycu/callback"


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
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

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

    def cleanup(self, now: int | None = None) -> None:
        now = now or _now()
        with self._connection() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            conn.execute(
                "DELETE FROM oauth_states WHERE created_at <= ?",
                (now - OAUTH_STATE_AGE_SECONDS,),
            )

    def put_oauth_state(self, state: str, verifier: str, return_to: str) -> None:
        now = _now()
        self.cleanup(now)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO oauth_states(state_hash, code_verifier, return_to, created_at) "
                "VALUES (?, ?, ?, ?)",
                (_hash_token(state), verifier, _safe_return_to(return_to), now),
            )

    def consume_oauth_state(self, state: str) -> sqlite3.Row | None:
        state_hash = _hash_token(state)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT code_verifier, return_to, created_at FROM oauth_states "
                "WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            conn.execute("DELETE FROM oauth_states WHERE state_hash = ?", (state_hash,))
        if not row or row["created_at"] <= _now() - OAUTH_STATE_AGE_SECONDS:
            return None
        return row

    def get_or_create_user(self, subject: str, email: str | None) -> dict:
        now = _now()
        display_name = (email or subject).split("@", 1)[0][:80] or "NYCU 使用者"
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT u.id, u.display_name, u.email
                FROM oauth_identities i
                JOIN users u ON u.id = i.user_id
                WHERE i.provider = 'nycu' AND i.subject = ?
                """,
                (subject,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE oauth_identities SET email = ?, updated_at = ? "
                    "WHERE provider = 'nycu' AND subject = ?",
                    (email, now, subject),
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
                "VALUES ('nycu', ?, ?, ?, ?, ?)",
                (subject, user_id, email, now, now),
            )
            return {"id": user_id, "display_name": display_name, "email": email}

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
                SELECT u.id, u.display_name, u.email, i.subject
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                JOIN oauth_identities i ON i.user_id = u.id AND i.provider = 'nycu'
                WHERE s.token_hash = ? AND s.expires_at > ?
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


def _error_page(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    body = _account_html(None, False, title=title, message=message)
    return HTMLResponse(body, status_code=status_code)


def _account_html(
    user: dict | None,
    configured: bool,
    *,
    title: str = "帳號",
    message: str | None = None,
) -> str:
    if user:
        email = html.escape(user.get("email") or "")
        subject = html.escape(user.get("subject") or "")
        card = f"""
        <div class="account-status"><span class="account-dot"></span>已使用陽明交大 OAuth 登入</div>
        <h2>{html.escape(user.get('display_name') or 'NYCU 使用者')}</h2>
        <dl><div><dt>學校帳號</dt><dd>{subject}</dd></div>{f'<div><dt>Email</dt><dd>{email}</dd></div>' if email else ''}</dl>
        <form method="post" action="/auth/logout"><button class="btn account-action" type="submit">登出</button></form>
        """
    elif configured:
        card = """
        <p class="eyebrow">OAuth-only account</p>
        <h2>登入竹梅</h2>
        <p>使用陽明交大單一入口驗證身分。竹梅不會取得或儲存你的學校密碼。</p>
        <a class="btn btn-primary account-action" href="/auth/nycu/start">使用陽明交大 OAuth 登入</a>
        <p class="privacy-note">目前只要求基本 profile，用來取得穩定帳號識別與校方 Email。</p>
        """
    else:
        card = """
        <p class="eyebrow">OAuth-only account</p>
        <h2>登入功能設定中</h2>
        <p>NYCU OAuth Client 尚未完成設定，請稍後再試。</p>
        <span class="btn btn-primary account-action disabled" aria-disabled="true">使用陽明交大 OAuth 登入</span>
        """
    alert = f'<div class="account-alert">{html.escape(message)}</div>' if message else ""
    content = f"""
<section class="account-page">
  <div class="hero">
    <h1>{html.escape(title)}</h1>
    <p>使用校方 OAuth 管理你的竹梅登入身分。</p>
  </div>
  {alert}
  <section class="account-card">{card}</section>
</section>
"""
    return page_shell(
        f"{title}｜竹梅活動觀測站",
        "使用陽明交通大學 OAuth 登入竹梅。",
        content,
        canonical="https://chumei.observe.tw/account/",
    )


def create_app(
    config: AuthConfig | None = None,
    store: AuthStore | None = None,
    oauth_client: NYCUOAuthClient | None = None,
) -> Starlette:
    config = config or AuthConfig.from_env()
    store = store or AuthStore(config.database_path)
    oauth_client = oauth_client or NYCUOAuthClient()

    async def account(request: Request):
        user = store.session_user(request.cookies.get(SESSION_COOKIE))
        return HTMLResponse(_account_html(user, config.configured))

    async def oauth_start(request: Request):
        if not config.configured:
            return _error_page("登入功能設定中", "NYCU OAuth Client 尚未完成設定。", 503)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        return_to = _safe_return_to(request.query_params.get("return_to"))
        store.put_oauth_state(state, verifier, return_to)
        params = {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": "profile",
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
        response = RedirectResponse(f"{NYCU_AUTHORIZE_URL}?{urlencode(params)}", 302)
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
        provider_error = request.query_params.get("error")
        state = request.query_params.get("state") or ""
        state_cookie = request.cookies.get(OAUTH_STATE_COOKIE) or ""
        if provider_error:
            return _error_page("登入已取消", "陽明交大未授權登入，帳號沒有建立。")
        if not state or not secrets.compare_digest(state, state_cookie):
            return _error_page("登入驗證失敗", "登入狀態已失效，請回到帳號頁重新登入。")
        state_row = store.consume_oauth_state(state)
        code = request.query_params.get("code")
        if not state_row or not code:
            return _error_page("登入驗證失敗", "授權碼或登入狀態已失效，請重新登入。")
        try:
            access_token = await run_in_threadpool(
                oauth_client.exchange_code, config, code, state_row["code_verifier"]
            )
            subject, email = await run_in_threadpool(oauth_client.profile, access_token)
            user = store.get_or_create_user(subject, email)
            raw_session = store.create_session(user["id"])
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            return _error_page(
                "登入暫時失敗", "無法向陽明交大完成身分驗證，請稍後再試。", 502
            )
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
                    "provider": "nycu",
                },
            }
        )

    async def logout(request: Request):
        raw_session = request.cookies.get(SESSION_COOKIE)
        store.delete_session(raw_session)
        response = RedirectResponse("/account/", 303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    async def health(request: Request):
        return JSONResponse(
            {"ok": True, "service": "chumei-auth", "configured": config.configured}
        )

    app = Starlette(
        routes=[
            Route("/account", account, methods=["GET"]),
            Route("/account/", account, methods=["GET"]),
            Route("/auth/nycu/start", oauth_start, methods=["GET"]),
            Route("/auth/nycu/callback", oauth_callback, methods=["GET"]),
            Route("/auth/me", me, methods=["GET"]),
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
