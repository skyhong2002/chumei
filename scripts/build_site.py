"""組站：extraction + NYCU LIFE 結構化活動 → site/data、site/api、site/feeds、詳情頁、sitemap。"""

import csv
import hashlib
import html
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from chumei_lib import load_env, now_iso, read_sources_csv, ROOT, TZ_TAIPEI

SITE = ROOT / "site"
BASE_URL = "https://chumei.observe.tw"
EXTRACT_DIR = ROOT / "state" / "extraction"
POSTER_DIR = SITE / "assets" / "posters"
VERSIONED_ASSETS = ("tokens.css", "site.css", "app.js")

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
        nl_events = json.loads(nl.read_text())
        # first_seen 用 seen-state 的首次收錄時間，否則貼文時間每次 build 都會被蓋成現在
        seen_path = ROOT / "state" / "seen" / "nycu-life-api.json"
        seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}
        for ev in nl_events:
            pid = (ev.get("source") or {}).get("post_id")
            ts = seen.get(f"nycu_life_api\t{pid}")
            if ts:
                ev.setdefault("first_seen", ts)
        events += nl_events
    for path in sorted(EXTRACT_DIR.glob("*.json")):
        for pid, rec in json.loads(path.read_text()).items():
            for ev in rec.get("events", []):
                ev.setdefault("first_seen", rec.get("ts"))
                # 同貼文的例行時段（社課），Telegram 推播時附一行
                if rec.get("recurrings"):
                    ev["post_recurrings"] = [
                        {k: r.get(k) for k in ("title", "weekday", "time", "venue")}
                        for r in rec["recurrings"]]
                events.append(ev)
    return events


WEEKDAY_ZH = "一二三四五六日"


def recurring_label(r):
    lab = f"每週{WEEKDAY_ZH[r['weekday'] - 1]} {r['time']} {r['title']}"
    return lab + (f"（{r['venue']}）" if r.get("venue") else "")


def load_recurrings():
    """例行時段（定期社課）：sid → 去重後清單。半年內有貼文重申才算數，避免陳年資訊誤導。"""
    cutoff = (datetime.now(TZ_TAIPEI) - timedelta(days=180)).isoformat()
    best = {}  # (sid, weekday, time) → recurring（取最新一次宣告）
    for path in sorted(EXTRACT_DIR.glob("*.json")):
        for pid, rec in json.loads(path.read_text()).items():
            for r in rec.get("recurrings", []):
                ts = rec.get("ts") or ""
                if ts < cutoff:
                    continue
                sid = (r.get("source") or {}).get("source_id") or path.stem
                key = (sid, r["weekday"], r["time"])
                if ts > best.get(key, ({}, ""))[1]:
                    best[key] = ({**r, "sid": sid, "seen": ts}, ts)
    by_sid = {}
    for (sid, _, _), (r, _) in sorted(best.items()):
        by_sid.setdefault(sid, []).append(r)
    return by_sid


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
    """正規化標題相似：包含關係或 bigram Jaccard ≥ 0.6。
    短字串（≤5 字）只差一字 Jaccard 也會壓線過（羽球／網球夏令營），改要求完全相等。"""
    if not a or not b:
        return False
    if min(len(a), len(b)) <= 5:
        return a == b
    if a in b or b in a:
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
    def absorb(keep, dup_e):
        """dup_e 併入 keep：原始貼文完整記錄進 alt_posts（顯示用），網址進 alt_sources（相容舊 API）。"""
        keep.setdefault("alt_posts", []).append(dup_e["source"])
        keep["alt_posts"] += dup_e.get("alt_posts", [])
        keep["alt_sources"] = [p.get("url") for p in keep["alt_posts"] if p.get("url")]

    stage1 = []
    for grp in groups.values():
        grp.sort(key=score, reverse=True)
        best = grp[0]
        for g in grp[1:]:
            absorb(best, g)
        stage1.append(best)

    # 第二階段：同一天、標題相似（同活動多貼文/轉發）。
    # 跨平台轉發常見「社名＋活動名」vs「活動名」——剝掉主辦名後核心相同也視為同活動。
    def title_core(e):
        t = norm_title(e["title"])
        for cand in {norm_title(e.get("organizer") or ""), _norm_org(e.get("organizer") or "")}:
            if cand and len(cand) >= 3 and cand in t and len(t) - len(cand) >= 3:
                t = t.replace(cand, "")
        return t

    # 同帳號連發多篇貼文宣傳同一場活動，標題每次寫法不同（「工工新生北區茶會」vs
    # 「工業工程與管理學系北區新生茶會」）會低於相似門檻；改用「同帳號＋不同貼文＋
    # 開始時間到分相同＋地點相容」判定，標題只需沾到邊（≥2 個共同 bigram）。
    def same_slot(k, e):
        if k.get("all_day") or e.get("all_day") or k.get("start_at") != e.get("start_at"):
            return False
        ks, es = k["source"], e["source"]
        if ks["source_id"] == es["source_id"] and ks["post_id"] == es["post_id"]:
            return False
        ta, tb = norm_title(k["title"]), norm_title(e["title"])
        ba, bb = _bigrams(ta), _bigrams(tb)
        va, vb = norm_title(k.get("venue")), norm_title(e.get("venue"))
        venue_ok = bool(va and vb and (va in vb or vb in va or _similar(va, vb)))
        if ks["source_id"] == es["source_id"]:
            if len(ba & bb) < 2:
                return False
            if va and vb:
                return venue_ok
            # 缺地點佐證時提高標題門檻：只共享尾綴（「游泳／羽球夏令營」）不算同活動
            return len(ba & bb) / max(1, len(ba | bb)) >= 0.4
        # 跨帳號（主辦與轉發單位各自發文、副標改寫）要更硬的證據：
        # 起訖時間全等＋地點相容＋標題共同前綴夠長（系列名，如「台灣矽谷解密：」）。
        # 前綴不能太短，免得「社團博覽會Ａ社攤位」「社團博覽會Ｂ社攤位」這類同場不同攤被誤併。
        if not venue_ok or k.get("end_at") != e.get("end_at"):
            return False
        prefix = next((i for i, (x, y) in enumerate(zip(ta, tb)) if x != y), min(len(ta), len(tb)))
        return prefix >= 6

    by_day = {}
    for e in stage1:
        by_day.setdefault((e.get("start_at") or "")[:10], []).append(e)
    out = []
    for grp in by_day.values():
        kept = []
        for e in sorted(grp, key=score, reverse=True):
            dup = next((k for k in kept if _similar(norm_title(k["title"]), norm_title(e["title"]))
                        or (title_core(k) and title_core(k) == title_core(e))
                        or same_slot(k, e)), None)
            if dup:
                absorb(dup, e)
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
        campus = e.get("campus")
        if campus in ("online",):
            continue
        hit = None
        if venue and campus in CAMPUS_GEO:
            # 已知實體校區時只能在該校區內配對。同名場館在不同學校／校區很常見，
            # 缺少本校區登錄時寧可退回校區中心，也不能被另一校區唯一登錄的泛稱帶走。
            hit = match(venue, [v for v in venues if v["campus"] == campus])
        elif venue:
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


GEOCODE_CACHE = ROOT / "data" / "sources" / "geocode.json"
_GEO_UNKNOWN = re.compile(r"未公布|未定|待定|線上|另行通知|TBA", re.I)
_GEO_ADDR = re.compile(
    r"(?:[台臺]北市|新北市|桃園市|[台臺]中市|[台臺]南市|高雄市|基隆市|新竹[市縣]|嘉義[市縣]|"
    r"苗栗縣|彰化縣|南投縣|雲林縣|屏東縣|宜蘭縣|花蓮縣|[台臺]東縣)[^，,；;（）()]*?[路街][^，,；;（）()]*")


