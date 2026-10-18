"""把新收錄的活動推送給 Web Push 訂閱者（偏好過濾版的 publish_telegram）。

與 Telegram 頻道共用同一套「新活動」語意：首跑建 baseline 不洗版、
start_at 在今天以後、貼文逾 14 天不推（防回填洪水）、01:00–08:00 靜音
（事件保留到早上再發）。每個訂閱者只收到符合其偏好的活動；單輪命中
超過 3 場則收合成一則摘要通知。

綁帳號的訂閱：追蹤單位以帳號現況為準；帳號加入「我會去」的活動，在活動
前一天（或當天才標記時當天）推一則提醒到該帳號的所有裝置，每場只提醒一次。

launchd: tw.observe.chumei.push-drip（每 30 分鐘）。
"""

import argparse
import copy
import errno
import sys
import time
from contextlib import nullcontext
from datetime import date, timedelta

from chumei_lib import ROOT, now_iso
import push_common as pc
import push_delivery as pd
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


def failure_diagnostic(error):
    """Fixed classes and known socket errno only; never inspect exception text.

    Inspect at most four explicit cause links, with a cycle guard. These facts
    describe this failure only and cannot establish a provider or route cause.
    """
    try:
        from socket import gaierror, herror
        from ssl import SSLError as SocketSSLError
        from urllib3.exceptions import (
            ConnectTimeoutError, NameResolutionError, NewConnectionError, SSLError,
        )
        # NewConnectionError itself inherits ConnectTimeoutError in urllib3.
        classifiers = (((NameResolutionError, gaierror, herror), "dns_resolution"),
                       ((NewConnectionError,), "new_connection"),
                       ((ConnectTimeoutError,), "connect_timeout"),
                       ((SSLError, SocketSSLError), "tls"))
        chain, seen = [], set()
        current = error
        for depth in range(5):  # Original plus at most four followed cause links.
            if not isinstance(current, BaseException) or id(current) in seen:
                raise ValueError("incomplete diagnostic chain")
            seen.add(id(current))
            chain.append(current)
            # Built-in descriptors avoid custom exception properties/args/repr.
            following = BaseException.__cause__.__get__(current)
            if following is None:
                break
            if depth == 4:
                raise ValueError("diagnostic chain exceeds bound")
            current = following
        # First known exception from the outside; precedence within each node.
        known_index, category = next(((index, label) for index, item in enumerate(chain)
                                      for classes, label in classifiers if isinstance(item, classes)),
                                     (None, "other"))
        allowed_errno = {getattr(errno, name) for name in (
            "ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED", "ETIMEDOUT",
            "EADDRNOTAVAIL", "EACCES", "EPERM", "ECONNRESET", "EAFNOSUPPORT",
        ) if hasattr(errno, name)}
        socket_errno = None
        excluded = (NameResolutionError, gaierror, herror, SSLError, SocketSSLError)
        if (category in {"new_connection", "connect_timeout"}
                and not any(isinstance(item, excluded) for item in chain)):
            # urllib3's connect exceptions explicitly chain their socket error.
            # Do not borrow errno from an unrelated outer/opaque wrapper.
            cause = chain[known_index + 1] if known_index + 1 < len(chain) else None
            if isinstance(cause, OSError):
                value = OSError.errno.__get__(cause)
                if type(value) is int and value in allowed_errno:
                    socket_errno = value
        return {"failure_cause": category, "socket_errno": socket_errno}
    except Exception:
        # Diagnostics never replace the original failure/retry/checkpoint path.
        return {"failure_cause": "other", "socket_errno": None}


def clear_failure_diagnostic(job):
    job.pop("failure_cause", None)
    job.pop("socket_errno", None)


def load_state(path=None):
    return pd.load(STATE_PATH if path is None else path)


def save_state(state, path=None):
    pd.save(state, STATE_PATH if path is None else path)


def pending_events(events, state):
    sent = state.get("sent", {})
    pending = [e for e in eligible_events(events)
               if not any(eid in sent for eid in [e["id"], *e.get("merged_event_ids", [])])]
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


def matched_events(subs, pending, org_sids, follows=None):
    follows = follows or {}
    for key, record in subs.items():
        prefs = pc.effective_prefs(record, follows)
        matched = [e for e in pending if pc.event_matches(e, prefs, org_sids)]
        if not matched:
            continue
        yield key, record, matched


