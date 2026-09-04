"""Secret-safe Apify account pool, quota aggregation and paced rotation."""

from __future__ import annotations

import fcntl
import json
import math
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import requests

from apify_contributions import active_tokens, invalidate, update_quota
from chumei_lib import ROOT, load_env


APIFY_BASE = "https://api.apify.com/v2"
CACHE_PATH = ROOT / "state" / "apify_quota.json"
POOL_STATE_PATH = ROOT / "state" / "apify_pool.json"
DEFAULT_COST_PER_SOURCE_USD = 0.015
MIN_ACCOUNT_RESERVE_USD = 0.02
MIN_INTERVAL_HOURS = 24.0
MAX_INTERVAL_HOURS = 168.0
# These free accounts can receive a one-cycle US$5 social-account promotion on
# top of their recurring US$5 allowance. Keep temporary credit spendable, but
# do not present it as a permanent plan upgrade.
RECURRING_LIMIT_OVERRIDES_USD = {
    "PRIMARY": 5.0,
    "GDGNTNU": 5.0,
    "SKYNTNU": 5.0,
    "UNICOURSE": 5.0,
}


def recurring_limit(
    label: str, api_limit: float, *, community: bool = False
) -> tuple[float, float]:
    """Return the stable monthly allowance and any temporary API credit."""
    override = 5.0 if community else RECURRING_LIMIT_OVERRIDES_USD.get(label, float(api_limit))
    recurring = min(float(api_limit), override)
    return recurring, max(0.0, float(api_limit) - recurring)


