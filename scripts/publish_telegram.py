"""Publish newly discovered Chumei events to the public Telegram channel.

The first normal run creates a baseline from current upcoming events so enabling
the publisher never floods a new channel with the existing catalogue.
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import requests

from chumei_lib import INBOX_DIR, ROOT, TZ_TAIPEI, load_env, now_iso

EVENTS_PATH = ROOT / "site" / "data" / "events.json"
STATE_PATH = ROOT / "state" / "telegram.json"
BASE_URL = "https://chumei.observe.tw"
FALLBACK_COVER = "/assets/fallback/event-cover.webp"
TELEGRAM_CAPTION_LIMIT = 1024
SCHOOL_LABEL = {"nthu": "清大", "nycu": "陽明交大", "both": "清大 × 交大", "external": "校外"}
CAMPUS_LABEL = {
    "nthu-main": "清大校本部",
    "nthu-nanda": "清大南大校區",
    "nycu-guangfu": "交大光復校區",
    "nycu-boai": "交大博愛校區",
    "nycu-yangming": "陽明校區",
    "online": "線上",
    "other": "其他地點",
}
PLATFORM_LABEL = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "bulletin": "官方網站",
    "api": "API",
    "rss": "RSS",
    "web": "網站",
}


class TelegramError(RuntimeError):
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


def load_events(path=EVENTS_PATH):
    return json.loads(path.read_text())["events"]


def load_source_records(inbox_dir=INBOX_DIR):
    """Return the newest raw inbox record keyed by (source_id, post_id)."""
    records = {}
    if not inbox_dir.exists():
        return {}
    for path in sorted(inbox_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                key = (str(item.get("source_id") or ""), str(item.get("post_id") or ""))
                if not all(key):
                    continue
                fetched_at = item.get("fetched_at") or ""
                if key not in records or fetched_at >= records[key][0]:
                    records[key] = (fetched_at, {
                        "text": str(item.get("text") or "").strip(),
                        "source_name": str(item.get("source_name") or "").strip(),
                        "platform": str(item.get("platform") or "").strip(),
                    })
    return {key: value[1] for key, value in records.items()}


def load_original_texts(inbox_dir=INBOX_DIR):
    """Backward-compatible raw-text view used by callers and tests."""
    return {key: record["text"] for key, record in load_source_records(inbox_dir).items() if record["text"]}


def attach_original_texts(events, originals):
    for event in events:
        source = event.get("source") or {}
        key = (str(source.get("source_id") or ""), str(source.get("post_id") or ""))
        event["original_text"] = originals.get(key) or event.get("description") or event.get("summary") or ""
    return events


def attach_source_context(events, records):
    for event in events:
        source = event.get("source") or {}
        key = (str(source.get("source_id") or ""), str(source.get("post_id") or ""))
        record = records.get(key) or {}
        event["original_text"] = record.get("text") or event.get("description") or event.get("summary") or ""
        event["source_name"] = record.get("source_name") or source.get("source_name") or ""
        event["source_platform"] = record.get("platform") or source.get("platform") or ""
    return events


def load_state(path=STATE_PATH):
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    state.setdefault("sent", {})
    return state


def save_state(state, path=STATE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(path)


MAX_POST_AGE_DAYS = 14  # 新收錄帳號的舊貼文不推播，防回填洪水


def post_is_fresh(event, today):
    """原貼文夠新才推。沒有 posted_at（舊快取）視為新，不影響正常流程。"""
    ts = ((event.get("source") or {}).get("posted_at") or "")[:10]
    if not ts:
        return True
    cutoff = (date.fromisoformat(today) - timedelta(days=MAX_POST_AGE_DAYS)).isoformat()
    return ts >= cutoff


def eligible_events(events, today=None):
    today = today or date.today().isoformat()
    return [
        event for event in events
        if event.get("id")
        and (event.get("start_at") or "")[:10] >= today
        and event.get("status") != "rejected"
        and post_is_fresh(event, today)
    ]


def pending_events(events, state, today=None):
    sent = state.get("sent", {})
    def complete(event_id):
        delivery = sent.get(event_id) or {}
        return bool(delivery.get("baselined_at") or delivery.get("sent_at") or delivery.get("status") == "sent")

    pending = [event for event in eligible_events(events, today) if not complete(event["id"])]
    return sorted(pending, key=lambda event: (event.get("first_seen") or "", event["start_at"], event["id"]))


def initialize_state(events, today=None):
    ts = now_iso()
    sent = {event["id"]: {"baselined_at": ts} for event in eligible_events(events, today)}
    return {"version": 1, "initialized_at": ts, "sent": sent}


def format_datetime(value, all_day=False):
    if not value:
        return "時間請見活動頁"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    weekday = "一二三四五六日"[dt.weekday()]
    result = f"{dt.month}/{dt.day}（{weekday}）"
    if not all_day and (dt.hour, dt.minute) != (0, 0):
        result += f" {dt:%H:%M}"
    return result


def event_location(event):
    campus = CAMPUS_LABEL.get(event.get("campus"), "")
    venue = (event.get("venue") or "").strip()
    if venue:
        return venue
    if event.get("campus") in (None, "", "other"):
        return "地點請見活動頁"
    return campus or "地點請見活動頁"


def format_location(event):
    location = compact(event_location(event), 180)
    safe_location = html.escape(location)
    if event.get("campus") == "online" or location == "地點請見活動頁":
        return f"📍 {safe_location}"
    campus = CAMPUS_LABEL.get(event.get("campus"), "")
    query = location
    if campus and event.get("campus") not in ("other", "online") and campus not in location:
        query = f"{location} {campus}"
    maps_url = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)
    return f'📍 <a href="{html.escape(maps_url, quote=True)}">{safe_location}</a>'


def compact(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def formal_source_name(name):
    name = str(name or "").strip()
    if name.startswith("交大公告-"):
        return "國立陽明交通大學校園公告－" + name.removeprefix("交大公告-")
    replacements = (
        ("陽明交大", "國立陽明交通大學"),
        ("交大", "國立陽明交通大學"),
        ("清華大學", "國立清華大學"),
        ("清大", "國立清華大學"),
    )
    for prefix, formal in replacements:
        if name.startswith(prefix):
            return formal + name[len(prefix):]
    return name


def format_source(event):
    source = event.get("source") or {}
    name = formal_source_name(event.get("source_name"))
    if not name:
        name = str(source.get("source_id") or "").strip()
    platform = event.get("source_platform") or source.get("platform") or ""
    platform = PLATFORM_LABEL.get(platform.lower(), platform)
    source_url = str(source.get("url") or "").strip()
    if not name:
        return ""
    label = html.escape(compact(name, 180))
    if platform:
        safe_platform = html.escape(compact(platform, 40))
        if source_url:
            safe_url = html.escape(source_url, quote=True)
            label += f' (<a href="{safe_url}">{safe_platform}</a>)'
        else:
            label += f" ({safe_platform})"
    return f"🔗 {label}"


def split_text(text, limit=2500):
    """Split a long original post without discarding any non-whitespace text."""
    remaining = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    chunks = []
    while len(remaining) > limit:
        candidates = [remaining.rfind(token, 0, limit + 1) for token in ("\n\n", "\n", " ")]
        cut = max(candidates)
        if cut < limit // 2:
            cut = limit
        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def rendered_length(value):
    """Approximate Telegram's post-entity character count for HTML text."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", value)))


