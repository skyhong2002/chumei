"""Bounded public, logged-out Threads fallback; no env/config/state imports.

RSSHub stays first. One account shares a 30 second scheduling deadline, at
most seven requests (RSSHub, three profile GETs, two metadata scripts, one
timeline POST), and 4 MiB per response. Socket timeouts are at most 10 seconds;
an in-flight read may cross the scheduling deadline before it returns. Only ephemeral public-profile cookies are retained,
for one account. No paid provider, authenticated API, retry or pagination.
"""
from __future__ import annotations

import datetime as dt
import html
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

USER_AGENT = "ChumeiSocialWatcher/1.0"

# Public, logged-out Threads protocol constants from the existing Harmonica adapter.
THREADS_BASE_URL = "https://www.threads.com"
THREADS_GRAPHQL_OPERATION = "BarcelonaProfileThreadsTabRefetchableDirectQuery"
THREADS_GRAPHQL_FALLBACK_DOC_ID = "27422205010763282"
THREADS_WEB_APP_ID = "238260118697367"
THREADS_ASBD_ID = "359341"
THREADS_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
THREADS_LSD_RE = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')
THREADS_PROFILE_USER_ID_RE = re.compile(
    r'"initial_thread_count":\d+.*?"user_id":"(\d+)"',
    re.DOTALL,
)
THREADS_SCRIPT_SRC_RE = re.compile(r'<script[^>]+src="(https://static\.cdninstagram\.com/[^"]+\.js)"')
THREADS_QUERY_DOC_ID_RE = re.compile(
    rf'{THREADS_GRAPHQL_OPERATION}_threadsRelayOperation".*?exports="(\d+)"',
    re.DOTALL,
)
THREADS_RELAY_VARIABLE_RE = re.compile(r'name:"(__relay_internal__pv__[A-Za-z0-9_]+)"')
THREADS_RELAY_TRUE_VARIABLES = {
    "__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider",
    "__relay_internal__pv__BarcelonaHasDearAlgoConsumptionrelayprovider",
    "__relay_internal__pv__BarcelonaHasGameScoreSharerelayprovider",
    "__relay_internal__pv__BarcelonaHasMusicrelayprovider",
    "__relay_internal__pv__BarcelonaHasPublicViewCountCardrelayprovider",
    "__relay_internal__pv__BarcelonaHasViewerRepliedrelayprovider",
    "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider",
}
THREADS_RELAY_DEFAULT_VARIABLES = THREADS_RELAY_TRUE_VARIABLES | {
    "__relay_internal__pv__BarcelonaCanSeeSponsoredContentrelayprovider",
    "__relay_internal__pv__BarcelonaGenAIRepliesEnabledrelayprovider",
    "__relay_internal__pv__BarcelonaHasCommunityEntityCardrelayprovider",
    "__relay_internal__pv__BarcelonaHasCommunityTopContributorsrelayprovider",
    "__relay_internal__pv__BarcelonaHasDearAlgoWebProductionrelayprovider",
    "__relay_internal__pv__BarcelonaHasEventBadgerelayprovider",
    "__relay_internal__pv__BarcelonaHasGhostPostEmojiActivationrelayprovider",
    "__relay_internal__pv__BarcelonaHasMessagingrelayprovider",
    "__relay_internal__pv__BarcelonaHasNewspaperLinkStylerelayprovider",
    "__relay_internal__pv__BarcelonaHasPodcastTextFragmentsrelayprovider",
    "__relay_internal__pv__BarcelonaHasPrivateRepliesDeprecationrelayprovider",
    "__relay_internal__pv__BarcelonaHasProfileSelfReplyContextrelayprovider",
    "__relay_internal__pv__BarcelonaHasScorecardCommunityrelayprovider",
    "__relay_internal__pv__BarcelonaHasSportTeamAllegianceCardrelayprovider",
    "__relay_internal__pv__BarcelonaHasWebFaviconsrelayprovider",
    "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider",
    "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider",
    "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider",
    "__relay_internal__pv__BarcelonaIsSearchDiscoveryEnabledrelayprovider",
    "__relay_internal__pv__BarcelonaShouldFulfillLightboxQueryrelayprovider",
    "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider",
}
THREADS_TOTAL_TIMEOUT_SECS = 30
THREADS_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
THREADS_MAX_METADATA_SCRIPTS = 2
_THREADS_QUERY_METADATA_CACHE = None

