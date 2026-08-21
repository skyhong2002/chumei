"""組站：extraction + NYCU LIFE 結構化活動 → site/data、site/api、site/feeds、詳情頁、sitemap。"""

import csv
import html
import io
import json
import re
import sys
from datetime import datetime, date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

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
CAMPUS_GEO = {
    "nthu-main": (24.7929, 120.9937),
    "nthu-nanda": (24.7934, 120.9647),
    "nycu-guangfu": (24.7874, 120.9972),
    "nycu-boai": (24.7977, 120.9819),
    "nycu-yangming": (25.12256, 121.51296),
}


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


def _bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def _similar(a, b):
    """正規化標題相似：包含關係或 bigram Jaccard ≥ 0.6。"""
    if not a or not b:
        return False
    if len(a) >= 6 and len(b) >= 6 and (a in b or b in a):
        return True
    ba, bb = _bigrams(a), _bigrams(b)
    return len(ba & bb) / max(1, len(ba | bb)) >= 0.6


def dedupe(events):
    def score(e):
        plat = {"api": 3, "bulletin": 1}.get(e["source"]["platform"], 0)
        return plat + e["extraction"]["confidence"] + (1 if e.get("venue") else 0) + (0 if e.get("all_day") else 1)

    # 第一階段：標題前綴＋日期完全相同
    groups = {}
    for e in events:
        day = (e.get("start_at") or "")[:10]
        groups.setdefault((norm_title(e["title"])[:24], day), []).append(e)
    stage1 = []
    for grp in groups.values():
        grp.sort(key=score, reverse=True)
        best = grp[0]
        if len(grp) > 1:
            best["alt_sources"] = [g["source"]["url"] for g in grp[1:]]
        stage1.append(best)

    # 第二階段：同一天、標題相似（同活動多貼文/轉發）
    by_day = {}
    for e in stage1:
        by_day.setdefault((e.get("start_at") or "")[:10], []).append(e)
    out = []
    for grp in by_day.values():
        kept = []
        for e in sorted(grp, key=score, reverse=True):
            dup = next((k for k in kept if _similar(norm_title(k["title"]), norm_title(e["title"]))), None)
            if dup:
                dup.setdefault("alt_sources", []).append(e["source"]["url"])
                if e.get("school") != dup.get("school"):
                    dup["school"] = "both"  # 跨校轉發＝兩校聯合
            else:
                kept.append(e)
        out.extend(kept)
    return out


def load_venues():
    rows = read_sources_csv("venues.csv")
    for r in rows:
        r["aliases"] = [a.strip() for a in (r.get("aliases") or "").replace("；", ";").split(";") if a.strip()]
    return rows


def attach_geo(events, venues):
    """venue 字串 → 建築座標；無精確場館時退回校區約略位置。"""
    def match(venue, cands):
        hits = []
        for v in cands:
            for key in [v["name"], *v["aliases"]]:
                if len(key) >= 2 and key in venue:
                    hits.append((len(key), v))
                    break
        if not hits:
            return None
        top = max(h[0] for h in hits)
        best = [v for l, v in hits if l == top]
        # 不同校區同名建築（體育館、活動中心⋯）無法裁決時放棄，寧缺勿錯
        if len({v["campus"] for v in best}) > 1:
            return None
        return best[0]

    n = 0
    for e in events:
        venue = (e.get("venue") or "").strip()
        if e.get("campus") in ("online",):
            continue
        hit = None
        if venue and e.get("campus"):
            hit = match(venue, [v for v in venues if v["campus"] == e["campus"]])
        elif venue:
            hit = match(venue, venues)
        # 擷取的校區可能只來自學校名；全域唯一場館登錄的實際校區優先。
        if venue and not hit:
            hit = match(venue, venues)
            if hit and hit["campus"] in CAMPUS_LABEL and hit["campus"] != "online":
                e["campus"] = hit["campus"]
        if hit:
            e["geo"] = {"lat": float(hit["lat"]), "lng": float(hit["lng"]), "name": hit["name"]}
            n += 1
            continue

        # 未寫教室的 ICT 訓練以官方主要基地工程一館標示為約略位置。
        if not venue and "ICT創創工坊" in (e.get("organizer") or ""):
            base = next((v for v in venues if v["campus"] == "nycu-guangfu" and v["name"] == "工程一館"), None)
            if base:
                e["geo"] = {"lat": float(base["lat"]), "lng": float(base["lng"]),
                            "name": "ICT 創創工坊（工程一館約略位置）", "approximate": True}
                n += 1
                continue

        # 活動確定屬於某實體校區但未公告教室時，仍讓地圖可見，並明確標示精度。
        campus = e.get("campus")
        if campus in CAMPUS_GEO:
            lat, lng = CAMPUS_GEO[campus]
            label = CAMPUS_LABEL[campus]
            e["geo"] = {"lat": lat, "lng": lng, "name": f"{label}（約略位置）", "approximate": True}
            n += 1
    return n


