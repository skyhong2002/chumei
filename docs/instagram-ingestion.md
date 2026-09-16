# Instagram ingestion

Chumei must not depend on a maintainer's Instagram login. Profile posts and
Stories use separate collectors because Instagram exposes them differently.

## Profile posts

`fetch_instagram_public.py` first tries Instagram's logged-out
`web_profile_info` response with no cookies. A server IP may receive 401/429;
that path then cools down for 24 hours. While the shared Apify pool has more
than US$10 remaining, the collector falls back to Apify's Instagram Profile
Scraper, which also needs no Chumei-owned Instagram account. The US$10 reserve
is kept for the existing Facebook collector.

Both paths write the existing `rsshub` inbox/seen namespace so switching
providers cannot republish old posts. Pinned posts are excluded from cadence
estimation. Each profile is assigned a stable 12, 24, 48, 72, 168, or 336 hour
polling tier from the median gap between its recent posts and how long it has
been dormant.

## Stories

`fetch_stories_apify.py` replaces the account-bound Instaloader job. The
actor (`intropix/instagram-stories-scraper`) grants every free-plan Apify
account 40 result items per day, at most 10 items and 10 scanned profiles per
run, and always admits an account's first run of the day even when the shared
free pool is busy. Each pipeline invocation rotates through the token pool:
every run takes a batch of up to ten due profiles on the account with the most
allowance left today (`apify_pool.choose_story_token`), and the number of runs
per invocation spreads the pool's remaining daily allowance over the eight
three-hour pipeline slots so live Stories are caught before they expire.
Per-account allowance lives in `state/apify_pool.json` (`accounts.<label>.story`)
and resets at UTC midnight; a `user_daily_exhausted` denial parks the account
until then, a `free_capacity_exhausted` denial for one hour. Profiles the
actor reports as not attempted stay due instead of being marked scanned.
Accounts are ranked by their historical posting cadence; active accounts are
checked first. Story media is downloaded immediately because CDN URLs expire.

Runs are not free: each charges the account's monthly credit (US$0.005 per
run start, US$0.002 per scanned profile, US$0.0025 per delivered item, about
US$0.03–0.05 per run), so the collector still stops at the same US$10
aggregate reserve as the Facebook collector.

The old `fetch_stories.py` and the authenticated backends in
`fetch_instagram.py` remain only as diagnostic/migration code. They are not
called by `run_pipeline.py`.

Anonymous Story viewer websites are not automated: the sites checked during
evaluation either prohibit bulk/scraping access or expose no supported API.
The Apify Story actor is used only for public organization/creator accounts;
private or personal accounts are outside this collector's scope.

## Free-credit guardrails

- No collector reads a maintainer's Instagram cookie.
- Profile batches default to five accounts; Story runs scan at most ten
  profiles and deliver at most ten items, and each Apify account gets at most
  40 Story items per day.
- Both Apify Instagram collectors stop when aggregate remaining credit reaches
  US$10.
- Fetch telemetry records the backend, batch size, and reported run cost.
