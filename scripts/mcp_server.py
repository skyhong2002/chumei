#!/usr/bin/env python3
"""竹梅 MCP server — 讓 AI 助理（Claude、ChatGPT…）直接查詢校園活動。

唯讀服務：資料源是 pipeline 產出的 site/api/events.json 與 site/data/sources.json，
每次請求檢查 mtime 自動重載，完全不碰抓取／建站流程。

對外：Caddy 把 https://chumei.observe.tw/mcp 反代到 127.0.0.1:8321（Streamable HTTP）。
排程：launchd deploy/tw.observe.chumei.mcp.plist 常駐。
本機測試：.venv/bin/python scripts/mcp_server.py 後
  npx @modelcontextprotocol/inspector 或 claude mcp add --transport http chumei http://127.0.0.1:8321/mcp
"""

import json
from datetime import datetime, timedelta

from mcp.server.mcpserver import MCPServer

from chumei_lib import ROOT, TZ_TAIPEI

BASE_URL = "https://chumei.observe.tw"
EVENTS_PATH = ROOT / "site" / "api" / "events.json"
SOURCES_PATH = ROOT / "site" / "data" / "sources.json"
PORT = 8321

CAT_SLUG = {"演講": "talk", "工作坊": "workshop", "表演": "show", "展覽": "expo",
            "比賽": "contest", "營隊": "camp", "徵才": "recruit", "市集": "market",
            "運動": "sport", "聚會": "social", "其他": "other"}
SLUG_CAT = {v: k for k, v in CAT_SLUG.items()}
ORG_SLUG = {"official": "official", "department": "dept", "club": "club", "external": "ext"}


_CACHE = {}


def _cached_json(path):
    """讀 JSON，mtime 沒變就用上次結果（events.json 1.7MB，pipeline 每 3 小時重建）。"""
    mtime = path.stat().st_mtime
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(path.read_text())
    _CACHE[path] = (mtime, data)
    return data


def load_events():
    return _cached_json(EVENTS_PATH)


def load_sources():
    return _cached_json(SOURCES_PATH)["entries"]


def _now():
    return datetime.now(TZ_TAIPEI)


def _parse_date(s, name):
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=TZ_TAIPEI)
    except ValueError:
        raise ValueError(f"{name} 需為 YYYY-MM-DD 格式，收到 {s!r}")


def _start_at(e):
    v = e.get("start_at")
    return datetime.fromisoformat(v) if v else None


def _norm_category(category):
    if not category:
        return None
    if category in CAT_SLUG:
        return category
    if category in SLUG_CAT:
        return SLUG_CAT[category]
    raise ValueError(f"未知的活動類型 {category!r}；可用：{'、'.join(CAT_SLUG)}（或英文代碼 {', '.join(SLUG_CAT)}）")


def _event_brief(e, labels):
    return {
        "id": e["id"],
        "title": e.get("title"),
        "summary": e.get("summary"),
        "start_at": e.get("start_at"),
        "end_at": e.get("end_at"),
        "all_day": e.get("all_day"),
        "school": labels["school"].get(e.get("school"), e.get("school")),
        "campus": labels["campus"].get(e.get("campus"), e.get("campus")),
        "venue": e.get("venue"),
        "organizer": e.get("organizer"),
        "category": e.get("category"),
        "registration_url": e.get("registration_url"),
        "url": f"{BASE_URL}/event/{e['id']}/",
    }


def _match_query(e, q):
    hay = " ".join(str(e.get(k) or "") for k in ("title", "summary", "description", "organizer", "venue"))
    return all(term.casefold() in hay.casefold() for term in q.split())


mcp = MCPServer(
    name="chumei",
    title="竹梅活動觀測站",
    website_url=BASE_URL,
    instructions=(
        "竹梅（chumei.observe.tw）自動彙整清華大學（NTHU）與陽明交通大學（NYCU）的公開校園活動——"
        "演講、工作坊、表演、比賽、市集等，來源為兩校公告系統與 470+ 學生社團/單位的公開社群貼文。"
        "查活動用 search_events（預設只回未來的活動）、細節用 get_event；"
        "查社團或主辦單位用 search_orgs / get_org；"
        "要長期追蹤就用 get_subscribe_urls 拿 iCalendar / RSS 訂閱網址。"
        "欄位由 LLM 從貼文擷取，時間地點以主辦單位公告為準（每筆都附原始貼文連結）。"
    ),
)