def event_photo_url(event):
    cover = event.get("poster_image") or event.get("cover_image") or FALLBACK_COVER
    cover = str(cover).strip()
    if cover.startswith(("http://", "https://")):
        return cover
    return BASE_URL + "/" + cover.lstrip("/")


WEEKDAY_ZH = "一二三四五六日"


def format_recurrings_line(event):
    """同貼文宣告的例行時段（定期社課），附一行就好，保持訊息簡潔。"""
    recs = event.get("post_recurrings") or []
    parts = [f"每週{WEEKDAY_ZH[r['weekday'] - 1]} {r['time']} {r['title']}"
             + (f"（{r['venue']}）" if r.get("venue") else "")
             for r in recs if r.get("weekday") and r.get("time")]
    return "📅 例行時段：" + html.escape("；".join(parts)) if parts else None


def format_event_messages(event, first_limit=4096):
    detail_url = f"{BASE_URL}/event/{event['id']}/"
    title = html.escape(compact(event.get("title"), 180))
    when = html.escape(format_datetime(event.get("start_at"), event.get("all_day")))
    summary_limit = 300 if first_limit <= TELEGRAM_CAPTION_LIMIT else 420
    summary = html.escape(compact(event.get("summary"), summary_limit))
    safe_detail_url = html.escape(detail_url, quote=True)
    lines = [f'<a href="{safe_detail_url}"><b>{title}</b></a>', ""]
    source_line = format_source(event)
    if source_line:
        lines.append(source_line)
    lines.extend([f"🗓 {when}", format_location(event)])
    rec_line = format_recurrings_line(event)
    if rec_line:
        lines.append(rec_line)
    if summary:
        lines.extend(["", summary])
    if (event.get("extraction") or {}).get("needs_review"):
        lines.extend(["", "⚠️ 資訊由公開貼文擷取，請以原始公告為準。"])
    original_chunks = split_text(event.get("original_text"))
    if not original_chunks:
        return ["\n".join(lines)]

    header = "\n".join(lines)
    first_block = f"<blockquote expandable>{html.escape(original_chunks[0])}</blockquote>"
    if rendered_length(header + "\n\n" + first_block) <= first_limit:
        messages = [header + "\n\n" + first_block]
        remaining_chunks = original_chunks[1:]
    else:
        messages = [header]
        remaining_chunks = original_chunks
    for chunk in remaining_chunks:
        messages.append(f"<blockquote expandable>{html.escape(chunk)}</blockquote>")
    return messages


