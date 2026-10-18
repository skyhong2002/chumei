"""Bounded public-only HTTP transport for URLs originating in untrusted content.

Resolve once per hop and connect to that literal IP, retaining the original TLS
SNI/certificate hostname and Host header. Never use environment proxies or let a
library follow redirects or resolve the hostname again.
"""
from __future__ import annotations

import errno
import ipaddress
import re
import socket
import ssl
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from urllib.parse import urljoin, urlsplit

import requests
import urllib3


class UnsafeURL(ValueError):
    pass


def parse_public_url(url):
    if not isinstance(url, str) or len(url) > 4096 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
        raise UnsafeURL("invalid URL")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").encode("idna").decode("ascii").lower()
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except (ValueError, UnicodeError) as exc:
        raise UnsafeURL("invalid URL") from exc
    if (parts.scheme not in {"http", "https"} or not host or parts.username is not None
            or parts.password is not None or port != (443 if parts.scheme == "https" else 80)):
        raise UnsafeURL("only public HTTP(S) on standard ports is allowed")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        if ("." not in host or host.endswith((".localhost", ".local", ".internal", ".home", ".test"))
                or not re.fullmatch(r"[a-z0-9.-]+", host) or host.endswith(".")):
            raise UnsafeURL("invalid public hostname")
    else:
        if not _public_ip(addr):
            raise UnsafeURL("non-public address")
    return parts, host, port


def _public_ip(addr):
    # Reject IPv4 transition encodings as well as private/reserved/link-local IPs.
    return (addr.is_global and not addr.is_multicast
            and not (isinstance(addr, ipaddress.IPv6Address)
                     and (addr.ipv4_mapped or addr.sixtofour or addr.teredo
                          or addr in ipaddress.ip_network("64:ff9b::/96"))))


# The platform resolver does not accept a timeout. Limit both caller wait time
# and outstanding resolver jobs so stalled DNS cannot accumulate threads/jobs.
_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="public-dns")
_dns_slots = threading.BoundedSemaphore(4)


def _resolve_public_addresses(host, port, timeout=5):
    deadline = time.monotonic() + timeout
    if timeout <= 0 or not _dns_slots.acquire(timeout=timeout):
        raise TimeoutError("DNS lookup deadline exceeded")
    future = _dns_executor.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: _dns_slots.release())
    try:
        answers = future.result(timeout=max(0, deadline - time.monotonic()))
    except FutureTimeout as exc:
        raise TimeoutError("DNS lookup deadline exceeded") from exc
    addresses = {item[4][0] for item in answers}
    if not addresses or any(not _public_ip(ipaddress.ip_address(ip)) for ip in addresses):
        raise UnsafeURL("DNS returned a non-public address")
    return sorted(addresses)


def resolve_public(host, port, timeout=5):
    return _resolve_public_addresses(host, port, timeout=timeout)[0]


def _push_connect_addresses(addresses):
    """Use the original first address, then favor family diversity; at most three."""
    unique = []
    seen = set()
    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if parsed not in seen:
            seen.add(parsed)
            unique.append((address, parsed.version))
    first = unique[0]
    other = next((item for item in unique[1:] if item[1] != first[1]), None)
    ordered = [first] + ([other] if other is not None else [])
    ordered.extend(item for item in unique[1:] if item != other)
    return [address for address, _ in ordered[:3]]


def _can_retry_push_connect(error):
    """Only an unwrapped, known failure before TCP/TLS/HTTP can change IPs.

    urllib3's _new_conn raises NewConnectionError directly from an OSError.
    Its timeout/DNS branches and any ambiguous wrapper are deliberately excluded.
    Read built-in descriptors rather than exception text or spoofable __class__.
    """
    try:
        if (not issubclass(type(error), urllib3.exceptions.NewConnectionError)
                or issubclass(type(error), (urllib3.exceptions.NameResolutionError,
                                           urllib3.exceptions.SSLError,
                                           urllib3.exceptions.ProtocolError))):
            return False
        cause = BaseException.__cause__.__get__(error)
        if (not issubclass(type(cause), OSError)
                or issubclass(type(cause), (socket.gaierror, socket.herror,
                                           TimeoutError, ssl.SSLError))
                or BaseException.__cause__.__get__(cause) is not None):
            return False
        number = OSError.errno.__get__(cause)
        return type(number) is int and number in {
            errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ECONNREFUSED,
            errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT,
        }
    except Exception:
        return False


