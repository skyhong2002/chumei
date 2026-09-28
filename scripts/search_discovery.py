"""Search entry pages and a focused sitemap; historic URLs remain accessible."""
import hashlib
import html
import json
import re
from datetime import timedelta
from xml.etree import ElementTree as ET

from event_curation import is_period_event
from event_time import event_datetime, event_end, event_has_not_ended

# 依搜尋意圖切的入口頁：學校、類型各一頁，標題用大家實際會搜的字。
HUBS = (
    dict(slug="nthu", school="nthu", category=None, label="清大活動",
         title="清大活動｜清華大學講座、社團與校園活動",
         desc="清華大學校方單位、系所與社團即將舉行的講座、工作坊、表演與各類活動，"
              "附日期、地點、主辦單位與原始公告連結。實際時間與報名方式以主辦單位公告為準。"),
    dict(slug="nycu", school="nycu", category=None, label="陽明交大活動",
         title="陽明交大活動｜陽明交通大學講座、社團與校園活動",
         desc="陽明交通大學校方單位、系所與社團即將舉行的講座、工作坊、表演與各類活動，"
              "附日期、地點、主辦單位與原始公告連結。實際時間與報名方式以主辦單位公告為準。"),
    dict(slug="talks", school=None, category="演講", label="演講與講座",
         title="清大、陽明交大演講與講座",
         desc="清華大學與陽明交通大學即將舉行的演講、講座與分享會，附日期、地點、主辦單位與原始公告連結。"
              "實際時間與報名方式以主辦單位公告為準。"),
)

# 首頁與活動總覽同一份入口列；current 讓入口頁自己標示所在位置。
def hub_links(current=None):
    items = "".join(
        f'<a class="feed-hub" href="/events/{h["slug"]}/"'
        + (' aria-current="page"' if h["slug"] == current else "")
        + f'>{h["label"]}</a>'
        for h in HUBS)
    return f'<nav class="feed-hubs" aria-label="依學校與活動類型瀏覽">{items}</nav>'


HOME_TITLE = "清大、陽明交大活動與講座｜竹梅活動觀測站"
_LINKS_RE = re.compile(r"<!-- search-entry-links -->.*?<!-- /search-entry-links -->", re.S)


def _hub_rows(events, hub, now):
    def sort_key(e):
        # 與活動總覽相同：未開始依開始時間，進行中依結束時間，長期展覽才不會一直占著最上面。
        start, end = event_datetime(e.get("start_at")), event_end(e)
        current = end if (start and end and start <= now <= end) else start
        return (current or start, e["start_at"], e["id"])

    return sorted(
        (e for e in events if event_has_not_ended(e, now)
         and (not hub["school"] or e.get("school") in (hub["school"], "both"))
         and (not hub["category"] or e.get("category") == hub["category"])),
        key=sort_key)


