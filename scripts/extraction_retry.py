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
TRANSIENT = {"timeout", "connection", "unavailable", "rate_limit", "quota", "invalid_response"}
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
    detail = str(error).lower()
    if response is not None:
        detail += " " + response.text[:2000].lower()
    if any(term in detail for term in ("insufficient_quota", "quota exceeded", "quota exhausted",
                                       "exhausted quota", "credit balance", "billing", "budget exceeded")):
        return "quota"
    if status in {401, 403} or re.search(r"\b(?:401|403)\b", detail) or "missing chumei_llm_api_key" in detail:
        return "authentication"
    # The legacy gateway discards 429 response bodies. Treat an opaque 429 as a
    # possible exhausted budget rather than probing many posts every half hour.
    if status is None and "gateway unavailable" in detail and re.search(r"\b429\b", detail):
        return "quota"
    if status == 429 or re.search(r"\b429\b", detail) or "rate limit" in detail:
        return "rate_limit"
    if isinstance(error, requests.Timeout) or "timeout" in detail or "timed out" in detail:
        return "timeout"
    if isinstance(error, requests.ConnectionError) or "connection" in detail:
        return "connection"
    if status in {408, 425} or (status is not None and 500 <= status < 600) or re.search(r"\b5\d\d\b", detail) or "gateway unavailable" in detail:
        return "unavailable"
    if isinstance(error, (json.JSONDecodeError, ValueError, TypeError, KeyError, AttributeError)) or any(
            term in detail for term in ("expecting value", "expecting property name", "unterminated string")):
        return "invalid_response"
    if (status is not None and 400 <= status < 500) or re.search(r"\b400\b", detail):
        return "permanent"
    return "unknown"


def retry_delay(kind, attempts):
    minimum = {"quota": MAX_DELAY, "authentication": MAX_DELAY, "rate_limit": 1800}.get(kind, BASE_DELAY)
    return min(MAX_DELAY, max(minimum, BASE_DELAY * 4 ** min(max(attempts - 1, 0), 8)))


def error_record(error, previous=None, *, now=None):
    now = now or utcnow()
    previous = previous or {}
    attempts = int(previous.get("attempts", 1 if previous.get("error") else 0)) + 1
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


def retry_due(record, prompt_version, *, now=None, retry_errors=False):
    now = now or utcnow()
    if not record:
        return True
    if not record.get("error"):
        return record.get("prompt_version") != prompt_version
    # A prompt change must not reset an exhausted provider-error budget.
    if record.get("exhausted") or int(record.get("attempts", 1)) >= MAX_ATTEMPTS:
        return False
    kind = record.get("error_kind") or classify_error(record["error"])
    if kind not in TRANSIENT and not retry_errors:
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