class _MeteredOpener:
    """Report each actual HTTP attempt without retaining response data."""
    def __init__(self, opener, service, record_request):
        self.opener, self.service, self.record_request = opener, service, record_request
        self.count = 0

    def open(self, request, timeout):
        self.count += 1
        try:
            response = self.opener.open(request, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, OSError):
            if self.record_request:
                self.record_request(self.service, ok=False, source_count=int(self.count == 1))
            raise
        if self.record_request:
            self.record_request(self.service, ok=True, source_count=int(self.count == 1))
        return response


class _NoThreadsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _threads_profile_redirect(previous: str, location: str) -> str:
    target = urllib.parse.urljoin(previous, location)
    old, new = urllib.parse.urlsplit(previous), urllib.parse.urlsplit(target)
    try:
        valid = (old.scheme == new.scheme == "https"
                 and old.hostname in {"www.threads.com", "threads.com"}
                 and new.hostname in {"www.threads.com", "threads.com"}
                 and new.port in (None, 443) and not new.username and not new.password
                 and not new.query and not new.fragment
                 and re.fullmatch(r"/@[A-Za-z0-9._]{1,30}/?", new.path)
                 and old.path.rstrip("/") == new.path.rstrip("/"))
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError("Threads public profile redirect rejected")
    return target


def _threads_profile_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity",
        "User-Agent": THREADS_USER_AGENT,
    })


