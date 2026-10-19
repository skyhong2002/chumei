"""Persistent, bounded retry decisions; no sleeping or provider calls here."""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import math
import re

import requests

MAX_ATTEMPTS = 4
BASE_DELAY = 15 * 60
MAX_DELAY = 24 * 3600
TRANSIENT = {"timeout", "connection", "unavailable", "rate_limit", "quota", "invalid_response", "interrupted"}
GLOBAL_FAILURES = {"timeout", "connection", "unavailable", "rate_limit", "quota", "authentication"}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def utcnow():
    return datetime.now(timezone.utc)


def classify_error(error):
    """Inspect upstream detail but only persist/print a safe classification."""
    response = getattr(error, "response", None)
    status = response.status_code if response is not None else None
    # Parser positions (e.g. column 401) are not HTTP status codes. Shape errors
    # are item-local even when their text happens to contain gateway keywords.
    if isinstance(error, (json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError)):
        return "invalid_response"
    detail = str(error).lower()
    if response is not None:
        detail += " " + response.text[:2000].lower()
    if any(term in detail for term in ("insufficient_quota", "quota exceeded", "quota exhausted",
                                       "exhausted quota", "credit balance", "billing", "budget exceeded")):
        return "quota"
    if status is None:
        # Support the legacy gateway's opaque HTTP errors and '400: ...',
        # without interpreting arbitrary numbers in model/parser output.
        match = re.search(r"\bhttp(?:\s+status)?\s*[:=]?\s*([45]\d\d)\b", detail)
        match = match or re.match(r"\s*([45]\d\d)\s*:", detail)
        status = int(match.group(1)) if match else None
    if status in {401, 403} or "missing chumei_llm_api_key" in detail:
        return "authentication"
    # The legacy gateway discards 429 response bodies. Treat an opaque 429 as a
    # possible exhausted budget rather than probing many posts every half hour.
    if response is None and "gateway unavailable" in detail and status == 429:
        return "quota"
    if status == 429 or "rate limit" in detail:
        return "rate_limit"
    if isinstance(error, requests.Timeout) or "timeout" in detail or "timed out" in detail:
        return "timeout"
    if isinstance(error, requests.ConnectionError) or "connection" in detail:
        return "connection"
    if status in {408, 425} or (status is not None and 500 <= status < 600) or "gateway unavailable" in detail:
        return "unavailable"
    if any(term in detail for term in ("expecting value", "expecting property name", "unterminated string")):
        return "invalid_response"
    if status is not None and 400 <= status < 500:
        return "permanent"
    return "unknown"


def retry_delay(kind, attempts):
    minimum = {"quota": MAX_DELAY, "authentication": MAX_DELAY, "rate_limit": 1800}.get(kind, BASE_DELAY)
    return min(MAX_DELAY, max(minimum, BASE_DELAY * 4 ** min(max(attempts - 1, 0), 8)))


def attempt_count(record):
    return int((record or {}).get("attempts", 1 if (record or {}).get("error") else 0))


def error_record(error, previous=None, *, now=None, reserved=False):
    now = now or utcnow()
    previous = previous or {}
    attempts = attempt_count(previous) + (0 if reserved else 1)
    kind = classify_error(error)
    retryable = kind in TRANSIENT
    delay = retry_delay(kind, attempts)
    response = getattr(error, "response", None)
    if response is not None:
        header = response.headers.get("Retry-After")
        if header:
            try:
                seconds = float(header)
            except ValueError:
                try:
                    seconds = (parsedate_to_datetime(header) - now).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    seconds = 0
            # Honor longer upstream cooldowns as well as our own bounded backoff.
            if math.isfinite(seconds):
                delay = max(delay, min(seconds, 365 * 86400))
    retry_after = (now + timedelta(seconds=delay)).isoformat()
    return {"error": f"extraction failed ({kind})", "error_kind": kind,
            "attempts": attempts, "retryable": retryable,
            "retry_after": retry_after,
            "exhausted": attempts >= MAX_ATTEMPTS, "ts": now.isoformat()}


def retry_terminal(record):
    """Normalize legacy and current errors for automatic/manual recovery."""
    return bool(record and record.get("error") and (
        record.get("exhausted") or attempt_count(record) >= MAX_ATTEMPTS
        or record.get("retryable") is False
        or (record.get("error_kind") or classify_error(record["error"])) not in TRANSIENT))


def pending_record(previous, prompt_version, *, now=None):
    """An ambiguous/dead request consumes its reserved budget, even after restart."""
    now = now or utcnow()
    attempts = attempt_count(previous) + 1
    return {**(previous or {}), "prompt_version": prompt_version,
            "error": "extraction interrupted (pending request)", "error_kind": "interrupted",
            "attempts": attempts, "in_progress": True, "retryable": True,
            "exhausted": attempts >= MAX_ATTEMPTS, "ts": now.isoformat(),
            "retry_after": (now + timedelta(seconds=MAX_DELAY)).isoformat()}


def retry_due(record, prompt_version, *, now=None, retry_errors=False):
    now = now or utcnow()
    if not record:
        return True
    # Prompt upgrades, completed results and interrupted attempts share a budget.
    if record.get("exhausted") or attempt_count(record) >= MAX_ATTEMPTS:
        return False
    if not record.get("error"):
        return record.get("prompt_version") != prompt_version
    kind = record.get("error_kind") or classify_error(record["error"])
    if retry_terminal(record) and not retry_errors:
        return False
    due = timestamp(record.get("retry_after"))
    if due is None:
        # Legacy error records have only ts: migrate lazily without deleting cache.
        last = timestamp(record.get("ts"))
        if last is None:
            return True
        due = last + timedelta(seconds=retry_delay(kind, int(record.get("attempts", 1))))
    return now >= due


def gateway_blocked(record, *, now=None):
    due = timestamp((record or {}).get("retry_after"))
    return due is not None and (now or utcnow()) < due


class RequestDeferred(RuntimeError):
    """No provider attempt was admitted; leave its budget untouched."""


def admit_gateway_request(path, reserve=None):
    """Short shared gate: publication and admission have a common ordering.

    An admitted request may finish after another job opens the circuit. Never
    hold this lock during network I/O. Reserve durably before releasing it.
    """
    from pipeline_state import file_lock, read_json
    with file_lock(path.with_suffix(".lock")):
        if gateway_blocked(read_json(path, {})):
            raise RequestDeferred("gateway cooldown")
        return reserve() if reserve is not None else None


def record_gateway_failure(path, record):
    """Cooperate across extraction and submission jobs without shortening cooldown."""
    if record.get("error_kind") not in GLOBAL_FAILURES:
        return
    from pipeline_state import atomic_json, file_lock, read_json
    with file_lock(path.with_suffix(".lock")):
        previous = read_json(path, {})
        old, new = timestamp(previous.get("retry_after")), timestamp(record.get("retry_after"))
        if new is not None and (old is None or new > old):
            atomic_json(path, {k: record[k] for k in ("error_kind", "retry_after", "ts")})
