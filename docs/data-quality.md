# Activity data quality review

Every site build creates `/quality/` and `/api/data-quality.json` from the same event snapshot. The status page links to the queue. Event details explain missing venue/registration data, uncertain extraction and approximate map locations. An approximate campus marker is never presented as an exact meeting location. A missing or explicitly undecided venue cannot retain an old precise coordinate.

The queue prioritizes ongoing events and those starting within seven days, then undated records withheld from calendars, later events, and historical events with unknown categories. Undated review records retain their original unverified times for inspection but have no public event-detail link. They are not added to a calendar. Historical category reviews remain visible until corrected.

Coverage denominators include only ongoing/upcoming activities; venue and exact-location metrics exclude online events. Exact locations exclude approximate campus markers. Registration coverage counts valid HTTP(S) URLs among events requiring registration; it does **not** claim the remote form is reachable, accepting responses, or independently verified. Overlapping issue counts must not be added as if they were unique events.

Missing data starts as **unverified**: absence cannot establish whether the announcement omitted a fact or extraction missed it. A reviewer can distinguish these cases in `data/sources/event_quality_reviews.csv`:

```csv
event_id,field,status,evidence_url,note
evt_example,venue,source_not_provided,https://example.org/announcement,原公告未公告教室
```

Allowed fields: `venue`, `geo`, `registration_url`, `category`, `time`, `extraction`. Allowed evidence-backed states:

- `source_not_provided`: the public announcement was checked and lacks the fact.
- `not_extracted`: the public source includes the fact but the stored extraction missed it.
- `geocoding_failed`: a confirmed venue could not be mapped reliably.

Rows without a supported state, field or HTTP(S) evidence URL are ignored. Notes and evidence are public; include no personal or private information. The initial CSV intentionally contains no invented reviews.

Each queue row links to the source and a prefilled GitHub correction issue. Reviewers should verify the source, use `data/sources/event_overrides.csv` to correct known event fields, or add an unambiguous match to `data/sources/venues.csv`; attach an evidence-backed quality review if the fact remains unavailable. Correcting a timezone requires checking the source's local date and DST offset, not replacing the timezone suffix. Do not guess a missing venue, price or registration link. The next atomic build regenerates the queue, dropping resolved issues while preserving the source evidence for any remaining issue.

Validation rejects a missing quality page/report, stale build timestamp, invalid coverage counts, duplicate queue IDs or a link to an unpublished event. This is a review workflow, not a claim that all upstream announcements contain sufficient information.
