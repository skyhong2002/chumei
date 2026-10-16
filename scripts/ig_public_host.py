"""Host-wide pacing for logged-out Instagram queries.

Instagram rate-limits logged-out queries per server IP, and Chumei and
Harmonica run on the same host. Both projects therefore take turns through one
small state file outside either repository: any two queries are spaced at
least ``MIN_GAP_SECONDS`` apart, and once Instagram refuses one, every
collector on the host stops direct queries until the block is expected to
lift. Harmonica keeps an identical copy of this protocol; change both together.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path


STATE_PATH = Path(os.environ.get(
    "OBSERVE_IG_PUBLIC_HOST_STATE", "~/.cache/observe-instagram-public.json"
)).expanduser()
MIN_GAP_SECONDS = 10.0
BLOCK_SECONDS = 2 * 3600.0


@contextmanager
def _locked(path: Path | None = None):
    path = STATE_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        yield state
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(path)


def blocked_until(path: Path | None = None) -> float:
    with _locked(path) as state:
        return float(state.get("blockedUntil") or 0)


def wait_turn(*, path: Path | None = None, gap: float = MIN_GAP_SECONDS, sleep=time.sleep) -> bool:
    """Reserve the host's next query slot and wait for it; False while blocked."""
    with _locked(path) as state:
        now = time.time()
        if float(state.get("blockedUntil") or 0) > now:
            return False
        start = max(now, float(state.get("lastRequestAt") or 0) + gap)
        state["lastRequestAt"] = start
    if start > now:
        sleep(start - now)
    return True


def report_block(collector: str, *, path: Path | None = None, seconds: float = BLOCK_SECONDS) -> float:
    """Record that Instagram refused a logged-out query from this host."""
    with _locked(path) as state:
        until = max(float(state.get("blockedUntil") or 0), time.time() + seconds)
        state.update(blockedUntil=until, blockedBy=collector)
        return until
