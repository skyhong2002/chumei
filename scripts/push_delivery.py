"""Durable, local Web Push outbox; no subscription secrets are stored here.

The journal is a write-ahead checkpoint, not a second delivery queue. A failed
JSON snapshot replacement can be recovered without losing accepted receipts.
Callers hold publisher_lock across load/plan/send/save to serialize publishers.
"""

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

TERMINAL = {"sent", "gone", "cancelled", "exhausted"}
MAX_ATTEMPTS = 5
RETRY_BASE_SECONDS = 30 * 60
RETRY_MAX_SECONDS = 6 * 3600


def migrate(state):
    if not isinstance(state, dict) or state.get("version", 1) not in (1, 2):
        raise ValueError("unsupported push delivery state version")
    # Legacy membership is a replay fence, even for empty legacy values. There
    # is no reliable way to reconstruct which old recipients actually received.
    state.setdefault("sent", {})
    state.setdefault("reminders", {})
    state.setdefault("deliveries", {})
    if any(not isinstance(state[key], dict) for key in ("sent", "reminders", "deliveries")):
        raise ValueError("invalid push delivery state")
    if not isinstance(state.get("revision", 0), int) or state.get("revision", 0) < 0:
        raise ValueError("invalid push checkpoint revision")
    state["version"] = 2
    return state


def journal_path(path):
    return Path(str(path) + ".journal")


def load(path):
    path = Path(path)
    journal = journal_path(path)
    source = journal if journal.exists() else path
    if not source.exists():
        return None
    state = migrate(json.loads(source.read_text(encoding="utf-8")))
    if source == journal and path.exists():
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return state  # The durable journal can repair a torn snapshot.
        snapshot = migrate(snapshot)
        if snapshot.get("revision", 0) > state.get("revision", 0):
            return snapshot  # A backup may have captured an older journal.
    return state


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path, data):
    temporary = Path(str(path) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    _sync_dir(path.parent)


def save(state, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["revision"] = state.get("revision", 0) + 1
    data = json.dumps(state, ensure_ascii=False, indent=1)
    journal = journal_path(path)
    _atomic_write(journal, data)
    _atomic_write(path, data)
    journal.unlink()
    _sync_dir(path.parent)


@contextmanager
def publisher_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(str(path) + ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def group(state, kind, event_id, user_id=None):
    bucket = state["sent"] if kind == "event" else state["reminders"]
    identifier = event_id if kind == "event" else f"{user_id}:{event_id}"
    return bucket.setdefault(identifier, {"status": "queued", "devices": {}})


def enqueue(state, kind, device, event_ids, *, user_id=None, digest=False):
    identity = json.dumps([kind, user_id, device, sorted(event_ids)], separators=(",", ":"))
    delivery_id = hashlib.sha256(identity.encode()).hexdigest()[:32]
    job = state["deliveries"].setdefault(delivery_id, {
        "id": delivery_id, "kind": kind, "device": device, "event_ids": list(event_ids),
        "user_id": user_id, "digest": digest, "status": "pending", "attempts": 0,
    })
    for event_id in event_ids:
        group(state, kind, event_id, user_id)["devices"].setdefault(
            device, {"delivery_id": delivery_id, "status": job["status"]})
    return job


def receipt(state, job, event_id, status, stamp):
    entry = group(state, job["kind"], event_id, job.get("user_id"))
    device = entry["devices"][job["device"]]
    device.update(status=status, updated_at=stamp)
    if status == "sent":
        device["sent_at"] = stamp
    devices = entry["devices"].values()
    if all(value["status"] in TERMINAL for value in devices):
        entry.update(status="complete", completed_at=stamp)


def finish(state, job, status, stamp):
    job.update(status=status, updated_at=stamp)
    for event_id in job["event_ids"]:
        device = group(state, job["kind"], event_id, job.get("user_id"))["devices"][job["device"]]
        if device["status"] not in TERMINAL:
            receipt(state, job, event_id, status, stamp)


def retry_delay(attempts):
    return min(RETRY_BASE_SECONDS * 2 ** (attempts - 1), RETRY_MAX_SECONDS)
