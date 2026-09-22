# Event category vocabulary

`scripts/event_categories.py` owns the 11 category labels and subscription slugs.
NYCU LIFE ingestion, LLM extraction, build loading (including existing caches),
auth subscription filters, Bot and MCP use this vocabulary. Publication normalizes
before generating website data, RSS and ICS. Source-directory categories describe
organizations, not events, and keep their independent vocabulary.

Recognized aliases: `講座 → 演講`, `社交 → 聚會`, `競賽 → 比賽`.
English subscription slugs are also accepted. `學術` is too broad to infer an
activity format, so it follows the unknown-label path.

For aliases and unknown values, `category_original` and
`category_normalization: {original, canonical, recognized}` retain the source label.
Unknown values are published under `其他`, with
`extraction.needs_review: true` and
`extraction.category_review_reason: "unknown_category"` for review tooling.
Existing source and extraction provenance remains intact. Repeated normalization
does not erase the unknown flag, and does not hide the event from category feeds.

The extraction schema constrains future model responses to the 11 labels.
Normalization still handles old caches and alternate model backends. No extraction
rerun or paid request is needed to repair existing category values during a build.

`tests/test_event_categories.py` checks ingestion, cache migration, feed/Bot
matching, ICS labels, unknown review visibility and frontend/schema consistency.
