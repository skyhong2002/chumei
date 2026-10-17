"""Small local-state primitives for cooperating pipeline processes (macOS/Linux)."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile


class LockBusy(RuntimeError):
    pass


@contextmanager
def file_lock(path, *, blocking=True):
    """Lock a stable sidecar inode. Never unlink lock files after unlocking."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(handle, flags)
        except BlockingIOError as exc:
            raise LockBusy(f"Another job owns {path.name}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def atomic_json(path, data):
    """Replace with a unique, flushed same-directory file; readers see whole JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def merge_json(path, updates):
    """Reload under the OS lock, preserving unrelated records from other writers."""
    path = Path(path)
    with file_lock(path.with_suffix(path.suffix + ".lock")):
        data = read_json(path, {})
        data.update(updates)
        atomic_json(path, data)
    return data
