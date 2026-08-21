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
<link rel="icon" type="image/png" sizes="32x32" href="/assets/brand/logo-mark-32.png"><link rel="icon" type="image/png" sizes="64x64" href="/assets/brand/logo-mark-64.png"><link rel="apple-touch-icon" sizes="180x180" href="/assets/brand/logo-square-180.png">
<link rel="stylesheet" href="/assets/tokens.css">
<link rel="stylesheet" href="/assets/site.css">
<link rel="alternate" type="application/rss+xml" title="竹梅活動 RSS" href="/feeds/all.xml">
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t;else if(matchMedia('(prefers-color-scheme: dark)').matches)document.documentElement.dataset.theme='dark'}}catch(e){{}}</script>
</head>
<body>
<header class="site-header">
  <a class="brand" href="/"><span class="brand-chu">竹</span><span class="brand-mei">梅</span><span class="brand-sub">活動觀測站</span></a>
  <nav class="site-nav">
    <a href="/">最新</a>
    <a href="/events/">活動</a>
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
        f'<button class="btn btn-share" data-url="{BASE_URL}/event/{e["id"]}/" data-title="{esc(e["title"])}">分享</button>',
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


def _norm_org(s):
    s = re.sub(r"[（(].*?[)）]", "", s or "")
    s = re.sub(r"國立|清華大學|陽明交通大學|清大|交大|陽明|NTHU|NYCU|學生|大學", "", s, flags=re.I)
    return re.sub(r"[\\W_]+", "", s.lower())


def _org_campus(text):
    """從名稱/備註推斷 NYCU 校區：yangming / guangfu / None。"""
    t = text or ""
    if "陽明" in t and "陽明交通" not in t.replace("陽明交大", ""):
        return "yangming"
    if any(k in t for k in ("交大", "交通", "光復")) or "nctu" in t.lower():
        return "guangfu"
    return None


def _org_sim(a, b):
    if not a or not b:
        return 0
    if a == b:
        return 1.1  # 完全同名優先於包含關係（口琴社 vs 竹韻口琴社是不同社）
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return 1
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / max(1, len(A | B))


