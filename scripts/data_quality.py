"""Evidence-aware public review queue; never infer missing facts from absence."""
from collections import Counter
from datetime import datetime
import html
import json
import re
from urllib.parse import urlencode, urlparse

from chumei_lib import TZ_TAIPEI
from event_time import event_datetime, event_has_not_ended

UNKNOWN_VENUE = re.compile(r"未公布|未公告|未定|待定|另行通知|待確認|^TBA$|^TBD$", re.I)
REVIEW_STATES = {
    "source_not_provided": "已核對來源：原公告未提供",
    "not_extracted": "已核對來源：尚未正確擷取",
    "geocoding_failed": "已核對場地：定位失敗",
}
FIELDS = {"venue", "geo", "registration_url", "category", "time", "extraction"}


def public_url(value):
    try:
        parsed = urlparse(value or "")
        return value if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username else None
    except ValueError:
        return None


def missing_venue(event):
    venue = (event.get("venue") or "").strip()
    return not venue or bool(UNKNOWN_VENUE.search(venue))


def apply_quality_reviews(events, rows):
    by_id = {e["id"]: e for e in events}
    for row in rows:
        event = by_id.get(row.get("event_id"))
        field, status = row.get("field"), row.get("status")
        evidence = public_url(row.get("evidence_url"))
        # A conclusion without a supporting public source must remain unverified.
        if event is not None and field in FIELDS and status in REVIEW_STATES and evidence:
            event.setdefault("data_quality_review", {})[field] = {
                "status": status, "evidence_url": evidence, "note": (row.get("note") or "")[:500],
            }


def event_quality_issues(event):
    issues = []

    def add(field, code, message):
        review = (event.get("data_quality_review") or {}).get(field) or {}
        status = review.get("status")
        if status in REVIEW_STATES and public_url(review.get("evidence_url")):
            reason = REVIEW_STATES[status]
        else:
            status = "unverified"
            reason = "來源尚未核對，無法判斷原文未提供或尚未擷取"
        issues.append({"field": field, "code": code, "message": message,
                       "review_status": status, "reason": reason,
                       **({"evidence_url": review["evidence_url"], "note": review.get("note", "")} if status != "unverified" else {})})

    if event.get("campus") != "online":
        if missing_venue(event):
            add("venue", "missing_venue", "場地尚未確認，請先查看原公告")
        geo = event.get("geo") or {}
        if not geo:
            add("geo", "missing_geo", "沒有可用定位；有場地者需核對地址或補入場館表")
        elif geo.get("approximate"):
            add("geo", "approximate_geo", "地圖僅為約略位置，不能作為實際會場")
    if (event.get("registration_required") is True or event.get("reg") == "required") and not public_url(event.get("registration_url")):
        add("registration_url", "missing_registration_url", "需報名但沒有可用報名連結，請查看原公告或洽主辦")
    extraction = event.get("extraction") or {}
    normalization = event.get("category_normalization") or {}
    if normalization.get("recognized") is False or extraction.get("category_review_reason") == "unknown_category":
        add("category", "unknown_category", f'原分類「{event.get("category_original") or normalization.get("original") or "未知"}」尚待人工確認')
    reason = extraction.get("review_reason") or ""
    if extraction.get("unverified_times") or "timezone" in reason or not event_datetime(event.get("start_at")):
        add("time", "unverified_time", "日期／來源時區尚未確認，不提供未確認時間的行事曆")
    elif extraction.get("needs_review") and not any(x["field"] == "category" for x in issues):
        add("extraction", "extraction_review", "活動擷取結果待人工核對")
    return issues


def report_url(event, issues):
    source = public_url((event.get("source") or {}).get("url")) or "未提供"
    body = (f'活動 ID：{event["id"]}\n來源：{source}\n'
            f'待確認：{"、".join(i["message"] for i in issues)}\n\n'
            '正確資訊與公開證據連結：\n\n請勿填入私人聯絡方式或報名者資料。')
    return "https://github.com/skyhong2002/chumei/issues/new?" + urlencode({"title": f'[資料更正] {event.get("title") or event["id"]}', "body": body})


