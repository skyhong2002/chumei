"""Instagram fetch scheduling helpers.

The scheduler keeps request pacing durable across launchd invocations.  State is
stored below ``state/`` (gitignored), so a process restart does not reset the
cooldown or make every account immediately eligible again.
"""

import json
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path


RATE_LIMIT_MARKERS = (
    "429",
    "401",
    "too many requests",
    "please wait a few minutes",
    "401 unauthorized",
    "rate limit",
)

ADAPTIVE_INTERVAL_TIERS = (12, 24, 48, 72, 168, 336)


def _timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
            timezone.utc
        ).timestamp()
    except (TypeError, ValueError):
        return None


def adaptive_interval_hours(posted_at_values, *, now=None, minimum=12, maximum=336):
    """Choose a stable polling interval from a profile's recent post cadence.

    Poll around twice per observed posting interval, then progressively slow a
    dormant account.  Returning one of a few fixed tiers keeps schedule output
    understandable and avoids oscillating after every fetch.
    """
    now = time.time() if now is None else float(now)
    timestamps = sorted({ts for value in posted_at_values if (ts := _timestamp(value))},
                        reverse=True)
    if not timestamps:
        target = 168
    else:
        age_hours = max(0.0, (now - timestamps[0]) / 3600)
        gaps = [
            (newer - older) / 3600
            for newer, older in zip(timestamps, timestamps[1:])
            if newer > older
        ]
        cadence_target = statistics.median(gaps) / 2 if gaps else 24
        # Once a once-active account goes quiet, do not keep polling it at its
        # old high-frequency cadence forever.
        dormancy_target = age_hours / 4
        target = max(cadence_target, dormancy_target)

    tiers = [tier for tier in ADAPTIVE_INTERVAL_TIERS if minimum <= tier <= maximum]
    if not tiers:
        return float(minimum)
    return float(min(tiers, key=lambda tier: (abs(tier - target), tier)))


def load_schedule(path):
    if not path.exists():
        return {"version": 1, "accounts": {}, "rate_limit_streak": 0,
                "global_cooldown_until": 0}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        data = {}
    data.setdefault("version", 1)
    data.setdefault("accounts", {})
    data.setdefault("rate_limit_streak", 0)
    data.setdefault("global_cooldown_until", 0)
    return data


def save_schedule(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(path)


def select_due(usernames, state, limit, now=None, force=False):
    """Return a fair batch, oldest eligible account first."""
    now = time.time() if now is None else now
    accounts = state["accounts"]
    indexed = list(enumerate(usernames))
    if not force:
        indexed = [
            (i, username) for i, username in indexed
            if accounts.get(username, {}).get("next_eligible", 0) <= now
        ]
    indexed.sort(key=lambda item: (
        accounts.get(item[1], {}).get("next_eligible", 0),
        accounts.get(item[1], {}).get("last_attempt", 0),
        item[0],
    ))
    return [username for _, username in indexed[:limit]]


def mark_success(state, username, *, now=None, interval_hours=48,
                 jitter_hours=6, rng=None):
    now = time.time() if now is None else now
    rng = random.uniform if rng is None else rng
    account = state["accounts"].setdefault(username, {})
    account.update({
        "last_attempt": now,
        "last_success": now,
        "consecutive_failures": 0,
        "interval_hours": interval_hours,
        "next_eligible": now + interval_hours * 3600 + rng(0, jitter_hours * 3600),
    })


def mark_failure(state, username, *, now=None, base_hours=6, cap_hours=72,
                 jitter_hours=1, rng=None):
    now = time.time() if now is None else now
    rng = random.uniform if rng is None else rng
    account = state["accounts"].setdefault(username, {})
    failures = account.get("consecutive_failures", 0) + 1
    delay_hours = min(cap_hours, base_hours * (2 ** (failures - 1)))
    account.update({
        "last_attempt": now,
        "consecutive_failures": failures,
        "next_eligible": now + delay_hours * 3600 + rng(0, jitter_hours * 3600),
    })


def set_global_rate_limit(state, *, now=None, base_hours=12, cap_hours=72,
                          jitter_hours=3, rng=None):
    now = time.time() if now is None else now
    rng = random.uniform if rng is None else rng
    streak = state.get("rate_limit_streak", 0) + 1
    delay_hours = min(cap_hours, base_hours * (2 ** (streak - 1)))
    until = now + delay_hours * 3600 + rng(0, jitter_hours * 3600)
    state["rate_limit_streak"] = streak
    state["global_cooldown_until"] = until
    return until


def clear_global_rate_limit(state):
    state["rate_limit_streak"] = 0
    state["global_cooldown_until"] = 0


def is_rate_limited(error):
    message = str(error).lower()
    return any(marker in message for marker in RATE_LIMIT_MARKERS)
