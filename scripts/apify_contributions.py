"""Community-contributed Apify accounts with encrypted token storage.

Only sanitized quota metadata is public. Raw API tokens are encrypted before
they enter SQLite and are only decrypted in memory when the crawler builds its
runtime token pool.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

from chumei_lib import ROOT, load_env


APIFY_BASE = "https://api.apify.com/v2"
DEFAULT_DB = ROOT / "state" / "auth.sqlite3"
PRIORITY_BONUS_PER_ACCOUNT = 3
MAX_ACCOUNTS_PER_USER = 5
MIN_USABLE_REMAINING_USD = 0.02
TOKEN_RE = re.compile(r"\S{20,512}")
MAX_ACCOUNT_NAME_LENGTH = 32


def database_path() -> Path:
    return Path(load_env().get("CHUMEI_AUTH_DATABASE", DEFAULT_DB))


def _keychain_value(service: str) -> str:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", "chumei", "-s", service, "-w"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""


def encryption_secret() -> str:
    """Use a dedicated key when configured, with the existing OAuth secret as a stable fallback."""
    env = load_env()
    return (
        env.get("CHUMEI_APIFY_CONTRIBUTION_KEY", "").strip()
        or _keychain_value("tw.observe.chumei.apify-contribution-key")
        or env.get("CHUMEI_NYCU_OAUTH_CLIENT_SECRET", "").strip()
        or _keychain_value("tw.observe.chumei.nycu-oauth-secret")
    )


def encryption_available() -> bool:
    return bool(encryption_secret())


def _fernet() -> Fernet:
    secret = encryption_secret()
    if not secret:
        raise RuntimeError("Apify contribution encryption key is not configured")
    digest = hashlib.sha256(("chumei-apify-contributions-v1\0" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def normalize_token(value: str) -> str:
    token = str(value or "").strip()
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("invalid Apify token")
    return token


def normalize_account_name(value: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    if not name or len(name) > MAX_ACCOUNT_NAME_LENGTH or any(ord(char) < 32 for char in name):
        raise ValueError("invalid Apify account name")
    return name


def token_hash(token: str) -> str:
    return hashlib.sha256(normalize_token(token).encode()).hexdigest()


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(normalize_token(token).encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(str(ciphertext).encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        raise RuntimeError("stored Apify token cannot be decrypted") from exc


def verify_token(token: str, *, timeout: tuple[int, int] = (5, 15)) -> dict:
    """Verify a token against Apify and return quota metadata without identity data."""
    token = normalize_token(token)
    response = requests.get(
        APIFY_BASE + "/users/me/limits",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    cycle = data.get("monthlyUsageCycle") or {}
    configured = data.get("limits") or {}
    current = data.get("current") or {}
    limit = float(configured.get("maxMonthlyUsageUsd") or 0)
    used = float(current.get("monthlyUsageUsd") or 0)
    if limit <= 0:
        raise ValueError("Apify account has no monthly API allowance")
    return {
        "limitUsd": round(limit, 6),
        "usedUsd": round(used, 6),
        "remainingUsd": round(max(0.0, limit - used), 6),
        "cycleStart": cycle.get("startAt"),
        "cycleEnd": cycle.get("endAt"),
        "activeActorJobs": int(current.get("activeActorJobCount") or 0),
        "checkedAt": time.time(),
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS apify_contributions (
            id TEXT PRIMARY KEY,
            public_id TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            token_ciphertext TEXT NOT NULL,
            status TEXT NOT NULL,
            limit_usd REAL NOT NULL DEFAULT 0,
            used_usd REAL NOT NULL DEFAULT 0,
            remaining_usd REAL NOT NULL DEFAULT 0,
            cycle_start TEXT,
            cycle_end TEXT,
            checked_at REAL,
            last_error TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS apify_contributions_user
            ON apify_contributions(user_id, created_at);
        CREATE INDEX IF NOT EXISTS apify_contributions_status
            ON apify_contributions(status, remaining_usd DESC);
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(apify_contributions)")}
    if "display_name" not in columns:
        conn.execute(
            "ALTER TABLE apify_contributions ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
        )


def _connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or database_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _account_label(public_id: str, display_name: str = "") -> str:
    return display_name or "COMMUNITY-" + public_id.removeprefix("apy_")[-6:].upper()


def register(
    path: Path, user_id: str, token: str, quota: dict, name: str = ""
) -> tuple[str, dict | None]:
    token = normalize_token(token)
    now = int(time.time())
    digest = token_hash(token)
    ciphertext = encrypt_token(token)
    with closing(_connect(path)) as conn, conn:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM apify_contributions WHERE token_hash = ?", (digest,)
        ).fetchone()
        if existing and existing["user_id"] != user_id:
            return "claimed", None
        active_count = conn.execute(
            "SELECT count(*) FROM apify_contributions WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ).fetchone()[0]
        if (not existing or existing["status"] != "active") and active_count >= MAX_ACCOUNTS_PER_USER:
            return "limit", None
        display_name = (
            normalize_account_name(name)
            if str(name or "").strip()
            else str(existing["display_name"] or "") if existing else ""
        )
        values = (
            ciphertext,
            float(quota.get("limitUsd") or 0),
            float(quota.get("usedUsd") or 0),
            float(quota.get("remainingUsd") or 0),
            quota.get("cycleStart"),
            quota.get("cycleEnd"),
            float(quota.get("checkedAt") or time.time()),
            now,
        )
        if existing:
            conn.execute(
                "UPDATE apify_contributions SET token_ciphertext=?,display_name=?,status='active',limit_usd=?,"
                "used_usd=?,remaining_usd=?,cycle_start=?,cycle_end=?,checked_at=?,last_error='',"
                "updated_at=? WHERE id=?",
                (ciphertext, display_name, *values[1:], existing["id"]),
            )
            public_id = existing["public_id"]
            code = "reactivated" if existing["status"] != "active" else "updated"
        else:
            contribution_id = "contrib_" + secrets.token_hex(10)
            public_id = "apy_" + secrets.token_hex(5)
            conn.execute(
                "INSERT INTO apify_contributions(id,public_id,user_id,token_hash,token_ciphertext,display_name,status,"
                "limit_usd,used_usd,remaining_usd,cycle_start,cycle_end,checked_at,last_error,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,'active',?,?,?,?,?,?, '',?,?)",
                (
                    contribution_id, public_id, user_id, digest, ciphertext, display_name,
                    *values[1:7], now, now,
                ),
            )
            code = "created"
    return code, {
        "publicId": public_id,
        "accountLabel": _account_label(public_id, display_name),
    }


def rename(path: Path, user_id: str, public_id: str, name: str) -> str | None:
    display_name = normalize_account_name(name)
    with closing(_connect(path)) as conn, conn:
        ensure_schema(conn)
        changed = conn.execute(
            "UPDATE apify_contributions SET display_name=?,updated_at=? "
            "WHERE user_id=? AND public_id=?",
            (display_name, int(time.time()), user_id, public_id),
        ).rowcount
    return display_name if changed else None


def disable(path: Path, user_id: str, public_id: str) -> bool:
    with closing(_connect(path)) as conn, conn:
        ensure_schema(conn)
        changed = conn.execute(
            "UPDATE apify_contributions SET status='disabled',token_ciphertext='',updated_at=? "
            "WHERE user_id=? AND public_id=? AND status='active'",
            (int(time.time()), user_id, public_id),
        ).rowcount
    return bool(changed)


def active_count(path: Path, user_id: str) -> int:
    with closing(_connect(path)) as conn:
        ensure_schema(conn)
        return int(conn.execute(
            "SELECT count(*) FROM apify_contributions WHERE user_id=? AND status='active'",
            (user_id,),
        ).fetchone()[0])


def active_tokens(path: Path | None = None) -> list[dict]:
    db_path = path or database_path()
    if not db_path.exists() or not encryption_available():
        return []
    with closing(_connect(db_path)) as conn:
        try:
            rows = conn.execute(
                "SELECT id,public_id,display_name,token_ciphertext,limit_usd,used_usd,remaining_usd,"
                "cycle_start,cycle_end,checked_at FROM apify_contributions "
                "WHERE status='active' AND token_ciphertext<>'' ORDER BY created_at"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    accounts = []
    for row in rows:
        try:
            token = decrypt_token(row["token_ciphertext"])
        except RuntimeError:
            continue
        accounts.append({
            "label": _account_label(row["public_id"], row["display_name"]),
            "token": token,
            "contributionId": row["id"],
            "verifiedQuota": {
                "limitUsd": row["limit_usd"], "usedUsd": row["used_usd"],
                "remainingUsd": row["remaining_usd"], "cycleStart": row["cycle_start"],
                "cycleEnd": row["cycle_end"], "checkedAt": row["checked_at"],
            },
        })
    return accounts


def update_quota(path: Path | None, contribution_id: str, quota: dict, error: str = "") -> None:
    db_path = path or database_path()
    if not db_path.exists():
        return
    with closing(_connect(db_path)) as conn, conn:
        ensure_schema(conn)
        if error:
            conn.execute(
                "UPDATE apify_contributions SET checked_at=?,last_error=?,updated_at=? WHERE id=?",
                (time.time(), str(error)[:240], int(time.time()), contribution_id),
            )
            return
        conn.execute(
            "UPDATE apify_contributions SET limit_usd=?,used_usd=?,remaining_usd=?,cycle_start=?,"
            "cycle_end=?,checked_at=?,last_error='',updated_at=? WHERE id=?",
            (
                float(quota.get("limitUsd") or 0),
                float(quota.get("usedUsd") or 0),
                float(quota.get("remainingUsd") or 0),
                quota.get("cycleStart"),
                quota.get("cycleEnd"),
                float(quota.get("checkedAt") or time.time()),
                int(time.time()),
                contribution_id,
            ),
        )


def invalidate(path: Path | None, contribution_id: str, error: str) -> None:
    """Fail closed when Apify says a contributed credential is no longer authorized."""
    db_path = path or database_path()
    if not db_path.exists():
        return
    with closing(_connect(db_path)) as conn, conn:
        ensure_schema(conn)
        now = int(time.time())
        conn.execute(
            "UPDATE apify_contributions SET status='invalid',token_ciphertext='',remaining_usd=0,"
            "checked_at=?,last_error=?,updated_at=? WHERE id=?",
            (time.time(), str(error)[:240], now, contribution_id),
        )


def user_rows(path: Path, user_id: str) -> list[dict]:
    with closing(_connect(path)) as conn:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT public_id,display_name,status,limit_usd,used_usd,remaining_usd,cycle_end,checked_at,created_at "
            "FROM apify_contributions WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [
        {
            "publicId": row["public_id"],
            "accountLabel": _account_label(row["public_id"], row["display_name"]),
            "status": row["status"],
            "limitUsd": row["limit_usd"],
            "usedUsd": row["used_usd"],
            "remainingUsd": row["remaining_usd"],
            "cycleEnd": row["cycle_end"],
            "checkedAt": row["checked_at"],
            "createdAt": row["created_at"],
            "usable": (
                row["status"] == "active"
                and float(row["remaining_usd"] or 0) > MIN_USABLE_REMAINING_USD
            ),
            "priorityBonus": PRIORITY_BONUS_PER_ACCOUNT if row["status"] == "active" else 0,
        }
        for row in rows
    ]


def dashboard(path: Path) -> dict:
    with closing(_connect(path)) as conn:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT c.public_id,c.display_name AS account_name,c.limit_usd,c.used_usd,"
            "c.remaining_usd,c.cycle_end,c.checked_at,c.created_at,u.id AS user_id,"
            "u.display_name AS contributor_name,u.handle,u.profile_public "
            "FROM apify_contributions c JOIN users u ON u.id=c.user_id "
            "WHERE c.status='active' ORDER BY c.remaining_usd DESC,c.created_at"
        ).fetchall()
    accounts = []
    contributors: dict[str, dict] = {}
    for row in rows:
        handle = row["handle"] if row["profile_public"] else None
        contributor_name = row["contributor_name"] if row["profile_public"] else "匿名貢獻者"
        contributor_key = row["user_id"]
        usable = float(row["remaining_usd"] or 0) > MIN_USABLE_REMAINING_USD
        account = {
            "accountLabel": _account_label(row["public_id"], row["account_name"]),
            "contributor": contributor_name,
            "handle": handle,
            "limitUsd": row["limit_usd"],
            "usedUsd": row["used_usd"],
            "remainingUsd": row["remaining_usd"],
            "cycleEnd": row["cycle_end"],
            "checkedAt": row["checked_at"],
            "createdAt": row["created_at"],
            "usable": usable,
        }
        accounts.append(account)
        contributor = contributors.setdefault(contributor_key, {
            "name": contributor_name, "handle": handle, "accounts": 0, "usableAccounts": 0,
            "limitUsd": 0.0, "remainingUsd": 0.0, "priorityBonus": 0,
        })
        contributor["accounts"] += 1
        contributor["usableAccounts"] += int(usable)
        contributor["limitUsd"] += float(row["limit_usd"] or 0)
        contributor["remainingUsd"] += float(row["remaining_usd"] or 0)
        contributor["priorityBonus"] += PRIORITY_BONUS_PER_ACCOUNT
    scoreboard = sorted(
        contributors.values(),
        key=lambda row: (
            -row["accounts"], -row["usableAccounts"], -row["remainingUsd"], row["name"]
        ),
    )
    return {
        "accounts": accounts,
        "scoreboard": scoreboard,
        "totals": {
            "accounts": sum(bool(row["usable"]) for row in accounts),
            "registeredAccounts": len(accounts),
            "contributors": len(scoreboard),
            "limitUsd": round(sum(float(row["limitUsd"] or 0) for row in accounts), 6),
            "remainingUsd": round(sum(float(row["remainingUsd"] or 0) for row in accounts), 6),
            "extraSlots": sum(bool(row["usable"]) for row in accounts)
            * PRIORITY_BONUS_PER_ACCOUNT,
        },
    }
