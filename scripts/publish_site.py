"""Build and validate an isolated release, then atomically switch publication.

Caddy must serve published/current. site/ remains the mutable source/cache tree.
Run --rollback to switch back to the previous successful release.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
BUILD_STEPS = ("build_map_data.py", "build_site.py", "build_status_page.py", "validate_outputs.py")
# A publication normally takes ~4 minutes; the slowest seen took ~14, almost all
# of it in build_site.py. Both limits stay well below run_pipeline's 7200s step
# limit so a hung build times out here and removes its own staging directory
# instead of being SIGKILLed with the staging copy orphaned.
STEP_TIMEOUT = 1800
PUBLISH_BUDGET = 3600


@contextmanager
def exclusive_lock(path):
    """Fail visibly if another job owns the lock; process death releases it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another job is running (lock: {path})") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_link(link, target):
    """rename(2) replaces a symlink without any missing-current interval."""
    temporary = link.parent / f".{link.name}-{uuid.uuid4().hex}"
    try:
        temporary.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def copy_tree(source, target):
    """Overlay source onto target as independent files (never hardlinks).

    On macOS, APFS clones share blocks copy-on-write, so a release costs almost
    no SSD writes yet later writes to either tree never reach the other. cp falls
    back to a real copy on filesystems without cloning; copytree covers other
    platforms or any cp failure, overwriting whatever a partial cp left behind.
    """
    if sys.platform == "darwin":
        # -L follows symlinks like copytree(symlinks=False); -p matches copy2.
        result = subprocess.run(["/bin/cp", "-c", "-p", "-R", "-L", f"{source}/.", f"{target}/"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            return
        print(f"Clone copy failed, using a full copy: {result.stderr.strip()}", file=sys.stderr)
    shutil.copytree(source, target, dirs_exist_ok=True)


def step_timeout(script, deadline):
    """Per-step limit, capped by what is left of the whole publication's budget."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(script, 0)
    return min(STEP_TIMEOUT, remaining)


def run_build_step(script, stage, root=ROOT, *, offline=False, timeout=STEP_TIMEOUT):
    env = dict(os.environ, CHUMEI_BUILD_DIR=str(stage))
    if offline:
        env["CHUMEI_BUILD_OFFLINE"] = "1"
    python = root / ".venv" / "bin" / "python"
    subprocess.run([str(python), str(root / "scripts" / script)], env=env,
                   check=True, timeout=timeout)


def _managed_target(link, releases):
    if not link.is_symlink():
        if link.exists():
            raise RuntimeError(f"Refusing to replace non-symlink: {link}")
        return None
    target = link.resolve(strict=True)
    if target.parent != releases.resolve() or not (target / ".release.json").is_file():
        raise RuntimeError(f"Not a managed release: {link}")
    return target


def publish(root=ROOT, *, runner=None, offline=False):
    """All mutations before the final symlink replacement are private."""
    root = Path(root).resolve()
    publication = root / "published"
    releases = publication / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + PUBLISH_BUDGET
    runner = runner or (lambda script, stage: run_build_step(
        script, stage, root, offline=offline, timeout=step_timeout(script, deadline)))
    with exclusive_lock(root / "state" / "publish.lock"):
        current = publication / "current"
        previous = publication / "previous"
        old = _managed_target(current, releases)
        _managed_target(previous, releases)
        stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=releases))
        candidate = None
        try:
            # Independent copies (never hardlinks) keep builds from mutating live
            # files. Preserve historic event URLs and generated image caches, then
            # overlay repository templates/assets and the latest fetcher outputs.
            if old:
                copy_tree(old, stage)
            copy_tree(root / "site", stage)
            (stage / ".release.json").unlink(missing_ok=True)
            for script in BUILD_STEPS:
                runner(script, stage)
            name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
            (stage / ".release.json").write_text(json.dumps({
                "id": name, "validated": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }) + "\n")
            candidate = releases / name
            os.replace(stage, candidate)
            if old:
                atomic_link(previous, old)
            atomic_link(current, candidate)
            # Retention runs separately after publication, under the same lock.
            return candidate
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            # If the pointer switch succeeded, the release must remain available.
            if candidate and (not current.is_symlink() or current.resolve() != candidate):
                shutil.rmtree(candidate, ignore_errors=True)
            raise


def rollback(root=ROOT):
    root = Path(root).resolve()
    publication = root / "published"
    releases = publication / "releases"
    with exclusive_lock(root / "state" / "publish.lock"):
        current = _managed_target(publication / "current", releases)
        previous = _managed_target(publication / "previous", releases)
        if current is None or previous is None:
            raise RuntimeError("No previous successful publication to restore")
        # Switching current is the only operation necessary for rollback. Keep the
        # previous pointer unchanged so interrupted rollback remains repeatable.
        atomic_link(publication / "current", previous)
        return previous


def prune(root=ROOT, *, keep=3):
    """Keep the newest N managed releases, always protecting both pointers."""
    if keep < 2:
        raise ValueError("keep must be at least 2")
    root = Path(root).resolve()
    publication = root / "published"
    releases = publication / "releases"
    with exclusive_lock(root / "state" / "publish.lock"):
        protected = {_managed_target(publication / name, releases)
                     for name in ("current", "previous")}
        candidates = sorted((path for path in releases.glob("*")
                             if path.is_dir() and not path.is_symlink()
                             and not path.name.startswith(".")
                             and (path / ".release.json").is_file()),
                            key=lambda path: path.name, reverse=True)
        protected.update(candidates[:keep])
        removed = []
        for path in candidates:
            if path not in protected:
                shutil.rmtree(path)
                removed.append(path)
        return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--rollback", action="store_true")
    actions.add_argument("--prune", action="store_true", help="Only prune old managed releases")
    parser.add_argument("--keep", type=int, default=3, help="Retain at least this many newest releases, plus current/previous")
    parser.add_argument("--offline", action="store_true", help="Use cached images/geocodes and quota status; no build-time network")
    args = parser.parse_args()
    if args.keep < 2:
        parser.error("--keep must be at least 2")
    try:
        if args.prune:
            print(f"Pruned {len(prune(keep=args.keep))} old releases")
            return 0
        release = rollback() if args.rollback else publish(offline=args.offline)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Publication failed; current release retained: {exc}", file=sys.stderr)
        return 1
    print(f"Published: {release}")
    if not args.rollback:
        try:
            prune(keep=args.keep)
        except (OSError, RuntimeError) as exc:
            # Publication succeeded; retention trouble must not misreport it.
            print(f"Release retention deferred: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
