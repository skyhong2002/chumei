"""組站：extraction + NYCU LIFE 結構化活動 → site/data、site/api、site/feeds、詳情頁、sitemap。"""

import csv
import html
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

import requests

from chumei_lib import load_env, now_iso, read_sources_csv, ROOT, TZ_TAIPEI

SITE = ROOT / "site"
BASE_URL = "https://chumei.observe.tw"
EXTRACT_DIR = ROOT / "state" / "extraction"
POSTER_DIR = SITE / "assets" / "posters"

SCHOOL_LABEL = {"nthu": "清大", "nycu": "陽明交大", "both": "清大×交大", "external": "校外"}
CAMPUS_LABEL = {
    "nthu-main": "清大校本部", "nthu-nanda": "清大南大校區",
    "nycu-guangfu": "交大光復校區", "nycu-boai": "交大博愛校區",
    "nycu-yangming": "陽明校區", "online": "線上", "other": "其他地點",
}
ORG_LABEL = {"official": "校方", "department": "系所", "club": "社團", "external": "校外單位"}


def load_events():
    events = []
    nl = ROOT / "state" / "nycu_life_activities.json"
    if nl.exists():
        events += json.loads(nl.read_text())
    for path in sorted(EXTRACT_DIR.glob("*.json")):
        for pid, rec in json.loads(path.read_text()).items():
            for ev in rec.get("events", []):
                ev.setdefault("first_seen", rec.get("ts"))
                events.append(ev)
    return events


def apply_overrides(events):
    by_id = {e["id"]: e for e in events}
    for row in read_sources_csv("event_overrides.csv"):
        ev = by_id.get(row["event_id"])
        if not ev:
            continue
        field, value = row["field"], row["value"]
        if value in ("", "null"):
            value = None
        if field == "status" and value == "rejected":
            ev["status"] = "rejected"
        elif field in ev or field in ("start_at", "end_at", "campus", "venue", "title", "category", "school"):
            ev[field] = value
            if ev.get("status") == "review":
                ev["status"] = "published"
    return [e for e in events if e.get("status") != "rejected"]


def norm_title(t):
    return re.sub(r"[\W_]+", "", (t or "").lower())


def dedupe(events):
    def score(e):
        plat = {"api": 3, "bulletin": 1}.get(e["source"]["platform"], 0)
        return plat + e["extraction"]["confidence"] + (1 if e.get("venue") else 0) + (0 if e.get("all_day") else 1)

    groups = {}
    for e in events:
        day = (e.get("start_at") or "")[:10]
        groups.setdefault((norm_title(e["title"])[:24], day), []).append(e)
    out = []
    for grp in groups.values():
        grp.sort(key=score, reverse=True)
        best = grp[0]
        if len(grp) > 1:
            best["alt_sources"] = [g["source"]["url"] for g in grp[1:]]
        out.append(best)
    return out


def cache_posters(events):
    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    for e in events:
        url = e.get("poster_image")
        if not url:
            continue
        if url.startswith("/assets/posters/"):
            continue
        url = html.unescape(url)
        dest = POSTER_DIR / f"{e['id']}.jpg"
        if not dest.exists():
            try:
                r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 (chumei.observe.tw)"})
                r.raise_for_status()
                if r.headers.get("content-type", "").startswith("image/") and len(r.content) > 2000:
                    dest.write_bytes(r.content)
            except Exception as ex:
                print(f"  poster fail {e['id']}: {str(ex)[:80]}", file=sys.stderr)
        if dest.exists():
            e["poster_image"] = f"/assets/posters/{e['id']}.jpg"
        else:
            e["poster_image"] = None


def esc(s):
    return html.escape(str(s or ""), quote=True)


def fmt_dt(iso, all_day=False):
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    wd = "一二三四五六日"[d.weekday()]
    base = f"{d.year}/{d.month}/{d.day}（{wd}）"
    if all_day or (d.hour, d.minute) == (0, 0):
        return base
    return f"{base} {d:%H:%M}"


def ics_escape(s):
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def event_ics(e):
    uid = f"{e['id']}@chumei.observe.tw"
    lines = ["BEGIN:VEVENT", f"UID:{uid}"]
    try:
        st = datetime.fromisoformat(e["start_at"])
    except (TypeError, ValueError):
        return ""
    if e.get("all_day"):
        lines.append(f"DTSTART;VALUE=DATE:{st:%Y%m%d}")
    else:
        lines.append(f"DTSTART;TZID=Asia/Taipei:{st:%Y%m%dT%H%M%S}")
        if e.get("end_at"):
            try:
                en = datetime.fromisoformat(e["end_at"])
                lines.append(f"DTEND;TZID=Asia/Taipei:{en:%Y%m%dT%H%M%S}")
            except ValueError:
                pass
    loc = " ".join(filter(None, [CAMPUS_LABEL.get(e.get("campus") or "", ""), e.get("venue") or ""]))
    lines += [
        f"SUMMARY:{ics_escape(e['title'])}",
        f"DESCRIPTION:{ics_escape((e.get('summary') or '') + '\n' + BASE_URL + '/event/' + e['id'] + '/')}",
        f"LOCATION:{ics_escape(loc)}" if loc else None,
        f"URL:{BASE_URL}/event/{e['id']}/",
        "END:VEVENT",
    ]
    return "\r\n".join(l for l in lines if l)


