"""Web Push 訂閱 API（Starlette + uvicorn，同 bot_line 模式）。

對外：Caddy 把 https://chumei.observe.tw/push/* 反代到 127.0.0.1:8323。
端點：
  GET  /push/config       → {publicKey}（VAPID 公鑰，前端 subscribe 用）
  POST /push/subscribe    → {subscription, prefs?, migrate_from?}；新訂閱回發歡迎通知
                            帶竹梅 session cookie 就把訂閱綁到帳號（登出狀態則解除）
  POST /push/unsubscribe  → {endpoint}
  POST /push/status       → {endpoint} → {subscribed, prefs, linked}（UI 還原狀態用；
                            同時依 cookie 校正綁定）
  GET  /push/stats        → 匿名推播裝置／偏好計數
  POST /push/test         → {endpoint}；重發測試通知

launchd: tw.observe.chumei.push（deploy/tw.observe.chumei.push.plist）。
"""

import json
import time
from collections import deque

from safe_outbound import validate_push_endpoint, UnsafeURL

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

import push_common as pc

PORT = 8323


def bad_request(msg):
    return JSONResponse({"ok": False, "error": msg}, status_code=400)


def valid_subscription(sub):
    if not isinstance(sub, dict):
        return False
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    try:
        validate_push_endpoint(endpoint)
    except (UnsafeURL, TypeError):
        return False
    return (
        isinstance(keys, dict)
        and isinstance(keys.get("p256dh"), str)
        and isinstance(keys.get("auth"), str)
        and 1 <= len(keys["p256dh"]) <= 256
        and 1 <= len(keys["auth"]) <= 128
    )


async def config(request):
    _, public_key = pc.ensure_vapid()
    return JSONResponse({"ok": True, "publicKey": public_key})


WELCOME = {
    "title": "竹梅推播已開啟 ✅",
    "body": "之後有符合你訂閱條件的新活動，就會像這樣通知你。",
    "url": "/subscribe/",
    "tag": "chumei-welcome",
}


# Single-process uvicorn service. Global cap protects against spoofed forwarded
# headers and endpoint rotation; per-device cap also covers welcome/test sends.
_send_times = deque()
_endpoint_times = {}


def allow_send(endpoint):
    now = time.monotonic()
    while _send_times and _send_times[0] <= now - 60:
        _send_times.popleft()
    for key, timestamp in list(_endpoint_times.items()):
        if timestamp <= now - 60:
            del _endpoint_times[key]
    if len(_send_times) >= 30 or endpoint in _endpoint_times:
        return False
    _send_times.append(now)
    _endpoint_times[endpoint] = now
    return True


async def read_body(request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 16384:
            raise ValueError("request too large")
    body = json.loads(data)
    if not isinstance(body, dict):
        raise ValueError("expected object")
    return body


async def subscribe(request):
    try:
        body = await read_body(request)
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    sub = body.get("subscription")
    if not valid_subscription(sub):
        return bad_request("無效的訂閱；目前支援 Chrome／Edge、Firefox 與 Safari 的標準推播服務。")
    if not allow_send(sub["endpoint"]):
        return JSONResponse({"ok": False, "error": "請稍後再試"}, status_code=429)
    existed = pc.get_sub(sub["endpoint"]) is not None
    prefs = body.get("prefs")  # None＝不動既有偏好（pushsubscriptionchange 遷移時）
    record = pc.upsert_sub(
        sub,
        prefs=prefs,
        migrate_from=body.get("migrate_from"),
        ua=request.headers.get("user-agent", ""),
        user_id=pc.session_user_id(request.cookies.get(pc.SESSION_COOKIE)) or "",
    )
    if not existed and not body.get("migrate_from"):
        try:
            pc.send_push(record, WELCOME, ttl=300)
        except pc.PushGone:
            pc.prune_endpoint(sub["endpoint"])
            return bad_request("endpoint rejected by push service")
        except Exception as exc:  # 歡迎通知失敗不擋訂閱本身
            print(f"push: welcome push failed: {exc}")
    return JSONResponse({"ok": True, "prefs": record["prefs"], "linked": bool(record.get("user_id"))})


async def unsubscribe(request):
    try:
        body = await read_body(request)
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    endpoint = body.get("endpoint")
    if not isinstance(endpoint, str):
        return bad_request("missing endpoint")
    return JSONResponse({"ok": True, "removed": pc.remove_sub(endpoint)})


async def status(request):
    try:
        body = await read_body(request)
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    endpoint = body.get("endpoint")
    if not isinstance(endpoint, str):
        return bad_request("missing endpoint")
    record = pc.get_sub(endpoint)
    if not record:
        return JSONResponse({"ok": True, "subscribed": False})
    user_id = pc.session_user_id(request.cookies.get(pc.SESSION_COOKIE)) or ""
    if (record.get("user_id") or "") != user_id:
        record = pc.upsert_sub(record["sub"], user_id=user_id)
    return JSONResponse({"ok": True, "subscribed": True, "prefs": record["prefs"],
                         "linked": bool(record.get("user_id"))})


async def stats(request):
    return JSONResponse({"ok": True, **pc.subscription_stats()})


async def test(request):
    try:
        body = await read_body(request)
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    endpoint = body.get("endpoint")
    record = pc.get_sub(endpoint) if isinstance(endpoint, str) else None
    if not record:
        return bad_request("not subscribed")
    if not allow_send(endpoint):
        return JSONResponse({"ok": False, "error": "請稍後再試"}, status_code=429)
    payload = {
        "title": "測試通知 🔔",
        "body": "收到這則代表推播運作正常。",
        "url": "/subscribe/",
        "tag": "chumei-test",
    }
    try:
        pc.send_push(record, payload, ttl=300)
    except UnsafeURL:
        return bad_request("不支援這個推播服務，請重新開啟瀏覽器通知。")
    except pc.PushGone:
        pc.prune_endpoint(endpoint)
        return bad_request("endpoint gone")
    return JSONResponse({"ok": True})


app = Starlette(routes=[
    Route("/push/config", config, methods=["GET"]),
    Route("/push/subscribe", subscribe, methods=["POST"]),
    Route("/push/unsubscribe", unsubscribe, methods=["POST"]),
    Route("/push/status", status, methods=["POST"]),
    Route("/push/stats", stats, methods=["GET"]),
    Route("/push/test", test, methods=["POST"]),
])

if __name__ == "__main__":
    import uvicorn

    pc.ensure_vapid()  # 首次啟動就產好金鑰
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