def build_sources_data(events):
    """全機構名錄 site/data/sources.json：官方名冊為底＋監測帳號＋公告來源，含未收錄單位。"""
    counts = {}
    for e in events:
        sid = e["source"]["source_id"]
        counts[sid] = counts.get(sid, 0) + 1

    # 各 source_id 最近一篇貼文/公告時間（inbox 掃描）
    from chumei_lib import iter_inbox
    now = now_iso()
    latest = {}
    for it in iter_inbox():
        sid = it["source_id"]
        # infonews 的公告日期可能是未來的展示起始日，最新更新時間以現在為上限
        ts = min(it.get("posted_at") or "", now)
        if ts > latest.get(sid, ""):
            latest[sid] = ts

    # 穩定公開 ID：對照表持久化，新條目往後編號，永不重發
    id_path = ROOT / "data" / "sources" / "directory_ids.json"
    id_map = json.loads(id_path.read_text()) if id_path.exists() else {}

    entries = []
    # 1. 官方名冊打底
    for school, fname in (("nthu", "club_roster_nthu.csv"), ("nycu", "club_roster_nycu.csv")):
        for r in read_sources_csv(fname):
            cat = r["category"]
            kind = "gov" if ("自治" in cat or "學生會" in cat) else "club"
            notes = r.get("notes") or ""
            campus = None
            if school == "nycu":
                campus = "yangming" if "陽明" in notes else "guangfu" if "光復" in notes else _org_campus(r["club_name"])
            entries.append({
                "name": r["club_name"], "school": school, "kind": kind,
                "category": re.sub(r"社團$", "", cat), "campus": campus,
                "links": [], "events": 0, "roster": True,
            })
    norms = [_norm_org(e["name"]) for e in entries]

    def attach(name, school, org_type, platform, url, label, sid, note=None):
        n = _norm_org(name)
        src_campus = _org_campus(name) if school == "nycu" else None
        best_i, best = -1, 0.55
        for i, e in enumerate(entries):
            if e["school"] != school:
                continue
            # 陽明與交通的社團是兩套系統：兩邊校區皆已知且不同 → 不配對
            if school == "nycu" and src_campus and e.get("campus") and e["campus"] != src_campus:
                continue
            v = _org_sim(n, norms[i])
            if v and src_campus and e.get("campus") == src_campus:
                v += 0.05  # 校區吻合優先
            if v > best:
                best_i, best = i, v
        if best_i == -1:
            kind = {"official": "unit", "department": "dept", "club": "club", "external": "ext"}.get(org_type, "club")
            entries.append({"name": name, "school": school, "kind": kind, "category": None,
                            "campus": src_campus, "links": [], "events": 0, "roster": False})
            norms.append(_norm_org(name))
            best_i = len(entries) - 1
        e = entries[best_i]
        e["links"].append({"platform": platform, "url": url, "label": label,
                           "events": counts.get(sid, 0)})
        e.setdefault("sids", []).append(sid)
        e["events"] += counts.get(sid, 0)
        ts = latest.get(sid)
        if ts and ts > (e.get("updated") or ""):
            e["updated"] = ts

    for r in read_sources_csv("ig_accounts.csv"):
        if r.get("active", "true").lower() == "false":
            continue
        u = r["username"].strip().lstrip("@")
        attach(r["name"], r.get("school") or "other", r.get("org_type"), "instagram",
               f"https://www.instagram.com/{u}/", f"@{u}", f"ig_{u}")
    from fetch_facebook import page_slug
    for r in read_sources_csv("fb_pages.csv"):
        if r.get("active", "true").lower() == "false":
            continue
        page = r["page"].strip()
        url = page if page.startswith("http") else f"https://www.facebook.com/{page}"
        attach(r["name"], r.get("school") or "other", r.get("org_type"), "facebook",
               url, "Facebook", f"fb_{page_slug(page)}")
    for r in read_sources_csv("social_accounts.csv"):
        if r.get("active", "true").lower() == "false" or r["platform"] != "website":
            continue
        url = r["username"].strip()
        from urllib.parse import urlparse as _up
        host = _up(url).netloc or url
        attach(r["name"], r.get("school") or "other", r.get("org_type"), "website",
               url, host, f"web_{host}")
    SOCIAL_URL = {"threads": "https://www.threads.com/@{u}", "x": "https://x.com/{u}"}
    for r in read_sources_csv("social_accounts.csv"):
        if r.get("active", "true").lower() == "false" or r["platform"] not in SOCIAL_URL:
            continue
        u = r["username"].strip().lstrip("@")
        attach(r["name"], r.get("school") or "other", r.get("org_type"), r["platform"],
               SOCIAL_URL[r["platform"]].format(u=u), f"@{u}", f"{r['platform']}_{u}")

    # 3. 公告系統／官方 API（獨立條目）
    for r in read_sources_csv("bulletin_sources.csv"):
        entries.append({"name": r["name"], "school": r["school"], "kind": "bulletin",
                        "category": None, "campus": None,
                        "links": [{"platform": "bulletin", "url": r["url"], "label": "公告頁",
                                   "events": counts.get(r["source_id"], 0)}],
                        "events": counts.get(r["source_id"], 0), "roster": False,
                        "updated": latest.get(r["source_id"])})

    entries.sort(key=lambda e: (-e["events"], -len(e["links"]), e["name"]))
    next_id = max(id_map.values(), default=0) + 1
    for e in entries:
        key = f"{e['school']}|{e['name']}"
        if key not in id_map:
            id_map[key] = next_id
            next_id += 1
        e["id"] = id_map[key]
    id_path.write_text(json.dumps(id_map, ensure_ascii=False, indent=0))

    # 頭貼：IG/Threads/X 由 fetcher 從 RSSHub channel image 存；FB 用 graph 公開頭貼端點補
    from chumei_lib import save_avatar, AVATAR_DIR
    for e in entries:
        keys = e.get("sids", [])
        for k in keys:
            if k.startswith("fb_"):
                save_avatar(k, f"https://graph.facebook.com/{k[3:]}/picture?type=large", max_age_days=30)
        # 優先序：IG > Threads > FB > X
        for prefix in ("ig_", "threads_", "fb_", "x_"):
            hit = next((k for k in keys if k.startswith(prefix) and (AVATAR_DIR / f"{k}.jpg").exists()), None)
            if hit:
                e["avatar"] = f"/assets/avatars/{hit}.jpg"
                break
    n_av = sum(1 for e in entries if e.get("avatar"))
    print(f"avatars: {n_av}/{sum(1 for e in entries if e['links'])} covered entries")
    (SITE / "data").mkdir(parents=True, exist_ok=True)
    (SITE / "data" / "sources.json").write_text(json.dumps({
        "generated_at": now_iso(), "entries": entries,
    }, ensure_ascii=False))
    covered = sum(1 for e in entries if e["links"])
    print(f"sources: {len(entries)} entries, {covered} covered, "
          f"{sum(1 for e in entries if e['roster'] and not e['links'])} roster-uncovered")
    return entries


