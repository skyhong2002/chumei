"""NYCU LIFE 官方活動 API fetcher。

這個來源本身就是結構化活動，除了進 inbox 之外，另存結構化 JSON 供 build_site 直接採用
（跳過 LLM 抽取，欄位是權威的）。
"""

import sys

import requests

from event_categories import normalize_event_category
from chumei_lib import SeenState, append_inbox, iter_inbox, now_iso, ROOT
from extraction_retry import timestamp
from pipeline_state import LockBusy, atomic_json, file_lock, merge_json, read_json
from source_status import record_fetch

API = "https://events.life.nycu.edu.tw/api/activities"
RAW_SOURCE = "nycu-life-api"
STRUCTURED = ROOT / "state" / "nycu_life_activities.json"

CAMPUS_MAP = {"光復": "nycu-guangfu", "博愛": "nycu-boai", "陽明": "nycu-yangming"}


def fetch():
    try:
        resp = requests.get(API, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        record_fetch("bulletin:nycu_life_api", backend="JSON API", ok=False, error=exc)
        raise

    seen = SeenState(RAW_SOURCE)
    previous = {e["id"]: e for e in read_json(STRUCTURED, [])}
    inbox = {it["post_id"]: it for it in iter_inbox() if it["raw_source"] == RAW_SOURCE}
    fetched_at = now_iso()
    fresh = []
    # API snapshots may omit ended activities. Keep the local history by ID.
    structured = dict(previous)
    for a in data:
        pid = a["publicId"]
        eid = f"evt_nyculife_{pid}"
        old = previous.get(eid, {})
        old_inbox = inbox.get(pid, {})
        first_seen = (old.get("first_seen") or seen.data.get(f"nycu_life_api\t{pid}")
                      or old_inbox.get("first_seen") or old_inbox.get("fetched_at") or fetched_at)
        published_at = a.get("publishedAt") or old.get("published_at")
        published = timestamp(published_at)
        if published is None or published > timestamp(fetched_at):
            published_at = None
        posted_at = published_at or first_seen
        publication_time_basis = "source" if published_at else "first_seen"
        title = (a.get("title") or {}).get("zhTW") or ""
        summary = (a.get("summary") or {}).get("zhTW") or ""
        locs = a.get("locations") or ([a["location"]] if a.get("location") else [])
        venue_txt = "；".join(
            f"{l.get('campus') or ''} {((l.get('venue') or {}).get('zhTW') or '')}".strip() for l in locs
        )
        organizer = ((a.get("organizer") or {}).get("name") or {}).get("zhTW") or "NYCU LIFE"
        structured[eid] = normalize_event_category({
            **old,
            "id": eid,
            "title": title,
            "summary": summary[:120],
            "description": summary,
            "start_at": a.get("startAt"),
            "end_at": a.get("endAt"),
            "first_seen": first_seen,
            "fetched_at": fetched_at,
            "published_at": published_at,
            "publication_time_basis": publication_time_basis,
            "all_day": False,
            "campus": CAMPUS_MAP.get((locs[0].get("campus") if locs else None), "other"),
            "venue": venue_txt or None,
            "school": "nycu",
            "organizer": organizer,
            "organizer_type": "official",
            "category": a.get("category"),
            "registration_url": a.get("canonicalUrl"),
            "registration_deadline": (a.get("registration") or {}).get("deadline"),
            "price": None,
            "source": {"platform": "api", "url": a.get("canonicalUrl"), "source_id": "nycu_life_api", "post_id": pid,
                       "posted_at": posted_at, "published_at": published_at,
                       "publication_time_basis": publication_time_basis},
            "poster_image": a.get("coverImageUrl"),
            "extraction": {"model": "none", "confidence": 1.0, "needs_review": False, "prompt_version": 0},
            "status": "published",
        })
        if not seen.has("nycu_life_api", pid) and pid not in inbox:
            fresh.append({
                "source_id": "nycu_life_api",
                "source_name": "NYCU LIFE",
                "platform": "api",
                "raw_source": RAW_SOURCE,
                "school": "nycu",
                "org_type": "official",
                "post_id": pid,
                "url": a.get("canonicalUrl"),
                "posted_at": posted_at,
                "published_at": published_at,
                "publication_time_basis": publication_time_basis,
                "first_seen": first_seen,
                "text": f"{title}\n\n{summary}",
                "images": [a.get("coverImageUrl")] if a.get("coverImageUrl") else [],
                "fetched_at": fetched_at,
            })
        seen.data.setdefault(f"nycu_life_api\t{pid}", first_seen)

    append_inbox(RAW_SOURCE, fresh)
    merge_json(seen.path, seen.data)
    atomic_json(STRUCTURED, list(structured.values()))
    record_fetch("bulletin:nycu_life_api", backend="JSON API", ok=True, items=len(data))
    print(f"nycu-life: {len(data)} activities, {len(fresh)} new in inbox")


def main():
    try:
        with file_lock(STRUCTURED.with_suffix(".lock"), blocking=False):
            return fetch()
    except LockBusy:
        print("nycu-life: deferred; another fetch is running")
        return 0


if __name__ == "__main__":
    sys.exit(main())
