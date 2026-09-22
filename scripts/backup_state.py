#!/usr/bin/env python3
"""Private local snapshots and verified, isolated restore; never replaces live state."""
from __future__ import annotations
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def private_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)


@contextmanager
def file_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        path.chmod(0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def ledger_from_db(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='account_deletions'").fetchone():
            return []  # Pre-deletion-feature databases have no tombstones.
        return [dict(user_id=r[0], deleted_at=r[1]) for r in conn.execute('SELECT user_id,deleted_at FROM account_deletions')]


def merge_ledgers(*ledgers):
    result = {}
    for records in ledgers:
        for row in records:
            uid, when = str(row['user_id']), int(row['deleted_at'])
            result[uid] = max(result.get(uid, 0), when)
    return [dict(user_id=uid, deleted_at=when) for uid, when in sorted(result.items())]


def check_db(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite foreign-key check failed')


def private_copy(source, target):
    if source.is_symlink():
        raise ValueError('Refusing symlink in backup input')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(source, target)
    target.chmod(0o600)


def snapshot(root, destination, *, database=None, keep=168):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if keep < 1:
        raise ValueError('keep must be at least 1')
    database = Path(database) if database else root / 'state/auth.sqlite3'
    if not database.is_file():
        raise ValueError('Auth database does not exist')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    with file_lock(destination / '.backup.lock'):
        staging = Path(tempfile.mkdtemp(prefix='.incomplete-', dir=destination))
        try:
            (staging / 'state/push').mkdir(parents=True, mode=0o700)
            # Same lock order as account deletion: push lock, then SQLite.
            with file_lock(root / 'state/push/subscriptions.lock'):
                with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as source:
                    with closing(sqlite3.connect(staging / 'state/auth.sqlite3')) as target:
                        source.backup(target)
                for path in (root / 'state/push').rglob('*'):
                    if path.is_file() and path.suffix not in {'.lock', '.tmp'}:
                        private_copy(path, staging / path.relative_to(root))
            for relative in ['.env', '.env.apify', 'state/telegram.json', 'state/bot_telegram.json']:
                source = root / relative
                if source.is_file():
                    private_copy(source, staging / relative)
            ledger_path = destination / 'account-deletions.json'
            ledger = merge_ledgers(json.loads(ledger_path.read_text()) if ledger_path.exists() else [], ledger_from_db(staging / 'state/auth.sqlite3'))
            private_json(ledger_path, ledger)  # Kept independently of snapshot retention.
            private_json(staging / 'account-deletions.json', ledger)
            check_db(staging / 'state/auth.sqlite3')
            revision = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
            files = {}
            for path in staging.rglob('*'):
                if path.is_file():
                    path.chmod(0o600)
                    if path.suffix == '.json':
                        json.loads(path.read_text())  # Reject a torn concurrent bot-state write.
                    files[str(path.relative_to(staging))] = hashlib.sha256(path.read_bytes()).hexdigest()
                elif path.is_dir():
                    path.chmod(0o700)
            manifest = dict(version=1, created_at=datetime.now(timezone.utc).isoformat(), git_revision=revision, files=files,
                            keychain_included=False, credential_storage="env_files", offsite_copy=False)
            private_json(staging / 'manifest.json', manifest)
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:8]
            final = destination / name
            staging.rename(final)
            # Prune only directories carrying our validated manifest format.
            snapshots = sorted(p for p in destination.iterdir() if p.is_dir() and not p.is_symlink() and (p / 'manifest.json').is_file() and re.fullmatch(r'\d{8}T\d{6}\.\d{6}Z-[0-9a-f]{8}', p.name))
            for old in snapshots[:-keep]:
                verify(old)
            for old in snapshots[:-keep]:
                shutil.rmtree(old)
            return final
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise


def verify(bundle):
    bundle = Path(bundle).resolve()
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('version') != 1 or not {'state/auth.sqlite3', 'account-deletions.json'}.issubset(manifest.get('files', {})):
        raise ValueError('Unsupported or incomplete backup manifest')
    for relative, digest in manifest['files'].items():
        path = bundle / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts or path.resolve().is_relative_to(bundle) is False or path.is_symlink():
            raise ValueError('Unsafe path in backup manifest')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Backup checksum mismatch')
    check_db(bundle / 'state/auth.sqlite3')
    return manifest


def restore(bundle, output, *, live_database=None, deletion_ledger=None):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Restore output must not exist; live replacement is never automatic')
    if live_database is None and deletion_ledger is None:
        raise ValueError('Fresh live database or independently preserved deletion ledger is required')
    manifest = verify(bundle)
    ledgers = [json.loads((bundle / 'account-deletions.json').read_text())]
    if live_database is not None:
        ledgers.append(ledger_from_db(Path(live_database)))
    if deletion_ledger is not None:
        ledgers.append(json.loads(Path(deletion_ledger).read_text()))
    ledger = merge_ledgers(*ledgers)
    output.mkdir(parents=True, mode=0o700)
    try:
        for relative in manifest['files']:
            private_copy(bundle / relative, output / relative)
        # Import only when restoring; all mutable paths are scoped to this stage.
        import push_common
        from auth_server import AuthStore
        previous = (push_common.PUSH_DIR, push_common.SUBS_PATH, push_common.LOCK_PATH)
        push_common.PUSH_DIR = output / 'state/push'
        push_common.SUBS_PATH = push_common.PUSH_DIR / 'subscriptions.json'
        push_common.LOCK_PATH = push_common.PUSH_DIR / 'subscriptions.lock'
        try:
            AuthStore(output / 'state/auth.sqlite3').reapply_account_deletions(ledger)
        finally:
            push_common.PUSH_DIR, push_common.SUBS_PATH, push_common.LOCK_PATH = previous
        check_db(output / 'state/auth.sqlite3')
        private_json(output / 'account-deletions.json', ledger)
        private_json(output / 'restore-report.json', dict(verified=True, source_created_at=manifest['created_at'], git_revision=manifest['git_revision'], replayed_deletions=len(ledger)))
        for path in output.rglob('*'):
            path.chmod(0o700 if path.is_dir() else 0o600)
        return output
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create')
    create.add_argument('--root', type=Path, default=ROOT)
    create.add_argument('--destination', type=Path, required=True)
    create.add_argument('--database', type=Path)
    create.add_argument('--keep', type=int, default=168)
    check = sub.add_parser('verify')
    check.add_argument('bundle', type=Path)
    recover = sub.add_parser('restore')
    recover.add_argument('bundle', type=Path)
    recover.add_argument('--output', type=Path, required=True)
    recover.add_argument('--live-database', type=Path)
    recover.add_argument('--deletion-ledger', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == 'create':
        print(snapshot(args.root, args.destination, database=args.database, keep=args.keep))
    elif args.command == 'verify':
        verify(args.bundle)
        print('Backup checksums and SQLite integrity verified.')
    else:
        print(restore(args.bundle, args.output, live_database=args.live_database, deletion_ledger=args.deletion_ledger))


if __name__ == '__main__':
    main()
