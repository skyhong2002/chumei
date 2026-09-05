#!/usr/bin/env python3
"""Safely consume authenticated priority-fetch requests from the shared queue."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

from chumei_lib import ROOT, load_env
from source_status import apify_quota, source_registry


PYTHON = ROOT / ".venv" / "bin" / "python"
DEFAULT_DB = ROOT / "state" / "auth.sqlite3"
PRIORITY_MIN_INTERVAL_SECONDS = 3 * 3600


def database_path() -> Path:
    return Path(load_env().get("CHUMEI_AUTH_DATABASE", DEFAULT_DB))


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def claim(path: Path) -> dict | None:
    now = int(time.time())
    with closing(connect(path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM source_priority_weights WHERE weight > 0 "
            "AND status IN ('active','deferred') AND next_attempt_at <= ? "
            "ORDER BY ((? - CASE WHEN last_run_at > 0 THEN last_run_at ELSE created_at END) * weight) DESC, "
            "weight DESC,created_at LIMIT 1",
            (now, now),
        ).fetchone()
        if not row:
            return None
        changed = conn.execute(
            "UPDATE source_priority_weights SET status='processing',reason='',updated_at=? "
            "WHERE source_id=? AND status IN ('active','deferred')",
            (now, row["source_id"]),
        ).rowcount
        return dict(row) if changed else None


def finish(path: Path, request: dict, status: str, reason: str = "", next_attempt: int = 0) -> None:
    now = int(time.time())
    if status == "completed":
        stored_status = "active"
        next_attempt = max(int(next_attempt), now + PRIORITY_MIN_INTERVAL_SECONDS)
        last_run = now
    elif status == "deferred":
        stored_status = "deferred"
        last_run = int(request.get("last_run_at") or 0)
    else:
        # 無法安全抓取的來源暫停加權排程；再次投入 quota 時會重新啟用。
        stored_status = "failed"
        last_run = now
    with closing(connect(path)) as conn, conn:
        conn.execute(
            "UPDATE source_priority_weights SET status=?,reason=?,next_attempt_at=?,last_run_at=?,updated_at=? "
            "WHERE source_id=?",
            (
                stored_status, reason[:300], int(next_attempt), last_run, now,
                request["source_id"],
            ),
        )


def cooldown_until(kind: str) -> float:
    if kind not in {"instagram_profile", "instagram_story"}:
        return 0
    name = (
        "instagram_public_profile_schedule.json"
        if kind == "instagram_profile"
        else "instagram_apify_stories_schedule.json"
    )
    try:
        state = json.loads((ROOT / "state" / name).read_text())
        return float(state.get("global_cooldown_until") or 0)
    except (OSError, ValueError, TypeError):
        return 0


def command_for(source: dict) -> list[str] | None:
    username, kind = source["username"], source["kind"]
    if kind == "instagram_profile":
        return ["fetch_instagram_public.py", "--accounts", username, "--max-accounts", "1", "--limit", "5"]
    if kind == "instagram_story":
        return ["fetch_stories_apify.py", "--accounts", username, "--max-accounts", "1"]
    if kind == "facebook":
        return ["fetch_facebook.py", "--pages", username, "--limit", "5", "--max-pages-per-run", "1"]
    if kind in {"threads", "x"}:
        return ["fetch_social.py", "--platform", kind, "--accounts", username, "--limit", "5", "--sleep", "0"]
    if kind == "infonews_category":
        return ["fetch_infonews.py", "--sources", source["sourceId"], "--max-pages", "2"]
    if kind == "nycu_open_data":
        return ["fetch_nycu_open_data.py", "--sources", source["sourceId"]]
    if kind == "rpage_list":
        return ["fetch_rpage.py", "--sources", source["sourceId"], "--max-pages", "2"]
    if kind == "wp_api":
        return ["fetch_wp.py", "--sources", source["sourceId"]]
    if kind in {"api", "nycu_life"} and source["sourceId"] == "nycu_life_api":
        return ["fetch_nycu_life.py"]
    return None


def process_one(path: Path, request: dict, registry: dict[str, dict], *, dry_run: bool = False) -> str:
    source = registry.get(request["source_id"])
    if not source:
        finish(path, request, "failed", "來源已從公開登錄移除")
        return "failed"
    cooldown = cooldown_until(source["kind"])
    if cooldown > time.time():
        reason = "Instagram 全域冷卻中，將在冷卻結束後重試"
        finish(path, request, "deferred", reason, int(cooldown) + 60)
        return "deferred"
    if source["kind"] == "facebook":
        quota = apify_quota(refresh=True)
        if quota.get("exhausted") or not quota.get("available"):
            try:
                retry = int(datetime.fromisoformat(str(quota.get("cycleEnd")).replace("Z", "+00:00")).timestamp()) + 60
            except (TypeError, ValueError):
                retry = int(time.time()) + 6 * 3600
            finish(path, request, "deferred", "Apify 本期額度已用完", retry)
            return "deferred"
    command = command_for(source)
    if not command:
        finish(path, request, "failed", "這個來源目前沒有安全的單來源抓取器")
        return "failed"
    if dry_run:
        finish(path, request, "deferred", "dry-run", int(time.time()) + 60)
        print("would run:", " ".join(command))
        return "dry-run"
    try:
        result = subprocess.run(
            [str(PYTHON), str(ROOT / "scripts" / command[0]), *command[1:]],
            cwd=ROOT, timeout=900, capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        finish(path, request, "failed", "抓取逾時")
        return "failed"
    if result.returncode == 0:
        finish(path, request, "completed", (result.stdout or "完成").strip()[-300:])
        return "completed"
    reason = (result.stderr or result.stdout or f"exit {result.returncode}").strip()[-300:]
    finish(path, request, "failed", reason)
    return "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-requests", type=int, default=2)
    parser.add_argument("--buffer-seconds", type=float, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    path = database_path()
    if not path.exists():
        print("priority fetch: auth database does not exist")
        return 0
    registry = {source["id"]: source for source in source_registry()}
    handled = 0
    for index in range(max(0, args.max_requests)):
        request = claim(path)
        if not request:
            break
        outcome = process_one(path, request, registry, dry_run=args.dry_run)
        handled += 1
        print(
            f"priority weight {request['source_id']} x{int(request.get('weight') or 0)}: {outcome}"
        )
        if index + 1 < args.max_requests and outcome not in {"deferred", "dry-run"}:
            time.sleep(max(0, args.buffer_seconds))
    print(f"priority fetch: handled {handled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
