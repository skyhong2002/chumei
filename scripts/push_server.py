"""Web Push 訂閱 API（Starlette + uvicorn，同 bot_line 模式）。

對外：Caddy 把 https://chumei.observe.tw/push/* 反代到 127.0.0.1:8323。
端點：
  GET  /push/config       → {publicKey}（VAPID 公鑰，前端 subscribe 用）
  POST /push/subscribe    → {subscription, prefs?, migrate_from?}；新訂閱回發歡迎通知
  POST /push/unsubscribe  → {endpoint}
  POST /push/status       → {endpoint} → {subscribed, prefs}（UI 還原狀態用）
  POST /push/test         → {endpoint}；重發測試通知

launchd: tw.observe.chumei.push（deploy/tw.observe.chumei.push.plist）。
"""

import json

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
    return (
        isinstance(endpoint, str)
        and endpoint.startswith("https://")
        and len(endpoint) < 1024
        and isinstance(keys.get("p256dh"), str)
        and isinstance(keys.get("auth"), str)
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


async def subscribe(request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    sub = body.get("subscription")
    if not valid_subscription(sub):
        return bad_request("invalid subscription")
    existed = pc.get_sub(sub["endpoint"]) is not None
    prefs = body.get("prefs")  # None＝不動既有偏好（pushsubscriptionchange 遷移時）
    record = pc.upsert_sub(
        sub,
        prefs=prefs,
        migrate_from=body.get("migrate_from"),
        ua=request.headers.get("user-agent", ""),
    )
    if not existed and not body.get("migrate_from"):
        try:
            pc.send_push(record, WELCOME, ttl=300)
        except pc.PushGone:
            pc.prune_endpoint(sub["endpoint"])
            return bad_request("endpoint rejected by push service")
        except Exception as exc:  # 歡迎通知失敗不擋訂閱本身
            print(f"push: welcome push failed: {exc}")
    return JSONResponse({"ok": True, "prefs": record["prefs"]})


async def unsubscribe(request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    endpoint = body.get("endpoint")
    if not isinstance(endpoint, str):
        return bad_request("missing endpoint")
    return JSONResponse({"ok": True, "removed": pc.remove_sub(endpoint)})


async def status(request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    endpoint = body.get("endpoint")
    if not isinstance(endpoint, str):
        return bad_request("missing endpoint")
    record = pc.get_sub(endpoint)
    if not record:
        return JSONResponse({"ok": True, "subscribed": False})
    return JSONResponse({"ok": True, "subscribed": True, "prefs": record["prefs"]})


async def test(request):
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return bad_request("invalid json")
    endpoint = body.get("endpoint")
    record = pc.get_sub(endpoint) if isinstance(endpoint, str) else None
    if not record:
        return bad_request("not subscribed")
    payload = {
        "title": "測試通知 🔔",
        "body": "收到這則代表推播運作正常。",
        "url": "/subscribe/",
        "tag": "chumei-test",
    }
    try:
        pc.send_push(record, payload, ttl=300)
    except pc.PushGone:
        pc.prune_endpoint(endpoint)
        return bad_request("endpoint gone")
    return JSONResponse({"ok": True})


app = Starlette(routes=[
    Route("/push/config", config, methods=["GET"]),
    Route("/push/subscribe", subscribe, methods=["POST"]),
    Route("/push/unsubscribe", unsubscribe, methods=["POST"]),
    Route("/push/status", status, methods=["POST"]),
    Route("/push/test", test, methods=["POST"]),
])

if __name__ == "__main__":
    import uvicorn

    pc.ensure_vapid()  # 首次啟動就產好金鑰
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
