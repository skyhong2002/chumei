"""Source registry and durable fetch telemetry for the public status page."""

from __future__ import annotations

import fcntl
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from apify_pool import pool_status, recommended_interval_hours
from chumei_lib import INBOX_DIR, ROOT, read_sources_csv


LEDGER_PATH = ROOT / "state" / "source_fetch_ledger.json"
USAGE_PATH = ROOT / "state" / "api_usage.jsonl"
HISTORY_LIMIT = 20


def _active(row: dict) -> bool:
    return row.get("active", "true").strip().lower() not in {"false", "link"}


def _slug(value: str) -> str:
    raw = value.strip()
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if parts and parts[0].lower() == "profile.php":
            raw = parse_qs(parsed.query).get("id", [""])[0]
        elif parts and parts[0].lower() == "groups" and len(parts) > 1:
            raw = "groups-" + parts[1]
        elif parts and parts[0].lower() in {"people", "p", "pages"} and len(parts) > 1:
            raw = parts[-1]
        elif parts:
            raw = parts[0]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw.strip("/@ ")).lower().strip("_") or "facebook_page"


def source_registry(*, facebook_interval_hours: float = 168.0) -> list[dict]:
    """Return every independently scheduled source, with stable public ids."""
    sources: list[dict] = []
    for row in read_sources_csv("ig_accounts.csv"):
        if not _active(row):
            continue
        username = row["username"].strip().lstrip("@")
        common = {
            "name": row.get("name") or username,
            "username": username,
            "platform": "Instagram",
            "school": row.get("school") or "other",
        }
        sources.append({
            **common, "id": f"instagram:{username}", "sourceId": f"ig_{username}",
            "kind": "instagram_profile", "backend": "Instagram public",
            "kindLabel": "貼文",
            "targetIntervalHours": 168.0,
        })
        sources.append({
            **common, "id": f"story:{username}", "sourceId": f"ig_{username}",
            "kind": "instagram_story", "backend": "Apify Stories",
            "kindLabel": "限時動態",
            "targetIntervalHours": 168.0,
        })
    for row in read_sources_csv("fb_pages.csv"):
        if not _active(row):
            continue
        page = row["page"].strip()
        slug = _slug(page)
        sources.append({
            "id": f"facebook:{slug}", "sourceId": f"fb_{slug}",
            "name": row.get("name") or slug, "username": slug,
            "platform": "Facebook", "kind": "facebook", "backend": "Apify",
            "kindLabel": "粉專貼文",
            "school": row.get("school") or "other", "targetIntervalHours": facebook_interval_hours,
        })
    for row in read_sources_csv("social_accounts.csv"):
        if not _active(row) or row.get("platform") not in {"threads", "x"}:
            continue
        platform = row["platform"].strip()
        username = row["username"].strip().lstrip("@")
        sources.append({
            "id": f"{platform}:{username}", "sourceId": f"{platform}_{username}",
            "name": row.get("name") or username, "username": username,
            "platform": "Threads" if platform == "threads" else "X",
            "kind": platform, "backend": "RSSHub",
            "kindLabel": "公開貼文",
            "school": row.get("school") or "other", "targetIntervalHours": 20.0,
        })
    for row in read_sources_csv("bulletin_sources.csv"):
        source_id = row.get("source_id", "").strip()
        kind = row.get("type", "").strip()
        if not source_id or kind not in {"infonews_category", "nycu_open_data", "rpage_list", "wp_api", "api"}:
            continue
        backend = {
            "infonews_category": "NYCU InfoNews",
            "nycu_open_data": "NYCU Open Data",
            "rpage_list": "NTHU RPage",
            "wp_api": "WordPress API",
            "api": "JSON API",
        }[kind]
        sources.append({
            "id": f"bulletin:{source_id}", "sourceId": source_id,
            "name": row.get("name") or source_id, "username": source_id,
            "platform": "校園公告", "kind": kind, "backend": backend,
            "kindLabel": "公告",
            "school": row.get("school") or "other", "targetIntervalHours": 3.0,
        })
    # NYCU LIFE is a first-class API fetch but is not duplicated in bulletin_sources.csv.
    if not any(s["sourceId"] == "nycu_life_api" for s in sources):
        sources.append({
            "id": "bulletin:nycu_life_api", "sourceId": "nycu_life_api",
            "name": "NYCU LIFE 活動 API", "username": "nycu_life_api",
            "platform": "校園公告", "kind": "nycu_life", "backend": "JSON API",
            "kindLabel": "活動 API",
            "school": "nycu", "targetIntervalHours": 3.0,
        })
    return sources