# 店名式查詢的門檻：泛稱（社辦、重訓室、體育館…）丟給 Nominatim 會亂配到全台同名地點
_GEO_PLACEY = re.compile(r"[市縣]|[台臺][北中南]|高雄|桃園|新竹|基隆|店|館|空間|餐酒|餐廳|咖啡|cafe|廣場|園區", re.I)


def _geo_queries(venue):
    """依序嘗試的查詢：完整地址 → 去門牌號的路段 → 店名（需含場所詞）。"""
    qs = []
    m = _GEO_ADDR.search(venue)
    if m:
        addr = m.group(0)
        qs.append(addr)
        street = re.sub(r"[\d\s]+[-之\d\s]*號.*$", "", addr).strip()  # 台灣門牌 Nominatim 常查無，退回路段（含「302 號」空格寫法）
        if street != addr and len(street) >= 6:
            qs.append(street)
    name = re.sub(r"[（(].*?[）)]", "", venue).strip()
    name = re.split(r"[｜|，,；;]", name)[0].strip()
    if len(name) >= 4 and _GEO_PLACEY.search(name):
        qs.append(name)
    return qs


def geocode_external(events):
    """校外場地（campus=other/未知）用 Nominatim 補座標；結果快取避免重打。

    新生茶會季常見台北/台中/台南店家，很多 venue 直接附地址——
    這些不該被歸為「無法定位」。命中寫 external 標記；查無結果的
    七天後才會重試一次。
    """
    import time as _time

    try:
        cache = json.loads(GEOCODE_CACHE.read_text())
    except Exception:
        cache = {}
    changed = False
    n = 0
    for e in events:
        if e.get("geo"):
            continue
        venue = (e.get("venue") or "").strip()
        if not venue or e.get("campus") not in (None, "", "other"):
            continue
        if _GEO_UNKNOWN.search(venue):
            continue
        ent = cache.get(venue)
        stale_miss = ent and ent.get("lat") is None and _time.time() - ent.get("t", 0) > 7 * 86400
        if ent is None or stale_miss:
            hit = None
            used_q = None
            failed = False
            for q in _geo_queries(venue):
                try:
                    r = requests.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={"format": "json", "limit": 1, "countrycodes": "tw", "q": q},
                        headers={"User-Agent": "chumei.observe.tw geocoder"},
                        timeout=10,
                    )
                    r.raise_for_status()
                    res = r.json()
                    _time.sleep(1.1)  # Nominatim 禮貌頻率
                    if res:
                        hit = (float(res[0]["lat"]), float(res[0]["lon"]))
                        used_q = q
                        break
                except Exception:
                    failed = True
                    break
            if failed:
                continue  # 網路失敗不寫快取，下輪 build 再試
            cache[venue] = {"lat": hit and hit[0], "lng": hit and hit[1], "q": used_q, "t": int(_time.time())}
            changed = True
            ent = cache[venue]
        if ent and ent.get("lat"):
            name = re.sub(r"[（(].*?[）)]", "", venue).strip() or venue
            e["geo"] = {"lat": ent["lat"], "lng": ent["lng"], "name": name, "external": True}
            n += 1
    if changed:
        GEOCODE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    return n


def attach_reg_status(events):
    """參加方式雙軸：
    e["reg"] ∈ required（需事先報名）| free（自由入場）| None（未註明）
    e["fee"] ∈ paid | free | None —— 從 LLM 抽的 price 與內文推導。"""
    import re as _re
    FREE_KW = ("免報名", "自由入場", "自由參加", "無需報名", "不須報名", "不需報名", "免費入場")
    NEED_KW = ("報名連結", "報名表", "報名網址", "報名截止", "請報名", "須報名", "需報名", "填寫表單", "購票", "售票")
    PAID_RE = _re.compile(r"(?:報名費|入場費|門票|票價|收費)[^。\n]{0,10}?(?:NT\$|\$)?\s*\d+\s*元?|購票|售票")
    BENEFIT_RE = _re.compile(r"(?:補助|獎金|首獎|貳獎|參獎|獎品|回饋|折抵|抵用)[^。\n]{0,12}?\d+\s*元")
    n_reg = n_fee = 0
    for e in events:
        text = (e.get("summary") or "") + (e.get("description") or "")
        rr = e.get("registration_required")
        if rr is True:
            e["reg"] = "required"
        elif rr is False:
            e["reg"] = "free"
        elif any(k in text for k in FREE_KW):
            e["reg"] = "free"
        elif e.get("registration_url") or e.get("registration_deadline") or any(k in text for k in NEED_KW):
            e["reg"] = "required"
        else:
            e["reg"] = None

        price = (e.get("price") or "").strip()
        # 補助/獎金的金額是給你錢，不是收費——先剔除再判斷
        fee_text = BENEFIT_RE.sub("", text)
        if price:
            e["fee"] = "free" if ("免費" in price or price.lower() == "free") else "paid"
        elif "免費" in text:
            e["fee"] = "free"
        elif PAID_RE.search(fee_text):
            e["fee"] = "paid"
        else:
            e["fee"] = None
        n_reg += bool(e["reg"])
        n_fee += bool(e["fee"])
    print(f"reg status: {n_reg}/{len(events)} | fee status: {n_fee}/{len(events)}")


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
<html lang="zh-Hant-TW" data-theme="dark">
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
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#000000">
<meta name="apple-mobile-web-app-title" content="竹梅">
<link rel="stylesheet" href="/assets/tokens.css">
<link rel="stylesheet" href="/assets/site.css">
<link rel="alternate" type="application/rss+xml" title="竹梅活動 RSS" href="/feeds/all.xml">
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
</head>
<body>
<header class="site-header">
  <a class="brand" href="/" aria-label="竹梅活動觀測站"><span class="brand-chu">竹</span><span class="brand-mei">梅</span><span class="brand-sub">活動觀測站</span></a>
  <nav class="site-nav" aria-label="主導覽">
    <a class="nav-item" href="/"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l-2 0l9 -9l9 9l-2 0"/><path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-7"/><path d="M9 21v-6a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v6"/></svg><span class="nav-label">最新</span></a>
    <a class="nav-item" href="/events/"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l0 2"/><path d="M15 11l0 2"/><path d="M15 17l0 2"/><path d="M5 5h14a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-3a2 2 0 0 0 0 -4v-3a2 2 0 0 1 2 -2"/></svg><span class="nav-label">活動</span></a>
    <a class="nav-item" href="/calendar/"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"/><path d="M16 3l0 4"/><path d="M8 3l0 4"/><path d="M4 11l16 0"/><path d="M8 15h2v2h-2z"/></svg><span class="nav-label">日曆</span></a>
    <a class="nav-item" href="/stories/"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"/><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"/><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"/><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"/><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"/><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"/><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"/><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"/></svg><span class="nav-label">限動</span></a>
    <details class="nav-more">
      <summary class="nav-item" aria-label="更多選單"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6l16 0"/><path d="M4 12l16 0"/><path d="M4 18l16 0"/></svg><span class="nav-label">更多</span></summary>
      <div class="nav-more-menu">
        <a href="/notify/">App 通知</a>
        <a href="/subscribe/">訂閱管道</a>
        <a href="/source/">資料來源</a>
        <a href="/account/">登入／帳號</a>
        <a href="/about/">關於竹梅</a>
        <button id="theme-toggle">切換深淺色</button>
      </div>
    </details>
  </nav>
