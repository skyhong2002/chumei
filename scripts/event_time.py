"""Shared activity lifetime rules for feeds and upcoming lists.

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
