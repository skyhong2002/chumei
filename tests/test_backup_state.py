import json
from contextlib import closing
from pathlib import Path
import plistlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import backup_state
from auth_server import AuthStore
import push_common
import render_deployment


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'app'
        self.push = self.root / 'state/push'
        self.push.mkdir(parents=True)
        self.db = self.root / 'state/auth.sqlite3'
        self.store = AuthStore(self.db)
        self.backups = self.base / 'backups'
        for name, value in [('PUSH_DIR', self.push), ('SUBS_PATH', self.push / 'subscriptions.json'), ('LOCK_PATH', self.push / 'subscriptions.lock')]:
            patch = mock.patch.object(push_common, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.user = self.store.get_or_create_user('google', 'one', 'one@example.test')
        self.other = self.store.get_or_create_user('google', 'two', 'two@example.test')
        self.session = self.store.create_session(self.user['id'])
        self.other_session = self.store.create_session(self.other['id'])
        self.store.set_user_follow(self.other['id'], 42, 'club', True)
        self.calendar = self.store.calendar_token(self.other['id'])
        push_common.save_subs({'subs': {'one': {'user_id': self.user['id']}, 'two': {'user_id': self.other['id']}}})
        (self.push / 'vapid_private.pem').write_text('fixture-key')
        (self.root / '.env').write_text('FIXTURE_ONLY=secret')

    def test_verified_restore_retains_account_calendar_follow_and_key(self):
        bundle = backup_state.snapshot(self.root, self.backups)
        self.assertEqual(backup_state.verify(bundle)['version'], 1)
        output = backup_state.restore(bundle, self.base / 'restored', live_database=self.db)
        store = AuthStore(output / 'state/auth.sqlite3')
        self.assertEqual(store.session_user(self.other_session)['id'], self.other['id'])
        self.assertEqual(store.user_by_calendar_token(self.calendar)['id'], self.other['id'])
        self.assertEqual(store.follow_snapshot(self.other['id'])['following'][0]['id'], 42)
        self.assertEqual((output / 'state/push/vapid_private.pem').read_text(), 'fixture-key')
        self.assertEqual((output / '.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)

    def test_newer_deletion_cannot_resurrect_from_old_snapshot(self):
        bundle = backup_state.snapshot(self.root, self.backups)
        self.store.delete_account(self.user['id'])
        output = backup_state.restore(bundle, self.base / 'restored', live_database=self.db)
        store = AuthStore(output / 'state/auth.sqlite3')
        self.assertIsNone(store.session_user(self.session))
        self.assertIsNotNone(store.session_user(self.other_session))
        self.assertEqual(set(json.loads((output / 'state/push/subscriptions.json').read_text())['subs']), {'two'})
        self.assertIsNone(self.store.session_user(self.session))
        self.assertEqual(push_common.PUSH_DIR, self.push)

    def test_retention_keeps_independent_ledger_and_unrelated_directory(self):
        self.store.delete_account(self.user['id'])
        old = backup_state.snapshot(self.root, self.backups, keep=1)
        unrelated = self.backups / 'personal'
        unrelated.mkdir()
        newest = backup_state.snapshot(self.root, self.backups, keep=1)
        self.assertFalse(old.exists())
        self.assertTrue(newest.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(json.loads((self.backups / 'account-deletions.json').read_text())[0]['user_id'], self.user['id'])

    def test_tampering_refused_before_restore_writes(self):
        bundle = backup_state.snapshot(self.root, self.backups)
        (bundle / '.env').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            backup_state.restore(bundle, self.base / 'restored', live_database=self.db)
        self.assertFalse((self.base / 'restored').exists())

    def test_restore_requires_fresh_ledger_and_never_overwrites(self):
        bundle = backup_state.snapshot(self.root, self.backups)
        with self.assertRaisesRegex(ValueError, 'Fresh'):
            backup_state.restore(bundle, self.base / 'restored')
        with self.assertRaisesRegex(ValueError, 'must not exist'):
            backup_state.restore(bundle, self.root, live_database=self.db)

    def test_committed_wal_rows_are_backed_up(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=0')
            connection.execute("UPDATE users SET display_name='WAL snapshot' WHERE id=?", (self.other['id'],))
            connection.commit()
            bundle = backup_state.snapshot(self.root, self.backups)
            with closing(sqlite3.connect(bundle / 'state/auth.sqlite3')) as saved:
                self.assertEqual(saved.execute('SELECT display_name FROM users WHERE id=?', (self.other['id'],)).fetchone()[0], 'WAL snapshot')

    def test_separate_deletion_ledger_restore_and_idempotence(self):
        bundle = backup_state.snapshot(self.root, self.backups)
        ledger = self.base / 'fresh-ledger.json'
        ledger.write_text(json.dumps([{'user_id': self.user['id'], 'deleted_at': 123}]))
        output = backup_state.restore(bundle, self.base / 'restored', deletion_ledger=ledger)
        again = backup_state.restore(bundle, self.base / 'again', deletion_ledger=output / 'account-deletions.json')
        self.assertIsNone(AuthStore(again / 'state/auth.sqlite3').session_user(self.session))

    def test_invalid_runtime_json_does_not_publish_or_prune(self):
        good = backup_state.snapshot(self.root, self.backups, keep=1)
        (self.root / 'state/bot_telegram.json').write_text('{incomplete')
        with self.assertRaises(json.JSONDecodeError):
            backup_state.snapshot(self.root, self.backups, keep=1)
        self.assertTrue(good.exists())
        self.assertFalse(list(self.backups.glob('.incomplete-*')))

    def test_rendered_inventory_uses_new_root_and_never_starts_senders(self):
        output = render_deployment.render(self.root, self.base / 'deploy', self.backups)
        files = list(output.glob('*.plist'))
        self.assertEqual(len(files), 10)
        for path in files:
            config = plistlib.loads(path.read_bytes())
            self.assertEqual(config['WorkingDirectory'], str(self.root.resolve()))
            self.assertNotIn(render_deployment.OLD_ROOT, path.read_text())
        for label in ['backup', 'telegram', 'push-drip']:
            config = plistlib.loads((output / ('tw.observe.chumei.' + label + '.plist')).read_bytes())
            self.assertFalse(config['RunAtLoad'])
        self.assertIn(str(self.root.resolve() / 'published/current'), (output / 'chumei.caddy').read_text())


if __name__ == '__main__':
    unittest.main()