def token_accounts(env: dict | None = None) -> list[dict]:
    """Return distinct configured tokens; callers must never serialize token values."""
    include_community = env is None
    values = env if env is not None else load_env()
    keys = [key for key in values if key == "APIFY_TOKEN" or key.startswith("APIFY_TOKEN_")]
    keys.sort(key=lambda key: (key != "APIFY_TOKEN", key))
    accounts = []
    seen = set()
    for key in keys:
        token = str(values.get(key) or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        label = "PRIMARY" if key == "APIFY_TOKEN" else key.removeprefix("APIFY_TOKEN_")
        accounts.append({"label": label, "token": token})
    if include_community:
        for account in active_tokens():
            if account["token"] in seen:
                configured = next(row for row in accounts if row["token"] == account["token"])
                configured["contributionId"] = account["contributionId"]
                continue
            seen.add(account["token"])
            accounts.append(account)
    return accounts


def community_account_count(accounts: list[dict] | None = None) -> int:
    selected = token_accounts() if accounts is None else accounts
    return sum(bool(row.get("contributionId")) for row in selected)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


@contextmanager
def _locked_state(path: Path = POOL_STATE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = _read_json(path) or {"version": 1, "accounts": {}, "runs": []}
        yield data
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _fetch_quota(account: dict, *, now: float) -> dict:
    response = requests.get(
        APIFY_BASE + "/users/me/limits",
        headers={"Authorization": f"Bearer {account['token']}", "Accept": "application/json"},
        timeout=(5, 15),
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    cycle = data.get("monthlyUsageCycle") or {}
    configured = data.get("limits") or {}
    current = data.get("current") or {}
    api_limit = float(configured.get("maxMonthlyUsageUsd") or 0)
    limit, temporary_credit = recurring_limit(
        account["label"], api_limit, community=bool(account.get("contributionId"))
    )
    used = float(current.get("monthlyUsageUsd") or 0)
    remaining = max(0.0, api_limit - used)
    return {
        "label": account["label"],
        "community": bool(account.get("contributionId")),
        "available": True,
        "checkedAt": now,
        "cycleStart": cycle.get("startAt"),
        "cycleEnd": cycle.get("endAt"),
        "limitUsd": limit,
        "temporaryCreditUsd": temporary_credit,
        "usedUsd": used,
        "remainingUsd": round(remaining, 6),
        "activeActorJobs": int(current.get("activeActorJobCount") or 0),
        "exhausted": remaining <= MIN_ACCOUNT_RESERVE_USD,
    }


def pool_status(*, refresh: bool = True, now: float | None = None) -> dict:
    """Return sanitized per-account and aggregate quota data."""
    now = time.time() if now is None else float(now)
    cached = _read_json(CACHE_PATH)
    configured = token_accounts()
    if not refresh:
        return cached
    if not configured:
        return cached or {"available": False, "checkedAt": now, "exhausted": True, "accounts": []}

    cached_by_label = {row.get("label"): row for row in cached.get("accounts", [])}
    rows = []
    for account in configured:
        try:
            row = _fetch_quota(account, now=now)
            rows.append(row)
            if account.get("contributionId"):
                update_quota(None, account["contributionId"], row)
        except (requests.RequestException, ValueError, TypeError) as exc:
            if account.get("contributionId"):
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code in {401, 403}:
                    invalidate(None, account["contributionId"], str(exc))
                else:
                    update_quota(None, account["contributionId"], {}, error=str(exc))
            prior = dict(cached_by_label.get(account["label"]) or {})
            if prior:
                prior["stale"] = True
                rows.append(prior)
            else:
                rows.append({
                    "label": account["label"], "available": False, "checkedAt": now,
                    "limitUsd": 0.0, "usedUsd": 0.0, "remainingUsd": 0.0,
                    "activeActorJobs": 0, "exhausted": True,
                })

    available = [row for row in rows if row.get("available")]
    cycle_starts = [row.get("cycleStart") for row in available if row.get("cycleStart")]
    cycle_ends = [row.get("cycleEnd") for row in available if row.get("cycleEnd")]
    result = {
        "available": bool(available),
        "checkedAt": now,
        "cycleStart": min(cycle_starts) if cycle_starts else None,
        "cycleEnd": max(cycle_ends) if cycle_ends else None,
        "limitUsd": round(sum(float(row.get("limitUsd") or 0) for row in available), 6),
        "usedUsd": round(sum(float(row.get("usedUsd") or 0) for row in available), 6),
        "remainingUsd": round(sum(float(row.get("remainingUsd") or 0) for row in available), 6),
        "temporaryCreditUsd": round(
            sum(float(row.get("temporaryCreditUsd") or 0) for row in available), 6
        ),
        "activeActorJobs": sum(int(row.get("activeActorJobs") or 0) for row in available),
        "accountCount": len(rows),
        "usableAccountCount": sum(
            bool(row.get("available")) and float(row.get("remainingUsd") or 0) > MIN_ACCOUNT_RESERVE_USD
            for row in rows
        ),
        "accounts": rows,
    }
    result["exhausted"] = result["usableAccountCount"] == 0
    result["stale"] = any(row.get("stale") for row in rows)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(CACHE_PATH.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CACHE_PATH)
    return result


def _timestamp(value) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return float("inf")


def choose_token(*, refresh: bool = True, exclude: set[str] | None = None) -> tuple[str, str, dict]:
    """Choose the usable account expiring first, balancing usage within a cycle."""
    accounts = {row["label"]: row for row in token_accounts()}
    status = pool_status(refresh=refresh)
    excluded = exclude or set()
    candidates = [
        row for row in status.get("accounts", [])
        if row.get("label") in accounts and row.get("label") not in excluded
        and row.get("available") and not row.get("exhausted")
        and float(row.get("remainingUsd") or 0) > MIN_ACCOUNT_RESERVE_USD
    ]
    if not candidates:
        raise RuntimeError("Apify token pool has no usable account")
    state = _read_json(POOL_STATE_PATH)
    account_state = state.get("accounts") or {}
    candidates.sort(key=lambda row: (
        int(row.get("activeActorJobs") or 0) > 0,
        bool(row.get("stale")),
        _timestamp(row.get("cycleEnd")),
        float(row.get("usedUsd") or 0) / max(float(row.get("limitUsd") or 0), 0.001),
        float((account_state.get(row["label"]) or {}).get("lastSelectedAt") or 0),
        row["label"],
    ))
    selected = candidates[0]
    with _locked_state() as current:
        entry = current.setdefault("accounts", {}).setdefault(selected["label"], {})
        entry["lastSelectedAt"] = time.time()
        entry["selectionCount"] = int(entry.get("selectionCount") or 0) + 1
    return selected["label"], accounts[selected["label"]]["token"], selected


def record_run(label: str, *, cost_usd: float | None, source_count: int, ok: bool) -> None:
    """Record sanitized run telemetry used for the full-batch moving cost estimate."""
    row = {
        "ts": time.time(), "label": label, "sourceCount": max(0, int(source_count)),
        "ok": bool(ok), "costUsd": float(cost_usd) if cost_usd is not None else None,
    }
    with _locked_state() as state:
        runs = state.setdefault("runs", [])
        runs.append(row)
        state["runs"] = runs[-100:]
        if ok and cost_usd is not None and source_count >= 50:
            previous = state.get("fullBatchCostPerSourceEmaUsd")
            unit = float(cost_usd) / source_count
            state["fullBatchCostPerSourceEmaUsd"] = unit if previous is None else 0.35 * unit + 0.65 * float(previous)


def recommended_interval_hours(status: dict, *, source_count: int, now: float | None = None) -> float:
    """Spend remaining quota evenly before the latest usable account resets."""
    now = time.time() if now is None else float(now)
    state = _read_json(POOL_STATE_PATH)
    unit_cost = float(state.get("fullBatchCostPerSourceEmaUsd") or DEFAULT_COST_PER_SOURCE_USD)
    estimated_run_cost = max(0.5, unit_cost * max(1, source_count))
    usable = []
    capacity = 0
    for row in status.get("accounts", []):
        remaining = max(0.0, float(row.get("remainingUsd") or 0) - MIN_ACCOUNT_RESERVE_USD)
        runs = math.floor(remaining / estimated_run_cost)
        if row.get("available") and runs > 0:
            capacity += runs
            usable.append(row)
    if capacity <= 0:
        return MAX_INTERVAL_HOURS
    deadlines = [_timestamp(row.get("cycleEnd")) for row in usable]
    deadlines = [value for value in deadlines if math.isfinite(value) and value > now]
    if not deadlines:
        return MAX_INTERVAL_HOURS
    horizon_hours = (max(deadlines) - now) / 3600
    interval = horizon_hours / (capacity + 1)
    return round(min(MAX_INTERVAL_HOURS, max(MIN_INTERVAL_HOURS, interval)), 2)
