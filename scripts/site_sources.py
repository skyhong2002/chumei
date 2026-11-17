"""Carry repository changes under site/ into a separately mounted site directory.

Production mounts persistent storage over ROOT/site, so the checkout's own site/
files are hidden there and a `git pull` alone never updates templates or assets.
Before each publication, apply what changed in the repository since the last
synchronised commit. Files the repository did not touch keep their runtime
content (refreshed avatars, generated pages).
"""

import os
from pathlib import Path
import subprocess
import sys

MARKER = Path("state") / "site_source_revision"


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".sync-tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def sync_site_sources(root):
    """Return (updated, removed) counts; never raises, so publication continues."""
    root = Path(root)
    site = root / "site"
    if not site.is_mount():
        return 0, 0  # site/ is the working tree itself; git already manages it.
    marker = root / MARKER
    try:
        head = _git(root, "rev-parse", "HEAD").decode().strip()
        previous = marker.read_text().strip() if marker.is_file() else ""
        if previous == head:
            return 0, 0
        updated = removed = 0
        if previous:
            changes = _git(root, "diff", "--no-renames", "--name-status", "-z",
                           previous, head, "--", "site").decode().split("\0")
            for status, name in zip(changes[0::2], changes[1::2]):
                target = root / name
                if status == "D":
                    removed += target.is_file()
                    target.unlink(missing_ok=True)
                else:
                    _write(target, _git(root, "cat-file", "blob", f"{head}:{name}"))
                    updated += 1
        _write(marker, (head + "\n").encode())
        print(f"site sources: {updated} updated, {removed} removed "
              f"({previous[:7] or 'first run'} -> {head[:7]})", flush=True)
        return updated, removed
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", b"") or b""
        print(f"site sources not synchronised: {error} {detail.decode(errors='replace').strip()}",
              file=sys.stderr, flush=True)
        return 0, 0