def build_quality_report(events, generated_at, now=None):
    now = now or datetime.now(TZ_TAIPEI)
    active = [e for e in events if event_has_not_ended(e, now)]
    undated = [e for e in events if not event_datetime(e.get("start_at"))]
    historical_review = [e for e in events if event_datetime(e.get("start_at"))
                         and not event_has_not_ended(e, now)
                         and ((e.get("category_normalization") or {}).get("recognized") is False
                              or (e.get("extraction") or {}).get("category_review_reason") == "unknown_category")]
    rows = []
    counts = Counter()
    for event in active + undated + historical_review:
        issues = event_quality_issues(event)
        if not issues:
            continue
        counts.update(i["code"] for i in issues)
        start = event_datetime(event.get("start_at"))
        priority = ("undated" if start is None else "historical_review" if not event_has_not_ended(event, now)
                    else "next_7_days" if (start - now).total_seconds() <= 7 * 86400 else "later")
        rows.append({"id": event["id"], "title": event.get("title") or "未命名活動",
                     "start_at": event.get("start_at"), "priority": priority,
                     "event_url": f'/event/{event["id"]}/' if start else None,
                     "source_url": public_url((event.get("source") or {}).get("url")),
                     "source_timezone": event.get("source_timezone"),
                     "unverified_times": (event.get("extraction") or {}).get("unverified_times"),
                     "issues": issues, "report_url": report_url(event, issues)})
    rows.sort(key=lambda r: ({"next_7_days": 0, "undated": 1, "later": 2, "historical_review": 3}[r["priority"]],
                             event_datetime(r["start_at"]) or now, r["id"]))
    physical = [e for e in active if e.get("campus") != "online"]
    required = [e for e in active if e.get("registration_required") is True or e.get("reg") == "required"]
    return {"generated_at": generated_at, "scope": "ongoing_upcoming_undated_and_historical_category_review",
            "counts": {"active_events": len(active), "undated_events": len(undated), "historical_category_reviews": len(historical_review), "queued_events": len(rows), "issues": dict(counts)},
            "coverage": {
                "venue": {"available": sum(not missing_venue(e) for e in physical), "total": len(physical)},
                "exact_location": {"available": sum(bool(e.get("geo")) and not e["geo"].get("approximate") for e in physical), "total": len(physical)},
                "registration_link": {"available": sum(bool(public_url(e.get("registration_url"))) for e in required), "total": len(required)},
            }, "items": rows}


def render_quality_page(report, page_shell):
    esc = lambda value: html.escape(str(value or ""), quote=True)
    labels = {"venue": "場地", "exact_location": "精確定位", "registration_link": "需報名活動的連結"}
    metrics = "；".join(f'{labels[k]} {v["available"]} / {v["total"]}' for k, v in report["coverage"].items())
    rows = []
    for row in report["items"]:
        issues = "".join('<li>' + esc(i["message"]) + ' — ' + esc(i["reason"]) +
                         (f'（{esc(i.get("note"))}）' if i.get("note") else '') +
                         (f' <a href="{esc(i["evidence_url"])}" rel="noopener">核對證據</a>' if i.get("evidence_url") else '') + '</li>' for i in row["issues"])
        title = esc(row["title"])
        if row["event_url"]:
            title = f'<a href="{esc(row["event_url"])}">{title}</a>'
        links = f'<a href="{esc(row["source_url"])}" rel="noopener">查看原公告</a> · ' if row["source_url"] else '尚無來源連結 · '
        rows.append(f'<li id="{esc(row["id"])}"><h2>{title}</h2><p>{esc(row["start_at"] or "日期／時區待確認（未加入活動行事曆）")}</p><ul>{issues}</ul><p>{links}<a href="{esc(row["report_url"])}" rel="noopener">回報更正（GitHub）</a></p></li>')
    content = f'''<section class="quality-page"><h1>活動資料待確認清單</h1>
<p>快照：{esc(report["generated_at"])}。優先列出進行中與七日內活動，其次是日期待確認與較晚的活動，最後保留歷史活動的未知分類。缺值不代表原公告未提供；「已核對」結論必須有公開證據。線上活動不計實體場地與定位，約略座標不計精確定位。</p>
<p>{esc(metrics)}。分母為尚未結束活動；連結可用率只檢查是否有 HTTP(S) 網址，未聲稱外站報名仍開放。</p>
<p>共 {report["counts"]["queued_events"]} 場待核對。<a href="/api/data-quality.json">下載資料品質 JSON</a> · <a href="/status/">資料來源狀態</a> · <a href="/submit/">提供新的活動公告</a></p>
<p>回報更正時請附正確資訊與公開證據；維護者核對後修正資料，下次建站即更新清單。未確認地點、費用或時間不會自動補猜。</p>
<ol>{''.join(rows) or '<li>目前沒有待確認活動。</li>'}</ol></section>
<style>.quality-page{{max-width:900px;margin:auto}}.quality-page a{{text-decoration:underline;text-underline-offset:.18em}}.quality-page>ol>li{{margin:2rem 0;border-top:1px solid #ddd;padding-top:1rem}}.quality-page h2{{font-size:1.15rem}}.quality-page li{{overflow-wrap:anywhere}}.quality-page a:focus-visible{{outline:3px solid currentColor;outline-offset:3px}}</style>'''
    return page_shell("活動資料待確認清單｜竹梅活動觀測站", "核對近期活動的場地、定位、報名連結、分類與日期。", content, canonical="https://chumei.observe.tw/quality/")


def write_quality_report(site, report, page_shell):
    (site / "api").mkdir(parents=True, exist_ok=True)
    (site / "quality").mkdir(parents=True, exist_ok=True)
    (site / "api/data-quality.json").write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (site / "quality/index.html").write_text(render_quality_page(report, page_shell), encoding="utf-8")
