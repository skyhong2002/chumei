"""查詢 bot 共用核心 — LINE 與 Telegram 私訊查活動的解析、搜尋與排版。

唯讀：資料源同 mcp_server（site/api/events.json、site/data/sources.json），
mtime 快取自動重載。平台 adapter（bot_telegram.py / bot_line.py）只負責收發訊息，
把使用者輸入丟進 answer()，拿回平台中立的回覆結構再自行渲染。
"""

import json
import re
from datetime import datetime, timedelta

from chumei_lib import ROOT, TZ_TAIPEI

BASE_URL = "https://chumei.observe.tw"
EVENTS_PATH = ROOT / "site" / "api" / "events.json"
SOURCES_PATH = ROOT / "site" / "data" / "sources.json"
MAX_EVENTS = 8

_CACHE = {}


def _cached_json(path):
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


# ---------- 查詢解析 ----------
# 使用者多半不加空白（「這週末清大演講」），所以用「已知詞彙掃描＋剩餘當關鍵字」：
# 依序抽時間詞、學校/校區詞、類型詞（都是長詞優先），剩下的字串做全文關鍵字。

_WEEK_CJK = "一二三四五六日"


def _day(base, offset=0):
    return (base + timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)


def _time_range(word, now):
    """回 (start, end, 標籤)。end 為排除端點。"""
    today = _day(now)
    monday = today - timedelta(days=today.weekday())
    if word in ("今天", "今日"):
        return today, _day(today, 1), "今天"
    if word in ("明天", "明日"):
        return _day(today, 1), _day(today, 2), "明天"
    if word == "後天":
        return _day(today, 2), _day(today, 3), "後天"
    if word in ("這週末", "這周末", "本週末", "本周末", "週末", "周末"):
        sat = monday + timedelta(days=5)
        start = max(today, sat)
        return start, monday + timedelta(days=7), "這週末"
    if word in ("這週", "這周", "本週", "本周"):
        return today, monday + timedelta(days=7), "這週"
    if word in ("下週", "下周"):
        return monday + timedelta(days=7), monday + timedelta(days=14), "下週"
    if word in ("這個月", "本月"):
        nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        return today, nxt, "這個月"
    return None


_TIME_WORDS = ["這個月", "這週末", "這周末", "本週末", "本周末", "本月",
               "這週", "這周", "本週", "本周", "下週", "下周",
               "週末", "周末", "今天", "今日", "明天", "明日", "後天"]

# 長詞在前：先吃「陽明交大」再輪得到「陽明」「交大」
_PLACE_WORDS = [
    ("陽明交大", ("school", "nycu")),
    ("陽明", ("campus", "nycu-yangming")),
    ("光復", ("campus", "nycu-guangfu")),
    ("博愛", ("campus", "nycu-boai")),
    ("南大", ("campus", "nthu-nanda")),
    ("清華", ("school", "nthu")),
    ("清大", ("school", "nthu")),
    ("交大", ("school", "nycu")),
    ("線上", ("campus", "online")),
]

_CAT_WORDS = [
    ("工作坊", "工作坊"), ("演講", "演講"), ("講座", "演講"), ("表演", "表演"),
    ("展覽", "展覽"), ("比賽", "比賽"), ("競賽", "比賽"), ("營隊", "營隊"),
    ("徵才", "徵才"), ("市集", "市集"), ("運動", "運動"), ("聚會", "聚會"),
]

_HELP_WORDS = {"help", "說明", "幫助", "指令", "?", "？"}


def parse_query(text, now=None):
    """把一句話拆成 {time: (start,end,label)|None, school, campus, category, keyword, help}。"""
    now = now or _now()
    q = {"time": None, "school": None, "campus": None, "category": None,
         "keyword": "", "help": False}
    rest = (text or "").strip()
    if not rest or rest.lower().lstrip("/") in _HELP_WORDS or rest in ("/start", "/help"):
        q["help"] = True
        return q

    for w in _TIME_WORDS:
        if w in rest:
            q["time"] = _time_range(w, now)
            rest = rest.replace(w, " ")
            break
    for w, (kind, value) in _PLACE_WORDS:
        if w in rest:
            q[kind] = value
            rest = rest.replace(w, " ")
            break
    for w, cat in _CAT_WORDS:
        if w in rest:
            q["category"] = cat
            rest = rest.replace(w, " ")
            break
    q["keyword"] = re.sub(r"[\s,，。!！?？的]+", " ", rest).strip()
    return q


# ---------- 搜尋 ----------

def _start_at(e):
    v = e.get("start_at")
    return datetime.fromisoformat(v) if v else None