def cache_posters(events):
    """保留原始海報；失效或缺圖時再從原始活動頁找公開主圖。"""
    from PIL import Image
    from fetch_infonews import HttpClient, parse_detail, _RelaxedAdapter
    from render_source_covers import cached_source_cover

    class DiscoveryParser(HTMLParser):
        VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

        def __init__(self, page_url):
            super().__init__(convert_charrefs=True)
            self.page_url = page_url
            self.meta_images = []
            self.descriptions = []
            self.content_images = []
            self.content_depth = 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "meta":
                key = (attrs.get("property") or attrs.get("name") or "").lower()
                content = attrs.get("content") or ""
                if key in ("og:image", "og:image:url", "twitter:image") and content:
                    self.meta_images.append(urljoin(self.page_url, html.unescape(content)))
                elif key == "description" and content:
                    self.descriptions.append(content)
            classes = set((attrs.get("class") or "").split())
            if tag == "div" and ("meditor" in classes or attrs.get("id") == "changeWidh"):
                self.content_depth = 1
            elif self.content_depth and tag not in self.VOID_TAGS:
                self.content_depth += 1
            if self.content_depth and tag == "img" and attrs.get("src"):
                self.content_images.append(urljoin(self.page_url, html.unescape(attrs["src"])))

        def handle_endtag(self, tag):
            if self.content_depth and tag not in self.VOID_TAGS:
                self.content_depth -= 1

    def discover(source_url):
        if not source_url:
            return []
        try:
            page = HttpClient(delay=0, timeout=25).get_text(source_url)
            parser = DiscoveryParser(source_url)
            parser.feed(page)
            candidates = list(parser.meta_images)
            if "infonews.nycu.edu.tw" in urlparse(source_url).netloc:
                candidates.extend(parse_detail(page, source_url)[1])
            candidates.extend(parser.content_images)
            for desc in parser.descriptions:
                for raw in re.findall(r'<img\b[^>]+src=["\']([^"\']+)', html.unescape(desc), re.I):
                    candidates.append(urljoin(source_url, html.unescape(raw)))
            out = []
            for candidate in candidates:
                low = candidate.lower()
                if any(token in low for token in ("favicon", "logo", "clear.gif", "fonts.gstatic.com")):
                    continue
                if candidate not in out:
                    out.append(candidate)
            return out
        except Exception as ex:
            print(f"  cover discovery fail {source_url}: {str(ex)[:80]}", file=sys.stderr)
            return []

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (chumei.observe.tw)"})
    session.mount("https://", _RelaxedAdapter())
    source_cache = {}

    def save_candidate(url, dest):
        try:
            r = session.get(html.unescape(url), timeout=25)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("image/") or len(r.content) <= 2000:
                return False
            image = Image.open(io.BytesIO(r.content)).convert("RGB")
            if min(image.size) < 250 or max(image.size) < 400:
                return False
            image.thumbnail((1200, 1200))
            image.save(dest, "JPEG", quality=84, optimize=True)
            return True
        except Exception:
            return False

    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    for e in events:
        url = e.get("poster_image")
        dest = POSTER_DIR / f"{e['id']}.jpg"
        if dest.exists():
            e["poster_image"] = f"/assets/posters/{e['id']}.jpg"
            e["image_kind"] = "source"
            e["cover_image"] = e["poster_image"]
            continue

        candidates = []
        if url and not url.startswith("/assets/posters/"):
            candidates.append(url)
        source_url = (e.get("source") or {}).get("url")
        source_shot_cached = cached_source_cover(source_url)
        if e.get("start_at", "")[:10] >= today and source_url and not source_shot_cached:
            if source_url not in source_cache:
                source_cache[source_url] = discover(source_url)
            candidates.extend(source_cache[source_url])
        for candidate in dict.fromkeys(candidates):
            if save_candidate(candidate, dest):
                break
        if dest.exists():
            e["poster_image"] = f"/assets/posters/{e['id']}.jpg"
            e["image_kind"] = "source"
            e["cover_image"] = e["poster_image"]
        else:
            e["poster_image"] = None
            e["image_kind"] = "illustration"
            e["cover_image"] = "/assets/fallback/event-cover.webp"


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
        if e.get("end_at"):
            try:
                from datetime import timedelta
                en = datetime.fromisoformat(e["end_at"]) + timedelta(days=1)  # ICS 全日 DTEND 為 exclusive
                lines.append(f"DTEND;VALUE=DATE:{en:%Y%m%d}")
            except ValueError:
                pass
    else:
        lines.append(f"DTSTART;TZID=Asia/Taipei:{st:%Y%m%dT%H%M%S}")
        if e.get("end_at"):
            try:
                en = datetime.fromisoformat(e["end_at"])
                lines.append(f"DTEND;TZID=Asia/Taipei:{en:%Y%m%dT%H%M%S}")
            except ValueError:
                pass
    loc = join_loc(e, " ")
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
        desc = esc(f"{fmt_dt(e.get('start_at'), e.get('all_day'))}｜{join_loc(e, ' ')}｜{e.get('organizer')}\n{e.get('summary')}")
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
<meta property="og:site_name" content="竹梅活動觀測站">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/brand/logo-square-32.png"><link rel="icon" type="image/png" sizes="256x256" href="/assets/brand/logo-square-256.png"><link rel="apple-touch-icon" sizes="180x180" href="/assets/brand/logo-square-180.png">
<link rel="stylesheet" href="/assets/tokens.css">
<link rel="stylesheet" href="/assets/site.css">
<link rel="alternate" type="application/rss+xml" title="竹梅活動 RSS" href="/feeds/all.xml">
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t;else if(matchMedia('(prefers-color-scheme: dark)').matches)document.documentElement.dataset.theme='dark'}}catch(e){{}}</script>
</head>
<body>
<header class="site-header">
  <a class="brand" href="/"><span class="brand-chu">竹</span><span class="brand-mei">梅</span><span class="brand-sub">活動觀測站</span></a>
  <nav class="site-nav">
    <a href="/">活動</a>
    <a href="/calendar/">日曆</a>
    <a href="/stories/">限動</a>
    <a href="/subscribe/">訂閱</a>
    <a href="/source/">來源</a>
    <a href="/about/">關於</a>
    <button id="theme-toggle" aria-label="切換深淺色主題">◐</button>
  </nav>
