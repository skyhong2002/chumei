"""Free web Story viewers tried before the Apify Story actor.

Both sites look Stories up on their own servers and answer anonymous visitors,
so these lookups never leave Chumei's IP for Instagram. Neither publishes an
API or a quota. Each viewer therefore gets a conservative daily lookup cap,
lookups are spaced apart, and the first sign of throttling or of a changed
protocol parks the viewer for hours. That state lives in
``state/story_viewers.json`` so it holds across pipeline runs.

A viewer returns the account's live Stories as dicts with ``id`` (Instagram's
story pk, the same id the Apify actor reports), ``taken_at`` (epoch seconds),
``image_url`` (a still image, also for video Stories) and ``is_video``.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from chumei_lib import ROOT


STATE_PATH = ROOT / "state" / "story_viewers.json"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/141.0 Safari/537.36")
MIN_GAP_SECONDS = 10.0
PARK_HOURS = 6.0
# Consecutive "not available" answers that look like throttling, not accounts.
MAX_CONSECUTIVE_MISSES = 3


class ViewerUnavailable(RuntimeError):
    """The viewer refused or no longer speaks the expected protocol."""


class AccountUnavailable(RuntimeError):
    """The viewer answered, but has nothing for this account (private, renamed)."""


def _utc_day(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")


@contextmanager
def _state(path: Path):
    """Lock, read and (also when the body raises) write back the viewer state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        try:
            yield data
        finally:
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            tmp.replace(path)


class Viewer:
    name = ""
    daily_limit = 0

    def __init__(self, *, session: requests.Session | None = None, timeout: float = 30.0):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.timeout = timeout

    def fetch(self, username: str) -> list[dict]:
        raise NotImplementedError


class InstaStoriesViewer(Viewer):
    """insta-stories-viewer.com: one Socket.IO search over HTTP long-polling."""

    name = "insta-stories-viewer"
    base = "https://insta-stories-viewer.com"
    image_base = "https://cdn.iqsaved.com/img2.php?url="
    daily_limit = 150

    def _socket(self, method: str, path: str, data: str | None = None) -> str:
        response = self.session.request(
            method, self.base + path, data=data, timeout=self.timeout,
            headers={"Content-Type": "text/plain;charset=UTF-8"} if data is not None else None,
        )
        if response.status_code != 200:
            raise ViewerUnavailable(f"{self.name}: HTTP {response.status_code} on {path.split('?')[0]}")
        return response.text

    def fetch(self, username: str) -> list[dict]:
        self.session.headers.update({"Origin": self.base, "Referer": f"{self.base}/{username}/"})
        connect = self.session.get(f"{self.base}/connect/", timeout=self.timeout)
        if connect.status_code != 200:
            raise ViewerUnavailable(f"{self.name}: HTTP {connect.status_code} on /connect/")
        try:
            token = connect.json()["token"]
            path = "/socket.io/?EIO=4&transport=polling"
            path += "&sid=" + json.loads(self._socket("GET", path)[1:])["sid"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ViewerUnavailable(f"{self.name}: unexpected handshake ({exc})") from exc
        self._socket("POST", path, "40")
        self._socket("GET", path)
        search = ["search", {"username": username, "date": int(time.time() * 1000),
                             "token": token, "serverType": "stories"}]
        self._socket("POST", path, "42" + json.dumps(search, separators=(",", ":")))
        for _ in range(6):
            body = self._socket("GET", path)
            if body == "2":  # Engine.IO ping
                self._socket("POST", path, "3")
                continue
            if "searchResult" in body:
                return self._parse(body[body.index("["):])
        raise ViewerUnavailable(f"{self.name}: no search result")

    def _parse(self, body: str) -> list[dict]:
        try:
            data = json.loads(body)[1]["data"]
            if data.get("status") == "success":
                return [{
                    "id": str(reel["id"]),
                    "taken_at": float(reel["taken_at"]),
                    "image_url": self.image_base + quote(str(reel.get("display_url") or reel["thumbnail_src"]), safe=""),
                    "is_video": str(reel.get("is_video")).lower() == "true",
                } for reel in (data.get("user") or {}).get("reels") or []
                    if reel.get("id") and reel.get("taken_at")
                    and (reel.get("display_url") or reel.get("thumbnail_src"))]
            code = data.get("code")
        except (TypeError, ValueError, KeyError, IndexError, AttributeError) as exc:
            raise ViewerUnavailable(f"{self.name}: unreadable result ({exc!r})") from exc
        # 430 is what the site answers for missing and private accounts.
        if code == 430:
            raise AccountUnavailable(f"{self.name}: code 430")
        raise ViewerUnavailable(f"{self.name}: code {code}")


class Inflact(Viewer):
    """inflact.com Story viewer: a signed JSON API, three free views a day."""

    name = "inflact"
    base = "https://inflact.com"
    page = "https://inflact.com/instagram-stories-viewer/"
    daily_limit = 3
    # The page's bundle assembles the HMAC key from XOR-masked char arrays:
    # [s(c(i).join("")),s(c(d).join("")),...].join("")
    KEY_PARTS = re.compile(r'\[((?:\w+\(\w+\(\w+\)\.join\(""\)\),?){4,})\]\.join\(""\)')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.csrf = self.key = None
        self.client_id = secrets.token_hex(16)

    def _bootstrap(self) -> None:
        page = self.session.get(self.page, timeout=self.timeout)
        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text)
        if page.status_code != 200 or not csrf:
            raise ViewerUnavailable(f"{self.name}: viewer page HTTP {page.status_code}")
        self.csrf = csrf.group(1)
        for src in re.findall(r'<script[^>]+src="(/static/js/[^"]+)"', page.text):
            script = self.session.get(self.base + src, timeout=self.timeout).text
            if "X-Client-Signature" in script and (key := self.signing_key(script)):
                self.key = key
                return
        raise ViewerUnavailable(f"{self.name}: signing key not found")

    @classmethod
    def signing_key(cls, script: str) -> str | None:
        assembly = cls.KEY_PARTS.search(script)
        if not assembly:
            return None
        names = re.findall(r'\w+\(\w+\((\w+)\)\.join', assembly.group(1))
        parts = []
        for name in names:
            # Minified names repeat across modules; the arrays sit next to the assembly.
            arrays = list(re.finditer(rf'(?<![\w$.]){re.escape(name)}=\[([\d,]+)\]', script))
            if not arrays:
                return None
            array = min(arrays, key=lambda match: abs(match.start() - assembly.start()))
            parts.append("".join(chr(int(code) ^ index)
                                 for index, code in enumerate(array.group(1).split(","))))
        return "".join(parts)

    def fetch(self, username: str) -> list[dict]:
        if not self.key:
            self._bootstrap()
        token = json.dumps({"timestamp": int(time.time()), "clientId": self.client_id,
                            "nonce": secrets.token_hex(16)}, separators=(",", ":")).encode()
        response = self.session.post(
            f"{self.base}/downloader/api/viewer/stories/", json={"url": username, "cursor": ""},
            timeout=self.timeout, headers={
                "Origin": self.base, "Referer": self.page, "X-CSRF-Token": self.csrf,
                "X-Client-Token": base64.b64encode(token).decode(),
                "X-Client-Signature": hmac.new(self.key.encode(), token, hashlib.sha256).hexdigest(),
            },
        )
        try:
            payload = response.json()
            if response.status_code != 200 or payload.get("status") != "success":
                raise ViewerUnavailable(f"{self.name}: {payload.get('message') or response.status_code}")
            return [{
                "id": str(story["id"]),
                "taken_at": float(story["takenAt"]),
                "image_url": str(story["displayUrl"]),
                "is_video": bool(story.get("videoUrl")),
            } for story in (payload.get("data") or {}).get("stories") or []
                if story.get("id") and story.get("takenAt") and story.get("displayUrl")]
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise ViewerUnavailable(f"{self.name}: HTTP {response.status_code}, unreadable ({exc!r})") from exc