@contextmanager
def _locked_json(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = json.loads(path.read_text()) if path.exists() else {"version": 1, "sources": {}}
        except (OSError, ValueError):
            data = {"version": 1, "sources": {}}
        yield data
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def record_fetch(source_key: str, *, backend: str, ok: bool, items: int = 0,
                 error: object = "", attempted_at: float | None = None) -> None:
    ts = float(attempted_at or time.time())
    with _locked_json(LEDGER_PATH) as data:
        entry = data.setdefault("sources", {}).setdefault(source_key, {})
        entry["lastAttempt"] = ts
        entry["backend"] = backend
        entry["lastItems"] = max(0, int(items or 0))
        if ok:
            entry["lastSuccess"] = ts
            entry["lastError"] = ""
            entry["consecutiveFailures"] = 0
            history = [float(value) for value in entry.get("successHistory", [])]
            if not history or abs(history[-1] - ts) > 1:
                history.append(ts)
            entry["successHistory"] = history[-HISTORY_LIMIT:]
        else:
            entry["lastError"] = str(error)[:300]
            entry["consecutiveFailures"] = int(entry.get("consecutiveFailures", 0)) + 1


def record_api_call(service: str, *, operation: str, source_count: int = 1,
                    request_count: int = 1, ok: bool = True,
                    cost_usd: float | None = None) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": time.time(), "service": service, "operation": operation,
        "sourceCount": max(0, int(source_count)),
        "requestCount": max(0, int(request_count)), "ok": bool(ok),
    }
    if cost_usd is not None:
        row["costUsd"] = float(cost_usd)
    with USAGE_PATH.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_ledger() -> dict:
    try:
        return json.loads(LEDGER_PATH.read_text()).get("sources", {})
    except (OSError, ValueError, TypeError):
        return {}