def build_search_pages(site, events, now, base_url, page_shell, render_row):
    paths = []
    for hub in HUBS:
        rows = _hub_rows(events, hub, now)
        groups = [(label, group) for label, group in (
            ("定時活動", [e for e in rows if not is_period_event(e)]),
            ("期間活動", [e for e in rows if is_period_event(e)])) if group]
        listing = ("".join(
            f'<h2 class="event-section-title">{label} · {len(group)} 場</h2>'
            f'<div class="event-rows">{"".join(render_row(e) for e in group)}</div>'
            for label, group in groups)
            or '<p class="empty">目前沒有即將舉行的活動，歡迎到<a href="/events/">活動總覽</a>看看。</p>')
        content = (
            '<section class="hero hub-hero">'
            f'<h1>{html.escape(hub["title"])}</h1>'
            f'<p>{html.escape(hub["desc"])}</p>'
            + hub_links(hub["slug"])
            + "</section>"
            f'<section class="hub-list" aria-label="活動列表">{listing}</section>')
        path = f'/events/{hub["slug"]}/'
        target = site / path.strip("/") / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page_shell(hub["title"] + "｜竹梅活動觀測站", hub["desc"], content,
                                     canonical=base_url + path))
        paths.append(path)

    # 入口列放在 JS 不會重繪的位置；重跑建站時以註解標記原地替換。
    block = "<!-- search-entry-links -->" + hub_links() + "<!-- /search-entry-links -->"
    for rel in ("index.html", "events/index.html"):
        path = site / rel
        source = path.read_text()
        if _LINKS_RE.search(source):
            source = _LINKS_RE.sub(lambda _: block, source, count=1)
        elif rel == "index.html" and '<div class="feed-tabs-row">' in source:
            # 首頁：限動列之後、河道之前，讓入口列成為版面的一部分而不是頁首雜訊。
            source = source.replace('<div class="feed-tabs-row">', block + '\n  <div class="feed-tabs-row">', 1)
        else:
            source = re.sub(r"(</h1>)", lambda m: m[0] + block, source, count=1)
        if rel == "index.html":
            source = re.sub(r"<title>.*?</title>", f"<title>{HOME_TITLE}</title>", source)
            source = re.sub(r'(<meta (?:property="og:title"|name="twitter:title") content=")[^"]*',
                            lambda m: m[1] + HOME_TITLE, source)
        path.write_text(source)
    return paths


_MAIN_RE = re.compile(r"<main\b[^>]*>(.*?)</main>", re.S)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
# 同單位其他活動、可能相關的活動會隨別的活動增減而變，不算這一頁的內容更新。
_VOLATILE_RE = re.compile(r'<section class="(?:org-more|related-events)">.*?</section>', re.S)


def page_digest(source):
    main = _MAIN_RE.search(source)
    title = _TITLE_RE.search(source)
    content = _VOLATILE_RE.sub("", main[1] if main else source) + (title[1] if title else "")
    return hashlib.sha256(content.encode()).hexdigest()


def write_search_sitemap(site, events, org_ids, hub_paths, now, base_url, *, state_path):
    """state_path 記錄各頁內容雜湊與 lastmod；必須放在網站根目錄之外，跨發布版本沿用。"""
    # 近三個月結束的活動仍有人搜；更早的存檔頁保留網址與站內連結，但不進 sitemap。
    cutoff = now - timedelta(days=90)
    recent = [e for e in events if event_end(e) and event_end(e) >= cutoff]
    paths = ["/", "/events/", "/calendar/", "/source/", "/about/", "/subscribe/"]
    paths += hub_paths + [f'/event/{e["id"]}/' for e in recent]
    paths += [f"/org/{oid}/" for oid in org_ids]

    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    state = {}
    stamp = now.replace(microsecond=0).isoformat()
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", ns)
    root = ET.Element(f"{{{ns}}}urlset")
    for path in dict.fromkeys(paths):
        target = site / path.strip("/") / "index.html"
        if not target.exists():
            continue
        entry = ET.SubElement(root, f"{{{ns}}}url")
        ET.SubElement(entry, f"{{{ns}}}loc").text = base_url + path
        # 首頁與單位頁帶相對時間標籤，每次建站都會變，不給 lastmod。
        if path.startswith("/event/") or path in hub_paths:
            digest = page_digest(target.read_text())
            old = previous.get(path, {})
            modified = (old.get("lastmod") if old.get("hash") == digest else None) or stamp
            state[path] = {"hash": digest, "lastmod": modified}
            ET.SubElement(entry, f"{{{ns}}}lastmod").text = modified
    (site / "sitemap.xml").write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False))
    # 舊版曾把狀態檔寫進網站根目錄；發布時會從前一版複製過來，這裡清掉。
    (site / ".sitemap-state.json").unlink(missing_ok=True)
    (site / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n")
    print(f"search sitemap: {len(root)} URLs, {len(recent)} recent/ongoing events")