</header>
<main>
{content}
</main>
<footer class="site-footer">
  <p>竹梅活動觀測站彙整清大、陽明交大公開活動資訊；內容以主辦單位公告為準。</p>
  <p><a href="/notify/">App 通知</a> ・ <a href="/subscribe/">RSS / 行事曆訂閱</a> ・ <a href="/source/">資料來源</a> ・ <a href="/about/">關於與回報</a></p>
</footer>
<a class="fab" href="/notify/" aria-label="App 通知"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12.5 17h-8.5a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6a2 2 0 1 1 4 0a7 7 0 0 1 4 6v1.5"/><path d="M9 17v1a3 3 0 0 0 4.5 2.6"/><path d="M16 19h6"/><path d="M19 16v6"/></svg></a>
<script src="/assets/app.js"></script>
</body>
</html>"""


def version_static_assets():
    """替 HTML 內的核心 CSS/JS 加內容版本，避免手機沿用舊手勢程式。"""
    versions = {}
    for name in VERSIONED_ASSETS:
        path = SITE / "assets" / name
        versions[name] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]

    pattern = re.compile(
        r"/assets/(tokens\.css|site\.css|app\.js)(?:\?v=[0-9a-f]+)?"
    )
    changed = 0
    for path in SITE.rglob("*.html"):
        source = path.read_text()
        rendered = pattern.sub(
            lambda match: f"/assets/{match.group(1)}?v={versions[match.group(1)]}",
            source,
        )
        if rendered != source:
            path.write_text(rendered)
            changed += 1
    print(f"asset versions: {changed} HTML files updated")


def join_loc(e, sep=" ・ "):
    parts = [CAMPUS_LABEL.get(e.get("campus") or "", ""), e.get("venue") or ""]
    parts = [p for p in parts if p]
    if len(parts) == 2 and (parts[1] == parts[0] or parts[0] in parts[1]):
        parts = parts[1:]
    return sep.join(parts)


def detail_page(e, org=None, org_sections=(), alt_posts=()):
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
        ("主辦", (f'<a href="/org/{org[0]}/">{esc(org[1])}</a>（{ORG_LABEL.get(e.get("organizer_type"), "")}）'
                 if org else f"{esc(e.get('organizer'))}（{ORG_LABEL.get(e.get('organizer_type'), '')}）")),
        ("類型", e.get("category")),
        ("報名", {"required": "需事先報名", "free": "自由入場，免報名"}.get(e.get("reg"))),
        ("費用", e.get("price") or {"free": "免費", "paid": "需付費（金額見原文）"}.get(e.get("fee"))),
        ("報名截止", fmt_dt(e.get("registration_deadline"))),
        ("原始貼文", "、".join(
            f'<a href="{esc(p["url"])}" rel="noopener" target="_blank">{esc(p["label"])} ↗</a>'
            for p in alt_posts) or None),
    ]
    meta_html = "".join(
        f"<div class='meta-row'><dt>{esc(k)}</dt><dd>{v if k in ('主辦', '原始貼文') else esc(v)}</dd></div>"
        for k, v in rows if v)
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
        # 原始貼文統一列在資訊列（含帳號／平台／日期），不另設按鈕
        f'<button class="btn btn-share" data-url="{BASE_URL}/event/{e["id"]}/" data-title="{esc(e["title"])}">分享</button>',
        (f'<button class="btn heart-btn heart-btn-label" data-org-id="{org[0]}" data-org-name="{esc(org[1])}" '
         f'aria-pressed="false" title="追蹤 {esc(org[1])}">{FEED_ICON["heart"]}'
         f'<span class="hb-follow">追蹤主辦</span><span class="hb-following">追蹤中</span></button>') if org else None,
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
        "sameAs": [p["url"] for p in alt_posts] or None,
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
    {''.join(
      (f'<section class="org-more"><h2>來自 <a href="/org/{oid}/">{esc(oname)}</a> 的更多活動</h2><ul class="org-evs">'
       + "".join(f'<li class="org-ev"><a href="/event/{s2["id"]}/"><span class="org-ev-date">{fmt_dt(s2["start_at"], s2.get("all_day"))}</span>{esc(s2["title"])}</a></li>' for s2 in sibs)
       + f'</ul><p class="src-desc"><a href="/org/{oid}/">查看 {esc(oname)} 的完整頁面 →</a></p></section>')
      if sibs else
      (f'<section class="org-more"><h2>來自 <a href="/org/{oid}/">{esc(oname)}</a> 的更多活動</h2>'
       f'<p class="src-desc">這是目前收錄自該單位的唯一活動。<a href="/org/{oid}/">查看 {esc(oname)} 的完整頁面 →</a></p></section>')
      for oid, oname, sibs in org_sections)}
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
    import unicodedata
    raw = re.sub(r"[（(].*?[)）]", "", unicodedata.normalize("NFKC", s or ""))
    out = re.sub(r"國立|清華大學|陽明交通大學|清大|交大|陽明|NTHU|NYCU|學生|大學", "", raw, flags=re.I)
    out = re.sub(r"[\W_]+", "", out.lower())
    if not out:  # 全稱剝完變空（如「國立清華大學」）→ 退回原名比對
        out = re.sub(r"[\W_]+", "", raw.lower())
    return out


def _org_campus(text):
    """從名稱/備註推斷 NYCU 校區：yangming / guangfu / None。
    「陽明交大／陽明交通大學」是全校前綴，先剝除再判斷；兩關鍵字都在時取先出現者。"""
    t = (text or "")
    for whole in ("國立陽明交通大學", "陽明交通大學", "陽明交大"):
        t = t.replace(whole, "")
    i_ym = t.find("陽明")
    cands = [i for i in (t.find("交大"), t.find("交通"), t.find("光復"), t.lower().find("nctu")) if i != -1]
    i_gf = min(cands) if cands else -1
    if i_ym != -1 and (i_gf == -1 or i_ym < i_gf):
        return "yangming"
    if i_gf != -1:
        return "guangfu"
    return None


def org_display_name(name, school, campus=None):
    """依名錄校別產生一致的公開名稱，避免同名單位無法辨識。

    NYCU 的學生組織以校區區分「交大／陽明」；校區不明的校級單位使用
    「陽明交大」。原始名稱會由 build_sources_data 保存在 base_name。
    """
    raw = str(name or "").strip()
    if not raw or school not in {"nthu", "nycu", "both"}:
        return raw
    if school == "nycu":
        prefix = "陽明" if campus == "yangming" else "交大" if campus == "guangfu" else "陽明交大"
        pattern = r"^(?:(?:國立)?(?:陽明交通大學|交通大學|陽明大學)|陽明交大|交大|陽明|NYCU|NCTU)\s*"
    elif school == "nthu":
        prefix = "清大"
        pattern = r"^(?:(?:國立)?清華大學|清大|NTHU)\s*"
    else:
        prefix = "清交"
        pattern = r"^(?:清大(?:×|x|X|與|、)?交大|清交|清大×交大)\s*"
    body = re.sub(pattern, "", raw, count=1, flags=re.I).strip()
    return prefix + body


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
    seen = {}  # sid → 活動 id 集合（跨帳號合併的活動歸戶到每個來源；同帳號多貼文只算一次）
    for e in events:
        for src in [e["source"]] + e.get("alt_posts", []):
            seen.setdefault(src["source_id"], set()).add(e["id"])
    counts = {sid: len(ids) for sid, ids in seen.items()}

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
                i_ym, i_gf = notes.find("陽明"), notes.find("光復")
                if i_gf != -1 and (i_ym == -1 or i_gf < i_ym):
                    campus = "guangfu"
                elif i_ym != -1:
                    campus = "yangming"
                else:
                    campus = _org_campus(r["club_name"])
            entries.append({
                "name": r["club_name"], "school": school, "kind": kind,
                # 名冊分冊尾碼（學術性B、體育性A⋯）對訪客沒意義，顯示前去掉
                "category": re.sub(r"(?<=性)[AB]$", "", re.sub(r"社團$", "", cat)), "campus": campus,
                "links": [], "events": 0, "roster": True,
            })
    # 正名：官方名冊的通用名（口琴社）換成社團的專屬名（揚鳴口琴社）
    for ov in read_sources_csv("org_overrides.csv"):
        for e in entries:
            if (e["school"] == ov["school"] and e["name"] == ov["roster_name"]
                    and (e.get("campus") or "") == (ov.get("campus") or "")):
                e["name"] = ov["display_name"]
                break

    norms = [_norm_org(e["name"]) for e in entries]

    def attach(name, school, org_type, platform, url, label, sid, note=None, fallback_kind=None):
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
            kind = fallback_kind or {"official": "unit", "department": "dept", "club": "club", "external": "ext"}.get(org_type, "club")
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

    # 3. 公告系統／官方 API：先嘗試歸戶到既有單位（如藝文中心官網→藝文中心），配不到才獨立
    for r in read_sources_csv("bulletin_sources.csv"):
        attach(r["name"], r["school"], "official", "bulletin", r["url"], "公告頁",
               r["source_id"], fallback_kind="bulletin")

    entries.sort(key=lambda e: (-e["events"], -len(e["links"]), e["name"]))
    next_id = max(id_map.values(), default=0) + 1
    claimed_legacy = set()
    for e in sorted(entries, key=lambda x: (not x["roster"], x["name"])):
        key = f"{e['school']}|{e.get('campus') or ''}|{e['name']}"
        if key not in id_map:
            legacy = f"{e['school']}|{e['name']}"
            if legacy in id_map and legacy not in claimed_legacy:
                id_map[key] = id_map[legacy]
                claimed_legacy.add(legacy)
            else:
                id_map[key] = next_id
                next_id += 1
        e["id"] = id_map[key]
    id_path.write_text(json.dumps(id_map, ensure_ascii=False, indent=0))

    # 例行時段（定期社課）：掛到單位條目，同單位多帳號重申的同一時段只留一筆
    rec_by_sid = load_recurrings()
    n_sched = 0
    for e in entries:
        slots = {}
        for sid in e.get("sids", []):
            for r in rec_by_sid.get(sid, []):
                slots.setdefault((r["weekday"], r["time"]), r)
        if slots:
            e["schedule"] = [
                {"title": r["title"], "weekday": r["weekday"], "time": r["time"],
                 "venue": r["venue"], "note": r.get("note"),
                 "url": (r.get("source") or {}).get("url")}
                for r in sorted(slots.values(), key=lambda r: (r["weekday"], r["time"]))]
            n_sched += 1
    if n_sched:
        print(f"recurring schedules: {n_sched} orgs")

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
    # ID 與來源歸戶使用原始名稱；配對完成後才統一公開顯示名稱。
    renamed = 0
    for e in entries:
        base_name = e["name"]
        display_name = org_display_name(base_name, e["school"], e.get("campus"))
        e["base_name"] = base_name
        if display_name != base_name:
            e["name"] = display_name
            renamed += 1
    expected_prefix = {
        ("nthu", None): "清大",
        ("nycu", "guangfu"): "交大",
        ("nycu", "yangming"): "陽明",
        ("nycu", None): "陽明交大",
        ("both", None): "清交",
    }
    bad = [e for e in entries
           if expected_prefix.get((e["school"], e.get("campus")))
           and not e["name"].startswith(expected_prefix[(e["school"], e.get("campus"))])]
    duplicate_names = {name for name, n in Counter(e["name"] for e in entries).items() if n > 1}
    if bad or duplicate_names:
        raise ValueError(f"organization display-name audit failed: bad={len(bad)}, duplicates={sorted(duplicate_names)}")
    print(f"organization display names: {renamed}/{len(entries)} prefixed or normalized")
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
    """每個名錄條目一頁 /org/<id>/：頭貼、連結、該單位的活動與收錄貼文。"""
    by_sid = {}
    for e in events:
        for src in [e["source"]] + e.get("alt_posts", []):  # 跨帳號合併的活動歸戶到每個來源單位
            by_sid.setdefault(src["source_id"], []).append(e)
    # 收錄貼文（含沒抽出活動的），各來源合流
    from chumei_lib import iter_inbox
    now = now_iso()
    posts_by_sid, ev_per_post = {}, {}
    for it in iter_inbox():
        posts_by_sid.setdefault(it["source_id"], []).append(it)
    for e in events:
        for src in [e["source"]] + e.get("alt_posts", []):
            k = (src["source_id"], src["post_id"])
            ev_per_post[k] = ev_per_post.get(k, 0) + 1
    today = date.today().isoformat()
    PLAT = {"instagram": "Instagram", "facebook": "Facebook", "threads": "Threads",
            "x": "X", "bulletin": "公告頁", "website": "官網", "api": "NYCU LIFE"}
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
        follow_btn = (f'<button class="btn heart-btn heart-btn-label" data-org-id="{ent["id"]}" '
                      f'data-org-name="{esc(ent["name"])}" aria-pressed="false" '
                      f'title="追蹤 {esc(ent["name"])}">{FEED_ICON["heart"]}'
                      f'<span class="hb-follow">追蹤</span>'
                      f'<span class="hb-following">追蹤中</span></button>')
        links = follow_btn + "".join(
            f'<a class="btn" href="{esc(l["url"])}" rel="noopener">{PLAT.get(l["platform"], l["platform"])}</a>'
            for l in ent["links"])
        campus_chip = ""
        if ent.get("campus") in ("yangming", "guangfu"):
            campus_chip = f'<span class="chip chip-campus">{"陽明" if ent["campus"] == "yangming" else "交大"}校區</span>'
        chips = (f'<span class="chip chip-{esc(ent["school"])}">{SCHOOL_LABEL.get(ent["school"], "其他")}</span>'
                 + campus_chip +
                 f'<span class="chip">{KIND_LABEL.get(ent["kind"], "")}</span>'
                 + (f'<span class="chip">{esc(ent["category"])}</span>' if ent.get("category") else ""))
        body = [f'<article class="org-page"><div class="org-head">{avatar}<div class="org-head-main">'
                f'<h1>{esc(ent["name"])}</h1><p class="chips">{chips}</p>'
                f'<div class="actions org-links">{links}</div></div></div>']
        if not ent["links"]:
            body.append('<p class="review-note">這個單位還沒有被竹梅收錄——如果你知道它的公開社群帳號，'
                        '歡迎到<a href="/about/">回報管道</a>告訴我們。</p>')
        if ent.get("schedule"):
            def sched_row(r):
                lab = f'每週{WEEKDAY_ZH[r["weekday"] - 1]} {r["time"]}'
                inner = (f'<span class="org-ev-date">{lab}</span>{esc(r["title"])}'
                         f'<span class="org-sched-venue">{esc(r["venue"])}</span>')
                if r.get("url"):
                    inner = f'<a href="{esc(r["url"])}" rel="noopener">{inner}</a>'
                return f'<li class="org-ev org-sched-row">{inner}</li>'
            body.append('<h2>例行時段</h2><ul class="org-evs">'
                        + "".join(sched_row(r) for r in ent["schedule"])
                        + '</ul><p class="src-desc">依社團近期公開貼文整理，實際時間以社團公告為準。</p>')
        if upcoming:
            body.append(f'<h2>即將舉行（{len(upcoming)}）</h2><ul class="org-evs">'
                        + "".join(ev_row(e) for e in upcoming) + "</ul>")
        if past:
            body.append(f'<h2>過往活動</h2><ul class="org-evs">'
                        + "".join(ev_row(e) for e in past) + "</ul>")
        if not evs and ent["links"]:
            body.append('<p class="src-desc">尚未從這個來源收錄到活動。</p>')

        # 收錄貼文：各來源合流、含沒抽出活動的，最新在前
        posts = {(p["source_id"], p["post_id"]): p
                 for sid in ent.get("sids", []) for p in posts_by_sid.get(sid, [])}
        if posts:
            def post_key(p):
                return min(p.get("posted_at") or p.get("fetched_at") or "", now)
            ordered = sorted(posts.values(), key=post_key, reverse=True)
            shown = ordered[:30]

            PLAT_S = {"instagram": "IG", "facebook": "FB", "threads": "Threads", "x": "X",
                      "bulletin": "公告", "website": "官網", "api": "LIFE"}

            def post_row(p):
                snippet = re.sub(r"\s+", " ", p.get("text") or "").strip()[:60] or "（無文字）"
                d8 = post_key(p)[:10]
                d_lab = f"{int(d8[5:7])}/{int(d8[8:10])}" if len(d8) == 10 else "—"
                n_ev = ev_per_post.get((p["source_id"], p["post_id"]), 0)
                inner = (f'<span class="org-ev-date org-post-date">{d_lab}'
                         f'<span class="org-post-plat">{PLAT_S.get(p.get("platform"), p.get("platform") or "")}</span></span>'
                         f'<span class="org-post-txt">{esc(snippet)}</span>'
                         + (f'<span class="org-post-ev">{n_ev} 場</span>' if n_ev else ""))
                if p.get("url"):
                    return f'<li class="org-ev org-post"><a href="{esc(p["url"])}" rel="noopener">{inner}</a></li>'
                return f'<li class="org-ev org-post"><span class="org-post-static">{inner}</span></li>'

            more = f"，顯示最近 {len(shown)} 則" if len(ordered) > len(shown) else ""
            body.append(f'<h2>收錄貼文（{len(ordered)} 則{more}）</h2><ul class="org-evs">'
                        + "".join(post_row(p) for p in shown) + "</ul>")
        body.append('<p class="src-desc"><a href="/source/">← 回資料來源名錄</a></p></article>')
        d = SITE / "org" / str(ent["id"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page_shell(
            f"{ent['name']}｜竹梅活動觀測站",
            f"{ent['name']}的公開帳號與活動記錄。",
            "\n".join(body), canonical=f"{BASE_URL}/org/{ent['id']}/"))
    # 清掉已不存在的舊單位頁（條目合併/改名後）
    valid = {str(ent["id"]) for ent in entries}
    import shutil
    org_root = SITE / "org"
    if org_root.exists():
        for d in org_root.iterdir():
            if d.is_dir() and d.name not in valid:
                shutil.rmtree(d)
    print(f"org pages: {len(entries)}")
    return [ent["id"] for ent in entries]


def source_page(events, entries):
    """/source/：表格於 build 時整份預渲染（SSR）；app.js 讀 sources.json 後原地重繪加上篩選排序。"""
    content = f"""<section class="hero"><h1>資料來源與機構名錄</h1>
