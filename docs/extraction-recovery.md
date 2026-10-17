# Extraction recovery and observation times

`extract_events.py` now retries due transient failures during an ordinary pipeline run. Each item gets at most four provider requests, including its initial request. A legacy error with no attempt count consumes one attempt. No request contains an internal transport retry or immediate JSON-repair request. Successful activities and confirmed empty/non-event results remain cached for their prompt version. Failed prompt upgrades retain historical events and recurring sessions.

Timeouts, connections, unavailable gateways, rate limits, quota errors and malformed responses are transient. Authentication, invalid requests and unknown failures wait for explicit `--retry-errors`; that flag still honors cooldowns and the four-attempt ceiling. Prompt changes do not reset an error budget. Retry intervals start at 15 minutes, then one hour, four hours and sixteen hours, capped at 24 hours. Rate limits wait at least 30 minutes; quota/authentication failures wait at least 24 hours. A usable upstream `Retry-After` can lengthen the delay (malformed/nonfinite values are ignored, and extreme values are capped at one year).

The existing `llm_gateway.py` loses the response body and headers when its last 429 fails. This patch leaves that module unchanged and conservatively treats its opaque `gateway unavailable … HTTP 429` exception as a quota failure with a 24-hour cooldown. Genuine HTTP exceptions retaining a response can distinguish rate limits, quota errors and `Retry-After`. Preserving those details in the gateway is a follow-up integration improvement.

Provider-wide transport, service, authentication and quota failures persist a circuit cooldown in `state/extraction_gateway.json`, outside the extraction source-cache directory. New scheduling stops immediately after a failure is observed; at most `--workers` requests can already be in flight. Submission reviews share this circuit and use one transport attempt. A later pipeline run can build existing cached data during a cooldown. A cooldown is not evidence that ingestion or extraction completed successfully.

Extraction holds an OS advisory lock for the whole run, so a submission-triggered extractor and the regular pipeline cannot charge for the same item concurrently. A competing job defers successfully; the owner continues. Submission processing and NYCU LIFE fetching each have their own run lock. Cache updates reload and merge changed post IDs under a stable sidecar OS lock. JSON writes use unique temporary files in the destination directory, flush/fsync, and atomic replacement. Readers see complete old or new JSON; process death releases the locks. Lock files intentionally remain and must not be unlinked during operation. These protections require cooperating versions of the scripts; do not run an old extractor alongside a new one.

Accepted submissions with due extraction errors are retried even when there are no new pending reports. Exhausted/nonretryable extraction goes to manual review. Presence in inbox alone no longer means a report was confirmed to be a non-event. This change does not migrate terminal legacy submission statuses automatically.

No cache reset or state migration is required. This implementation performs no bulk deletion, recategorization, geocoding or avatar update. Operator recovery of exhausted records should be a deliberate, record-specific action after checking the cause; `--retry-errors` deliberately cannot flood an exhausted budget by resetting all records.

## Time contract and builder handoff

NYCU LIFE no longer uses a future activity start for `posted_at`. Its structured records and new inbox items distinguish:

- `first_seen`: stable discovery time, carried from previous structured data, seen state or existing inbox before falling back to this fetch.
- `fetched_at`: time of the current fetch (structured records update it; append-only inbox retains its original observation).
- `published_at`: a valid, timezone-bearing API `publishedAt` at or before the fetch; otherwise null.
- `publication_time_basis`: `source` when publication is known, otherwise `first_seen`.
- `posted_at`: compatibility time, known publication or stable discovery; never event start.
- `start_at` / `end_at`: activity time only.

NYCU LIFE keeps historical structured records absent from later API snapshots. An empty successful response cannot erase the archive. Existing field values not owned by the API adapter are retained when an activity is refreshed. An inbox row also prevents re-appending after a crash between the inbox write and the seen-state write.

`build_site.py` is intentionally outside this change. Its integration still needs independent review:

1. `load_events()` already honors event `first_seen` via `setdefault`; preserve this behavior and prefer record `first_seen` over retry completion `ts` for legacy caches without event timestamps.
2. `build_posts_data()` currently prioritizes inbox `posted_at` and `fetched_at`. For NYCU LIFE, prefer structured source `published_at`, otherwise stable `first_seen`, and expose `publication_time_basis`. Old inbox records still contain the buggy `posted_at=startAt`, including starts that are now in the past; its existing future-only clamp cannot repair those. Use the source ID/metadata to identify this legacy case without rewriting the inbox or guessing publication from event start.
3. The loop attaching inbox timestamps to event sources near `post_ts` currently overwrites structured source `posted_at`. Preserve trustworthy structured publication metadata and apply the discovery fallback for old NYCU LIFE rows. Publication-based delivery filters must not mistake discovery for a verified source publication.
4. Preserve historical activities, user corrections, geocodes, covers and avatars through this integration. No global cache reset is needed. Feed/RSS/ICS created timestamps should remain stable across retries and rebuilds.

The offline tests use fixed clocks, mock provider responses and real competing child processes against temporary fixtures. Network can be guarded with `PYTHONPATH="$PWD/tests/ci_network_guard:$PWD/scripts:$PWD/tests"` and `python -m unittest test_extraction_retry test_pipeline_state test_fetch_nycu_life test_submission_extraction_retry test_run_pipeline test_submissions test_event_timezones test_event_categories test_llm_gateway`.
