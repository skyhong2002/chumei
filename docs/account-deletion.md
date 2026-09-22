# Account deletion and retention

Account settings now offer permanent deletion after entering `刪除我的帳號`.
`POST /auth/account/delete` accepts only an authenticated browser, the configured
public Origin, and a session-bound confirmation token rendered on that user's
settings page. It takes the user ID only from the session. GET never deletes.
The public `/account/privacy` page explains stored data, visibility, deletion,
external-provider authorization, and backup limitations.

## What is removed

One SQLite transaction deletes identities, all sessions, follows, going marks,
private calendar token, signed saved feeds, source requests and allocations,
encrypted Apify contributions, pending OAuth account-link states, and submission
reports (including notes and verdicts). Source priority totals are reduced by
this user's allocations. Already published public events and source records are
not deleted. User IDs are random; a minimal `account_deletions(user_id, deleted_at)`
tombstone remains to prevent a later restore from resurrecting the account.

Linked push devices are removed under the shared push file lock before the DB
transaction commits. If push cleanup fails, the DB deletion rolls back and the
page reports failure. SQLite and a JSON file cannot commit atomically together:
a crash after writing push data but before SQLite commits can stop push without
finishing deletion; repeating the deletion is safe. Push writes resolve the
session again while holding that lock to prevent a delayed request from
recreating a deleted account's device. Submission inserts similarly reject
accounts deleted after their HTTP request started.

Old sessions and private/signed feed URLs fail immediately. Account identity
mapping is gone, so a later OAuth login creates a new account. Browser cookies
are expired and `Clear-Site-Data: "storage"` asks supporting browsers to remove
local state and service workers. Other browsers/devices may retain local data;
external provider accounts and already downloaded calendars are unaffected.
Already dispatched external jobs may finish. Apify runtime tokens are loaded
from the live contribution table; pool cache files store quota metadata, not
plaintext tokens, and therefore cannot supply a removed credential for a new
job. A separately configured operator token remains operator-managed.

## Deployment and restoring backups

Restart both auth and push services after deploying. Auth startup adds the
`account_deletions` table and the submission ownership trigger automatically; no manual
migration or removal of actual users is needed. No existing account is deleted
by deployment.

Before replacing a database with an older backup, export the freshest rows from
`SELECT user_id, deleted_at FROM account_deletions` and keep this ledger apart
from the database being replaced. Merge it with separately preserved ledgers;
keep the greatest timestamp for each user. Restore with services stopped, then
instantiate `AuthStore(restored_database_path)` and call:

```python
store.reapply_account_deletions(records)  # [{"user_id": "...", "deleted_at": 123}]
```

This replays deletions idempotently, restores the minimal tombstones, removes
linked push devices, and corrects priority totals. Point `push_common.PUSH_DIR`,
`SUBS_PATH`, and `LOCK_PATH` at the restored push state if staging a restore away
from the application state directory. Verify removed sessions/feeds stay
invalid before restarting services. The current ledger must be retained until
all older backups expire; preserve a fresh separate/offsite copy as appropriate.
If both the newest live database and freshest ledger are lost, the system cannot
infer deletions made after the surviving backup. Do not promise otherwise.

Backup files and access logs are not individually rewritten on deletion. Their
actual retention is governed by deployment settings; the privacy page does not
invent a guaranteed erasure deadline. Raw SQLite/WAL pages and external copies
are likewise not claimed to be securely erased immediately.

## Verification

Auth tests cover complete removal and isolation from another account, expired
sessions and both private/signed feed formats, changed account identity on later
login, Origin/CSRF/confirmation checks, concurrent push/report writes, rollback
on push disk failure, and reapplying a deletion to an older SQLite backup. All
fixtures use isolated temporary account and push state; no real account is
removed and no external push or OAuth request is sent.
