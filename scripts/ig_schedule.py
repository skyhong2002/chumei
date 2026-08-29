"""Instagram fetch scheduling helpers.

The scheduler keeps request pacing durable across launchd invocations.  State is
stored below ``state/`` (gitignored), so a process restart does not reset the
cooldown or make every account immediately eligible again.
"""

import json
import random
import time
from pathlib import Path


RATE_LIMIT_MARKERS = (
    "429",
    "401",
    "too many requests",
    "please wait a few minutes",
    "401 unauthorized",
    "rate limit",
)


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