<p>以兩校 114 學年度官方社團名冊為底，加上竹梅監測中的公告系統與社群帳號。
還沒找到公開帳號的單位也列出——如果你知道它們的 IG／FB，歡迎到<a href="/about/">回報管道</a>告訴我們。
<span id="src-count" aria-live="polite">目前列出 {len(entries)} 個單位。</span></p></section>
<section class="filters" aria-label="名錄篩選">
  <div class="filter-row"><span class="label">學校</span><span id="sf-school" class="fgroup"></span>
    <span class="search-hit"><input id="search" type="search" placeholder="搜尋社團、單位…" aria-label="搜尋名錄"></span></div>
  <div class="filter-row"><span class="label">狀態</span><span id="sf-status" class="fgroup"></span></div>
  <div class="filter-row"><span class="label">類型</span><span id="sf-kind" class="fgroup"></span></div>
  <div class="filter-row"><span class="label">平台</span><span id="sf-platform" class="fgroup"></span></div>
</section>
<div id="source-table" class="src-table" aria-label="機構名錄">{source_table_html(entries)}</div>"""
    d = SITE / "source"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(page_shell(
        "資料來源與機構名錄｜竹梅活動觀測站",
        "清大×交大全部社團與單位的名錄：竹梅監測中的公告系統、IG、FB、Threads、X 帳號，以及尚未收錄的單位。",
        content, canonical=f"{BASE_URL}/source/"))
    return org_pages(entries, events)


def post_campus(directory_entry, events):
    """Return the NYCU campus used to split the homepage feed.

    A source directory assignment is stronger than an event venue: a Guangfu
    club holding an event at Yangming is still a Guangfu-campus organization.
    School-wide sources fall back to the event campus when it is unambiguous.
    """
    directory_entry = directory_entry or {}
    campus = directory_entry.get("campus")
    if campus in {"guangfu", "yangming"}:
        return campus

    observed = set()
    for event in events:
        event_campus = event.get("campus")
        if event_campus == "nycu-yangming":
            observed.add("yangming")
        elif event_campus in {"nycu-guangfu", "nycu-boai"}:
            observed.add("guangfu")
    if len(observed) == 1:
        return observed.pop()

    inferred = _org_campus(directory_entry.get("base_name") or directory_entry.get("name") or "")
    return inferred if inferred in {"guangfu", "yangming"} else None


def build_posts_data(events, sid_to_entry=None):
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
        directory_entry = (sid_to_entry or {}).get(sid) or {}
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
        post_school = it.get("school") or lead.get("school")
        posts.append({
            "source_id": sid, "post_id": pid,
            "source_name": directory_entry.get("name") or it.get("source_name"), "platform": it.get("platform"),
            "school": post_school,
            "campus": post_campus(directory_entry, evs) if post_school == "nycu" else None,
            "url": it.get("url"), "posted_at": posted,
            "org_type": it.get("org_type") or lead.get("organizer_type"),
            "text": text[:500] + ("…" if len(text) > 500 else ""),
            "image": image, "avatar": avatar,
            "org_id": (sid_to_entry.get(sid) or {}).get("id") if sid_to_entry else None,
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
    return posts


# ---- 首頁河道 SSR ----
# markup 須與 site/assets/app.js 的 row()/evChip() 逐字一致：app.js 載入 posts.json 後
# 會整段重繪，兩邊一致才不會閃動；改其中一邊記得同步另一邊。
FEED_SVG_OPEN = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                 'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">')
FEED_ICON = {
    "dots": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
             '<circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/></svg>'),
    "cal": FEED_SVG_OPEN + '<path d="M4 5m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"/><path d="M16 3l0 4"/><path d="M8 3l0 4"/><path d="M4 11l16 0"/><path d="M8 15h2v2h-2z"/></svg>',
    "send": FEED_SVG_OPEN + '<path d="M10 14l11 -11"/><path d="M21 3l-6.5 18a.55 .55 0 0 1 -1 0l-3.5 -7l-7 -3.5a.55 .55 0 0 1 0 -1l18 -6.5"/></svg>',
    "ext": FEED_SVG_OPEN + '<path d="M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6"/><path d="M11 13l9 -9"/><path d="M15 4h5v5"/></svg>',
    "heart": FEED_SVG_OPEN + '<path d="M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6"/><path d="M9 17v1a3 3 0 0 0 6 0v-1"/></svg>',
}


def heart_btn(org_id, org_name, extra_class=""):
    """追蹤愛心：狀態由 app.js 依 push-prefs 的 orgs 同步。"""
    return (f'<button class="heart-btn{" " + extra_class if extra_class else ""}" '
            f'data-org-id="{org_id}" data-org-name="{esc(org_name)}" '
            f'aria-pressed="false" title="追蹤 {esc(org_name)}">{FEED_ICON["heart"]}</button>')
FEED_PLAT = {"instagram": "IG", "facebook": "FB", "threads": "Threads", "x": "X", "bulletin": "公告", "api": "官方"}


def _iso_dt(s):
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ_TAIPEI)


def _feed_ago(iso, now):
    dt = _iso_dt(iso)
    if dt is None:
        return ""
    h = max(0.0, (now - dt).total_seconds()) / 3600
    if h < 1:
        return f"{max(1, round(h * 60))} 分鐘前"
    if h < 24:
        return f"{round(h)} 小時前"
    d = dt.astimezone(TZ_TAIPEI)
    return f"{d.month}/{d.day}"


def _feed_ev_chip(e):
    esc = html.escape
    d = _iso_dt(e["start_at"]).astimezone(TZ_TAIPEI)
    when = f"{d.month}/{d.day}" + ("" if e.get("all_day") else f" {d.hour:02d}:{d.minute:02d}")
    return (f'<a class="feed-ev" data-id="{esc(e["id"])}" href="/event/{e["id"]}/">'
            f'<span class="feed-ev-date">{esc(when)}</span><span class="feed-ev-title">{esc(e["title"])}</span></a>')


def _feed_school_label(post):
    if post.get("school") == "nycu":
        if post.get("campus") == "guangfu":
            return "交大"
        if post.get("campus") == "yangming":
            return "陽明"
    return SCHOOL_LABEL.get(post.get("school") or "", "")


def _feed_row(p, now):
    esc = html.escape
    if p.get("avatar"):
        avatar = f'<img class="feed-avatar" src="{esc(p["avatar"])}" alt="">'
    else:
        initial = re.sub(r"^(清大|交大|陽明|國立)", "", p.get("source_name") or "？")[:1]
        avatar = f'<span class="feed-avatar src-avatar-fallback av-{esc(p.get("school") or "")}">{esc(initial)}</span>'
    org_href = f'/org/{p["org_id"]}/' if p.get("org_id") else None
    avatar_el = (f'<a class="feed-org-link" href="{org_href}" aria-label="{esc(p.get("source_name") or "")} 的單位頁">{avatar}</a>'
                 if org_href else avatar)
    school_label = _feed_school_label(p)
    plat = FEED_PLAT.get(p.get("platform"), p.get("platform"))
    menu_items = ((f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">查看原文（{esc(plat)}）↗</a>' if p.get("url") else "") +
                  (f'<a href="{org_href}">單位頁面</a>' if org_href else ""))
    menu = (f'<details class="post-menu"><summary aria-label="更多選項">{FEED_ICON["dots"]}</summary>'
            f'<div class="post-menu-panel">{menu_items}</div></details>') if menu_items else ""
    name = (f'<a class="feed-org-link" href="{org_href}">{esc(p.get("source_name") or "")}</a>'
            if org_href else esc(p.get("source_name") or ""))
    head = ('<div class="feed-head">'
            f'<strong class="feed-name">{name}</strong>' +
            (f'<span class="feed-topic"><span class="sep">›</span>{esc(school_label)}</span>' if school_label else "") +
            f'<span class="feed-time">{esc(_feed_ago(p.get("posted_at"), now))}</span>{menu}</div>')
    body = ((f'<p class="feed-text">{esc(p["text"])}</p>' if p.get("text") else "") +
            (f'<img class="feed-img" src="{esc(p["image"])}" alt="" loading="lazy">' if p.get("image") else ""))
    evs = ('<div class="feed-evs">' + "".join(_feed_ev_chip(e) for e in p["events"]) + "</div>") if p["events"] else ""
    ev0 = p["events"][0] if p["events"] else None
    share_url = f'{BASE_URL}/event/{ev0["id"]}/' if ev0 else (p.get("url") or BASE_URL)
    share_title = ev0["title"] if ev0 else (p.get("source_name") or "竹梅活動觀測站")
    actions = ('<div class="feed-actions">' +
               (heart_btn(p["org_id"], p.get("source_name") or "", "feed-action") if p.get("org_id") else "") +
               (f'<a class="feed-action" href="/event/{ev0["id"]}/" title="活動詳情">{FEED_ICON["cal"]}' +
                (f'<span>{len(p["events"])}</span>' if len(p["events"]) > 1 else "") + "</a>" if ev0 else "") +
               f'<button class="feed-action btn-share" data-url="{esc(share_url)}" data-title="{esc(share_title)}" title="分享">{FEED_ICON["send"]}</button>' +
               (f'<a class="feed-action" href="{esc(p["url"])}" target="_blank" rel="noopener" title="開啟原文">{FEED_ICON["ext"]}</a>' if p.get("url") else "") +
               "</div>")
    return f'<article class="feed-post">{avatar_el}<div class="feed-content">{head}{body}{evs}{actions}</div></article>'


def _inject_ssr(path, marker, body):
    start, end = f"<!-- {marker} -->", f"<!-- /{marker} -->"
    src = path.read_text()
    if start not in src or end not in src:
        print(f"prerender: {path} 缺 {marker} 標記，略過")
        return
    head, _, rest = src.partition(start)
    _, _, tail = rest.partition(end)
    path.write_text(head + start + body + end + tail)


def prerender_feed(posts, shown=30):
    """把河道前 shown 則靜態渲染進 site/index.html 的 ssr-feed 標記之間，
    讓爬蟲與初載畫面直接拿到內容；app.js 抓到 posts.json 後原地重繪接手。"""
    now = datetime.now(TZ_TAIPEI)
    body = "".join(_feed_row(p, now) for p in posts[:shown]) or '<p class="empty">尚無貼文。</p>'
    if len(posts) > shown:
        body += f'<button class="fchip feed-more">載入更多（還有 {len(posts) - shown} 則）</button>'
    _inject_ssr(SITE / "index.html", "ssr-feed", body)
    print(f"prerender: {min(shown, len(posts))} posts into index.html")


def _ev_when(e, with_weekday=True):
    d = _iso_dt(e["start_at"]).astimezone(TZ_TAIPEI)
    wd = f"（{'日一二三四五六'[(d.weekday() + 1) % 7]}）" if with_weekday else ""
    return f"{d.month}/{d.day}{wd}" + ("" if e.get("all_day") else f" {d.hour:02d}:{d.minute:02d}")


def _ev_list_row(e):
    """app.js initList 的 listRow()：/events/ 列表列。"""
    esc = html.escape
    where = " ".join(x for x in (CAMPUS_LABEL.get(e.get("campus") or ""), e.get("venue")) if x)
    sch = e.get("school")
    if e.get("poster_image"):
        thumb = f'<img class="evr-thumb" src="{esc(e["poster_image"])}" alt="" loading="lazy">'
    else:
        np = sch if sch in ("nthu", "nycu") else "other"
        thumb = (f'<span class="evr-thumb evr-thumb-txt np-{np}">'
                 + ("梅" if sch == "nthu" else "竹" if sch == "nycu" else "梅竹") + "</span>")
    reg, fee = e.get("reg"), e.get("fee")
    chips = (('<span class="chip chip-reg-req">需報名</span>' if reg == "required" else
              '<span class="chip chip-reg-free">自由入場</span>' if reg == "free" else "") +
             ('<span class="chip chip-fee-free">免費</span>' if fee == "free" else
              '<span class="chip chip-fee-paid">$</span>' if fee == "paid" else "") +
             ('<span class="chip chip-review">待確認</span>' if (e.get("extraction") or {}).get("needs_review") else ""))
    meta = "｜".join(x for x in (where, e.get("organizer")) if x)
    row_heart = (heart_btn(e["org_id"], e.get("org_name") or e.get("organizer") or "", "ev-row-heart")
                 if e.get("org_id") else "")
    return (f'<div class="ev-row-wrap">{row_heart}'
            f'<a class="ev-row ev-row-{esc(sch or "")}" href="/event/{e["id"]}/">{thumb}'
            f'<span class="evr-main"><span class="evr-when">{esc(_ev_when(e))}{chips}</span>'
            f'<span class="evr-title">{esc(e["title"])}</span>'
            f'<span class="evr-meta">{esc(meta)}</span></span></a></div>')


def prerender_events(events):
    """/events/ SSR：預設篩選（未來 7 天）的列表列。JS 載入 events.json 後依裝置重繪。"""
    now = datetime.now(TZ_TAIPEI)
    today = now.strftime("%Y-%m-%d")
    range_end = now + timedelta(days=7)

    def in_default_range(e):
        t = _iso_dt(e["start_at"])
        if t is None:
            return False
        if e.get("all_day"):
            return e["start_at"][:10] >= today and t <= range_end
        end = _iso_dt(e.get("end_at")) or t
        return end >= now and t <= range_end

    rows = [e for e in events if in_default_range(e)]
    # 與 app.js 相同：未開始以開始時間排序，進行中則以截止時間排序。
    def sort_time(e):
        start = _iso_dt(e["start_at"])
        end = _iso_dt(e.get("end_at"))
        return end if end is not None and start <= now <= end else start

    rows.sort(key=lambda e: (sort_time(e), e["start_at"], e["title"]))
    body = "".join(_ev_list_row(e) for e in rows) or \
        '<p class="empty">沒有符合條件的活動。試著放寬篩選，或到「全部」看看過去的活動。</p>'
    _inject_ssr(SITE / "events" / "index.html", "ssr-events", body)
    print(f"prerender: {len(rows)} events (7d) into events/index.html")


def prerender_calendar(events, months_ahead=2):
    """/calendar/ SSR：本月起三個月的議程列表（app.js agendaMonthHtml 的手機版 markup）。
    桌機 JS 載入後會換成月曆格；無 JS／爬蟲拿到的是可讀的逐日清單。"""
    esc = html.escape
    now = datetime.now(TZ_TAIPEI)
    today = now.strftime("%Y-%m-%d")
    by_day = {}
    for e in events:
        by_day.setdefault((e.get("start_at") or "")[:10], []).append(e)

    out = []
    for off in range(0, months_ahead + 1):
        y = now.year + (now.month - 1 + off) // 12
        mo = (now.month - 1 + off) % 12 + 1
        days_in_month = ((date(y, mo, 1).replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day
        start_day = now.day if off == 0 else 1
        month_total, body = 0, ""
        for day in range(start_day, days_in_month + 1):
            key = f"{y}-{mo:02d}-{day:02d}"
            day_events = by_day.get(key) or []
            if not day_events:
                continue
            month_total += len(day_events)
            wd = "日一二三四五六"[(date(y, mo, day).weekday() + 1) % 7]
            items = ""
            for e in day_events:
                d = _iso_dt(e["start_at"]).astimezone(TZ_TAIPEI)
                when = "全天" if e.get("all_day") else f"{d.hour:02d}:{d.minute:02d}"
                where = " ".join(x for x in (CAMPUS_LABEL.get(e.get("campus") or ""), e.get("venue")) if x)
                items += (f'<a class="agd-ev ev-{esc(e.get("school") or "")}" href="/event/{e["id"]}/">'
                          f'<span class="agd-when">{esc(when)}</span>'
                          f'<span class="agd-main"><span class="agd-title">{esc(e["title"])}</span>'
                          + (f'<span class="agd-meta">{esc(where)}</span>' if where else "") + "</span></a>")
            body += (f'<div class="agd-day{" today" if key == today else ""}">'
                     f'<span class="agd-date">{mo}/{day}（{wd}）</span>{items}</div>')
        out.append(f'<section class="cal-month" id="cal-{y}-{mo}">'
                   f'<h2 class="cal-month-title">{y} 年 {mo} 月<span class="cal-month-n">{month_total} 場</span></h2>'
                   + (body or '<p class="agd-empty">這個月（在目前篩選下）沒有活動。</p>') + "</section>")
    _inject_ssr(SITE / "calendar" / "index.html", "ssr-cal", "".join(out))
    print(f"prerender: {months_ahead + 1} months into calendar/index.html")


def prerender_stories():
    """/stories/ SSR：動態牆卡片（app.js initStories 的 wall markup）。"""
    esc = html.escape
    path = SITE / "data" / "stories.json"
    stories = json.loads(path.read_text()).get("stories") if path.exists() else []
    stories = stories or []
    now = datetime.now(TZ_TAIPEI)

    def ago(iso):
        dt = _iso_dt(iso)
        h = max(0.0, (now - dt).total_seconds() / 3600) if dt else 0
        return f"{round(h * 60)} 分鐘前" if h < 1 else f"{round(h)} 小時前"

    # 與 JS 相同：依帳號分組、組序取該帳號首次出現的順序
    groups, order = {}, []
    for s in stories:
        if s["username"] not in groups:
            groups[s["username"]] = []
            order.append(s["username"])
        groups[s["username"]].append(s)
    flat = [s for u in order for s in groups[u]]

    if not flat:
        body = '<p class="empty">現在沒有進行中的限時動態 — 限動 24 小時後就會消失，晚點再來看看。</p>'
    else:
        body = "".join(
            f'<button class="story-card" data-i="{i}">'
            f'<img src="{esc(s["media"])}" alt="{esc(s["name"])} 的限時動態" loading="lazy">'
            + ('<span class="sc-video">▶</span>' if s.get("is_video") else "") +
            '<span class="sc-meta">'
            + (f'<img class="sc-avatar" src="{esc(s["avatar"])}" alt="">' if s.get("avatar") else "") +
            f'<span class="sc-who"><strong>{esc(s["name"])}</strong>{ago(s["taken_at"])}</span></span></button>'
            for i, s in enumerate(flat))
    _inject_ssr(SITE / "stories" / "index.html", "ssr-stories", body)
    print(f"prerender: {len(flat)} stories into stories/index.html")


def source_table_html(entries):
    """/source/ SSR：完整名錄表；追蹤數載入前暫以收錄活動數穩定排序。"""
    esc = html.escape
    now = datetime.now(TZ_TAIPEI)
    PLAT = {"instagram": "IG", "facebook": "FB", "threads": "Threads", "x": "X", "bulletin": "公告", "website": "官網"}

    def fmt_updated(iso):
        dt = _iso_dt(iso)
        if dt is None:
            return "—"
        days = (now - dt).total_seconds() / 86400
        if days < 1:
            return "今天"
        if days < 30:
            return f"{round(days)} 天前"
        d = dt.astimezone(TZ_TAIPEI)
        return f"{d.year}/{d.month}/{d.day}"

    def row(e):
        links = "".join(
            f'<a class="src-link" href="{esc(l["url"])}" rel="noopener" target="_blank">'
            + esc(PLAT.get(l["platform"], l["platform"]))
            + (" " + esc(l["label"]) if l.get("label") and l["label"] not in ("Facebook", "公告頁") else "")
            + "</a>" for l in e["links"])
        links_html = links or '<span class="src-none">尚未找到公開帳號</span>'
        if e.get("avatar"):
            avatar = f'<img class="src-avatar src-c-ava" src="{esc(e["avatar"])}" alt="" loading="lazy">'
        else:
            initial = re.sub(r"^(清大|交大|陽明|國立)", "", e["name"])[:1] or "？"
            avatar = f'<span class="src-avatar src-c-ava src-avatar-fallback av-{esc(e["school"])}">{esc(initial)}</span>'
        m_label = ("清大" if e["school"] == "nthu"
                   else ("陽明" if e.get("campus") == "yangming" else "交大" if e.get("campus") == "guangfu" else "陽明交大")
                   if e["school"] == "nycu" else "其他")
        school_label = "清大" if e["school"] == "nthu" else "陽明交大" if e["school"] == "nycu" else "其他"
        return ('<div class="src-row' + ("" if e["links"] else " src-uncovered") + '">'
                f'<span class="src-id src-c-id" aria-label="名錄 ID {e["id"]}">#{e["id"]}</span>'
                f'<span class="src-c-name">{avatar}'
                f'<a class="src-name" href="/org/{e["id"]}/">{esc(e["name"])}</a>'
                f'<span class="chip chip-m chip-{esc(e["school"])}">{m_label}</span></span>'
                '<span class="chips src-c-chips">'
                f'<span class="chip chip-school chip-{esc(e["school"])}">{esc(school_label)}</span>'
                + (f'<span class="chip chip-campus">{"陽明" if e["campus"] == "yangming" else "交大"}</span>' if e.get("campus") else "")
                + f'<span class="chip chip-extra">{esc(KIND_LABEL.get(e["kind"], ""))}</span>'
                + (f'<span class="chip chip-extra">{esc(e["category"])}</span>' if e.get("category") else "")
                + "</span>"
                f'<div class="src-links">{links_html}</div>'
                f'<div class="src-upd" title="{esc(e.get("updated") or "")}">{fmt_updated(e.get("updated"))}</div>'
                f'<div class="src-ev">{str(e["events"]) + " 場" if e["events"] else "—"}</div>'
                + (f'<button class="heart-btn heart-btn-label src-c-follow" data-org-id="{e["id"]}" '
                   f'data-org-name="{esc(e["name"])}" aria-pressed="false" aria-label="追蹤 {esc(e["name"])}" '
                   f'title="追蹤 {esc(e["name"])}">'
                   f'{FEED_ICON["heart"]}<span class="hb-follow">追蹤</span>'
                   f'<span class="hb-following">追蹤中</span></button>') + "</div>")

    def th(key, label, extra_cls="", on=False, arrow=" ↕"):
        cls = "src-th" + (f" {extra_cls}" if extra_cls else "") + (" src-th-on" if on else "")
        return f'<button class="{cls}" data-sort="{key}">{label}{arrow}</button>'

    head = ('<div class="src-head">' + th("id", "ID") + th("name", "名稱", "src-th-left") +
            '<span class="src-th-plain">標籤</span><span class="src-th-plain src-th-links">連結</span>' +
            th("updated", "更新") + th("events", "收錄") +
            th("follow", "追蹤", "src-th-follow", on=True, arrow=" ↓") + "</div>")
    # 公開追蹤數由 /auth/follows 動態載入；載入前沿用穩定的收錄數排序，JS 隨即重排。
    ordered = sorted(entries, key=lambda e: (-e["events"], -len(e["links"]), e["name"]))
    return head + "".join(row(e) for e in ordered)


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
    attach_reg_status(events)
    venues = load_venues()
    n_geo = attach_geo(events, venues)
    print(f"geo: {n_geo}/{sum(1 for e in events if e.get('venue'))} venue-matched ({len(venues)} registry rows)")
    n_ext = geocode_external(events)
    print(f"geo-external: {n_ext} 校外場地 geocoded")

    today = date.today().isoformat()
    upcoming = [e for e in events if e["start_at"][:10] >= today]

    for d in ("data", "api", "feeds", "event"):
        (SITE / d).mkdir(parents=True, exist_ok=True)

    # 原貼文時間掛回活動（Telegram 用「貼文新舊」判斷是否推播，防新帳號回填洪水）
    from chumei_lib import iter_inbox
    post_ts = {}
    for it in iter_inbox():
        post_ts[(it["source_id"], it["post_id"])] = it.get("posted_at")
    for e in events:
        for src in [e.get("source") or {}] + e.get("alt_posts", []):
            ts = post_ts.get((src.get("source_id"), src.get("post_id")))
            if ts:
                src["posted_at"] = ts

    # 名錄歸戶提前：活動 JSON 帶 org_id/org_name，前端愛心（追蹤單位）靠它
    entries = build_sources_data(events)
    sid_to_entry = {}
    for ent in entries:
        for sid in ent.get("sids", []):
            sid_to_entry[sid] = ent
    for e in events:
        ent = sid_to_entry.get((e.get("source") or {}).get("source_id"))
        if ent is not None:
            e["org_id"], e["org_name"] = ent["id"], ent["name"]

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

    today_s = date.today().isoformat()
    ent_events = {}
    for e in events:
        seen_ent = set()
        for src in [e["source"]] + e.get("alt_posts", []):
            ent = sid_to_entry.get(src.get("source_id"))
            if ent is not None and ent["id"] not in seen_ent:
                seen_ent.add(ent["id"])
                ent_events.setdefault(ent["id"], []).append(e)
    for e in events:
        ent = sid_to_entry.get(e["source"]["source_id"])
        org = (ent["id"], ent["name"]) if ent else None
        # 每個來源單位（主來源優先）各一段「更多活動」
        org_sections, seen_ent = [], set()
        for src in [e["source"]] + e.get("alt_posts", []):
            ent2 = sid_to_entry.get(src.get("source_id"))
            if ent2 is None or ent2["id"] in seen_ent:
                continue
            seen_ent.add(ent2["id"])
            sibs = [x for x in ent_events.get(ent2["id"], []) if x["id"] != e["id"]]
            up = sorted([x for x in sibs if x["start_at"][:10] >= today_s], key=lambda x: x["start_at"])
            past = sorted([x for x in sibs if x["start_at"][:10] < today_s], key=lambda x: x["start_at"], reverse=True)
            org_sections.append((ent2["id"], ent2["name"], (up + past)[:4]))
        # 資訊列「原始貼文」＝這場活動的所有來源貼文（主來源＋合併掉的），依發文時間排序
        alt_posts = []
        for src in sorted([e["source"]] + e.get("alt_posts", []), key=lambda s2: s2.get("posted_at") or "9999"):
            if not src.get("url"):
                continue
            ent2 = sid_to_entry.get(src.get("source_id"))
            plat = FEED_PLAT.get(src.get("platform"), src.get("platform") or "")
            posted = _iso_dt(src.get("posted_at"))
            when = f"，{posted.astimezone(TZ_TAIPEI).month}/{posted.astimezone(TZ_TAIPEI).day}" if posted else ""
            alt_posts.append({"url": src["url"],
                              "label": (f'{ent2["name"]}（{plat}{when}）' if ent2 else plat + when.lstrip("，"))})
        d = SITE / "event" / e["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(detail_page(e, org=org, org_sections=org_sections, alt_posts=alt_posts))

    org_ids = source_page(events, entries)
    prerender_feed(build_posts_data(events, sid_to_entry))
    prerender_events(events)
    prerender_calendar(events)
    prerender_stories()
    version_static_assets()

    urls = [f"{BASE_URL}/", f"{BASE_URL}/calendar/", f"{BASE_URL}/subscribe/", f"{BASE_URL}/notify/", f"{BASE_URL}/about/", f"{BASE_URL}/source/", f"{BASE_URL}/stories/", f"{BASE_URL}/events/"] + \
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