def _threads_read(opener, request, *, deadline: float, stage: str,
                  profile_redirects: bool = False) -> tuple[bytes, str]:
    """Bound each response and share one source deadline; never retry a request.

    Only profile GETs can follow up to two canonical same-profile redirects.
    Redirects use newly constructed profile headers, never ephemeral API headers.
    """
    for redirect in range(3 if profile_redirects else 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Threads source request deadline exceeded")
        try:
            with opener.open(request, timeout=min(10, remaining)) as response:
                if response.status != 200:
                    raise RuntimeError(f"Threads {stage} response not successful")
                if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
                    raise RuntimeError(f"Threads {stage} compressed response rejected")
                chunks = bytearray()
                while True:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Threads source request deadline exceeded")
                    chunk = response.read(min(65536, THREADS_MAX_RESPONSE_BYTES + 1 - len(chunks)))
                    if not chunk:
                        break
                    chunks.extend(chunk)
                    if len(chunks) > THREADS_MAX_RESPONSE_BYTES:
                        raise RuntimeError(f"Threads {stage} response too large")
                return bytes(chunks), request.full_url
        except urllib.error.HTTPError as exc:
            try:
                location = exc.headers.get("Location") if exc.headers else None
                if (profile_redirects and request.get_method() == "GET" and redirect < 2
                        and exc.code in {301, 302, 303, 307, 308} and location):
                    request = _threads_profile_request(_threads_profile_redirect(request.full_url, location))
                    continue
                raise RuntimeError(f"Threads {stage} HTTP failure ({exc.code})") from None
            finally:
                exc.close()
        except (urllib.error.URLError, TimeoutError, OSError):
            # No endpoint, ephemeral token, response body or raw exception text.
            raise RuntimeError(f"Threads {stage} transport unavailable") from None
    raise RuntimeError("Threads public profile redirect budget exceeded")


def _threads_query_metadata(opener, profile_html: str, *, deadline: float) -> tuple[str, set[str]]:
    global _THREADS_QUERY_METADATA_CACHE
    if _THREADS_QUERY_METADATA_CACHE is not None:
        return _THREADS_QUERY_METADATA_CACHE
    urls = list(dict.fromkeys(html.unescape(url) for url in THREADS_SCRIPT_SRC_RE.findall(profile_html)))
    for url in list(reversed(urls))[:THREADS_MAX_METADATA_SCRIPTS]:
        parsed = urllib.parse.urlsplit(url)
        try:
            valid = (parsed.scheme == "https" and parsed.hostname == "static.cdninstagram.com"
                     and parsed.port in (None, 443) and not parsed.username and not parsed.password
                     and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            continue
        try:
            raw, _ = _threads_read(opener, urllib.request.Request(url, headers={
                "User-Agent": THREADS_USER_AGENT, "Accept-Encoding": "identity"}),
                deadline=deadline, stage="metadata")
        except RuntimeError:
            continue
        script = raw.decode("utf-8", "replace")
        match = THREADS_QUERY_DOC_ID_RE.search(script)
        if match:
            variables = set(THREADS_RELAY_VARIABLE_RE.findall(script))
            _THREADS_QUERY_METADATA_CACHE = (match.group(1), variables)
            return _THREADS_QUERY_METADATA_CACHE
    return THREADS_GRAPHQL_FALLBACK_DOC_ID, set(THREADS_RELAY_DEFAULT_VARIABLES)


def _threads_images(post: dict[str, Any]) -> list[str]:
    rows = post.get("carousel_media") if isinstance(post.get("carousel_media"), list) else [post]
    result = []
    for row in rows[:10]:
        if not isinstance(row, dict):
            continue
        image = row.get("image_versions2")
        candidates = image.get("candidates", []) if isinstance(image, dict) else []
        for options in (candidates,):
            if not isinstance(options, list) or not options or not isinstance(options[0], dict):
                continue
            url = options[0].get("url")
            if not isinstance(url, str) or len(url) > 4096:
                continue
            try:
                parsed = urllib.parse.urlsplit(url)
            except ValueError:
                continue
            if (parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                    and url not in result):
                result.append(url)
    return result


def normalize_threads_posts(source: dict[str, Any], payload: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Threads public timeline shape unavailable")
    data = payload.get("data") if isinstance(payload, dict) else None
    media = data.get("mediaData") if isinstance(data, dict) else None
    edges = media.get("edges") if isinstance(media, dict) else None
    if payload.get("errors") or not isinstance(edges, list):
        raise RuntimeError("Threads public timeline unavailable")
    username = source["username"].lstrip("@")
    rows, seen = [], set()
    valid_threads = False
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        items = node.get("thread_items") if isinstance(node, dict) else None
        if not isinstance(items, list):
            continue
        valid_threads = True
        for item in items:
            post = item.get("post") if isinstance(item, dict) else None
            if not isinstance(post, dict):
                continue
            author = post.get("user")
            if (not isinstance(author, dict) or not isinstance(author.get("username"), str)
                    or not re.fullmatch(r"[A-Za-z0-9._]{1,30}", author["username"])
                    or author["username"].casefold() != username.casefold()):
                continue
            code = post.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code) or code in seen:
                continue
            seen.add(code)
            caption = post.get("caption")
            text = caption.get("text", "") if isinstance(caption, dict) else caption
            stamp = post.get("taken_at")
            try:
                posted = (dt.datetime.fromtimestamp(stamp, dt.timezone.utc).isoformat(timespec="seconds")
                          if type(stamp) in (int, float) else "")
            except (ValueError, OverflowError, OSError):
                posted = ""
            # Chumei's existing RSS post identity is the shortcode, never numeric pk.
            rows.append({"post_id": code,
                         "url": f"{THREADS_BASE_URL}/@{urllib.parse.quote(author['username'])}/post/{code}",
                         "posted_at": posted, "text": text if isinstance(text, str) and text else "（純圖片貼文，內容見海報）",
                         "images": _threads_images(post)})
            if len(rows) >= max(1, min(limit, 15)):
                return rows
    if edges and not valid_threads:
        raise RuntimeError("Threads public timeline shape unavailable")
    return rows


def fetch_threads_graphql(source: dict[str, Any], *, limit: int, opener=None,
                         deadline: float | None = None, record_request=None) -> list[dict[str, Any]]:
    username = source.get("username")
    if not isinstance(username, str) or not re.fullmatch(r"@?[A-Za-z0-9._]{1,30}", username):
        raise RuntimeError("Threads public username invalid")
    username = username.lstrip("@")
    deadline = deadline if deadline is not None else time.monotonic() + THREADS_TOTAL_TIMEOUT_SECS
    cookies = http.cookiejar.CookieJar()
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),
                  urllib.request.HTTPCookieProcessor(cookies), _NoThreadsRedirect())
    opener = _MeteredOpener(opener, "Threads public logged-out", record_request)
    raw, profile_url = _threads_read(opener, _threads_profile_request(f"{THREADS_BASE_URL}/@{username}"),
                                    deadline=deadline, stage="profile", profile_redirects=True)
    profile = raw.decode("utf-8", "replace")
    lsd, user_id = THREADS_LSD_RE.search(profile), THREADS_PROFILE_USER_ID_RE.search(profile)
    if not lsd or not user_id:
        raise RuntimeError("Threads public profile metadata unavailable")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", lsd.group(1)) or len(user_id.group(1)) > 32:
        raise RuntimeError("Threads public profile metadata invalid")
    doc_id, names = _threads_query_metadata(opener, profile, deadline=deadline)
    variables = {"after": None, "allow_page_info_for_lox_user": True, "before": None,
                 "first": max(1, min(limit, 15)), "last": None, "userID": user_id.group(1)}
    variables.update({name: name in THREADS_RELAY_TRUE_VARIABLES for name in names})
    variables["__relay_internal__pv__BarcelonaHasProfileSelfReplyContextrelayprovider"] = False
    token = lsd.group(1)
    body = urllib.parse.urlencode({"lsd": token, "doc_id": doc_id,
        "fb_api_req_friendly_name": THREADS_GRAPHQL_OPERATION, "fb_api_caller_class": "RelayModern",
        "server_timestamps": "true", "variables": json.dumps(variables, separators=(",", ":"))}).encode()
    origin = "https://" + urllib.parse.urlsplit(profile_url).netloc
    request = urllib.request.Request(origin + "/graphql/query", data=body, method="POST", headers={
        "Accept": "*/*", "Accept-Encoding": "identity", "Content-Type": "application/x-www-form-urlencoded",
        "Origin": origin, "Referer": profile_url, "User-Agent": THREADS_USER_AGENT,
        "X-ASBD-ID": THREADS_ASBD_ID, "X-FB-Friendly-Name": THREADS_GRAPHQL_OPERATION,
        "X-FB-LSD": token, "X-IG-App-ID": THREADS_WEB_APP_ID,
        "X-LOGGED-OUT-THREADS-MIGRATED-REQUEST": "true",
        "X-Root-Field-Name": "xdt_api__v1__text_feed__user_id__profile__connection",
    })
    # Public session cookies stay in memory; no browser/account cookies or credentials.
    csrf = next((cookie.value for cookie in cookies if cookie.name == "csrftoken"), "")
    if csrf:
        request.add_header("X-CSRFToken", csrf)
    raw, _ = _threads_read(opener, request, deadline=deadline, stage="timeline")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise RuntimeError("Threads public timeline JSON unavailable") from None
    if not isinstance(payload, dict):
        raise RuntimeError("Threads public timeline shape unavailable")
    return normalize_threads_posts(source, payload, limit=limit)