def _inbox_last_success() -> dict[str, float]:
    latest: dict[str, float] = {}
    if not INBOX_DIR.exists():
        return latest
    for path in INBOX_DIR.glob("*.jsonl"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            try:
                row = json.loads(raw)
                value = datetime.fromisoformat(str(row.get("fetched_at", "")).replace("Z", "+00:00")).timestamp()
                source_id = str(row.get("source_id") or "")
                if source_id:
                    latest[source_id] = max(latest.get(source_id, 0), value)
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    return latest


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return {}


def _average_interval(history: list) -> float | None:
    values = sorted({float(value) for value in history if isinstance(value, (int, float))})
    if len(values) < 2:
        return None
    return sum(b - a for a, b in zip(values, values[1:])) / (len(values) - 1) / 3600


def api_usage_summary(now: float | None = None) -> dict:
    now = float(now or time.time())
    rows: list[dict] = []
    try:
        for line in USAGE_PATH.read_text(encoding="utf-8").splitlines()[-10000:]:
            rows.append(json.loads(line))
    except (OSError, ValueError):
        pass
    out = {}
    for service in ("Instagram public web", "RSSHub", "Instaloader", "Apify"):
        selected = [r for r in rows if r.get("service") == service]
        out[service] = {
            "requests24h": sum(int(r.get("requestCount", 0)) for r in selected if r.get("ts", 0) >= now - 86400),
            "requests30d": sum(int(r.get("requestCount", 0)) for r in selected if r.get("ts", 0) >= now - 30 * 86400),
            "sources24h": sum(int(r.get("sourceCount", 0)) for r in selected if r.get("ts", 0) >= now - 86400),
            "errors24h": sum(1 for r in selected if r.get("ts", 0) >= now - 86400 and not r.get("ok", True)),
            "cost30dUsd": round(sum(float(r.get("costUsd", 0)) for r in selected if r.get("ts", 0) >= now - 30 * 86400), 6),
        }
    return out


def method_summaries(rows: list[dict]) -> list[dict]:
    """Aggregate independently scheduled sources by their public fetch method."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(str(row.get("backend") or "其他"), []).append(row)
    result = []
    for backend, members in groups.items():
        intervals = sorted({float(row["targetIntervalHours"]) for row in members
                            if isinstance(row.get("targetIntervalHours"), (int, float))})
        attempts = [float(row["lastAttempt"]) for row in members
                    if isinstance(row.get("lastAttempt"), (int, float))]
        next_runs = [float(row["nextDue"]) for row in members
                     if isinstance(row.get("nextDue"), (int, float))]
        result.append({
            "backend": backend,
            "sources": len(members),
            "fresh": sum(row.get("status") == "ok" for row in members),
            "due": sum(row.get("status") == "due" for row in members),
            "errors": sum(row.get("status") == "error" for row in members),
            "blocked": sum(bool(row.get("blockedReason")) for row in members),
            "targetIntervalHours": intervals[0] if len(intervals) == 1 else None,
            "targetIntervalsHours": intervals,
            "lastAttempt": max(attempts) if attempts else None,
            "nextDue": min(next_runs) if next_runs else None,
        })
    return sorted(result, key=lambda row: (-row["sources"], row["backend"]))


def detect_incidents(*, now: float, profile_schedule: dict, story_schedule: dict,
                     apify: dict, facebook_interval_hours: float, rows: list[dict]) -> list[dict]:
    """進行中事件：純機器判定（排程冷卻、額度配速），不靠人工開關。"""
    incidents = []
    ig_cd = float(profile_schedule.get("global_cooldown_until") or 0)
    st_cd = float(story_schedule.get("global_cooldown_until") or 0)
    profile_public = any(
        row.get("kind") == "instagram_profile" and row.get("backend") == "Instagram public"
        for row in rows
    )
    # 兩邊同時冷卻或錯誤帶登入失效特徵 → 不是普通限流，是共用 session 死了
    session_dead = (ig_cd > now and st_cd > now) or any(
        marker in str(row.get("lastError") or "").lower()
        for row in rows if str(row.get("kind", "")).startswith("instagram")
        for marker in ("require_login", "not authenticated"))
    session_hint = "錯誤特徵指向共用登入（session）失效，需要人工更新登入後才會恢復。" if session_dead else ""
    if ig_cd > now:
        streak = max(1, int(profile_schedule.get("rate_limit_streak") or 0))
        detail = (
            f"Instagram 拒絕了不登入的公開網頁請求，整批抓取暫停（第 {streak} 次退避）；"
            "這條路徑不會使用任何人的 IG 帳號。"
            if profile_public else
            f"Instagram 拒絕了共用登入的請求，整批抓取暫停（第 {streak} 次退避）；"
            f"期間 IG 貼文與頭貼不會更新。{session_hint}"
        )
        incidents.append({
            "id": "ig-posts-cooldown", "severity": "major", "until": ig_cd,
            "title": "Instagram 貼文抓取暫停中",
            "detail": detail})
    if st_cd > now:
        streak = max(1, int(story_schedule.get("rate_limit_streak") or 0))
        incidents.append({
            "id": "ig-stories-cooldown", "severity": "major", "until": st_cd,
            "title": "Instagram 限時動態抓取暫停中",
            "detail": f"限時動態批次被 Instagram 擋下（第 {streak} 次退避）。{session_hint}"})
    if apify.get("exhausted"):
        incidents.append({
            "id": "fb-quota-exhausted", "severity": "major", "until": apify.get("cycleEnd"),
            "title": "Facebook 粉專抓取暫停中",
            "detail": "Apify 帳號池本期額度已用完，Facebook 貼文暫停更新到額度重置。"})
    elif facebook_interval_hours >= 48:
        remaining = float(apify.get("remainingUsd") or 0)
        incidents.append({
            "id": "fb-slow-pacing", "severity": "minor", "until": None,
            "title": "Facebook 更新頻率降低",
            "detail": f"為了讓剩餘 Apify 額度（US${remaining:.2f}）撐到重置日，"
                      f"每個粉專約每 {facebook_interval_hours / 24:.1f} 天輪抓一次（每輪滾動抓少量頁面）。"})
    return incidents


def apify_quota(refresh: bool = True) -> dict:
    """Return sanitized aggregate and per-account limits; tokens never leave the server."""
    return pool_status(refresh=refresh)


def build_status_payload(*, refresh_apify: bool = True, now: float | None = None) -> dict:
    now = float(now or time.time())
    ledger = load_ledger()
    inbox_latest = _inbox_last_success()
    pipeline = _read_json(ROOT / "state" / "pipeline.json")
    profile_schedule = _read_json(ROOT / "state" / "instagram_public_profile_schedule.json")
    story_schedule = _read_json(ROOT / "state" / "instagram_apify_stories_schedule.json")
    facebook_schedule = _read_json(ROOT / "state" / "facebook_schedule.json")
    social_schedule = _read_json(ROOT / "state" / "social_schedule.json")
    apify = apify_quota(refresh=refresh_apify)
    facebook_count = sum(
        row.get("active", "true").strip().lower() not in {"false", "link"}
        for row in read_sources_csv("fb_pages.csv")
    )
    facebook_interval = recommended_interval_hours(apify, source_count=facebook_count, now=now)
    rows = []
    for source in source_registry(facebook_interval_hours=facebook_interval):
        entry = ledger.get(source["id"], {})
        last_attempt = entry.get("lastAttempt")
        # Profile/feed inbox timestamps cannot prove that the independent story
        # endpoint was queried.  Stories only gain an exact success time from
        # their own telemetry going forward.
        last_success = entry.get("lastSuccess")
        if not last_success and source["kind"] != "instagram_story":
            last_success = inbox_latest.get(source["sourceId"])
        next_due = None
        instagram_cooldown = 0.0
        if source["kind"] in {"instagram_profile", "instagram_story"}:
            schedule = profile_schedule if source["kind"] == "instagram_profile" else story_schedule
            account = (schedule.get("accounts") or {}).get(source["username"], {})
            last_attempt = account.get("last_attempt") or last_attempt
            next_due = account.get("next_eligible")
            if account.get("interval_hours"):
                source["targetIntervalHours"] = float(account["interval_hours"])
            cooldown = float(schedule.get("global_cooldown_until") or 0)
            instagram_cooldown = cooldown
            if cooldown > (next_due or 0):
                next_due = cooldown
        elif source["kind"] == "facebook":
            account = (facebook_schedule.get("accounts") or {}).get(source["username"], {})
            last_attempt = account.get("last_attempt") or last_attempt or pipeline.get("last_fb_run")
            next_due = account.get("next_eligible") or (
                (float(last_attempt) + facebook_interval * 3600) if last_attempt else now)
        elif source["kind"] in {"threads", "x"}:
            account = (social_schedule.get("accounts") or {}).get(f"{source['kind']}:{source['username']}", {})
            last_attempt = account.get("last_attempt") or last_attempt or pipeline.get("last_social_run")
            next_due = account.get("next_eligible") or (
                (float(last_attempt) + 20 * 3600) if last_attempt else now)
        else:
            try:
                pipeline_last = datetime.fromisoformat(str(pipeline.get("last_run", "")).replace("Z", "+00:00")).timestamp()
            except ValueError:
                pipeline_last = 0
            last_attempt = last_attempt or pipeline_last or None
            next_due = (float(last_attempt) + source["targetIntervalHours"] * 3600) if last_attempt else now
        if next_due is None:
            next_due = (float(last_success) + source["targetIntervalHours"] * 3600) if last_success else now
        error = str(entry.get("lastError") or "")
        blocked = ""
        if error and instagram_cooldown > now:
            blocked = "Instagram 公開來源冷卻中"
        elif source["kind"] == "facebook" and apify.get("exhausted"):
            blocked = "Apify 本期額度已用完"
        state = "blocked" if blocked else ("error" if error else ("due" if next_due <= now else "ok"))
        rows.append({
            **source, "lastAttempt": last_attempt, "lastSuccess": last_success,
            "nextDue": next_due, "averageIntervalHours": _average_interval(entry.get("successHistory", [])),
            "lastItems": int(entry.get("lastItems") or 0), "lastError": error,
            "consecutiveFailures": int(entry.get("consecutiveFailures") or 0),
            "status": state, "requestable": True, "blockedReason": blocked,
        })
    counts = {
        "sources": len(rows), "due": sum(r["status"] == "due" for r in rows),
        "errors": sum(r["status"] == "error" for r in rows),
        "blocked": sum(r["status"] == "blocked" for r in rows),
        "fresh": sum(r["status"] == "ok" for r in rows),
    }
    usage = api_usage_summary(now)
    return {
        "generatedAt": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
        "pipeline": {"lastRun": pipeline.get("last_run"), "lastResults": pipeline.get("last_results", {}),
                     "intervalHours": 3.0},
        "counts": counts, "apiUsage": usage, "apify": apify,
        "incidents": detect_incidents(now=now, profile_schedule=profile_schedule,
                                      story_schedule=story_schedule, apify=apify,
                                      facebook_interval_hours=facebook_interval, rows=rows),
        "methods": method_summaries(rows),
        "sources": rows,
    }
