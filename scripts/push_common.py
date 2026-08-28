"""Web Push 共用層：訂閱儲存、偏好比對、VAPID 金鑰、實際發送。

訂閱存 state/push/subscriptions.json（跨行程以 flock 保護——push_server 寫入、
publish_push 讀取兼清理失效 endpoint）。每筆訂閱帶偏好（prefs）：

偏好是「規則清單」——任一條規則命中就推播（規則之間 OR）：

  orgs:  [{"id": 47, "name": "陽明交大藝文中心"}, ...]
         追蹤的單位，自成一條規則：這些單位的活動一律通知。
  rules: [{ schools, campuses, orgTypes, reg, fee, cats, keywords,
            not: { cats, keywords, reg, fee, campuses, orgTypes } }, ...]

單條規則內：**各維度之間 AND，同維度內 OR**，留空＝該維度不限；
`not` 內任一命中就否決整條規則。例：
  (學校=nycu) AND (類型∈{表演,展覽}) AND NOT(費用=付費)

orgs 與 rules 都空＝所有新活動都通知。舊版平鋪格式會自動轉成單一規則。

訂閱可綁竹梅帳號（record["user_id"]，由 push_server 用 session cookie 解析
state/auth.sqlite3）。綁定後：
  - 發送時 orgs 以帳號目前的追蹤清單為準（任一裝置按鈴鐺，所有裝置都生效）
  - mode／rules 儲存時同步到同帳號的其他裝置
  - 「我要去」的活動前一天會收到提醒（publish_push）
"""

import fcntl
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from chumei_lib import ROOT, load_env, now_iso

PUSH_DIR = ROOT / "state" / "push"
SUBS_PATH = PUSH_DIR / "subscriptions.json"
LOCK_PATH = PUSH_DIR / "subscriptions.lock"
VAPID_KEY_PATH = PUSH_DIR / "vapid_private.pem"
SOURCES_PATH = ROOT / "site" / "data" / "sources.json"
VAPID_SUB = "mailto:chumei@observe.tw"
AUTH_DB_PATH = ROOT / "state" / "auth.sqlite3"
SESSION_COOKIE = "chumei_session"


# ---- 帳號（唯讀查 auth_server 的 SQLite） ----

def _auth_db_path():
    return Path(load_env().get("CHUMEI_AUTH_DATABASE") or AUTH_DB_PATH)


def _auth_query(sql, params=()):
    path = _auth_db_path()
    if not path.exists():
        return []
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def session_user_id(raw_token):
    """session cookie → user_id；無效／過期回 None。"""
    if not raw_token:
        return None
    token_hash = hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()
    rows = _auth_query(
        "SELECT user_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
        (token_hash, int(time.time())),
    )
    return rows[0]["user_id"] if rows else None


def account_follows():
    """{user_id: [{"id", "name"}]} — 有追蹤紀錄的帳號。"""
    out = {}
    for row in _auth_query("SELECT user_id, org_id, org_name FROM user_org_follows ORDER BY created_at"):
        out.setdefault(row["user_id"], []).append({"id": row["org_id"], "name": row["org_name"]})
    return out


def account_going():
    """{user_id: [event_id, ...]} — 「我要去」標記。"""
    out = {}
    for row in _auth_query("SELECT user_id, event_id FROM user_event_going ORDER BY created_at"):
        out.setdefault(row["user_id"], []).append(row["event_id"])
    return out


def effective_prefs(record, follows):
    """綁帳號的訂閱：追蹤單位以帳號現況為準（多裝置一致）；未綁維持裝置偏好。"""
    prefs = record.get("prefs") or {}
    user_id = record.get("user_id")
    if user_id and user_id in follows:
        prefs = dict(prefs)
        prefs["orgs"] = follows[user_id]
    return prefs


# ---- 儲存 ----

@contextmanager
def subs_lock():
    PUSH_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def sub_key(endpoint):
    return hashlib.sha256(str(endpoint).encode()).hexdigest()[:24]


def load_subs():
    if not SUBS_PATH.exists():
        return {"version": 1, "subs": {}}
    data = json.loads(SUBS_PATH.read_text())
    data.setdefault("subs", {})
    return data


def save_subs(data):
    PUSH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SUBS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(SUBS_PATH)


CAMPUSES = ("nthu-main", "nthu-nanda", "nycu-guangfu", "nycu-boai", "nycu-yangming", "online", "other")
ORG_TYPES = ("official", "department", "club", "external")
REG_VALUES = ("required", "free")
FEE_VALUES = ("free", "paid")