def format_event(event):
    """Backward-compatible helper for previews and short-message tests."""
    return format_event_messages(event)[0]


def group_pending_by_post(pending):
    """同一則貼文的多場活動合併成一組，一組發一則訊息。"""
    groups, order = {}, []
    for event in pending:
        src = event.get("source") or {}
        key = (src.get("source_id"), src.get("post_id"))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(event)
    return [groups[k] for k in order]


def format_post_messages(group, first_limit=4096):
    """一則來源貼文（可含多場活動）→ 訊息串。單場活動沿用原格式。"""
    if len(group) == 1:
        return format_event_messages(group[0], first_limit=first_limit)
    lead = group[0]
    lines = []
    source_line = format_source(lead)
    if source_line:
        lines.append(source_line)
    lines.append(f"這則貼文包含 <b>{len(group)}</b> 場活動：")
    for event in group:
        title = html.escape(compact(event.get("title"), 120))
        url = html.escape(f"{BASE_URL}/event/{event['id']}/", quote=True)
        when = html.escape(format_datetime(event.get("start_at"), event.get("all_day")))
        loc = format_location(event)
        lines.extend(["", f'▸ <a href="{url}"><b>{title}</b></a>', f"　🗓 {when}", f"　{loc}"])
    rec_line = format_recurrings_line(lead)
    if rec_line:
        lines.extend(["", rec_line])
    if any((e.get("extraction") or {}).get("needs_review") for e in group):
        lines.extend(["", "⚠️ 資訊由公開貼文擷取，請以原始公告為準。"])
    header = "\n".join(lines)
    original_chunks = split_text(lead.get("original_text"))
    if not original_chunks:
        return [header]
    first_block = f"<blockquote expandable>{html.escape(original_chunks[0])}</blockquote>"
    if rendered_length(header + "\n\n" + first_block) <= first_limit:
        messages = [header + "\n\n" + first_block]
        remaining = original_chunks[1:]
    else:
        messages = [header]
        remaining = original_chunks
    for chunk in remaining:
        messages.append(f"<blockquote expandable>{html.escape(chunk)}</blockquote>")
    return messages


def is_silent_hour(now=None):
    now = now or datetime.now(TZ_TAIPEI)
    return now.hour >= 22 or now.hour < 8


class TelegramClient:
    def __init__(self, token, channel, session=None):
        self.channel = channel
        self.base = f"https://api.telegram.org/bot{token}"
        self.session = session or requests.Session()

    def call(self, method, payload, attempts=2):
        last_error = None
        for attempt in range(attempts):
            try:
                response = self.session.post(f"{self.base}/{method}", json=payload, timeout=30)
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = TelegramError(f"{method} network/response error: {exc}")
                if attempt + 1 < attempts:
                    time.sleep(2)
                    continue
                raise last_error
            if data.get("ok"):
                return data["result"]
            code = data.get("error_code")
            description = data.get("description") or "unknown Telegram error"
            retry_after = (data.get("parameters") or {}).get("retry_after")
            last_error = TelegramError(f"{method} failed ({code}): {description}", code)
            if attempt + 1 < attempts and (code == 429 or (code and code >= 500)):
                time.sleep(min(int(retry_after or 2), 30))
                continue
            raise last_error
        raise last_error

    def check(self):
        bot = self.call("getMe", {})
        chat = self.call("getChat", {"chat_id": self.channel})
        member = self.call("getChatMember", {"chat_id": self.channel, "user_id": bot["id"]})
        if member.get("status") not in {"administrator", "creator"} or member.get("can_post_messages") is not True:
            raise TelegramError("bot is not a channel administrator with can_post_messages")
        return bot, chat

    def send_post(self, group, silent=False, start_part=0, on_sent=None):
        event = group[0]
        messages = format_post_messages(group, first_limit=TELEGRAM_CAPTION_LIMIT)
        results = []
        for index, text in enumerate(messages[start_part:], start=start_part):
            if index == 0:
                payload = {
                    "chat_id": self.channel,
                    "photo": event_photo_url(event),
                    "caption": text,
                    "parse_mode": "HTML",
                    "disable_notification": silent,
                }
                result = self.call("sendPhoto", payload)
            else:
                payload = {
                    "chat_id": self.channel,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_notification": silent,
                    "link_preview_options": {"is_disabled": True},
                }
                result = self.call("sendMessage", payload)
            results.append(result)
            if on_sent:
                on_sent(result, index, len(messages))
            if index + 1 < len(messages):
                time.sleep(1)
        return results

    def send_event(self, event, silent=False, start_part=0, on_sent=None):
        return self.send_post([event], silent=silent, start_part=start_part, on_sent=on_sent)

    def announce(self, text, silent=False):
        return self.call(
            "sendMessage",
            {
                "chat_id": self.channel,
                "text": text,
                "parse_mode": "HTML",
                "disable_notification": silent,
                "reply_markup": {"inline_keyboard": [[{"text": "瀏覽近期活動", "url": BASE_URL}]]},
                "link_preview_options": {"is_disabled": True},
            },
        )


