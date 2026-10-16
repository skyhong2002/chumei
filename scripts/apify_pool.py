"""Secret-safe Apify account pool, quota aggregation and paced rotation."""

from __future__ import annotations

import fcntl
import json
import math
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from apify_contributions import active_tokens, invalidate, update_quota
from chumei_lib import ROOT, load_env


APIFY_BASE = "https://api.apify.com/v2"
CACHE_PATH = ROOT / "state" / "apify_quota.json"
POOL_STATE_PATH = ROOT / "state" / "apify_pool.json"
MIN_ACCOUNT_RESERVE_USD = 0.02
MIN_INTERVAL_HOURS = 24.0
MAX_INTERVAL_HOURS = 168.0
# intropix/instagram-stories-scraper free-plan guard: per Apify account it
# grants 40 result items per day, at most 10 result items and 10 scanned
# profiles per run, and always lets the first run of the day through even
# when the shared free pool is busy. Every run still charges the account's
# own monthly credit (actor start + scanned profiles + delivered items).
STORY_DAILY_RESULT_LIMIT = 40
STORY_RUN_RESULT_LIMIT = 10
STORY_RUN_TARGET_LIMIT = 10
STORY_DENIAL_COOLDOWN_HOURS = 1.0
STORY_RUN_COST_ESTIMATE_USD = 0.045
# Every Apify consumer shares the pool's monthly credit equally. Each UTC day
# the pool may spend its remaining credit spread evenly over the days left in
# each account's cycle, and each consumer is guaranteed an equal share of that.
# A share that has not been spent expires gradually over the day, so others may
# use what a consumer no longer needs, but never what it could still claim.
CONSUMERS = ("facebook", "story", "instagram")
# Observed mean cost per scanned source, used to size batches before a run and
# to charge runs whose cost Apify did not report.
SOURCE_COST_ESTIMATE_USD = {"facebook": 0.013, "story": 0.0045, "instagram": 0.0025}
SPEND_HISTORY_DAYS = 14
PIPELINE_ROUND_HOURS = 3.0  # launchd pipeline cadence
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
                if account.get("verifiedQuota"):
                    configured["verifiedQuota"] = account["verifiedQuota"]
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
def _locked_state(path: Path | None = None):
    path = POOL_STATE_PATH if path is None else path
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
        # Registration has already verified quota with Apify. Merge that result
        # immediately, without another network request or waiting for a pipeline.
        cached_by_label = {row.get("label"): row for row in cached.get("accounts", [])}
        rows = []
        for account in configured:
            prior = cached_by_label.get(account["label"], {})
            verified = account.get("verifiedQuota") or {}
            if verified and float(verified.get("checkedAt") or 0) >= float(prior.get("checkedAt") or 0):
                limit, _ = recurring_limit(account["label"], float(verified.get("limitUsd") or 0), community=True)
                used = float(verified.get("usedUsd") or 0)
                remaining = float(verified.get("remainingUsd") or 0)
                row = {
                    **verified, "label": account["label"], "community": True,
                    "available": True, "limitUsd": limit,
                    "temporaryCreditUsd": max(0.0, used + remaining - limit),
                    "activeActorJobs": int(prior.get("activeActorJobs") or 0),
                    "exhausted": remaining <= MIN_ACCOUNT_RESERVE_USD,
                }
            else:
                row = {**prior, "label": account["label"], "community": bool(account.get("contributionId"))}
            rows.append(row)
        checked_at = max((float(row.get("checkedAt") or 0) for row in rows), default=0)
        return _aggregate_status(rows, now=checked_at)
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

    result = _aggregate_status(rows, now=now)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(CACHE_PATH.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CACHE_PATH)
    return result


def _aggregate_status(rows: list[dict], *, now: float) -> dict:
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


