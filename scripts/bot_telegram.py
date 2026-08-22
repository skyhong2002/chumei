"""Telegram 查詢 bot — 私訊回覆活動查詢（與頻道推播共用同一隻 bot token）。

長輪詢 getUpdates 常駐（launchd: tw.observe.chumei.bot-telegram），只理會私訊文字，
群組與頻道訊息一律忽略（頻道推播由 publish_telegram.py 負責，互不相干）。
offset 存 state/bot_telegram.json，重啟不重覆回覆。
"""

import html
import json
import time

import requests

import bot_core
from chumei_lib import ROOT, load_env

STATE_PATH = ROOT / "state" / "bot_telegram.json"

COMMANDS = [
    {"command": "today", "description": "今天的活動"},
    {"command": "tomorrow", "description": "明天的活動"},
    {"command": "week", "description": "這週的活動"},
    {"command": "weekend", "description": "這週末的活動"},
    {"command": "help", "description": "查詢說明"},
]
COMMAND_TEXT = {"/today": "今天", "/tomorrow": "明天", "/week": "這週", "/weekend": "這週末"}


def render(reply):
    """bot_core.answer() 結果 → Telegram HTML。"""
    if reply["kind"] != "events":
        return html.escape(reply["text"])
    lines = [f"<b>{html.escape(reply['title'])}</b>", ""]
    for e in reply["events"]:
        lines.append(f"・<a href=\"{e['url']}\">{html.escape(e['title'])}</a>")
        detail = f"　{e['when']}｜{e['where']}"
        if e["organizer"]:
            detail += f"｜{html.escape(e['organizer'])}"
        lines.append(detail)
    if reply["more"]:
        lines.append("")
        lines.append(f"…還有 {reply['more']} 場，完整清單：{reply['footer']}")
    return "\n".join(lines)


class Bot:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()

    def call(self, method, timeout=15, **payload):
        r = self.session.post(f"{self.base}/{method}", json=payload, timeout=timeout)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"{method}: {data.get('description')}")
        return data["result"]

    def run(self):
        self.call("setMyCommands", commands=COMMANDS)
        offset = 0
        if STATE_PATH.exists():
            offset = json.loads(STATE_PATH.read_text()).get("offset", 0)
        print(f"bot_telegram: polling from offset {offset}", flush=True)
        while True:
            try:
                updates = self.call("getUpdates", timeout=60, offset=offset,
                                    limit=20, allowed_updates=["message"])
            except Exception as exc:
                print(f"bot_telegram: getUpdates failed: {exc}", flush=True)
                time.sleep(10)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    self.handle(u.get("message") or {})
                except Exception as exc:
                    print(f"bot_telegram: handle failed: {exc}", flush=True)
            if updates:
                STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                STATE_PATH.write_text(json.dumps({"offset": offset}))

    def handle(self, msg):
        chat = msg.get("chat") or {}
        text = (msg.get("text") or "").strip()
        if chat.get("type") != "private" or not text:
            return
        text = COMMAND_TEXT.get(text.split("@")[0], text)
        reply = bot_core.answer(text)
        self.call("sendMessage", chat_id=chat["id"], text=render(reply),
                  parse_mode="HTML", disable_web_page_preview=True)


def main():
    token = load_env().get("CHUMEI_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("CHUMEI_TELEGRAM_BOT_TOKEN 未設定")
    Bot(token).run()


if __name__ == "__main__":
    main()
