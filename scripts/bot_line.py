"""LINE 查詢 bot — 官方帳號 webhook，只用免費的 Reply API（不主動推播、零訊息費）。

對外：Caddy 把 https://chumei.observe.tw/line/webhook 反代到 127.0.0.1:8322。
排程：launchd deploy/tw.observe.chumei.bot-line.plist 常駐（拿到金鑰後再載入）。
需要 .env：
  CHUMEI_LINE_CHANNEL_SECRET=<LINE Developers → channel → Basic settings>
  CHUMEI_LINE_ACCESS_TOKEN=<同上 → Messaging API → channel access token (long-lived)>
LINE Developers 後台 webhook URL 填 https://chumei.observe.tw/line/webhook 並開啟「Use webhook」；
「自動回應訊息」記得關掉，不然官方罐頭訊息會跟 bot 搶話。
"""

import base64
import hashlib
import hmac
import json

import requests
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

import bot_core
from chumei_lib import load_env

PORT = 8322
REPLY_URL = "https://api.line.me/v2/bot/message/reply"

_env = load_env()
CHANNEL_SECRET = _env.get("CHUMEI_LINE_CHANNEL_SECRET", "").strip()
ACCESS_TOKEN = _env.get("CHUMEI_LINE_ACCESS_TOKEN", "").strip()

WELCOME = (
    "歡迎加入竹梅活動觀測站！\n\n" + bot_core.HELP_TEXT
)


def render(reply):
    """bot_core.answer() 結果 → LINE 純文字（不支援 markdown，網址自動變連結）。"""
    if reply["kind"] != "events":
        return reply["text"]
    lines = [reply["title"], ""]
    for e in reply["events"]:
        lines.append(f"▪️ {e['title']}")
        detail = f"{e['when']}｜{e['where']}"
        if e["organizer"]:
            detail += f"｜{e['organizer']}"
        lines.append(detail)
        lines.append(e["url"])
        lines.append("")
    if reply["more"]:
        lines.append(f"…還有 {reply['more']} 場，完整清單：{reply['footer']}")
    return "\n".join(lines).strip()


def send_reply(reply_token, text):
    r = requests.post(REPLY_URL, timeout=15,
                      headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
                      json={"replyToken": reply_token,
                            "messages": [{"type": "text", "text": text[:4900]}]})
    if r.status_code != 200:
        print(f"bot_line: reply failed {r.status_code}: {r.text[:200]}", flush=True)


def valid_signature(body, signature):
    mac = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256)
    return hmac.compare_digest(base64.b64encode(mac.digest()).decode(), signature or "")


async def webhook(request):
    body = await request.body()
    if not valid_signature(body, request.headers.get("X-Line-Signature")):
        return PlainTextResponse("bad signature", status_code=403)
    for ev in json.loads(body).get("events", []):
        token = ev.get("replyToken")
        if not token:
            continue
        try:
            if ev.get("type") == "follow":
                send_reply(token, WELCOME)
            elif (ev.get("type") == "message"
                  and (ev.get("message") or {}).get("type") == "text"
                  and (ev.get("source") or {}).get("type") == "user"):
                send_reply(token, render(bot_core.answer(ev["message"]["text"])))
        except Exception as exc:
            print(f"bot_line: handle failed: {exc}", flush=True)
    return PlainTextResponse("ok")


app = Starlette(routes=[Route("/line/webhook", webhook, methods=["POST"])])

if __name__ == "__main__":
    import uvicorn
    if not (CHANNEL_SECRET and ACCESS_TOKEN):
        raise SystemExit("CHUMEI_LINE_CHANNEL_SECRET / CHUMEI_LINE_ACCESS_TOKEN 未設定")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
