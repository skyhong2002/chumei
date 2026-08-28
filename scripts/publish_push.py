"""把新收錄的活動推送給 Web Push 訂閱者（偏好過濾版的 publish_telegram）。

與 Telegram 頻道共用同一套「新活動」語意：首跑建 baseline 不洗版、
start_at 在今天以後、貼文逾 14 天不推（防回填洪水）、01:00–08:00 靜音
（事件保留到早上再發）。每個訂閱者只收到符合其偏好的活動；單輪命中
超過 3 場則收合成一則摘要通知。

綁帳號的訂閱：追蹤單位以帳號現況為準；帳號按過「我要去」的活動，在活動
前一天（或當天才標記時當天）推一則提醒到該帳號的所有裝置，每場只提醒一次。

launchd: tw.observe.chumei.push-drip（每 30 分鐘）。
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from chumei_lib import ROOT, now_iso
import push_common as pc
from publish_telegram import (
    compact,
    eligible_events,
    event_location,
    event_photo_url,
    format_datetime,
    is_silent_hour,
    load_events,
)

STATE_PATH = ROOT / "state" / "push" / "publish.json"
BASE_URL = "https://chumei.observe.tw"
DIGEST_THRESHOLD = 3  # 單輪單訂閱命中超過此數 → 摘要通知


def load_state(path=STATE_PATH):
    if not path.exists():
        return None
    state = json.loads(Path(path).read_text())
    state.setdefault("sent", {})
    return state


def save_state(state, path=STATE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(path)


def pending_events(events, state):
    sent = state.get("sent", {})
    pending = [e for e in eligible_events(events) if e["id"] not in sent]
    return sorted(pending, key=lambda e: (e.get("first_seen") or "", e["start_at"], e["id"]))


def event_payload(event):
    body_lines = [f"🗓 {format_datetime(event.get('start_at'), event.get('all_day'))}"
                  f" ・ {compact(event_location(event), 60)}"]
    organizer = compact(event.get("organizer"), 40)
    if organizer:
        body_lines.append(f"主辦：{organizer}")
    summary = compact(event.get("summary"), 90)
    if summary:
        body_lines.append(summary)
    return {
        "title": compact(event.get("title"), 60),
        "body": "\n".join(body_lines),
        "url": f"{BASE_URL}/event/{event['id']}/",
        "tag": f"chumei-{event['id']}",
        "image": event_photo_url(event),
    }


def digest_payload(matched):
    lines = [f"・{compact(e.get('title'), 32)}"
             f"（{format_datetime(e.get('start_at'), e.get('all_day'))}）"
             for e in matched[:5]]
    if len(matched) > 5:
        lines.append(f"⋯還有 {len(matched) - 5} 場")
    return {
        "title": f"有 {len(matched)} 場新活動符合你的訂閱",
        "body": "\n".join(lines),
        "url": f"{BASE_URL}/events/",
        "tag": "chumei-digest",
    }


def deliveries_for(subs, pending, org_sids, follows=None):
    """[(key, record, [payload, ...]), ...] — 每訂閱一組要發的通知。"""
    plan = []
    follows = follows or {}
    for key, record in subs.items():
        prefs = pc.effective_prefs(record, follows)
        matched = [e for e in pending if pc.event_matches(e, prefs, org_sids)]
        if not matched:
            continue
        if len(matched) > DIGEST_THRESHOLD:
            payloads = [digest_payload(matched)]
        else:
            payloads = [event_payload(e) for e in matched]
        plan.append((key, record, payloads, len(matched)))
    return plan


def reminder_payload(event, when):
    body = (f"🗓 {format_datetime(event.get('start_at'), event.get('all_day'))}"
            f" ・ {compact(event_location(event), 60)}")
    return {
        "title": f"{when}：{compact(event.get('title'), 50)}",
        "body": body,
        "url": f"{BASE_URL}/event/{event['id']}/",
        "tag": f"chumei-remind-{event['id']}",
        "image": event_photo_url(event),
    }


def reminders_for(subs, events, going, state, today=None):
    """[(user_id, event_id, [(key, record), ...], payload), ...]

    帳號標記「我要去」且活動明天開始（或今天開始但還沒提醒過）→ 推到該帳號所有裝置。
    """
    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    by_id = {e["id"]: e for e in events if e.get("id")}
    by_user = {}
    for key, record in subs.items():
        if record.get("user_id"):
            by_user.setdefault(record["user_id"], []).append((key, record))
    done = state.setdefault("reminders", {})
    plan = []
    for user_id, event_ids in going.items():
        devices = by_user.get(user_id)
        if not devices:
            continue
        for event_id in event_ids:
            event = by_id.get(event_id)
            if not event or event.get("status") == "rejected":
                continue
            start = (event.get("start_at") or "")[:10]
            if start == tomorrow.isoformat():
                when = "明天"
            elif start == today.isoformat():
                when = "今天"
            else:
                continue
            if f"{user_id}:{event_id}" in done:
                continue
            plan.append((user_id, event_id, devices, reminder_payload(event, when)))
    return plan


def send_reminders(subs, events, state, dry_run=False):
    """回傳 (提醒數, 通知數)；state 會被標記（呼叫端負責存檔）。"""
    going = pc.account_going()
    plan = reminders_for(subs, events, going, state)
    if dry_run:
        for user_id, event_id, devices, payload in plan:
            print(f"  remind {user_id[:8]}… {event_id} → {len(devices)} device(s): {payload['title']}")
        return len(plan), sum(len(d) for _, _, d, _ in plan)
    sent = 0
    for user_id, event_id, devices, payload in plan:
        for key, record in devices:
            try:
                pc.send_push(record, payload, ttl=6 * 3600)
                sent += 1
            except pc.PushGone as exc:
                pc.prune_endpoint(str(exc))
            except Exception as exc:
                print(f"push: reminder failed for {key}: {exc}", file=sys.stderr)
        state.setdefault("reminders", {})[f"{user_id}:{event_id}"] = {"sent_at": now_iso()}
    return len(plan), sent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show pending/deliveries without sending")
    parser.add_argument("--ignore-quiet-hours", action="store_true")
    args = parser.parse_args()

    try:
        if not pc.push_enabled():
            print("push: disabled")
            return 0
        events = load_events()
        state = load_state()
        if state is None:
            baseline = eligible_events(events)
            if args.dry_run:
                print(f"push dry-run: would baseline {len(baseline)} current upcoming events")
                return 0
            state = {"version": 1, "initialized_at": now_iso(),
                     "sent": {e["id"]: {"baselined_at": now_iso()} for e in baseline}}
            save_state(state)
            print(f"push: initialized baseline ({len(baseline)} upcoming events)")
            return 0

        pending = pending_events(events, state)
        if is_silent_hour() and not args.ignore_quiet_hours:
            print(f"push: quiet hours, {len(pending)} pending held for morning")
            return 0

        subs = pc.load_subs()["subs"]
        n_remind, n_remind_sent = send_reminders(subs, events, state, dry_run=args.dry_run)
        if n_remind and not args.dry_run:
            save_state(state)
        if not pending:
            print(f"push: OK (no pending events; {n_remind} reminders → {n_remind_sent} notifications)")
            return 0

        org_sids = pc.load_org_sids()
        plan = deliveries_for(subs, pending, org_sids, pc.account_follows())
        if args.dry_run:
            print(f"push dry-run: {len(pending)} pending events, {len(subs)} subs, {len(plan)} deliveries, "
                  f"{n_remind} reminders")
            for key, _record, payloads, n_matched in plan:
                kinds = "digest" if payloads and payloads[0].get("tag") == "chumei-digest" else "individual"
                print(f"  {key}: {n_matched} matched → {len(payloads)} notification(s) ({kinds})")
            return 0

        sent_n, gone_n, fail_n = 0, 0, 0
        for key, record, payloads, _n in plan:
            for payload in payloads:
                try:
                    pc.send_push(record, payload)
                    sent_n += 1
                except pc.PushGone as exc:
                    pc.prune_endpoint(str(exc))
                    gone_n += 1
                    break
                except Exception as exc:
                    print(f"push: send failed for {key}: {exc}", file=sys.stderr)
                    fail_n += 1
                    break

        stamp = now_iso()
        for event in pending:
            state["sent"][event["id"]] = {"sent_at": stamp}
        state["last_success_at"] = stamp
        save_state(state)
        print(f"push: OK ({len(pending)} events → {sent_n} notifications, "
              f"{len(subs)} subs, pruned {gone_n}, failed {fail_n}; "
              f"{n_remind} reminders → {n_remind_sent})")
        return 0
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"push: FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
