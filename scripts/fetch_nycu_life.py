"""NYCU LIFE 官方活動 API fetcher。

這個來源本身就是結構化活動，除了進 inbox 之外，另存結構化 JSON 供 build_site 直接採用
（跳過 LLM 抽取，欄位是權威的）。
"""

import json
import sys

import requests

from chumei_lib import SeenState, append_inbox, now_iso, ROOT
from source_status import record_fetch

API = "https://events.life.nycu.edu.tw/api/activities"
RAW_SOURCE = "nycu-life-api"
STRUCTURED = ROOT / "state" / "nycu_life_activities.json"

CAMPUS_MAP = {"光復": "nycu-guangfu", "博愛": "nycu-boai", "陽明": "nycu-yangming"}


def main():
    try:
        resp = requests.get(API, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        record_fetch("bulletin:nycu_life_api", backend="JSON API", ok=False, error=exc)
        raise

    seen = SeenState(RAW_SOURCE)
    fresh = []
    structured = []
    for a in data:
        pid = a["publicId"]
        title = (a.get("title") or {}).get("zhTW") or ""
        summary = (a.get("summary") or {}).get("zhTW") or ""
        locs = a.get("locations") or ([a["location"]] if a.get("location") else [])
        venue_txt = "；".join(
            f"{l.get('campus') or ''} {((l.get('venue') or {}).get('zhTW') or '')}".strip() for l in locs
        )
        organizer = ((a.get("organizer") or {}).get("name") or {}).get("zhTW") or "NYCU LIFE"
        structured.append({
            "id": f"evt_nyculife_{pid}",
            "title": title,
            "summary": summary[:120],
            "description": summary,
            "start_at": a.get("startAt"),
            "end_at": a.get("endAt"),
            "all_day": False,
            "campus": CAMPUS_MAP.get((locs[0].get("campus") if locs else None), "other"),
            "venue": venue_txt or None,
            "school": "nycu",
            "organizer": organizer,
            "organizer_type": "official",
            "category": a.get("category") or "其他",
            "registration_url": a.get("canonicalUrl"),
            "registration_deadline": (a.get("registration") or {}).get("deadline"),
            "price": None,
            "source": {"platform": "api", "url": a.get("canonicalUrl"), "source_id": "nycu_life_api", "post_id": pid},
            "poster_image": a.get("coverImageUrl"),
            "extraction": {"model": "none", "confidence": 1.0, "needs_review": False, "prompt_version": 0},
            "status": "published",
        })
        if not seen.has("nycu_life_api", pid):
            fresh.append({
                "source_id": "nycu_life_api",
                "source_name": "NYCU LIFE",
                "platform": "api",
                "raw_source": RAW_SOURCE,
                "school": "nycu",
                "org_type": "official",
                "post_id": pid,
                "url": a.get("canonicalUrl"),
                "posted_at": a.get("startAt") or now_iso(),
                "text": f"{title}\n\n{summary}",
                "images": [a.get("coverImageUrl")] if a.get("coverImageUrl") else [],
                "fetched_at": now_iso(),
            })
            seen.add("nycu_life_api", pid)

    append_inbox(RAW_SOURCE, fresh)
    seen.save()
    STRUCTURED.parent.mkdir(parents=True, exist_ok=True)
    STRUCTURED.write_text(json.dumps(structured, ensure_ascii=False, indent=1))
    record_fetch("bulletin:nycu_life_api", backend="JSON API", ok=True, items=len(data))
    print(f"nycu-life: {len(data)} activities, {len(fresh)} new in inbox")


if __name__ == "__main__":
    sys.exit(main())