def _pick(raw, key, allowed):
    """留下合法值；全選＝不限（回空 list）。"""
    seen, out = set(), []
    for v in (raw.get(key) or []):
        if v in allowed and v not in seen:
            seen.add(v)
            out.append(v)
    return [] if len(out) == len(allowed) else out


RULE_DIMS = {
    "schools": ("nthu", "nycu"),
    "campuses": CAMPUSES,
    "orgTypes": ORG_TYPES,
    "reg": REG_VALUES,
    "fee": FEE_VALUES,
}
NOT_DIMS = ("cats", "keywords", "reg", "fee", "campuses", "orgTypes")


def _strings(values, limit=30, maxlen=40):
    out, seen = [], set()
    for v in (values or []):
        s = str(v).strip()[:maxlen]
        if s and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _orgs(values):
    out = []
    for org in (values or [])[:200]:
        if isinstance(org, dict) and org.get("id") is not None:
            out.append({"id": org["id"], "name": str(org.get("name") or "")[:80]})
    return out


def normalize_rule(raw):
    raw = raw or {}
    rule = {k: _pick(raw, k, allowed) for k, allowed in RULE_DIMS.items()}
    rule["cats"] = _strings(raw.get("cats"), maxlen=20)
    rule["keywords"] = _strings(raw.get("keywords"))
    raw_not = raw.get("not") or {}
    rule["not"] = {
        "cats": _strings(raw_not.get("cats"), maxlen=20),
        "keywords": _strings(raw_not.get("keywords")),
        "reg": _pick(raw_not, "reg", REG_VALUES),
        "fee": _pick(raw_not, "fee", FEE_VALUES),
        "campuses": _pick(raw_not, "campuses", CAMPUSES),
        "orgTypes": _pick(raw_not, "orgTypes", ORG_TYPES),
    }
    rule["name"] = str(raw.get("name") or "")[:40]
    return rule


def rule_is_empty(rule):
    return not any(rule.get(k) for k in list(RULE_DIMS) + ["cats", "keywords"])


def normalize_prefs(raw):
    raw = raw or {}
    rules = [normalize_rule(r) for r in (raw.get("rules") or [])][:20]
    if not rules:
        # 舊版平鋪格式（schools/cats/keywords… 直接放在頂層）→ 轉成單一規則
        legacy = normalize_rule(raw)
        if not rule_is_empty(legacy):
            rules = [legacy]
    orgs = _orgs(raw.get("orgs"))
    mode = raw.get("mode")
    if mode not in {"all", "following", "custom"}:
        # 舊訂閱沒有 mode：依原本條件推導，維持既有通知範圍。
        mode = "custom" if rules else ("following" if orgs else "all")
    return {"mode": mode, "orgs": orgs, "rules": rules}


def upsert_sub(subscription, prefs=None, migrate_from=None, ua="", user_id=None):
    """新增/更新訂閱；migrate_from 時把舊 endpoint 的偏好搬到新 endpoint。

    user_id：字串＝綁定該帳號；""＝明確解除（瀏覽器已登出）；None＝不動。
    綁帳號且帶 prefs 時，mode／rules 會同步到同帳號的其他裝置。
    """
    endpoint = subscription["endpoint"]
    with subs_lock():
        data = load_subs()
        record = data["subs"].get(sub_key(endpoint))
        if migrate_from:
            old = data["subs"].pop(sub_key(migrate_from), None)
            if old and prefs is None and record is None:
                record = old
        if record is None:
            record = {"created_at": now_iso(), "prefs": normalize_prefs(prefs)}
        if prefs is not None:
            record["prefs"] = normalize_prefs(prefs)
        record["sub"] = {"endpoint": endpoint, "keys": subscription.get("keys") or {}}
        record["updated_at"] = now_iso()
        if ua:
            record["ua"] = str(ua)[:200]
        if user_id is not None:
            if user_id:
                record["user_id"] = str(user_id)
            else:
                record.pop("user_id", None)
        key = sub_key(endpoint)
        data["subs"][key] = record
        if record.get("user_id") and prefs is not None:
            for other_key, other in data["subs"].items():
                if other_key != key and other.get("user_id") == record["user_id"]:
                    other["prefs"] = dict(other.get("prefs") or {},
                                          mode=record["prefs"]["mode"], rules=record["prefs"]["rules"])
        save_subs(data)
        return record


def remove_sub(endpoint):
    with subs_lock():
        data = load_subs()
        removed = data["subs"].pop(sub_key(endpoint), None)
        if removed:
            save_subs(data)
        return removed is not None


def get_sub(endpoint):
    return load_subs()["subs"].get(sub_key(endpoint))


