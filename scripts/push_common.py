"""Web Push 共用層：訂閱儲存、偏好比對、VAPID 金鑰、實際發送。

訂閱存 state/push/subscriptions.json（跨行程以 flock 保護——push_server 寫入、
publish_push 讀取兼清理失效 endpoint）。每筆訂閱帶偏好（prefs）：

  schools:  ["nthu","nycu"]（空＝不限）
  cats:     ["演講","表演", ...]（中文標籤，同 events.json 的 category）
  orgs:     [{"id": 47, "name": "陽明交大藝文中心"}, ...]（/source/ 名錄 id）
  keywords: ["AI", "半導體", ...]

比對語意：學校先過濾；cats／orgs／keywords 三組之間是 OR——
全部留空＝該校所有新活動都通知，有選就只推命中的。
"""

import fcntl
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

from chumei_lib import ROOT, load_env, now_iso

PUSH_DIR = ROOT / "state" / "push"
SUBS_PATH = PUSH_DIR / "subscriptions.json"
LOCK_PATH = PUSH_DIR / "subscriptions.lock"
VAPID_KEY_PATH = PUSH_DIR / "vapid_private.pem"
SOURCES_PATH = ROOT / "site" / "data" / "sources.json"
VAPID_SUB = "mailto:chumei@observe.tw"


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


def normalize_prefs(raw):
    raw = raw or {}
    schools = [s for s in (raw.get("schools") or []) if s in ("nthu", "nycu")]
    if len(schools) == 2:  # 兩個都選＝不限
        schools = []
    cats = [str(c)[:20] for c in (raw.get("cats") or []) if str(c).strip()][:20]
    orgs = []
    for org in (raw.get("orgs") or [])[:50]:
        if isinstance(org, dict) and org.get("id") is not None:
            orgs.append({"id": org["id"], "name": str(org.get("name") or "")[:80]})
    keywords = [str(k).strip()[:40] for k in (raw.get("keywords") or []) if str(k).strip()][:20]
    return {"schools": schools, "cats": cats, "orgs": orgs, "keywords": keywords}


def upsert_sub(subscription, prefs=None, migrate_from=None, ua=""):
    """新增/更新訂閱；migrate_from 時把舊 endpoint 的偏好搬到新 endpoint。"""
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
        data["subs"][sub_key(endpoint)] = record
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


# ---- 偏好比對 ----

def load_org_sids(sources_path=SOURCES_PATH):
    """名錄 id → source_id 集合；發送時解析，社團新增帳號不用重訂閱。"""
    try:
        entries = json.loads(Path(sources_path).read_text()).get("entries") or []
    except (OSError, json.JSONDecodeError):
        return {}
    return {e["id"]: set(e.get("sids") or []) for e in entries if e.get("id") is not None}


def event_matches(event, prefs, org_sids):
    schools = prefs.get("schools") or []
    if schools:
        school = event.get("school")
        if school not in schools and school != "both":
            return False
    cats = prefs.get("cats") or []
    orgs = prefs.get("orgs") or []
    keywords = prefs.get("keywords") or []
    if not cats and not orgs and not keywords:
        return True
    if cats and (event.get("category") or "其他") in cats:
        return True
    if orgs:
        source_id = str((event.get("source") or {}).get("source_id") or "")
        for org in orgs:
            if source_id and source_id in org_sids.get(org["id"], ()):
                return True
    if keywords:
        haystack = " ".join(
            str(event.get(field) or "")
            for field in ("title", "summary", "description", "organizer", "venue")
        ).casefold()
        for keyword in keywords:
            if keyword.casefold() in haystack:
                return True
    return False


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