@mcp.tool()
def get_site_info() -> dict:
    """竹梅活動觀測站總覽：資料規模、更新時間、可用的學校／校區／類型代碼、訂閱端點。"""
    data = load_events()
    events = data["events"]
    now = _now()
    upcoming = [e for e in events if (s := _start_at(e)) and s >= now]
    return {
        "name": "竹梅活動觀測站",
        "description": "清大 × 陽明交大校園活動自動彙整（公告系統＋社團公開社群貼文，LLM 擷取欄位）",
        "url": BASE_URL,
        "generated_at": data.get("generated_at"),
        "total_events": len(events),
        "upcoming_events": len(upcoming),
        "orgs_in_directory": len(load_sources()),
        "labels": data["labels"],
        "categories": list(CAT_SLUG),
        "endpoints": {
            "json_api": f"{BASE_URL}/api/events.json",
            "subscribe_page": f"{BASE_URL}/subscribe/",
            "telegram": "https://t.me/chumei_events",
        },
    }


@mcp.tool()
def search_events(
    query: str = "",
    school: str | None = None,
    campus: str | None = None,
    category: str | None = None,
    organizer_type: str | None = None,
    starts_after: str | None = None,
    starts_before: str | None = None,
    include_past: bool = False,
    limit: int = 20,
) -> dict:
    """搜尋活動。預設只回「現在之後開始」的活動，依開始時間由近到遠排序。

    query：關鍵字（比對標題／摘要／內文／主辦／地點，空白分隔多詞 AND）。
    school：nthu｜nycu。campus：nthu-main｜nthu-nanda｜nycu-guangfu｜nycu-boai｜nycu-yangming｜online｜other。
    category：中文（演講、工作坊…）或代碼（talk、workshop…），見 get_site_info。
    organizer_type：official｜department｜club｜external。
    starts_after / starts_before：YYYY-MM-DD；給了 starts_after 或 include_past=True 才會納入過去的活動。
    """
    data = load_events()
    labels = data["labels"]
    category = _norm_category(category)
    after = _parse_date(starts_after, "starts_after") if starts_after else None
    before = _parse_date(starts_before, "starts_before") + timedelta(days=1) if starts_before else None
    if after is None and not include_past:
        after = _now()

    hits = []
    for e in data["events"]:
        s = _start_at(e)
        if s is None:
            continue
        if after and s < after:
            continue
        if before and s >= before:
            continue
        if school and e.get("school") not in (school, "both"):
            continue
        if campus and e.get("campus") != campus:
            continue
        if category and (e.get("category") or "其他") != category:
            continue
        if organizer_type and e.get("organizer_type") != organizer_type:
            continue
        if query and not _match_query(e, query):
            continue
        hits.append(e)

    hits.sort(key=_start_at, reverse=include_past and after is None)
    limit = max(1, min(limit, 100))
    return {
        "total": len(hits),
        "returned": min(len(hits), limit),
        "events": [_event_brief(e, labels) for e in hits[:limit]],
    }


@mcp.tool()
def get_event(event_id: str) -> dict:
    """依 id（如 evt_b81d02007302）取單場活動完整資訊，含原始貼文連結與報名資訊。"""
    data = load_events()
    for e in data["events"]:
        if e["id"] == event_id:
            full = _event_brief(e, data["labels"])
            full.update({
                "description": e.get("description"),
                "organizer_type": e.get("organizer_type"),
                "registration_deadline": e.get("registration_deadline"),
                "fee": e.get("fee") or e.get("price"),
                "source_post": (e.get("source") or {}).get("url"),
                "poster_image": (BASE_URL + e["poster_image"]) if e.get("poster_image") else None,
                "extraction_confidence": (e.get("extraction") or {}).get("confidence"),
            })
            return full
    raise ValueError(f"找不到活動 {event_id!r}（id 可由 search_events 取得）")