def _utc_day(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def _next_utc_day(now: float) -> float:
    today = datetime.fromtimestamp(now, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return (today + timedelta(days=1)).timestamp()


def record_run(label: str, *, consumer: str, cost_usd: float | None, source_count: int,
               ok: bool, now: float | None = None) -> None:
    """Record sanitized run telemetry and charge the run to its consumer's share."""
    if consumer not in CONSUMERS:
        raise ValueError(f"unknown Apify consumer {consumer!r}")
    now = time.time() if now is None else float(now)
    source_count = max(0, int(source_count))
    row = {
        "ts": now, "label": label, "consumer": consumer, "sourceCount": source_count,
        "ok": bool(ok), "costUsd": float(cost_usd) if cost_usd is not None else None,
    }
    spent = float(cost_usd) if cost_usd is not None else (
        SOURCE_COST_ESTIMATE_USD[consumer] * source_count if ok else 0.0)
    day = _utc_day(now)
    with _locked_state() as state:
        state.pop("fullBatchCostPerSourceEmaUsd", None)
        runs = state.setdefault("runs", [])
        runs.append(row)
        state["runs"] = runs[-100:]
        spend = state.get("spend") or {}
        if spend.get("day") != day:
            spend = {"day": day, "events": []}
        spend["events"].append([round(now, 3), label, consumer, round(spent, 6)])
        state["spend"] = spend
        history = state.setdefault("spendHistory", {})
        totals = history.setdefault(day, {})
        totals[consumer] = round(float(totals.get(consumer) or 0) + spent, 6)
        for old in sorted(history)[:-SPEND_HISTORY_DAYS]:
            del history[old]


def _today_events(state: dict, now: float) -> list:
    spend = state.get("spend") or {}
    return list(spend.get("events") or []) if spend.get("day") == _utc_day(now) else []


def _days_left(row: dict, now: float) -> float:
    cycle_end = _timestamp(row.get("cycleEnd"))
    return 1.0 if not math.isfinite(cycle_end) else max(1.0, math.ceil((cycle_end - now) / 86400))


def daily_pace_usd(status: dict, *, now: float, events: list) -> float:
    """Credit the pool may spend today if every account spreads its credit evenly."""
    total = 0.0
    for row in status.get("accounts", []):
        if not row.get("available"):
            continue
        # The quota snapshot already reflects spend recorded before it was taken.
        checked_at = float(row.get("checkedAt") or now)
        spent_before = sum(float(cost) for ts, label, _, cost in events
                           if label == row.get("label") and float(ts) <= checked_at)
        at_day_start = float(row.get("remainingUsd") or 0) + spent_before
        total += max(0.0, at_day_start - MIN_ACCOUNT_RESERVE_USD) / _days_left(row, now)
    return total


def apify_allocation(status: dict, *, now: float | None = None) -> dict:
    """Split today's evenly paced pool credit equally between Apify consumers."""
    now = time.time() if now is None else float(now)
    state = _read_json(POOL_STATE_PATH)
    events = _today_events(state, now)
    pace = daily_pace_usd(status, now=now, events=events)
    share = pace / len(CONSUMERS)
    day_start = _next_utc_day(now) - 86400
    elapsed = min(1.0, max(0.0, (now - day_start) / 86400))
    spent = {consumer: 0.0 for consumer in CONSUMERS}
    for _, _, consumer, cost in events:
        if consumer in spent:
            spent[consumer] += float(cost)
    # What a consumer can still claim today: its unspent share, shrinking as the day passes.
    held = {consumer: max(0.0, min(share - spent[consumer], share * (1 - elapsed)))
            for consumer in CONSUMERS}
    pool_left = sum(
        max(0.0, float(row.get("remainingUsd") or 0) - MIN_ACCOUNT_RESERVE_USD)
        for row in status.get("accounts", []) if row.get("available")
    )
    unspent_today = max(0.0, min(pool_left, pace - sum(spent.values())))
    history = state.get("spendHistory") or {}
    past_days = [day for day in sorted(history) if day < _utc_day(now)][-7:]
    consumers = {}
    for consumer in CONSUMERS:
        others_held = sum(value for other, value in held.items() if other != consumer)
        recent = [float((history[day] or {}).get(consumer) or 0) for day in past_days]
        consumers[consumer] = {
            "spentUsd": round(spent[consumer], 6),
            "heldUsd": round(held[consumer], 6),
            "availableUsd": round(max(0.0, unspent_today - others_held), 6),
            "averageDailyUsd": round(sum(recent) / len(recent), 6) if recent else None,
        }
    return {
        "day": _utc_day(now), "paceUsd": round(pace, 6), "shareUsd": round(share, 6),
        "resetsAt": _next_utc_day(now), "consumers": consumers,
    }


def round_budget_usd(consumer: str, status: dict, *, round_hours: float = PIPELINE_ROUND_HOURS,
                     now: float | None = None) -> float:
    """Spread a consumer's allowance over the pipeline rounds left today."""
    now = time.time() if now is None else float(now)
    available = apify_allocation(status, now=now)["consumers"][consumer]["availableUsd"]
    hours_left = max(1e-6, (_next_utc_day(now) - now) / 3600)
    return available * min(1.0, round_hours / hours_left)


def story_budget(entry: dict | None, *, now: float) -> dict:
    """Return the account's Story allowance for the current UTC day."""
    budget = dict((entry or {}).get("story") or {})
    if budget.get("day") != _utc_day(now):
        budget = {"day": _utc_day(now), "results": 0, "runs": 0}
    budget.setdefault("results", 0)
    budget.setdefault("runs", 0)
    budget.setdefault("costUsd", 0.0)
    if float(budget.get("deniedUntil") or 0) <= now:
        budget.pop("deniedUntil", None)
        budget.pop("deniedReason", None)
    return budget


def story_runs_left(row: dict, budget: dict) -> int:
    """Runs this account can still start today under its result allowance and credit."""
    if budget.get("deniedUntil"):
        return 0
    by_allowance = math.ceil((STORY_DAILY_RESULT_LIMIT - int(budget["results"])) / STORY_RUN_RESULT_LIMIT)
    credit_left = float(row.get("remainingUsd") or 0) - MIN_ACCOUNT_RESERVE_USD
    by_credit = math.floor(credit_left / STORY_RUN_COST_ESTIMATE_USD + 1e-9)
    return max(0, min(by_allowance, by_credit))


def _story_share_runs(status: dict, now: float) -> int:
    available = apify_allocation(status, now=now)["consumers"]["story"]["availableUsd"]
    return math.floor(available / STORY_RUN_COST_ESTIMATE_USD + 1e-9)


def choose_story_token(*, refresh: bool = False, exclude: set[str] | None = None,
                       now: float | None = None) -> tuple[str, str, dict, int]:
    """Choose the account with the most unused Story allowance today.

    Returns (label, token, status_row, result_items_left_today). Accounts that
    have not run today go first so their guaranteed first run is never wasted;
    accounts denied earlier today wait out their cooldown.
    """
    now = time.time() if now is None else float(now)
    accounts = {row["label"]: row for row in token_accounts()}
    status = pool_status(refresh=refresh)
    excluded = exclude or set()
    state = _read_json(POOL_STATE_PATH)
    account_state = state.get("accounts") or {}
    if _story_share_runs(status, now) <= 0:
        raise RuntimeError("Apify Story share of today's pool credit is used up")
    candidates = []
    for row in status.get("accounts", []):
        label = row.get("label")
        if (label not in accounts or label in excluded or not row.get("available")
                or row.get("exhausted") or float(row.get("remainingUsd") or 0) <= MIN_ACCOUNT_RESERVE_USD):
            continue
        budget = story_budget(account_state.get(label), now=now)
        left = STORY_DAILY_RESULT_LIMIT - int(budget["results"])
        if story_runs_left(row, budget) <= 0:
            continue
        candidates.append((row, budget, left))
    if not candidates:
        raise RuntimeError("Apify token pool has no account with Story allowance or credit left today")
    candidates.sort(key=lambda item: (
        int(item[0].get("activeActorJobs") or 0) > 0,
        int(item[1]["runs"]) > 0,
        -item[2],
        float(item[0].get("usedUsd") or 0) / max(float(item[0].get("limitUsd") or 0), 0.001),
        float((account_state.get(item[0]["label"]) or {}).get("lastSelectedAt") or 0),
        item[0]["label"],
    ))
    selected, _, left = candidates[0]
    with _locked_state() as current:
        entry = current.setdefault("accounts", {}).setdefault(selected["label"], {})
        entry["lastSelectedAt"] = now
        entry["selectionCount"] = int(entry.get("selectionCount") or 0) + 1
    return selected["label"], accounts[selected["label"]]["token"], selected, min(left, STORY_RUN_RESULT_LIMIT)


def record_story_run(label: str, *, delivered: int, denied_reason: str | None = None,
                     cost_usd: float | None = None, now: float | None = None) -> dict:
    """Charge a Story run against the account's daily allowance."""
    now = time.time() if now is None else float(now)
    with _locked_state() as state:
        entry = state.setdefault("accounts", {}).setdefault(label, {})
        budget = story_budget(entry, now=now)
        if denied_reason:
            budget["deniedReason"] = denied_reason
            if denied_reason == "user_daily_exhausted":
                budget["results"] = STORY_DAILY_RESULT_LIMIT
                budget["deniedUntil"] = _next_utc_day(now)
            else:
                budget["deniedUntil"] = now + STORY_DENIAL_COOLDOWN_HOURS * 3600
        else:
            budget["results"] = int(budget["results"]) + max(0, int(delivered))
            budget["runs"] = int(budget["runs"]) + 1
            budget["costUsd"] = round(float(budget.get("costUsd") or 0)
                                      + float(STORY_RUN_COST_ESTIMATE_USD if cost_usd is None else cost_usd), 6)
        entry["story"] = budget
        return dict(budget)


def story_runs_available(status: dict, *, now: float | None = None) -> int:
    """Count Story runs the pool can still start today (share, credit and allowance)."""
    now = time.time() if now is None else float(now)
    account_state = _read_json(POOL_STATE_PATH).get("accounts") or {}
    total = 0
    for row in status.get("accounts", []):
        if (not row.get("available") or row.get("exhausted")
                or float(row.get("remainingUsd") or 0) <= MIN_ACCOUNT_RESERVE_USD):
            continue
        budget = story_budget(account_state.get(row.get("label")), now=now)
        total += story_runs_left(row, budget)
    return max(0, min(total, _story_share_runs(status, now)))


def recommended_interval_hours(status: dict, *, source_count: int, now: float | None = None) -> float:
    """Facebook page revisit interval that its expected daily credit can sustain.

    Facebook gets its equal share plus whatever the other consumers have
    recently left unused (judged by their last week, never more than a share).
    """
    now = time.time() if now is None else float(now)
    allocation = apify_allocation(status, now=now)
    share = allocation["shareUsd"]
    others = sum(
        share if row["averageDailyUsd"] is None else min(share, row["averageDailyUsd"])
        for consumer, row in allocation["consumers"].items() if consumer != "facebook"
    )
    daily = allocation["paceUsd"] - others
    if daily <= 0:
        return MAX_INTERVAL_HOURS
    interval = 24 * max(1, source_count) * SOURCE_COST_ESTIMATE_USD["facebook"] / daily
    return round(min(MAX_INTERVAL_HOURS, max(MIN_INTERVAL_HOURS, interval)), 2)