def deliveries_for(subs, pending, org_sids, follows=None):
    """[(key, record, [payload, ...], event_count), ...]."""
    plan = []
    for key, record, matched in matched_events(subs, pending, org_sids, follows):
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

    帳號加入「我會去」且活動明天開始（或今天開始但還沒提醒過）→ 推到該帳號所有裝置。
    """
    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    by_id = {e["id"]: e for e in events if e.get("id")}
    for event in events:
        for old_id in event.get("merged_event_ids", []):
            by_id.setdefault(old_id, event)
    by_user = {}
    for key, record in subs.items():
        if record.get("user_id"):
            by_user.setdefault(record["user_id"], []).append((key, record))
    done = state.setdefault("reminders", {})
    plan = []
    scheduled = set()
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
            canonical_id = event["id"]
            aliases = [canonical_id, *event.get("merged_event_ids", [])]
            if (user_id, canonical_id) in scheduled or any(f"{user_id}:{eid}" in done for eid in aliases):
                continue
            scheduled.add((user_id, canonical_id))
            plan.append((user_id, canonical_id, devices, reminder_payload(event, when)))
    return plan


def queue_events(subs, pending, state, org_sids, follows):
    """Freeze each event's recipient cohort and each digest's membership once."""
    for event in pending:
        pd.group(state, "event", event["id"])
    for key, record, matched in matched_events(subs, pending, org_sids, follows):
        if len(matched) > DIGEST_THRESHOLD:
            pd.enqueue(state, "event", key, [e["id"] for e in matched], digest=True,
                       recipient_user_id=record.get("user_id"))
        else:
            for event in matched:
                pd.enqueue(state, "event", key, [event["id"]],
                           recipient_user_id=record.get("user_id"))
    for event in pending:
        entry = state["sent"][event["id"]]
        if not entry["devices"]:
            entry.update(status="complete", completed_at=now_iso(), reason="no_recipients")


def queue_reminders(subs, events, going, state, today=None):
    plan = reminders_for(subs, events, going, state, today=today)
    for user_id, event_id, devices, _payload in plan:
        for key, _record in devices:
            pd.enqueue(state, "reminder", key, [event_id], user_id=user_id)
    return len(plan)


def frozen_payload(job, active, active_ids, today):
    """Freeze before transport; only subtract digest members / update day wording."""
    if "payload" not in job:
        if job["kind"] == "reminder":
            when = "今天" if active[0]["start_at"][:10] == today.isoformat() else "明天"
            job["payload"] = reminder_payload(active[0], when)
            job["payload_when"] = when
        elif job["digest"]:
            # Minimal immutable projection, not a second copy of event metadata.
            job["payload_members"] = {
                event_id: {field: event.get(field) for field in ("title", "start_at", "all_day")}
                for event_id, event in zip(active_ids, active)}
            job["payload"] = digest_payload(active)
            job["payload"]["tag"] = f"chumei-digest-{job['id']}"
        else:
            job["payload"] = event_payload(active[0])
        job["payload_event_ids"] = list(active_ids)
    elif job["digest"] and job["payload_event_ids"] != active_ids:
        if not set(active_ids).issubset(job["payload_event_ids"]):
            raise ValueError("cannot expand frozen push payload")
        payload = digest_payload([job["payload_members"][eid] for eid in active_ids])
        payload["tag"] = job["payload"]["tag"]
        job["payload"] = payload
        job["payload_event_ids"] = list(active_ids)
    if job["kind"] == "reminder":
        when = "今天" if active[0]["start_at"][:10] == today.isoformat() else "明天"
        if when != job["payload_when"]:
            job["payload"]["title"] = when + job["payload"]["title"][len(job["payload_when"]):]
            job["payload_when"] = when
    return copy.deepcopy(job["payload"])


def send_deliveries(subs, events, state, going, *, today=None, clock=None, checkpoint=None):
    """Attempt each due job once; persist intent and result around every send.

    A transport timeout or interrupted attempt is uncertain, never a receipt.
    Retries use a bounded budget and backoff without sleeping in the publisher.
    Checkpoint failures escape immediately, so no later recipient is sent.
    """
    today = today or date.today()
    clock = clock or time.time
    checkpoint = checkpoint or save_state
    by_id = {e["id"]: e for e in events if e.get("id")}
    for event in events:
        for alias in event.get("merged_event_ids", []):
            by_id.setdefault(alias, event)
    eligible = {e["id"] for e in eligible_events(events, today.isoformat())}
    stats = {"sent": 0, "gone": 0, "failed": 0, "cancelled": 0}
    # A gone device remains terminal even if pruning subscriptions failed on a
    # previous invocation. Never send later jobs from this loaded subs snapshot.
    gone = {job["device"] for job in state["deliveries"].values() if job["status"] == "gone"}
    for key in gone:
        if key in subs:
            pc.prune_endpoint(subs[key]["sub"]["endpoint"])
    for job in state["deliveries"].values():
        if job["status"] in pd.TERMINAL:
            continue
        stamp = now_iso()
        key = job["device"]
        record = subs.get(key)
        if key in gone or record is None:
            clear_failure_diagnostic(job)
            pd.finish(state, job, "gone" if key in gone else "cancelled", stamp)
            checkpoint(state)
            continue
        active = []
        active_ids = []
        for event_id in job["event_ids"]:
            device = pd.group(state, job["kind"], event_id, job.get("user_id"))["devices"][key]
            if device["status"] in pd.TERMINAL:
                continue
            event = by_id.get(event_id)
            if event:
                aliases = [event["id"], *event.get("merged_event_ids", [])]
                bucket = state["sent"] if job["kind"] == "event" else state["reminders"]
                identifiers = aliases if job["kind"] == "event" else [
                    f"{job['user_id']}:{alias}" for alias in aliases]
                if pd.legacy_fence(bucket, identifiers):
                    pd.receipt(state, job, event_id, "cancelled", stamp)
                    continue
                prior = [bucket.get(identifier, {}) for identifier in identifiers]
                if any((entry.get("devices", {}).get(key) or {}).get("status") == "sent" for entry in prior):
                    pd.receipt(state, job, event_id, "sent", stamp)
                    continue
            valid = bool(event and event["id"] in eligible)
            if event and job["kind"] == "reminder":
                aliases = {event["id"], *event.get("merged_event_ids", [])}
                # Going reminders intentionally do not use the new-post age
                # fence: a months-old announcement still needs its reminder.
                valid = (event.get("status") != "rejected"
                         and record.get("user_id") == job["user_id"]
                         and bool(aliases.intersection(going.get(job["user_id"], [])))
                         and event["start_at"][:10] in {
                             today.isoformat(), (today + timedelta(days=1)).isoformat()})
            if valid:
                if event["id"] not in {e["id"] for e in active}:
                    active.append(event)
                    active_ids.append(event_id)
            else:
                pd.receipt(state, job, event_id, "cancelled", stamp)
        if not active:
            clear_failure_diagnostic(job)
            pd.finish(state, job, "cancelled", stamp)
            stats["cancelled"] += 1
            checkpoint(state)
            continue
        if job["attempts"] and "payload" not in job:
            # Upgrading an uncertain older attempt cannot recover its bytes.
            # Keep it unresolved for review rather than inventing retry content.
            job["reason"] = "missing_frozen_payload"
            pd.finish(state, job, "exhausted", stamp)
            checkpoint(state)
            continue
        if job["attempts"] and job["kind"] == "event" and "recipient_user_id" not in job:
            # An older upgraded attempt may have frozen bytes but no account.
            # Today's subscription cannot establish who that attempt targeted.
            job["reason"] = "missing_recipient_binding"
            pd.finish(state, job, "exhausted", stamp)
            checkpoint(state)
            continue
        if job["attempts"] >= pd.MAX_ATTEMPTS:
            pd.finish(state, job, "exhausted", stamp)
            checkpoint(state)
            continue
        now = clock()
        if job.get("next_attempt_at", 0) > now:
            continue
        # Upgrade unattempted event jobs with the first observed binding, even
        # when unlinked (None). Older reminders already freeze their user_id.
        # Persist this together with the payload and intent before transport.
        job.setdefault("recipient_user_id", job["user_id"] if job["kind"] == "reminder"
                       else record.get("user_id"))
        payload = frozen_payload(job, active, active_ids, today)
        # A new attempt must not retain diagnostics from a previous failure.
        # Keep existing error_type behavior for compatibility with older state.
        clear_failure_diagnostic(job)
        job["attempts"] += 1
        job.update(attempted_at=stamp, next_attempt_at=now + pd.retry_delay(job["attempts"]))
        pd.finish(state, job, "sending", stamp)
        checkpoint(state)  # No network call if durable intent cannot be saved.
        # Reload after checkpoint I/O and immediately before transport. A frozen
        # cohort never grants permission to contact a revoked/rebound device.
        # Atomic subscription replacement gives a complete snapshot; requests
        # already in flight may finish after a later unsubscribe.
        current = pc.load_subs()["subs"].get(key)
        binding = job["recipient_user_id"]
        if current is None or current.get("user_id") != binding:
            pd.finish(state, job, "cancelled", now_iso())
            stats["cancelled"] += 1
            checkpoint(state)
            continue
        record = current
        try:
            pc.send_push(record, payload, ttl=6 * 3600 if job["kind"] == "reminder" else 43200)
        except pc.PushGone:
            pd.finish(state, job, "gone", now_iso())
            gone.add(key)
            stats["gone"] += 1
            checkpoint(state)  # Keep the gone receipt even if pruning fails.
            pc.prune_endpoint(record["sub"]["endpoint"])
        except Exception as exc:
            job["error_type"] = type(exc).__name__
            job.update(failure_diagnostic(exc))
            pd.finish(state, job, "retry", now_iso())
            if job["attempts"] >= pd.MAX_ATTEMPTS:
                pd.finish(state, job, "exhausted", now_iso())
            stats["failed"] += 1
            checkpoint(state)
            # Provider exception strings may contain private endpoint URLs.
            print(f"push: {job['kind']} delivery failed ({type(exc).__name__}); "
                  f"attempt {job['attempts']}/{pd.MAX_ATTEMPTS}", file=sys.stderr)
        else:
            pd.finish(state, job, "sent", now_iso())
            stats["sent"] += 1
            checkpoint(state)
    return stats


def run(args):
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
        stamp = now_iso()
        state = pd.migrate({"initialized_at": stamp,
                            "sent": {e["id"]: {"baselined_at": stamp} for e in baseline}})
        save_state(state)
        print(f"push: initialized baseline ({len(baseline)} upcoming events)")
        return 0

    pending = pending_events(events, state)
    if is_silent_hour() and not args.ignore_quiet_hours:
        print(f"push: quiet hours, {len(pending)} new events and queued retries held for morning")
        return 0

    subs = pc.load_subs()["subs"]
    linked = any(record.get("user_id") for record in subs.values())
    # A DB failure is not evidence that a user withdrew their going/follows.
    # Do not permanently cancel reminder retries or freeze wrong cohorts.
    going = pc.account_going(strict=True) if linked else {}
    follows = pc.account_follows(strict=True) if linked else {}
    n_remind = queue_reminders(subs, events, going, state)
    queue_events(subs, pending, state, pc.load_org_sids(), follows)
    queued = [job for job in state["deliveries"].values() if job["status"] not in pd.TERMINAL]
    if args.dry_run:
        print(f"push dry-run: {len(pending)} new events, {len(subs)} subs, "
              f"{len(queued)} queued deliveries, {n_remind} new reminders")
        return 0

    save_state(state)  # Recipient cohorts are durable before the first push.
    stats = send_deliveries(subs, events, state, going)
    unresolved = sum(job["status"] in {"retry", "sending", "exhausted"}
                     for job in state["deliveries"].values())
    state["last_run_at"] = now_iso()
    if not unresolved:
        state["last_success_at"] = now_iso()
    save_state(state)
    print(f"push: {len(pending)} new events → {stats['sent']} notifications, "
          f"pruned {stats['gone']}, failed {stats['failed']}, unresolved {unresolved}; "
          f"{n_remind} new reminders")
    return 1 if unresolved else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show pending/deliveries without sending")
    parser.add_argument("--ignore-quiet-hours", action="store_true")
    args = parser.parse_args()

    try:
        with nullcontext(True) if args.dry_run else pd.publisher_lock(STATE_PATH) as acquired:
            if not acquired:
                print("push: another publisher is running")
                return 0
            return run(args)
    except (OSError, KeyError, ValueError) as exc:
        # Avoid leaking malformed state, subscription credentials or endpoints.
        print(f"push: FAILED ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