def subscription_stats():
    """Return anonymous aggregate counters for the public notification page."""
    records = list(load_subs().get("subs", {}).values())
    with_orgs = 0
    with_rules = 0
    linked = 0
    for record in records:
        prefs = record.get("prefs") or {}
        if prefs.get("orgs"):
            with_orgs += 1
        if prefs.get("rules"):
            with_rules += 1
        if record.get("user_id"):
            linked += 1
    return {
        "devices": len(records),
        "withOrganizations": with_orgs,
        "withRules": with_rules,
        "linked": linked,
    }


# ---- 偏好比對 ----

def load_org_sids(sources_path=SOURCES_PATH):
    """名錄 id → source_id 集合；發送時解析，社團新增帳號不用重訂閱。"""
    try:
        entries = json.loads(Path(sources_path).read_text()).get("entries") or []
    except (OSError, json.JSONDecodeError):
        return {}
    return {e["id"]: set(e.get("sids") or []) for e in entries if e.get("id") is not None}


def _haystack(event):
    return " ".join(
        str(event.get(field) or "")
        for field in ("title", "summary", "description", "organizer", "venue")
    ).casefold()


def _org_hit(event, orgs, org_sids):
    source_id = str((event.get("source") or {}).get("source_id") or "")
    if not source_id:
        return False
    return any(source_id in org_sids.get(org["id"], ()) for org in orgs)


def _event_values(event):
    return {
        "schools": ["nthu", "nycu"] if event.get("school") == "both" else [event.get("school")],
        "campuses": [event.get("campus") or "other"],
        "orgTypes": [event.get("organizer_type") or ""],
        "reg": [event.get("reg") or ""],
        "fee": [event.get("fee") or ""],
        "cats": [event.get("category") or "其他"],
    }


def rule_matches(event, rule, org_sids=None):
    """單條規則：各維度 AND、同維度內 OR；not 任一命中就否決。"""
    vals = _event_values(event)
    for dim in list(RULE_DIMS) + ["cats"]:
        want = rule.get(dim) or []
        if want and not any(v in want for v in vals[dim]):
            return False
    keywords = rule.get("keywords") or []
    if keywords:
        hay = _haystack(event)
        if not any(k.casefold() in hay for k in keywords):
            return False
    veto = rule.get("not") or {}
    for dim in ("campuses", "orgTypes", "reg", "fee", "cats"):
        bad = veto.get(dim) or []
        if bad and any(v in bad for v in vals[dim]):
            return False
    bad_kw = veto.get("keywords") or []
    if bad_kw:
        hay = _haystack(event)
        if any(k.casefold() in hay for k in bad_kw):
            return False
    return True


def event_matches(event, prefs, org_sids):
    """依通知模式判斷；custom 為追蹤單位或任一規則命中。"""
    prefs = prefs or {}
    orgs = prefs.get("orgs") or []
    rules = prefs.get("rules") or []
    mode = prefs.get("mode")
    if mode == "all" or mode not in {"following", "custom"}:
        return True
    org_hit = bool(orgs and _org_hit(event, orgs, org_sids or {}))
    if mode == "following":
        return org_hit
    if org_hit:
        return True
    return any(rule_matches(event, r, org_sids) for r in rules)


# ---- VAPID ----

def ensure_vapid():
    """回傳 (Vapid 實例, base64url 公鑰)；金鑰不存在就現場產生。"""
    from py_vapid import Vapid, b64urlencode
    from cryptography.hazmat.primitives import serialization

    PUSH_DIR.mkdir(parents=True, exist_ok=True)
    if not VAPID_KEY_PATH.exists():
        vapid = Vapid()
        vapid.generate_keys()
        vapid.save_key(str(VAPID_KEY_PATH))
        VAPID_KEY_PATH.chmod(0o600)
    vapid = Vapid.from_file(str(VAPID_KEY_PATH))
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return vapid, b64urlencode(raw)


# ---- 發送 ----

class PushGone(Exception):
    """endpoint 已失效（404/410），呼叫端應移除訂閱。"""


def send_push(record, payload, ttl=43200):
    """對單一訂閱發一則通知。payload 是 dict（sw.js 以 JSON 解讀）。"""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info=record["sub"],
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=str(VAPID_KEY_PATH),
            vapid_claims={"sub": VAPID_SUB},
            ttl=ttl,
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            raise PushGone(record["sub"]["endpoint"]) from exc
        raise


def prune_endpoint(endpoint):
    try:
        remove_sub(endpoint)
    except OSError:
        pass


def push_enabled():
    return load_env().get("CHUMEI_PUSH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
