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

`fetch_stories_apify.py` replaces the account-bound Instaloader job. It scans
at most five due organization accounts per three-hour pipeline run, delivers
at most ten active Stories, and stops at the same US$10 reserve. Accounts are
ranked by their historical posting cadence; active accounts are checked first.
Story media is downloaded immediately because CDN URLs expire.

The old `fetch_stories.py` and the authenticated backends in
`fetch_instagram.py` remain only as diagnostic/migration code. They are not
called by `run_pipeline.py`.

Anonymous Story viewer websites are not automated: the sites checked during
evaluation either prohibit bulk/scraping access or expose no supported API.
The Apify Story actor is used only for public organization/creator accounts;
private or personal accounts are outside this collector's scope.

## Free-credit guardrails

- No collector reads a maintainer's Instagram cookie.
- Profile and Story batches default to five accounts.
- The Story free-plan result cap is ten per run.
- Both Apify Instagram collectors stop when aggregate remaining credit reaches
  US$10.
- Fetch telemetry records the backend, batch size, and reported run cost.