</header>
<main>
{content}
</main>
<footer class="site-footer">
  <p>竹梅活動觀測站彙整清大、陽明交大公開活動資訊；內容以主辦單位公告為準。</p>
  <p><a href="/subscribe/">RSS / 行事曆訂閱</a> ・ <a href="/source/">資料來源</a> ・ <a href="/about/">關於與回報</a></p>
</footer>
<script src="/assets/app.js"></script>
</body>
</html>"""


def join_loc(e, sep=" ・ "):
    parts = [CAMPUS_LABEL.get(e.get("campus") or "", ""), e.get("venue") or ""]
    parts = [p for p in parts if p]
    if len(parts) == 2 and (parts[1] == parts[0] or parts[0] in parts[1]):
        parts = parts[1:]
    return sep.join(parts)


def detail_page(e):
    st, en = e.get("start_at"), e.get("end_at")
    loc = join_loc(e)
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
    if e.get("poster_image"):
        poster = f'<img class="detail-poster" src="{esc(e["poster_image"])}" alt="{esc(e["title"])} 活動海報">'
    elif e.get("image_kind") == "source_screenshot":
        cover = esc(e.get("cover_image"))
        school_class = esc(e.get("school") or "other")
        category = esc(e.get("category") or "活動")
        poster = (f'<div class="detail-source-cover source-cover source-cover-{school_class}" role="img" '
                  f'aria-label="{esc(e["title"])} 原始公告網頁截圖">'
                  f'<div class="source-cover-shot"><img src="{cover}" alt=""></div>'
                  f'<div class="source-cover-caption"><span>原始網頁截圖 · {category}</span>'
                  f'<strong>{esc(e["title"])}</strong></div></div>')
    else:
        school_class = esc(e.get("school") or "other")
        category = esc(e.get("category") or "其他")
        cover = esc(e.get("cover_image") or "/assets/fallback/event-cover.webp")
        poster = (f'<div class="detail-event-cover event-cover event-cover-{school_class}" role="img" '
                  f'aria-label="{category}活動示意封面">'
                  f'<img class="event-cover-bg" src="{cover}" alt="">'
                  '<div class="event-cover-content"><span class="event-cover-kicker">竹梅活動</span>'
                  f'<strong>{category}</strong><span class="event-cover-note">示意封面</span></div></div>')
    actions = "".join(filter(None, [
        f'<a class="btn btn-primary" href="{esc(e["registration_url"])}" rel="noopener">報名／活動頁</a>' if e.get("registration_url") else None,
        f'<a class="btn" href="{gcal}" rel="noopener">加入 Google 日曆</a>' if gcal else None,
        (f'<a class="btn" href="https://www.google.com/maps?q={e["geo"]["lat"]},{e["geo"]["lng"]}" rel="noopener">在地圖上看</a>'
         if e.get("geo") else None),
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
        f"{e['title']}｜竹梅活動觀測站", e.get("summary") or e["title"], content,
        og_image=(BASE_URL + e["poster_image"]) if e.get("poster_image") else None,
        canonical=f"{BASE_URL}/event/{e['id']}/",
    )


def source_page(events):
    """公開來源索引 /source/ — 列出每一個資料來源與收錄活動數。"""
    counts = {}
    for e in events:
        sid = e["source"]["source_id"]
        counts[sid] = counts.get(sid, 0) + 1

    def row_html(name, url, sid, tags):
        n = counts.get(sid, 0)
        chips = "".join(f'<span class="chip {c}">{esc(t)}</span>' for t, c in tags if t)
        cnt = f'<span class="src-count">{n} 場</span>' if n else '<span class="src-count src-zero">尚無收錄</span>'
        return (f'<li class="src-item"><a href="{esc(url)}" rel="noopener">{esc(name)}</a>'
                f'<span class="src-meta">{chips}{cnt}</span></li>')

    def school_chip(s):
        return (SCHOOL_LABEL.get(s, s), f"chip-{s}")

    sections = []
    bulletin_rows = []
    for r in read_sources_csv("bulletin_sources.csv"):
        bulletin_rows.append(row_html(r["name"], r["url"], r["source_id"], [school_chip(r["school"])]))
    sections.append(("校方公告與官方 API", "兩校公告系統與 NYCU LIFE 的結構化活動資料。", bulletin_rows))

    ig_rows = []
    for r in sorted(read_sources_csv("ig_accounts.csv"), key=lambda r: -counts.get(f"ig_{r['username']}", 0)):
        if r.get("active", "true").lower() == "false":
            continue
        u = r["username"].strip().lstrip("@")
        ig_rows.append(row_html(f"{r['name']}（@{u}）", f"https://www.instagram.com/{u}/",
                                f"ig_{u}", [school_chip(r["school"]), (r.get("category_hint"), "")]))
    sections.append(("Instagram 帳號", "學生社團與校內單位的公開貼文，活動欄位由 AI 從貼文與海報擷取。", ig_rows))

    social_rows = []
    SOCIAL_URL = {"threads": "https://www.threads.com/@{u}", "x": "https://x.com/{u}"}
    SOCIAL_TAG = {"threads": "Threads", "x": "X"}
    for r in sorted(read_sources_csv("social_accounts.csv"),
                    key=lambda r: (r["platform"], r["name"])):
        if r.get("active", "true").lower() == "false" or r["platform"] not in SOCIAL_URL:
            continue
        u = r["username"].strip().lstrip("@")
        social_rows.append(row_html(
            f"{r['name']}（@{u}）", SOCIAL_URL[r["platform"]].format(u=u),
            f"{r['platform']}_{u}",
            [(SOCIAL_TAG[r["platform"]], ""), school_chip(r["school"])]))
    sections.append(("Threads 與 X", "兩校官方與學生社群在 Threads/X 上的公開帳號。", social_rows))

    fb_rows = []
    for r in sorted(read_sources_csv("fb_pages.csv"), key=lambda r: r["name"]):
        if r.get("active", "true").lower() == "false":
            continue
        page = r["page"].strip()
        url = page if page.startswith("http") else f"https://www.facebook.com/{page}"
        from fetch_facebook import page_slug
        fb_rows.append(row_html(r["name"], url, f"fb_{page_slug(page)}", [school_chip(r["school"]), (r.get("category_hint"), "")]))
    sections.append(("Facebook 專頁", "校方單位、系學會與老牌社團的公開專頁，經 Apify 取得公開貼文。", fb_rows))

    body = ['<div class="prose"><h1>資料來源</h1>',
            f'<p>竹梅活動觀測站目前監測 {sum(len(s[2]) for s in sections)} 個公開來源。所有內容皆為公開資訊，'
            '活動頁都附原始連結；來源單位若希望調整或移除內容，請見<a href="/about/">關於頁</a>的回報管道。</p></div>']
    for title, desc, rows in sections:
        body.append(f'<section class="src-section"><h2>{title}<span class="src-n">{len(rows)}</span></h2>'
                    f'<p class="src-desc">{desc}</p><ul class="source-list">{"".join(rows)}</ul></section>')
    d = SITE / "source"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(page_shell(
        "資料來源｜竹梅活動觀測站",
        "竹梅活動觀測站監測的所有公開資料來源：兩校公告系統、NYCU LIFE、學生社團 Instagram 與 Facebook。",
        "\n".join(body), canonical=f"{BASE_URL}/source/"))


def main():
    events = dedupe(apply_overrides(load_events()))
    events = [e for e in events if e.get("start_at")]
    events.sort(key=lambda e: e["start_at"])
    cache_posters(events)
    from render_source_covers import attach_source_screenshots
    screenshot_limit = int(load_env().get("CHUMEI_SCREENSHOT_LIMIT", "20"))
    n_screenshots = attach_source_screenshots(events, limit=screenshot_limit)
    n_screenshot_events = sum(e.get("image_kind") == "source_screenshot" for e in events)
    print(f"source screenshots: {n_screenshots} created, {n_screenshot_events} events attached")
    venues = load_venues()
    n_geo = attach_geo(events, venues)
    print(f"geo: {n_geo}/{sum(1 for e in events if e.get('venue'))} venue-matched ({len(venues)} registry rows)")

    today = date.today().isoformat()
    upcoming = [e for e in events if e["start_at"][:10] >= today]

    for d in ("data", "api", "feeds", "event"):
        (SITE / d).mkdir(parents=True, exist_ok=True)

    bundle = {"generated_at": now_iso(), "events": events,
              "labels": {"school": SCHOOL_LABEL, "campus": CAMPUS_LABEL, "org": ORG_LABEL}}
    (SITE / "data" / "events.json").write_text(json.dumps(bundle, ensure_ascii=False))
    (SITE / "api" / "events.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1))

    write_rss(SITE / "feeds" / "all.xml", list(reversed(events)), "竹梅活動觀測站")
    for sch in ("nthu", "nycu"):
        subset = [e for e in reversed(events) if e.get("school") in (sch, "both")]
        write_rss(SITE / "feeds" / f"{sch}.xml", subset, f"竹梅活動觀測站｜{SCHOOL_LABEL[sch]}")
        write_ics(SITE / "feeds" / f"{sch}.ics", [e for e in upcoming if e.get("school") in (sch, "both")], f"竹梅 {SCHOOL_LABEL[sch]}活動")
    write_ics(SITE / "feeds" / "all.ics", upcoming, "竹梅活動觀測站")

    for e in events:
        d = SITE / "event" / e["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(detail_page(e))

    source_page(events)

    urls = [f"{BASE_URL}/", f"{BASE_URL}/calendar/", f"{BASE_URL}/subscribe/", f"{BASE_URL}/about/", f"{BASE_URL}/source/", f"{BASE_URL}/stories/"] + \
           [f"{BASE_URL}/event/{e['id']}/" for e in events]
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    n_review = sum(1 for e in events if e["extraction"].get("needs_review"))
    print(f"build: {len(events)} events ({len(upcoming)} upcoming, {n_review} needs_review)")


if __name__ == "__main__":
    sys.exit(main())