def write_ics(path, events, name):
    body = "\r\n".join(filter(None, (event_ics(e) for e in events)))
    path.write_text(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//chumei//observe.tw//ZH\r\n"
        f"X-WR-CALNAME:{name}\r\nX-WR-TIMEZONE:Asia/Taipei\r\n" + body + "\r\nEND:VCALENDAR\r\n"
    )


def write_rss(path, events, title):
    items = []
    for e in events[:80]:
        link = f"{BASE_URL}/event/{e['id']}/"
        desc = esc(f"{fmt_dt(e.get('start_at'), e.get('all_day'))}｜{CAMPUS_LABEL.get(e.get('campus') or '', '')} {e.get('venue') or ''}｜{e.get('organizer')}\n{e.get('summary')}")
        try:
            pub = datetime.fromisoformat(e.get("first_seen") or e["start_at"]).strftime("%a, %d %b %Y %H:%M:%S %z")
        except (TypeError, ValueError):
            pub = ""
        items.append(
            f"<item><title>{esc(e['title'])}</title><link>{link}</link>"
            f"<guid isPermaLink=\"true\">{link}</guid>"
            + (f"<pubDate>{pub}</pubDate>" if pub else "")
            + f"<description>{desc}</description></item>"
        )
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{esc(title)}</title><link>{BASE_URL}/</link>"
        f"<description>竹梅｜清大×交大校園活動觀測站</description><language>zh-tw</language>"
        + "".join(items) + "</channel></rss>"
    )


def page_shell(title, desc, content, og_image=None, canonical=None):
    og_img = og_image or f"{BASE_URL}/assets/og-default.png"
    return f"""<!doctype html>
<html lang="zh-Hant-TW" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{f'<link rel="canonical" href="{canonical}">' if canonical else ''}
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{og_img}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="竹梅｜清交校園活動">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/tokens.css">
<link rel="stylesheet" href="/assets/site.css">
<link rel="alternate" type="application/rss+xml" title="竹梅活動 RSS" href="/feeds/all.xml">
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t;else if(matchMedia('(prefers-color-scheme: dark)').matches)document.documentElement.dataset.theme='dark'}}catch(e){{}}</script>
</head>
<body>
<header class="site-header">
  <a class="brand" href="/"><span class="brand-chu">竹</span><span class="brand-mei">梅</span><span class="brand-sub">清大×交大 校園活動</span></a>
  <nav class="site-nav">
    <a href="/">活動</a>
    <a href="/calendar/">日曆</a>
    <a href="/subscribe/">訂閱</a>
    <a href="/about/">關於</a>
    <button id="theme-toggle" aria-label="切換深淺色主題">◐</button>
  </nav>
</header>
<main>
{content}
</main>
<footer class="site-footer">
  <p>竹梅彙整清大、陽明交大公開活動資訊；內容以主辦單位公告為準。</p>
  <p><a href="/subscribe/">RSS / 行事曆訂閱</a> ・ <a href="/about/">資料來源與回報</a></p>
</footer>
<script src="/assets/app.js"></script>
</body>
</html>"""