def configured_client():
    env = load_env()
    enabled = env.get("CHUMEI_TELEGRAM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None
    token = env.get("CHUMEI_TELEGRAM_BOT_TOKEN", "").strip()
    channel = env.get("CHUMEI_TELEGRAM_CHANNEL_ID", "").strip()
    if not token or not channel:
        raise TelegramError("Telegram is enabled but token/channel configuration is missing")
    return TelegramClient(token, channel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show pending events without sending or changing state")
    parser.add_argument("--check", action="store_true", help="verify bot identity and channel publishing permission")
    parser.add_argument("--announce", help="send a one-off HTML announcement instead of publishing events")
    parser.add_argument("--silent", action="store_true", help="force silent delivery")
    parser.add_argument("--max-messages", type=int, default=10)
    args = parser.parse_args()

    try:
        client = configured_client()
        if client is None:
            print("telegram: disabled")
            return 0
        if args.check:
            bot, chat = client.check()
            print(f"telegram: OK (bot=@{bot.get('username')}, channel=@{chat.get('username')})")
            return 0
        silent = args.silent or is_silent_hour()
        if args.announce is not None:
            if args.dry_run:
                print(f"telegram dry-run: announcement ({len(args.announce)} chars, silent={silent})")
                return 0
            message = client.announce(args.announce, silent=silent)
            print(f"telegram: announcement sent (message_id={message['message_id']}, silent={silent})")
            return 0

        events = attach_source_context(load_events(), load_source_records())
        state = load_state()
        if state is None:
            baseline = eligible_events(events)
            if args.dry_run:
                print(f"telegram dry-run: would baseline {len(baseline)} current upcoming events")
                return 0
            state = initialize_state(events)
            save_state(state)
            print(f"telegram: initialized baseline ({len(baseline)} upcoming events, 0 sent)")
            return 0

        pending = pending_events(events, state)
        groups = group_pending_by_post(pending)
        if args.dry_run:
            print(f"telegram dry-run: {len(pending)} pending events in {len(groups)} post group(s)")
            for group in groups[: args.max_messages]:
                parts = len(format_post_messages(group))
                titles = "；".join(compact(e.get("title"), 40) for e in group)
                print(f"  [{len(group)} 場/{parts} part(s)] {group[0]['id']} {titles}")
            return 0

        sent_count = 0
        for group in groups[: args.max_messages]:
            lead = group[0]
            delivery = state["sent"].setdefault(
                lead["id"], {"started_at": now_iso(), "message_ids": []}
            )
            delivery.setdefault("message_ids", [])

            def record_part(message, _index, _total):
                delivery["message_ids"].append(message["message_id"])
                save_state(state)

            client.send_post(
                group,
                silent=silent,
                start_part=len(delivery["message_ids"]),
                on_sent=record_part,
            )
            stamp = now_iso()
            for event in group:  # 同貼文的所有活動共享發送狀態
                rec = state["sent"].setdefault(event["id"], {"started_at": stamp})
                rec["sent_at"] = stamp
                rec["status"] = "sent"
                rec["message_id"] = delivery["message_ids"][0]
                rec.setdefault("message_ids", delivery["message_ids"])
            state["last_success_at"] = stamp
            save_state(state)
            sent_count += 1
            print(f"telegram: sent post {lead['id']} (+{len(group)-1} merged, message_ids={delivery['message_ids']})")
            if sent_count < min(len(groups), args.max_messages):
                time.sleep(1)
        print(f"telegram: OK ({sent_count} posts sent, {max(0, len(groups) - sent_count)} post(s) remaining, silent={silent})")
        return 0
    except (OSError, KeyError, json.JSONDecodeError, TelegramError) as exc:
        print(f"telegram: FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
