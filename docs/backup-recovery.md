# Backup, restore, and deployment

The repository previously had migration snapshots but no regular backup job.
The local inventory found two September 5 migration snapshots in `state/backups`
and no separately configured local backup job. Production service inventory includes auth, MCP, LINE/Telegram bots, push,
pipeline, submissions, push drip, and Telegram publishing. Existing external
backup coverage is **not verified**. Check the operator's backup service before
enabling another schedule. This implementation provides local recovery; a local
copy alone does not protect against host loss.

## What is captured

`backup_state.py create` uses SQLite's online backup API (including committed WAL
transactions), holds the same push lock as account deletion, and copies push
subscriptions, sending state, and the VAPID private key. It also captures `.env`,
`.env.apify`, Telegram delivery state, and Telegram bot offsets when present.
The private manifest records hashes and the Git revision, never credential
values. Directories are mode 0700 and files 0600. Copies contain personal data and
plaintext configured secrets: restrict their destination and encrypt any external
copy. The tool does not fetch from providers, send notifications, or export
Keychain entries; runtime credentials now come only from environment files or
process variables. Any process-only secret must also be preserved in a protected
credential file or separate encrypted custody. SQLite integrity and foreign keys are checked before a snapshot
becomes visible; incomplete snapshots are not considered backups.

```sh
.venv/bin/python scripts/backup_state.py create --destination /private/path/chumei-backups
.venv/bin/python scripts/backup_state.py verify /private/path/chumei-backups/SNAPSHOT
```

For a nondefault `CHUMEI_AUTH_DATABASE`, pass its absolute path with `--database`;
add that same argument to the generated backup job. Avoid placing backups in a
public static directory. Keep the destination outside the checkout, preferably
on a separate encrypted volume. Default retention is the latest **168 successful
snapshots**: approximately seven days with hourly execution. A failed backup does
not prune old snapshots. The independent `account-deletions.json` is cumulative
and is not pruned when snapshots expire. Also retain a fresh offsite ledger so an
older recovery never silently restores a deleted account. It contains random
user IDs and deletion times, not identities or tokens.

The hourly schedule gives a **target RPO of one hour while the machine and job
are healthy**. Monitor launchd's exit status and the newest manifest timestamp;
an outage or sleeping machine extends this window. The initial operational RTO
target is **one hour after a known-good snapshot and credentials are available**;
it is a target, not a measured guarantee for a complete replacement host. Fixture
restore tests verify account/session/subscription recovery and deletion replay.
Measure the full replacement-host drill before committing to a service SLA.

## Restore drill and recovery

Restore always writes a **new isolated directory**, verifies all hashes and
SQLite integrity, migrates the staged database, and reapplies the newest account
deletion ledger against the staged database and push subscriptions. It cannot
replace live state. `verify` is a read-only dry run. A live database or independently
preserved ledger is required for restore; an old bundle alone is insufficient.

```sh
.venv/bin/python scripts/backup_state.py restore /private/path/chumei-backups/SNAPSHOT \
  --output /private/path/chumei-restore-drill \
  --live-database /path/to/chumei/state/auth.sqlite3 \
  --deletion-ledger /private/path/chumei-backups/account-deletions.json
```

For a real restore, first stop **all writers** (auth, push, submissions, pipeline,
bots, and both sending jobs). Preserve the newest database/deletion ledger before
replacing anything. Run restore while writers remain stopped. Review
`restore-report.json`; verify account login/session lookup, follows, and private
feeds in isolation without sending notifications. Preserve another copy of the
old live state, then install the staged `state/auth.sqlite3` and `state/push` as a
unit, plus applicable Telegram files. Do not carry old `auth.sqlite3-wal` or
`auth.sqlite3-shm` into the restored state; move these sidecars aside with the old
database while all processes are stopped. Restore configuration deliberately;
the staged `.env` files must not blindly replace newer credentials. Restart only
read-serving services first and check logs before enabling scheduled writers or
notification senders. Staging and installing are separate to permit inspection
and rollback without destructive defaults.

If the live database and newest independent deletion ledger are both lost, newer
deletions cannot be reconstructed from an older snapshot. Supply the newest
surviving ledger and explicitly accept/document that gap before disaster restore.
Likewise, restored old delivery state can cause duplicate external messages:
inspect Telegram/push state and leave senders disabled until reconciled. Ordinary
online snapshots do not claim a globally atomic snapshot across bot offset and
Telegram publisher files; stop these writers for an exact cutover backup.

## Keys and an offsite copy

The following must be recoverable in an operator-controlled encrypted password
manager or encrypted credential-file backup, independently of the host:

- NYCU and Google OAuth client IDs/secrets; NTHU provider configuration.
- Feed signing key and Apify contribution encryption key. If derived from the
  NYCU client secret, preserve that original secret. Losing it invalidates saved
  feed signatures and prevents decrypting contributed API tokens.
- VAPID private key (included in the protected push backup). Generating a new key
  does not restore existing browser subscriptions.
- Telegram/LINE tokens, webhook secrets, and any operator Apify credentials.
- Caddy's complete host configuration/certificate state and DNS/tunnel credentials
  for the host; the repository template covers only this site's proxy block.

See [credential migration](credential-migration.md) before updating an older
Keychain-based host. New backups include the migrated `.env` and `.env.apify`
files; backups from before migration may lack those credentials. The backup
manifest records `credential_storage: env_files`, not proof that every required
key is present. No runtime Keychain access remains. Do not paste key material
into issue comments, logs, or this repository. An offsite destination is not
automatically configured. The operator must configure encrypted replication of
the backup directory **including the independent deletion ledger**, use separate
credentials/access control, set remote expiration consistent with privacy
retention, and perform a download-and-restore drill. Record its actual frequency,
retention, and most recent verified restore; do not label host-loss recovery ready
until this is done.

## Rebuilding on another Mac

1. Clone the manifest's Git revision. Install the documented Python version and
   dependencies; use the checked-in dependency lock when available. Install
   Playwright Chromium and Caddy. Recreate the private `state` directory.
2. Recover credentials and restore the verified private state as above. Recover
   `data/feeds`, extraction/cache state, and a published release from a separately
   configured content backup, or rebuild public source data. These bulk public
   caches are deliberately outside the account backup; rebuilding them may need
   provider access and quota. For immediate static availability preserve the
   existing `published/current` release externally as part of host backup.
3. Generate relocatable deployment files (this does not install/start anything):

   ```sh
   .venv/bin/python scripts/render_deployment.py --root /path/to/chumei \
     --output /private/path/chumei-deploy \
     --backup-destination /private/path/chumei-backups
   ```

   Output includes all tracked services plus `tw.observe.chumei.telegram.plist`
   and `tw.observe.chumei.backup.plist`. The latter runs hourly, retains 168
   snapshots, and does not run on load. Create the log/state and backup directories.
4. Publish a validated release via `scripts/publish_site.py --offline`; Caddy's
   rendered root points to `published/current`. Merge only this host block into
   the host's full Caddy config, validate it, and reload. See atomic-publication.md.
5. Install selected plists in `~/Library/LaunchAgents`, with `launchctl bootstrap
   gui/$(id -u) FILE`. Check existing labels first to avoid duplicate schedules.
   Persistent services have KeepAlive; scheduled writers have RunAtLoad false.
   Enabling publisher jobs may send real messages on their next interval; inspect
   state and perform their supported check/dry-run before enabling them.
6. Take and verify one manual backup, confirm scheduled exit status and freshness,
   then run the isolated restore command. Confirm a deleted account remains absent
   and another account/subscription survives. Document elapsed restore time and
   configure/verify encrypted offsite replication.