def detail_page(e):
    st, en = e.get("start_at"), e.get("end_at")
    loc = " ・ ".join(filter(None, [CAMPUS_LABEL.get(e.get("campus") or "", ""), e.get("venue") or ""]))
    gcal = ""
    try:
        d1 = datetime.fromisoformat(st)
        if e.get("all_day"):
            dates = f"{d1:%Y%m%d}/{d1:%Y%m%d}"
        else:
            d2 = datetime.fromisoformat(en) if en else d1
            dates = f"{d1:%Y%m%dT%H%M%S}/{d2:%Y%m%dT%H%M%S}"
        gcal = ("https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + requests.utils.quote(e["title"])
                + f"&dates={dates}&ctz=Asia/Taipei&location=" + requests.utils.quote(loc)
                + "&details=" + requests.utils.quote(f"{BASE_URL}/event/{e['id']}/"))
    except (TypeError, ValueError):
        pass

    rows = [
        ("時間", fmt_dt(st, e.get("all_day")) + (f" – {fmt_dt(en, e.get('all_day'))}" if en else "")),
        ("地點", loc or "詳見原始貼文"),
        ("主辦", f"{e.get('organizer')}（{ORG_LABEL.get(e.get('organizer_type'), '')}）"),
        ("類型", e.get("category")),
        ("費用", e.get("price")),
        ("報名截止", fmt_dt(e.get("registration_deadline"))),
    ]
    meta_html = "".join(f"<div class='meta-row'><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in rows if v)
    review = ('<p class="review-note">⚠️ 此活動由 AI 從公開貼文擷取，欄位尚待確認，請以原始貼文為準。</p>'
              if e["extraction"].get("needs_review") else "")
    poster = (f'<img class="detail-poster" src="{esc(e["poster_image"])}" alt="{esc(e["title"])} 活動海報">'
              if e.get("poster_image") else "")
    actions = "".join(filter(None, [
        f'<a class="btn btn-primary" href="{esc(e["registration_url"])}" rel="noopener">報名／活動頁</a>' if e.get("registration_url") else None,
        f'<a class="btn" href="{gcal}" rel="noopener">加入 Google 日曆</a>' if gcal else None,
        f'<a class="btn" href="{esc(e["source"]["url"])}" rel="noopener">原始貼文</a>' if e["source"].get("url") else None,
    ]))
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "Event",
        "name": e["title"], "startDate": st, "endDate": en,
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {"@type": "Place", "name": loc or "見活動資訊"},
        "organizer": {"@type": "Organization", "name": e.get("organizer")},
        "description": e.get("summary"),
        "image": (BASE_URL + e["poster_image"]) if e.get("poster_image") else None,
        "url": f"{BASE_URL}/event/{e['id']}/",
    }, ensure_ascii=False)
    school = e.get("school") or "other"
    content = f"""<article class="detail">
{review}
<div class="detail-grid">
  <div class="detail-media">{poster}</div>
  <div class="detail-body">
    <p class="chips"><span class="chip chip-{school}">{SCHOOL_LABEL.get(school, school)}</span>
    <span class="chip">{esc(e.get('category'))}</span></p>
    <h1>{esc(e['title'])}</h1>
    <p class="lede">{esc(e.get('summary'))}</p>
    <dl class="meta">{meta_html}</dl>
    <div class="actions">{actions}</div>
    <div class="desc">{''.join(f'<p>{esc(p)}</p>' for p in (e.get('description') or '').split(chr(10)) if p.strip())}</div>
  </div>
</div>
<script type="application/ld+json">{jsonld}</script>
</article>"""
    return page_shell(
        f"{e['title']}｜竹梅", e.get("summary") or e["title"], content,
        og_image=(BASE_URL + e["poster_image"]) if e.get("poster_image") else None,
        canonical=f"{BASE_URL}/event/{e['id']}/",
    )


def main():
    events = dedupe(apply_overrides(load_events()))
    events = [e for e in events if e.get("start_at")]
    events.sort(key=lambda e: e["start_at"])
    cache_posters(events)

    today = date.today().isoformat()
    upcoming = [e for e in events if e["start_at"][:10] >= today]

    for d in ("data", "api", "feeds", "event"):
        (SITE / d).mkdir(parents=True, exist_ok=True)

    bundle = {"generated_at": now_iso(), "events": events,
              "labels": {"school": SCHOOL_LABEL, "campus": CAMPUS_LABEL, "org": ORG_LABEL}}
    (SITE / "data" / "events.json").write_text(json.dumps(bundle, ensure_ascii=False))
    (SITE / "api" / "events.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1))

    write_rss(SITE / "feeds" / "all.xml", list(reversed(events)), "竹梅｜清交校園活動")
    for sch in ("nthu", "nycu"):
        subset = [e for e in reversed(events) if e.get("school") in (sch, "both")]
        write_rss(SITE / "feeds" / f"{sch}.xml", subset, f"竹梅｜{SCHOOL_LABEL[sch]}活動")
        write_ics(SITE / "feeds" / f"{sch}.ics", [e for e in upcoming if e.get("school") in (sch, "both")], f"竹梅 {SCHOOL_LABEL[sch]}活動")
    write_ics(SITE / "feeds" / "all.ics", upcoming, "竹梅 清交校園活動")

    for e in events:
        d = SITE / "event" / e["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(detail_page(e))

    urls = [f"{BASE_URL}/", f"{BASE_URL}/calendar/", f"{BASE_URL}/subscribe/", f"{BASE_URL}/about/"] + \
           [f"{BASE_URL}/event/{e['id']}/" for e in events]
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    n_review = sum(1 for e in events if e["extraction"].get("needs_review"))
    print(f"build: {len(events)} events ({len(upcoming)} upcoming, {n_review} needs_review)")


if __name__ == "__main__":
    sys.exit(main())