def fetch_threads_source(source: dict[str, Any], *, rsshub_url: str, limit: int,
                         parse_rss, record_request=None) -> tuple[list[dict[str, Any]], str, str]:
    """Return posts, RSS avatar and backend; callback retains existing RSS parsing."""
    username = source.get("username")
    if not isinstance(username, str) or not re.fullmatch(r"@?[A-Za-z0-9._]{1,30}", username):
        raise RuntimeError("Threads public username invalid")
    deadline = time.monotonic() + THREADS_TOTAL_TIMEOUT_SECS
    opener = _MeteredOpener(urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoThreadsRedirect()),
                            "RSSHub", record_request)
    try:
        raw, _ = _threads_read(opener, urllib.request.Request(rsshub_url, headers={
            "User-Agent": USER_AGENT, "Accept-Encoding": "identity"}), deadline=deadline, stage="RSSHub")
        root = ET.fromstring(raw)
        if root.tag != "rss" or root.find("./channel") is None:
            raise RuntimeError("Threads RSSHub feed shape unavailable")
        posts = list(parse_rss(raw.decode("utf-8", "replace"), "threads"))[:limit]
        avatar = (root.findtext("./channel/image/url") or "").strip()
        return posts, avatar, "RSSHub"
    except (RuntimeError, ET.ParseError):
        # Failures propagate to fetch_social's unchanged per-account backoff.
        try:
            return fetch_threads_graphql(source, limit=limit, deadline=deadline, record_request=record_request), "", "Threads public logged-out"
        except RuntimeError:
            raise RuntimeError("Threads RSSHub and public fallback unavailable") from None