KIND_LABEL = {"club": "社團", "gov": "自治組織", "dept": "系所", "unit": "校方單位",
              "bulletin": "公告系統", "ext": "校外"}


def org_pages(entries, events):
    """每個名錄條目一頁 /org/<id>/：頭貼、連結、該單位的活動。"""
    by_sid = {}
    for e in events:
        by_sid.setdefault(e["source"]["source_id"], []).append(e)
    today = date.today().isoformat()
    PLAT = {"instagram": "Instagram", "facebook": "Facebook", "threads": "Threads",
            "x": "X", "bulletin": "公告頁", "website": "官網"}
    for ent in entries:
        evs = [e for sid in ent.get("sids", []) for e in by_sid.get(sid, [])]
        for l in ent["links"]:
            if l["platform"] == "bulletin":
                evs += by_sid.get(next((s for s in ent.get("sids", [])), ""), [])
        evs = list({e["id"]: e for e in evs}.values())
        upcoming = sorted([e for e in evs if e["start_at"][:10] >= today], key=lambda e: e["start_at"])
        past = sorted([e for e in evs if e["start_at"][:10] < today], key=lambda e: e["start_at"], reverse=True)[:20]

        def ev_row(e):
            return (f'<li class="org-ev"><a href="/event/{e["id"]}/">'
                    f'<span class="org-ev-date">{fmt_dt(e["start_at"], e.get("all_day"))}</span>'
                    f'{esc(e["title"])}</a></li>')

        avatar = (f'<img class="org-avatar" src="{esc(ent["avatar"])}" alt="">' if ent.get("avatar")
                  else '<span class="org-avatar src-avatar-fallback av-' + esc(ent["school"]) + '">'
                       + esc((ent["name"] or "？")[len(ent["name"]) > 2 and ent["name"][:2] in ("清大", "交大", "陽明") and 2 or 0]) + "</span>")
        links = "".join(f'<a class="btn" href="{esc(l["url"])}" rel="noopener">{PLAT.get(l["platform"], l["platform"])}</a>'
                        for l in ent["links"])
        campus_chip = ""
        if ent.get("campus") in ("yangming", "guangfu"):
            campus_chip = f'<span class="chip chip-campus">{"陽明" if ent["campus"] == "yangming" else "交大"}校區</span>'
        chips = (f'<span class="chip chip-{esc(ent["school"])}">{SCHOOL_LABEL.get(ent["school"], "其他")}</span>'
                 + campus_chip +
                 f'<span class="chip">{KIND_LABEL.get(ent["kind"], "")}</span>'
                 + (f'<span class="chip">{esc(ent["category"])}</span>' if ent.get("category") else ""))
        body = [f'<article class="org-page"><div class="org-head">{avatar}<div>'
                f'<p class="chips">{chips}</p><h1>{esc(ent["name"])}</h1>'
                f'<div class="actions">{links}</div></div></div>']
        if not ent["links"]:
            body.append('<p class="review-note">這個單位還沒有被竹梅收錄——如果你知道它的公開社群帳號，'
                        '歡迎到<a href="/about/">回報管道</a>告訴我們。</p>')
        if upcoming:
            body.append(f'<h2>即將舉行（{len(upcoming)}）</h2><ul class="org-evs">'
                        + "".join(ev_row(e) for e in upcoming) + "</ul>")
        if past:
            body.append(f'<h2>過往活動</h2><ul class="org-evs">'
                        + "".join(ev_row(e) for e in past) + "</ul>")
        if not evs and ent["links"]:
            body.append('<p class="src-desc">尚未從這個來源收錄到活動。</p>')
        body.append('<p class="src-desc"><a href="/source/">← 回資料來源名錄</a></p></article>')
        d = SITE / "org" / str(ent["id"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page_shell(
            f"{ent['name']}｜竹梅活動觀測站",
            f"{ent['name']}的公開帳號與活動記錄。",
            "\n".join(body), canonical=f"{BASE_URL}/org/{ent['id']}/"))
    print(f"org pages: {len(entries)}")
    return [ent["id"] for ent in entries]


def source_page(events):
    """/source/ 靜態殼：資料由 app.js 讀 sources.json 渲染（表格＋篩選）。"""
    entries = build_sources_data(events)
    content = """<section class="hero"><h1>資料來源與機構名錄</h1>
<p>以兩校 114 學年度官方社團名冊為底，加上竹梅監測中的公告系統與社群帳號。
還沒找到公開帳號的單位也列出——如果你知道它們的 IG／FB，歡迎到<a href="/about/">回報管道</a>告訴我們。
<span id="src-count" aria-live="polite"></span></p></section>
<section class="filters" aria-label="名錄篩選">
  <div class="filter-row"><span class="label">學校</span><span id="sf-school" class="fgroup"></span>
    <span class="search-hit"><input id="search" type="search" placeholder="搜尋社團、單位…" aria-label="搜尋名錄"></span></div>
  <div class="filter-row"><span class="label">狀態</span><span id="sf-status" class="fgroup"></span></div>
  <div class="filter-row"><span class="label">類型</span><span id="sf-kind" class="fgroup"></span></div>
  <div class="filter-row"><span class="label">平台</span><span id="sf-platform" class="fgroup"></span></div>
</section>
<div id="source-table" class="src-table" aria-label="機構名錄"></div>"""
    d = SITE / "source"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(page_shell(
        "資料來源與機構名錄｜竹梅活動觀測站",
        "清大×交大全部社團與單位的名錄：竹梅監測中的公告系統、IG、FB、Threads、X 帳號，以及尚未收錄的單位。",
        content, canonical=f"{BASE_URL}/source/"))
    return org_pages(entries, events)


def build_posts_data(events):
    """貼文河道 site/data/posts.json：每則含活動的來源貼文＋其抽出的活動。"""
    from chumei_lib import iter_inbox, AVATAR_DIR
    groups = {}
    for e in events:
        src = e["source"]
        groups.setdefault((src["source_id"], src["post_id"]), []).append(e)

    inbox = {}
    for it in iter_inbox():
        inbox[(it["source_id"], it["post_id"])] = it

    posts = []
    for key, evs in groups.items():
        it = inbox.get(key)
        sid, pid = key
        lead = evs[0]
        if it is None:  # NYCU LIFE API 等結構化來源沒有貼文原文
            it = {"source_name": lead.get("organizer"), "platform": lead["source"]["platform"],
                  "school": lead.get("school"), "org_type": lead.get("organizer_type"),
                  "url": lead["source"].get("url"), "posted_at": lead.get("first_seen") or lead["start_at"],
                  "text": lead.get("summary") or ""}
        avatar = None
        for prefix in ("ig_", "threads_", "fb_", "x_"):
            if sid.startswith(prefix) and (AVATAR_DIR / f"{sid}.jpg").exists():
                avatar = f"/assets/avatars/{sid}.jpg"
                break
        # 河道只放貼文自己的圖：原始貼文有附圖才用（取已快取的本地副本）；
        # 探索來的 og 圖、截圖、示意封面是活動卡的 fallback，不進河道。
        has_own_image = bool(it.get("images")) or bool(it.get("image_url")) or it.get("platform") == "api"
        image = None
        if has_own_image:
            image = next((e.get("poster_image") for e in evs if e.get("poster_image")), None)
        # 保留段落換行；壓掉行內多餘空白與過多空行
        text = re.sub(r"[ \t]+", " ", it.get("text") or "")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        # 公告的日期欄常是未來的展示起始日；貼文時間以「首次收錄」為準，不讓未來日期霸榜
        posted = it.get("posted_at") or ""
        now = now_iso()
        if not posted or posted > now:
            posted = min(lead.get("first_seen") or now, now)
        posts.append({
            "source_id": sid, "post_id": pid,
            "source_name": it.get("source_name"), "platform": it.get("platform"),
            "school": it.get("school") or lead.get("school"),
            "url": it.get("url"), "posted_at": posted,
            "org_type": it.get("org_type") or lead.get("organizer_type"),
            "text": text[:500] + ("…" if len(text) > 500 else ""),
            "image": image, "avatar": avatar,
            "events": sorted(({"id": e["id"], "title": e["title"], "start_at": e["start_at"],
                               "all_day": e.get("all_day"), "campus": e.get("campus"),
                               "category": e.get("category"),
                               "venue": e.get("venue")} for e in evs), key=lambda x: x["start_at"]),
        })
    posts.sort(key=lambda p: p.get("posted_at") or "", reverse=True)
    posts = posts[:200]
    (SITE / "data").mkdir(parents=True, exist_ok=True)
    (SITE / "data" / "posts.json").write_text(json.dumps(
        {"generated_at": now_iso(), "posts": posts,
         "labels": {"school": SCHOOL_LABEL, "campus": CAMPUS_LABEL}}, ensure_ascii=False))
    print(f"posts: {len(posts)} event-posts in feed")


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

    # 自訂訂閱組合：學校 × （類型｜校區｜主辦）預產矩陣 → /feeds/c/
    CAT_SLUG = {"演講": "talk", "工作坊": "workshop", "表演": "show", "展覽": "expo",
                "比賽": "contest", "營隊": "camp", "徵才": "recruit", "市集": "market",
                "運動": "sport", "聚會": "social", "其他": "other"}
    ORG_SLUG = {"official": "official", "department": "dept", "club": "club", "external": "ext"}
    cdir = SITE / "feeds" / "c"
    cdir.mkdir(parents=True, exist_ok=True)
    combo_specs = {}
    for cat, slug in CAT_SLUG.items():
        combo_specs[f"cat-{slug}"] = ("類型 " + cat, lambda e, c=cat: (e.get("category") or "其他") == c)
    for campus in CAMPUS_LABEL:
        combo_specs[f"campus-{campus}"] = (CAMPUS_LABEL[campus], lambda e, c=campus: e.get("campus") == c)
    for org, slug in ORG_SLUG.items():
        combo_specs[f"org-{slug}"] = (ORG_LABEL[org], lambda e, o=org: e.get("organizer_type") == o)
    for sch in ("all", "nthu", "nycu"):
        sch_label = "清交" if sch == "all" else SCHOOL_LABEL[sch]
        def in_school(e, s2=sch):
            return s2 == "all" or e.get("school") in (s2, "both")
        for key, (label, pred) in combo_specs.items():
            subset_all = [e for e in events if in_school(e) and pred(e)]
            subset_up = [e for e in upcoming if in_school(e) and pred(e)]
            name = f"{sch}-{key}"
            title = f"竹梅｜{sch_label}・{label}"
            write_rss(cdir / f"{name}.xml", list(reversed(subset_all)), title)
            write_ics(cdir / f"{name}.ics", subset_up, title)
    print(f"combo feeds: {len(combo_specs) * 3} pairs")

    for e in events:
        d = SITE / "event" / e["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(detail_page(e))

    org_ids = source_page(events)
    build_posts_data(events)

    urls = [f"{BASE_URL}/", f"{BASE_URL}/calendar/", f"{BASE_URL}/subscribe/", f"{BASE_URL}/about/", f"{BASE_URL}/source/", f"{BASE_URL}/stories/", f"{BASE_URL}/events/"] + \
           [f"{BASE_URL}/event/{e['id']}/" for e in events] + \
           [f"{BASE_URL}/org/{i}/" for i in (org_ids or [])]
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    n_review = sum(1 for e in events if e["extraction"].get("needs_review"))
    print(f"build: {len(events)} events ({len(upcoming)} upcoming, {n_review} needs_review)")


if __name__ == "__main__":
    sys.exit(main())
