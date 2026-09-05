"""人工核對的活動合併；保留每篇來源與舊活動網址，不放寬名稱模糊比對。"""

from datetime import datetime, timedelta
from html import escape

from chumei_lib import read_sources_csv, TZ_TAIPEI


def merge_reviewed_events(events, rows=None):
    by_id = {e["id"]: e for e in events}
    removed = set()
    rows = read_sources_csv("event_merges.csv") if rows is None else rows
    for row in rows:
        old, target = row["event_id"], row["canonical_id"]
        if old == target or old not in by_id or target not in by_id:
            continue
        duplicate, keep = by_id[old], by_id[target]
        sources = [keep["source"], *keep.get("alt_posts", []), duplicate["source"], *duplicate.get("alt_posts", [])]
        unique = {(s["source_id"], s["post_id"]): s for s in sources}
        unique.pop((keep["source"]["source_id"], keep["source"]["post_id"]), None)
        keep["alt_posts"] = list(unique.values())
        keep["alt_sources"] = [s["url"] for s in unique.values() if s.get("url")]
        keep["merged_event_ids"] = sorted(set(keep.get("merged_event_ids", []) + [old] + duplicate.get("merged_event_ids", [])))
        removed.add(old)
    return [e for e in events if e["id"] not in removed]


def is_period_event(event):
    try:
        start = datetime.fromisoformat(event.get("start_at") or "").astimezone(TZ_TAIPEI)
        end = datetime.fromisoformat(event.get("end_at") or "").astimezone(TZ_TAIPEI)
    except (TypeError, ValueError):
        return False
    # 單晚跨午夜的定時場次仍在當日議程；多日營隊、展覽與申請區間另列。
    return end.date() > start.date() and (bool(event.get("all_day")) or end - start >= timedelta(days=1))


def write_merged_event_pages(events, site, base_url):
    for event in events:
        for old in event.get("merged_event_ids", []):
            target = f'/event/{event["id"]}/'
            title = escape(event["title"])
            description = escape(f'此宣傳已合併至「{event["title"]}」，原始來源保留於活動頁。')
            image = escape(base_url + (event.get("cover_image") or "/assets/og-default.png"))
            path = site / "event" / old / "index.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
                            '<meta name="robots" content="noindex,follow">'
                            f'<link rel="canonical" href="{escape(base_url + target)}">'
                            f'<meta http-equiv="refresh" content="0;url={escape(target)}">'
                            f'<meta name="description" content="{description}">'
                            f'<meta property="og:title" content="{title}">'
                            f'<meta property="og:description" content="{description}">'
                            f'<meta property="og:url" content="{escape(base_url + target)}">'
                            f'<meta property="og:image" content="{image}">'
                            f'<meta name="twitter:title" content="{title}">'
                            f'<meta name="twitter:description" content="{description}">'
                            f'<title>{title}</title></head><body><h1>{title}</h1>'
                            f'<p>此宣傳已合併至 <a href="{escape(target)}">{escape(event["title"])}</a>，原始來源保留於活動頁。</p>'
                            '</body></html>')
