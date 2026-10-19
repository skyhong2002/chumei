"""Shared activity lifetime and timestamp evidence rules for feeds.

Date-only and all-day end dates are inclusive. Timed ends are exclusive instants.
Without a usable end, keep the event through its start day in the supplied zone
(Taipei for naive/date-only values), since its duration is unknown.
"""

from datetime import datetime, time, timedelta

from chumei_lib import TZ_TAIPEI


def event_datetime(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=TZ_TAIPEI)


def validated_evidence_time(value, now, require_zone=False):
    """Normalize usable, non-future evidence; legacy naive values mean Taipei."""
    ceiling = now if isinstance(now, datetime) else event_datetime(now)
    if ceiling is None:
        return ""
    if ceiling.tzinfo is None:
        ceiling = ceiling.replace(tzinfo=TZ_TAIPEI)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if require_zone and parsed.tzinfo is None:
        return ""
    parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=TZ_TAIPEI)
    if parsed > ceiling:
        return ""
    return parsed.astimezone(TZ_TAIPEI).isoformat(timespec="seconds")


def first_valid_evidence_time(candidates, now):
    """Validate each candidate before selecting it, so bad evidence falls through."""
    return next((stamp for raw in candidates
                 if (stamp := validated_evidence_time(raw, now))), "")


def event_discovery_time(event, now):
    """Stable event/source observation only; start and mutable fetch are excluded."""
    source = event.get("source") or {}
    return first_valid_evidence_time((
        event.get("first_seen"), event.get("first_seen_at"),
        source.get("first_seen"), source.get("first_seen_at"),
    ), now)


def event_end(event):
    start = event_datetime(event.get("start_at"))
    if start is None:
        return None
    raw_end = event.get("end_at")
    end = event_datetime(raw_end)
    if end is None or end < start:
        end = start
        date_end = True
    else:
        date_end = len(str(raw_end)) == 10
    if event.get("all_day") or date_end:
        return datetime.combine(end.date() + timedelta(days=1), time.min, end.tzinfo)
    return end


def event_has_not_ended(event, now=None):
    end = event_end(event)
    now = now or datetime.now(TZ_TAIPEI)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_TAIPEI)
    return end is not None and end > now