def request(url, *, method="GET", headers=None, data=None, max_bytes=8_000_000,
            timeout=25, max_redirects=5, _push_connect_fallback=False):
    deadline = time.monotonic() + timeout
    headers = {k: str(v) for k, v in (headers or {}).items()
               if k.lower() not in {"host", "accept-encoding", "connection"}}
    headers["Accept-Encoding"] = "identity"
    for hop in range(max_redirects + 1):
        parts, host, port = parse_public_url(url)
        dns_timeout = min(5, max(0, deadline - time.monotonic()))
        # A stream/iterable may raise a connection-shaped error after transmission.
        # Only immutable bytes (or no body) can use the pre-connect fallback.
        if (_push_connect_fallback and method == "POST" and parts.scheme == "https"
                and max_redirects == 0 and (data is None or type(data) is bytes)):
            addresses = _push_connect_addresses(_resolve_public_addresses(host, port, timeout=dns_timeout))
        else:
            addresses = [resolve_public(host, port, timeout=dns_timeout)]
        for candidate, ip in enumerate(addresses):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("outbound request deadline exceeded")
            pool_cls = urllib3.HTTPSConnectionPool if parts.scheme == "https" else urllib3.HTTPConnectionPool
            tls = {"assert_hostname": host, "server_hostname": host, "cert_reqs": "CERT_REQUIRED"} if parts.scheme == "https" else {}
            pool = pool_cls(ip, port=port, **tls)
            response = None
            try:
                try:
                    response = pool.urlopen(method, (parts.path or "/") + ("?" + parts.query if parts.query else ""),
                                            body=data, headers={**headers, "Host": f"[{host}]" if ":" in host else host},
                                            timeout=urllib3.Timeout(total=remaining, connect=min(5, remaining), read=min(5, remaining)),
                                            redirect=False, retries=False, preload_content=False)
                except Exception as exc:
                    if candidate + 1 < len(addresses) and _can_retry_push_connect(exc):
                        continue
                    raise
                if response.status in {301, 302, 303, 307, 308}:
                    if method != "GET" or hop == max_redirects or not response.headers.get("Location"):
                        raise UnsafeURL("redirect not allowed")
                    url = urljoin(url, response.headers["Location"])
                    break
                if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
                    raise UnsafeURL("compressed response not allowed")
                if int(response.headers.get("Content-Length", "0")) > max_bytes:
                    raise UnsafeURL("response too large")
                content = bytearray()
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("outbound request deadline exceeded")
                    chunk = response.read1(min(65536, max_bytes + 1 - len(content)), decode_content=False)
                    if not chunk:
                        break
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise UnsafeURL("response too large")
                result = requests.Response()
                result.status_code = response.status
                result.headers.update(response.headers)
                result._content = bytes(content)
                result.url = url
                result.encoding = requests.utils.get_encoding_from_headers(result.headers)
                return result
            finally:
                try:
                    if response is not None:
                        response.close()
                finally:
                    pool.close()
    raise UnsafeURL("too many redirects")


def get(url, **kwargs):
    return request(url, **kwargs)


# Browser push services used by Chrome/Edge, Firefox and Safari. Exact host
# matching is intentional: a user-controlled subdomain is never trusted.
PUSH_HOSTS = {"fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com"}


def validate_push_endpoint(url):
    parts, host, _ = parse_public_url(url)
    if parts.scheme != "https" or host not in PUSH_HOSTS or len(url) >= 1024:
        raise UnsafeURL("unsupported push service")
    return True


class PushSession:
    def post(self, url, *, data=None, headers=None, timeout=None, **kwargs):
        validate_push_endpoint(url)
        return request(url, method="POST", data=data, headers=headers, timeout=15,
                       max_bytes=64_000, max_redirects=0, _push_connect_fallback=True)


def secure_browser_context(browser, **kwargs):
    """Render passive content; browser networking is offline, including workers.

    Each document/image/style/font response is supplied by our pinned transport.
    Never route.continue_() or route.fetch(): those would re-resolve in Chromium.
    """
    context = browser.new_context(**kwargs, java_script_enabled=False, service_workers="block", offline=True)
    budget = {"requests": 0, "bytes": 0}
    deadline = time.monotonic() + 30

    def route_request(route):
        budget["requests"] += 1
        remaining = deadline - time.monotonic()
        if (remaining <= 0 or budget["requests"] > 60 or budget["bytes"] >= 16_000_000
                or route.request.method != "GET"
                or route.request.resource_type not in {"document", "stylesheet", "image", "font"}):
            return route.abort()
        try:
            response = get(route.request.url, timeout=min(10, remaining),
                           max_bytes=min(4_000_000, 16_000_000 - budget["bytes"]))
            budget["bytes"] += len(response.content)
            route.fulfill(status=response.status_code, body=response.content,
                          headers={k: v for k, v in response.headers.items()
                                   if k.lower() in {"content-type", "access-control-allow-origin"}})
        except Exception:
            route.abort()
    context.route("**/*", route_request)
    return context