VIEWERS = (InstaStoriesViewer, Inflact)


class ViewerPool:
    """Hands out viewers that still have allowance today, and paces their use."""

    def __init__(self, viewers=VIEWERS, *, path: Path = STATE_PATH, sleep=time.sleep, clock=time.time):
        self.path, self.sleep, self.clock = path, sleep, clock
        self.viewers = [viewer() for viewer in viewers]

    def _row(self, state: dict, viewer: Viewer) -> dict:
        row = state.setdefault(viewer.name, {})
        today = _utc_day(self.clock())
        if row.get("day") != today:
            row.update(day=today, lookups=0)
        return row

    def _usable(self, row: dict, viewer: Viewer) -> bool:
        return (float(row.get("parkedUntil") or 0) <= self.clock()
                and row["lookups"] < viewer.daily_limit)

    def available(self) -> list[Viewer]:
        with _state(self.path) as state:
            return [viewer for viewer in self.viewers if self._usable(self._row(state, viewer), viewer)]

    def lookup(self, viewer: Viewer, username: str) -> list[dict]:
        """Run one lookup; parks the viewer on refusal and re-raises."""
        with _state(self.path) as state:
            row = self._row(state, viewer)
            # Another collector may have used the last lookup or parked it meanwhile.
            if not self._usable(row, viewer):
                raise ViewerUnavailable(f"{viewer.name}: no allowance left")
            start = max(self.clock(), float(row.get("lastRequestAt") or 0) + MIN_GAP_SECONDS)
            row["lastRequestAt"] = start
            row["lookups"] += 1
        if (wait := start - self.clock()) > 0:
            self.sleep(wait)
        try:
            stories = viewer.fetch(username)
        except AccountUnavailable as exc:
            with _state(self.path) as state:
                row = self._row(state, viewer)
                row["misses"] = int(row.get("misses") or 0) + 1
                if row["misses"] >= MAX_CONSECUTIVE_MISSES:
                    self._park(row, f"{row['misses']} accounts unavailable in a row")
                    raise ViewerUnavailable(f"{viewer.name}: {exc}") from exc
            raise
        except (ViewerUnavailable, requests.RequestException) as exc:
            with _state(self.path) as state:
                self._park(self._row(state, viewer), str(exc))
            raise ViewerUnavailable(str(exc)) from exc
        with _state(self.path) as state:
            row = self._row(state, viewer)
            row.update(misses=0, lastSuccessAt=self.clock(), lastError="")
        return stories

    def _park(self, row: dict, reason: str) -> None:
        row.update(parkedUntil=self.clock() + PARK_HOURS * 3600, lastError=reason[:200], misses=0)
