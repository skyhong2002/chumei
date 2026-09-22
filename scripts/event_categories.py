"""Canonical event categories shared by ingestion, publication and query adapters.

Unknown source labels remain discoverable under 其他 and carry review metadata;
source provenance and the original label are never discarded.
"""

CAT_SLUG = {
    "演講": "talk", "工作坊": "workshop", "表演": "show", "展覽": "expo",
    "比賽": "contest", "營隊": "camp", "徵才": "recruit", "市集": "market",
    "運動": "sport", "聚會": "social", "其他": "other",
}
SLUG_CAT = {slug: label for label, slug in CAT_SLUG.items()}
CATEGORY_ALIASES = {"講座": "演講", "社交": "聚會", "競賽": "比賽"}


def canonical_category(value):
    label = str(value or "").strip()
    return CATEGORY_ALIASES.get(label, SLUG_CAT.get(label, label if label in CAT_SLUG else "其他"))


def normalize_event_category(event):
    """Return a copy; safe to call repeatedly on old caches and new extraction."""
    result = dict(event)
    value = event.get("category")
    previous = event.get("category_normalization") or {}
    if previous and value == previous.get("canonical"):
        return result
    label = str(value or "").strip()
    canonical = canonical_category(value)
    recognized = label in CAT_SLUG or label in SLUG_CAT or label in CATEGORY_ALIASES
    result["category"] = canonical
    if value != canonical or not recognized:
        result["category_original"] = value
        result["category_normalization"] = {
            "original": value, "canonical": canonical, "recognized": recognized,
        }
    elif previous:
        result.pop("category_normalization", None)
    if not recognized:
        extraction = dict(event.get("extraction") or {})
        extraction.update(needs_review=True, category_review_reason="unknown_category")
        result["extraction"] = extraction
    return result


def normalize_event_bundle(bundle):
    return {**bundle, "events": [normalize_event_category(e) for e in bundle.get("events", [])]}