@mcp.tool()
def search_orgs(query: str = "", school: str | None = None, only_with_events: bool = False, limit: int = 20) -> dict:
    """搜尋機構名錄（470+ 個社團、系所、校方單位）。query 比對名稱；school：nthu｜nycu。

    回傳各單位的收錄活動數與社群連結；再用 get_org 取單位詳情與其活動。
    """
    entries = load_sources()
    hits = []
    for o in entries:
        if school and o.get("school") != school:
            continue
        if only_with_events and not o.get("events"):
            continue
        if query and not all(t.casefold() in o["name"].casefold() for t in query.split()):
            continue
        hits.append(o)
    hits.sort(key=lambda o: -(o.get("events") or 0))
    limit = max(1, min(limit, 100))
    return {
        "total": len(hits),
        "returned": min(len(hits), limit),
        "orgs": [{
            "id": o["id"],
            "name": o["name"],
            "school": o.get("school"),
            "events": o.get("events") or 0,
            "url": f"{BASE_URL}/org/{o['id']}/",
        } for o in hits[:limit]],
    }


@mcp.tool()
def get_org(org_id: int) -> dict:
    """依 search_orgs 給的 id 取單位詳情：社群連結、收錄貼文平台，與該單位即將舉行的活動。"""
    entries = load_sources()
    org = next((o for o in entries if o["id"] == org_id), None)
    if org is None:
        raise ValueError(f"找不到單位 id={org_id}（id 可由 search_orgs 取得）")
    data = load_events()
    sids = set(org.get("sids") or [])
    now = _now()
    upcoming = [e for e in data["events"]
                if (e.get("source") or {}).get("source_id") in sids
                and (s := _start_at(e)) and s >= now]
    upcoming.sort(key=_start_at)
    return {
        "id": org["id"],
        "name": org["name"],
        "school": org.get("school"),
        "kind": org.get("kind"),
        "url": f"{BASE_URL}/org/{org['id']}/",
        "links": [{"platform": l.get("platform"), "url": l.get("url")} for l in org.get("links") or []],
        "total_events": org.get("events") or 0,
        "upcoming_events": [_event_brief(e, data["labels"]) for e in upcoming[:20]],
    }


@mcp.tool()
def get_subscribe_urls(
    school: str = "all",
    category: str | None = None,
    campus: str | None = None,
    organizer_type: str | None = None,
) -> dict:
    """組出 iCalendar（Google/Apple 行事曆）與 RSS 訂閱網址。

    school：all｜nthu｜nycu。可再加「一個」篩選維度：category（類型）、campus（校區）
    或 organizer_type（official｜department｜club｜external），三者擇一。
    """
    if school not in ("all", "nthu", "nycu"):
        raise ValueError("school 需為 all｜nthu｜nycu")
    dims = [d for d in (category, campus, organizer_type) if d]
    if len(dims) > 1:
        raise ValueError("訂閱組合一次只能加一個維度（category／campus／organizer_type 擇一）")
    if category:
        dim = f"cat-{CAT_SLUG[_norm_category(category)]}"
    elif campus:
        if campus not in ("nthu-main", "nthu-nanda", "nycu-guangfu", "nycu-boai", "nycu-yangming", "online", "other"):
            raise ValueError(f"未知的校區代碼 {campus!r}，見 get_site_info 的 labels.campus")
        dim = f"campus-{campus}"
    elif organizer_type:
        if organizer_type not in ORG_SLUG:
            raise ValueError("organizer_type 需為 official｜department｜club｜external")
        dim = f"org-{ORG_SLUG[organizer_type]}"
    else:
        dim = None

    stem = f"feeds/c/{school}-{dim}" if dim else f"feeds/{school}"
    return {
        "ics": f"{BASE_URL}/{stem}.ics",
        "rss": f"{BASE_URL}/{stem}.xml",
        "how_to": "行事曆訂閱：Google Calendar「透過網址新增日曆」或 Apple 行事曆「新增訂閱行事曆」貼上 ics 網址",
        "telegram": "https://t.me/chumei_events",
        "subscribe_page": f"{BASE_URL}/subscribe/",
    }


# 公開唯讀服務、經 Caddy 反代對外 — 關掉 SDK 預設只允許 127.0.0.1 的 Host 檢查
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

app = mcp.streamable_http_app(
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