def _match_keyword(e, keyword):
    hay = " ".join(str(e.get(k) or "") for k in ("title", "summary", "description", "organizer", "venue"))
    return all(t.casefold() in hay.casefold() for t in keyword.split())


def search(q, now=None):
    """依 parse_query 結果過濾活動，開始時間由近到遠。"""
    now = now or _now()
    start, end = (q["time"][0], q["time"][1]) if q["time"] else (now, None)
    hits = []
    for e in load_events()["events"]:
        s = _start_at(e)
        if s is None or s < start or (end and s >= end):
            continue
        if q["school"] and e.get("school") not in (q["school"], "both"):
            continue
        if q["campus"] and e.get("campus") != q["campus"]:
            continue
        if q["category"] and (e.get("category") or "其他") != q["category"]:
            continue
        if q["keyword"] and not _match_keyword(e, q["keyword"]):
            continue
        hits.append(e)
    hits.sort(key=_start_at)
    return hits


def find_org(keyword):
    """關鍵字找不到活動時，試著在名錄裡找單位（回收錄活動數最多者）。"""
    if not keyword:
        return None
    terms = keyword.split()
    hits = [o for o in load_sources()
            if all(t.casefold() in o["name"].casefold() for t in terms)]
    hits.sort(key=lambda o: -(o.get("events") or 0))
    return hits[0] if hits else None


# ---------- 排版（平台中立） ----------

_WD = "一二三四五六日"


def format_when(e):
    s = _start_at(e)
    if s is None:
        return "時間未定"
    day = f"{s.month}/{s.day}（{_WD[s.weekday()]}）"
    return day if e.get("all_day") else f"{day}{s:%H:%M}"


def format_where(e, labels):
    campus = labels["campus"].get(e.get("campus"), "")
    venue = e.get("venue") or ""
    if venue and campus and campus not in ("線上", "其他地點"):
        return f"{campus}・{venue}"
    return venue or campus or "地點未定"


def describe(q):
    """把解析結果讀回人話，當回覆標題：「這週末 清大 演講」。"""
    labels = load_events()["labels"]
    parts = []
    if q["time"]:
        parts.append(q["time"][2])
    if q["school"]:
        parts.append(labels["school"].get(q["school"], q["school"]))
    if q["campus"]:
        parts.append(labels["campus"].get(q["campus"], q["campus"]))
    if q["category"]:
        parts.append(q["category"])
    if q["keyword"]:
        parts.append(f"「{q['keyword']}」")
    return " ".join(parts) or "接下來"


HELP_TEXT = (
    "我是竹梅活動觀測站的查詢小幫手，直接用一句話問我清大×陽明交大的活動：\n"
    "\n"
    "・今天 ─ 今天有什麼活動\n"
    "・這週末 清大 ─ 週末的清大活動\n"
    "・下週 演講 ─ 下週的演講\n"
    "・熱舞社 ─ 某個社團／單位的活動\n"
    "・交大 市集 ─ 地點＋類型隨意組合\n"
    "\n"
    f"完整地圖、日曆與篩選：{BASE_URL}\n"
    f"行事曆／RSS 訂閱：{BASE_URL}/subscribe/"
)


def answer(text, now=None):
    """主入口。回 {kind, title, events, more, org, footer}；kind ∈ help|events|org|empty。"""
    now = now or _now()
    q = parse_query(text, now)
    if q["help"]:
        return {"kind": "help", "text": HELP_TEXT}

    labels = load_events()["labels"]
    hits = search(q, now)
    if hits:
        shown = hits[:MAX_EVENTS]
        return {
            "kind": "events",
            "title": f"{describe(q)}的活動（{len(hits)} 場）",
            "events": [{
                "title": e.get("title") or "（未命名活動）",
                "when": format_when(e),
                "where": format_where(e, labels),
                "organizer": e.get("organizer") or "",
                "url": f"{BASE_URL}/event/{e['id']}/",
            } for e in shown],
            "more": len(hits) - len(shown),
            "footer": f"{BASE_URL}/events/",
        }

    org = find_org(q["keyword"])
    if org:
        return {
            "kind": "org",
            "text": (f"「{org['name']}」目前沒有即將舉行的活動；"
                     f"單位頁有歷年紀錄與社群連結：\n{BASE_URL}/org/{org['id']}/"),
        }
    return {
        "kind": "empty",
        "text": (f"找不到{describe(q)}相關的活動。換個關鍵字試試，"
                 f"或直接逛活動總覽：{BASE_URL}/events/\n（傳「說明」看查詢範例）"),
    }
