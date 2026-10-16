# Instagram ingestion

Chumei must not depend on a maintainer's Instagram login. Profile posts and
Stories use separate collectors because Instagram exposes them differently.

## Profile posts

`fetch_instagram_public.py` first asks instagram.com the way a logged-out
browser does: the profile page hands every anonymous visitor an LSD token and
`csrftoken`/`mid` cookies, and the web app's own profile-posts GraphQL query
(`PolarisProfilePostsQuery`, `fetch_instagram.PROFILE_POSTS_DOC_ID`) then
returns the latest posts without any Instagram account. The older
`api/v1/users/web_profile_info` endpoint now answers logged-out server IPs
with 401 `require_login` and is no longer used.

From this host Instagram still serves very few logged-out queries: popular
profiles usually answer, but most club accounts get 401 "Please wait a few
minutes" / `require_login` after the first query or two, and the block can
outlast an hour of one probe per minute (measured 2026-10-16). The direct path
is therefore a free best-effort first try, not the main collector.

Chumei and Harmonica run on the same host and share that per-IP allowance, so
both pace logged-out queries through `scripts/ig_public_host.py` (state in
`~/.cache/observe-instagram-public.json`, overridable with
`OBSERVE_IG_PUBLIC_HOST_STATE`). Any two queries from either project are at
least ten seconds apart, and the first refusal blocks direct queries for the
whole host for two hours, so neither project keeps the IP blocked. Three
consecutive non-rate-limit failures also stop the round, because they usually
mean the query itself changed. Instagram rotates the GraphQL doc id with web
releases; set `CHUMEI_IG_PROFILE_POSTS_DOC_ID` to override it without a deploy.
Harmonica keeps an identical copy of the host module; change both together.

Accounts the direct path could not serve fall back to Apify's Instagram
Profile Scraper, which also needs no Chumei-owned Instagram account. The
fallback is paid from the Instagram share of the pool's daily credit (see
below); accounts beyond that share wait, without backoff, for the next round.

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
US$0.03–0.05 per run), paid from the Story share of the pool (see below).

The old `fetch_stories.py` and the authenticated backends in
`fetch_instagram.py` remain only as diagnostic/migration code. They are not
called by `run_pipeline.py`.

Anonymous Story viewer websites are not automated: the sites checked during
evaluation either prohibit bulk/scraping access or expose no supported API.
The Apify Story actor is used only for public organization/creator accounts;
private or personal accounts are outside this collector's scope.

## Sharing Apify credit

Facebook pages, Instagram Stories and the Instagram post fallback draw on the
same Apify pool, and share it equally (`apify_pool.apify_allocation`):

- Each UTC day the pool may spend each account's remaining credit divided by
  the days left in its billing cycle, so the pool lasts until every reset.
- Each consumer is guaranteed a third of that daily amount. A share it has not
  spent expires gradually over the day: at 18:00 UTC a consumer that spent
  nothing still holds a quarter of its share. The expired part goes to whoever
  still needs credit, so busy collectors use what quiet ones leave, but never
  what those could still claim.
- Every run is charged to its consumer in `state/apify_pool.json` (`spend`,
  plus a 14-day `spendHistory`). Runs whose cost Apify does not report are
  charged a per-source estimate.
- Facebook's page revisit interval is sized from its share plus what the other
  consumers left unused over the past week. Each pipeline round, Facebook and
  the Instagram fallback spend the allowance spread over the rounds left in
  the UTC day.

`/status/` shows today's pace, each consumer's spend against its share, and
its 30-day spend.

## Free-credit guardrails

- No collector reads a maintainer's Instagram cookie.
- Profile batches default to five accounts; Story runs scan at most ten
  profiles and deliver at most ten items, and each Apify account gets at most
  40 Story items per day.
- Facebook, Stories and the Instagram post fallback each get an equal share
  of the pool's evenly paced daily credit.
- Fetch telemetry records the backend, batch size, and reported run cost.
