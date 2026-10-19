"""AST/fake transport tests; no product/package imports or real networking.

Run: /usr/bin/python3 -I -B tests/test_push_connect_fallback.py
"""
import ast
from concurrent.futures import TimeoutError as FutureTimeout
import errno
import ipaddress
from pathlib import Path
import re
import socket
import ssl
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urljoin, urlsplit


class ConnectTimeoutError(Exception):
    pass


class NewConnectionError(ConnectTimeoutError):
    pass


class NameResolutionError(NewConnectionError):
    pass


class SSLError(Exception):
    pass


class ProtocolError(Exception):
    pass


class ReadTimeoutError(Exception):
    pass


def chained(error, cause):
    error.__cause__ = cause
    return error


def failed(number=errno.EHOSTUNREACH):
    return chained(NewConnectionError("synthetic"), OSError(number, "synthetic"))


class FakeResponse:
    def __init__(self, status=201, headers=None, chunks=None):
        self.status = status
        self.headers = headers or {}
        self.chunks = list(chunks if chunks is not None else [b"ok", b""])
        self.closed = False
        self.reads = []

    def read1(self, size, decode_content=False):
        self.reads.append((size, decode_content))
        item = self.chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


class TransportTest(unittest.TestCase):
    def setUp(self):
        for owner, name in ((socket, "socket"), (socket, "getaddrinfo"),
                            (socket, "create_connection"), (ssl, "SSLContext")):
            guard = patch.object(owner, name, side_effect=AssertionError("network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        self.now = 0
        self.dns = ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111", "9.9.9.9"]
        self.dns_calls = []
        self.slot_calls = []
        self.actions = []
        self.pools = []
        self.requests = []
        self.dns_duration = 0
        self.slot_ok = True
        self.future_error = None
        owner = self

        class Future:
            def add_done_callback(self, callback):
                callback(self)

            def result(self, timeout):
                owner.now += owner.dns_duration
                if owner.future_error:
                    raise owner.future_error
                return [(None, None, None, None, (ip, 443)) for ip in owner.dns]

        class Executor:
            def submit(self, function, host, port, **kwargs):
                owner.dns_calls.append((function, host, port, kwargs))
                return Future()

        class Slots:
            def acquire(self, timeout):
                owner.slot_calls.append(("acquire", timeout))
                return owner.slot_ok

            def release(self):
                owner.slot_calls.append(("release",))

        class Pool:
            def __init__(self, ip, **kwargs):
                self.ip, self.kwargs, self.closed = ip, kwargs, False
                owner.pools.append(self)

            def urlopen(self, method, path, **kwargs):
                owner.requests.append((self.ip, method, path, kwargs))
                action = owner.actions.pop(0)
                if isinstance(action, tuple):
                    action, duration = action
                    owner.now += duration
                if callable(action):
                    action = action(kwargs)
                if isinstance(action, Exception):
                    raise action
                return action

            def close(self):
                self.closed = True

        class Response:
            def __init__(self):
                self.headers = {}

        errors = SimpleNamespace(NewConnectionError=NewConnectionError,
                                 NameResolutionError=NameResolutionError,
                                 SSLError=SSLError, ProtocolError=ProtocolError)
        self.ns = {"errno": errno, "ipaddress": ipaddress, "re": re, "socket": socket,
                   "ssl": ssl, "time": SimpleNamespace(monotonic=lambda: self.now),
                   "FutureTimeout": FutureTimeout, "urlsplit": urlsplit, "urljoin": urljoin,
                   "_dns_executor": Executor(), "_dns_slots": Slots(),
                   "urllib3": SimpleNamespace(exceptions=errors, HTTPSConnectionPool=Pool,
                                               HTTPConnectionPool=Pool,
                                               Timeout=lambda **kw: kw),
                   "requests": SimpleNamespace(Response=Response,
                                               utils=SimpleNamespace(get_encoding_from_headers=lambda _: None))}
        source = Path(__file__).resolve().parents[1] / "scripts/safe_outbound.py"
        tree = ast.parse(source.read_text())
        chosen = [node for node in tree.body
                  if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                  and node.name != "secure_browser_context"
                  or isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "PUSH_HOSTS"
                          for target in node.targets)]
        exec(compile(ast.Module(body=chosen, type_ignores=[]), str(source), "exec"), self.ns)
        self.post = self.ns["PushSession"]().post
        self.url = "https://fcm.googleapis.com/fake?synthetic=1"

    def send(self, data=b"synthetic", **kwargs):
        return self.post(self.url, data=data, **kwargs)

    def assertClosed(self):
        self.assertTrue(all(pool.closed for pool in self.pools))

    def test_first_failure_second_success_same_dns_and_tls_host(self):
        response = FakeResponse()
        self.actions = [failed(), response]
        result = self.send(headers={"Host": "evil.invalid", "Connection": "bad", "x": "value"})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result._content, b"ok")
        self.assertEqual(len(self.dns_calls), 1)
        self.assertEqual([pool.ip for pool in self.pools], ["1.1.1.1", "2606:4700:4700::1111"])
        for pool in self.pools:
            self.assertEqual(pool.kwargs, {"port": 443, "assert_hostname": "fcm.googleapis.com",
                                          "server_hostname": "fcm.googleapis.com", "cert_reqs": "CERT_REQUIRED"})
        for _, method, path, kw in self.requests:
            self.assertEqual((method, path), ("POST", "/fake?synthetic=1"))
            self.assertEqual(kw["body"], b"synthetic")
            self.assertEqual(kw["headers"], {"x": "value", "Accept-Encoding": "identity", "Host": "fcm.googleapis.com"})
            self.assertEqual((kw["redirect"], kw["retries"], kw["preload_content"]), (False, False, False))
        self.assertTrue(response.closed)
        self.assertClosed()

    def test_success_does_not_try_other_addresses(self):
        self.actions = [FakeResponse()]
        self.send()
        self.assertEqual(len(self.pools), 1)
        self.assertClosed()

    def test_all_known_failures_bounded_three_preserve_last_error(self):
        errors = [failed(), failed(errno.ENETUNREACH), failed(errno.ECONNREFUSED)]
        self.actions = list(errors)
        with self.assertRaises(NewConnectionError) as caught:
            self.send()
        self.assertIs(caught.exception, errors[-1])
        self.assertEqual(len(self.pools), 3)
        self.assertEqual(len(self.dns_calls), 1)
        self.assertClosed()

    def test_family_diversity_and_numeric_dedup(self):
        select = self.ns["_push_connect_addresses"]
        addresses = ["1.1.1.1", "8.8.8.8", "9.9.9.9", "2606:4700:4700::1111", "2606:4700:4700:0:0:0:0:1111"]
        self.assertEqual(select(addresses), ["1.1.1.1", "2606:4700:4700::1111", "8.8.8.8"])
        self.assertEqual(select(addresses[3:]), ["2606:4700:4700::1111"])
        self.assertEqual(select(["2606:4700:4700::1111", "2606:4700:4700::1001", "1.1.1.1"]),
                         ["2606:4700:4700::1111", "1.1.1.1", "2606:4700:4700::1001"])

    def test_original_first_sorted_and_resolve_public_api(self):
        self.assertEqual(self.ns["resolve_public"]("synthetic.example", 443), sorted(set(self.dns))[0])
        self.assertEqual(len(self.dns_calls), 1)

    def test_all_dns_answers_fail_closed_before_candidate_limit(self):
        unsafe = ["127.0.0.1", "10.0.0.1", "169.254.1.1", "224.0.0.1", "::1",
                  "2002:0808:0808::1", "64:ff9b::808:808", "::ffff:8.8.8.8", "2001::1", "not-an-ip"]
        for address in unsafe:
            with self.subTest(address=address):
                self.dns = ["1.1.1.1", "8.8.8.8", "9.9.9.9", address]
                with self.assertRaises((self.ns["UnsafeURL"], ValueError)):
                    self.send()
                self.assertEqual(self.pools, [])
        self.dns = []
        with self.assertRaises(self.ns["UnsafeURL"]):
            self.send()

    def test_dns_timeout_and_slot_failure_make_no_connection(self):
        self.future_error = FutureTimeout()
        with self.assertRaises(TimeoutError):
            self.send()
        self.future_error = None
        self.slot_ok = False
        with self.assertRaises(TimeoutError):
            self.send()
        self.assertEqual(self.pools, [])

    def test_original_deadline_includes_dns_and_prior_candidates(self):
        self.dns_duration = 2
        self.actions = [(failed(), 4), FakeResponse()]
        self.send(timeout=1000)
        self.assertEqual([item[3]["timeout"]["total"] for item in self.requests], [13, 9])
        self.assertEqual([item[3]["timeout"]["connect"] for item in self.requests], [5, 5])

    def test_deadline_prevents_next_candidate_and_closes_previous(self):
        self.actions = [(failed(), 15)]
        with self.assertRaises(TimeoutError):
            self.send()
        self.assertEqual(len(self.pools), 1)
        self.assertClosed()

    def test_remaining_budget_bounds_connect_and_read(self):
        self.actions = [(failed(), 13), FakeResponse()]
        self.send()
        self.assertEqual(self.requests[1][3]["timeout"], {"total": 2, "connect": 2, "read": 2})

    def test_only_small_known_errno_set_is_retryable(self):
        check = self.ns["_can_retry_push_connect"]
        for number in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ECONNREFUSED,
                       errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT):
            self.assertTrue(check(failed(number)))
        for number in (errno.ETIMEDOUT, errno.ECONNRESET, errno.EPIPE, errno.EACCES,
                       errno.EPERM, True, False, "65", None, 123456):
            self.assertFalse(check(failed(number)))

    def test_no_tls_dns_timeout_opaque_or_protocol_retry(self):
        errors = [SSLError(), ssl.SSLError(), ReadTimeoutError(), ConnectTimeoutError(),
                  TimeoutError(), ProtocolError(), OSError(errno.EHOSTUNREACH, "synthetic"),
                  chained(RuntimeError(), failed()),
                  chained(NewConnectionError(), RuntimeError()),
                  chained(NameResolutionError(), OSError(errno.EHOSTUNREACH, "synthetic")),
                  chained(NewConnectionError(), socket.gaierror(errno.EHOSTUNREACH, "synthetic")),
                  chained(NewConnectionError(), socket.herror(errno.EHOSTUNREACH, "synthetic")),
                  chained(NewConnectionError(), ssl.SSLError(errno.EHOSTUNREACH, "synthetic")),
                  chained(NewConnectionError(), TimeoutError(errno.EHOSTUNREACH, "synthetic")),
                  chained(NewConnectionError(), chained(OSError(errno.EHOSTUNREACH, "synthetic"), SSLError()))]
        for error in errors:
            with self.subTest(error_type=type(error).__name__):
                self.actions = [error]
                before = len(self.pools)
                with self.assertRaises(type(error)):
                    self.send()
                self.assertEqual(len(self.pools), before + 1)
                self.assertClosed()

    def test_exception_class_spoofs_and_descriptors(self):
        reads = []

        class Impostor(Exception):
            @property
            def __class__(self):
                reads.append("class")
                return NewConnectionError

        self.assertFalse(self.ns["_can_retry_push_connect"](chained(Impostor(), OSError(errno.EHOSTUNREACH, "x"))))

        class Legitimate(NewConnectionError):
            @property
            def __class__(self):
                raise AssertionError("class read")

        class Cause(OSError):
            def __getattribute__(self, name):
                if name in {"errno", "args", "__class__", "__cause__", "__context__"}:
                    raise AssertionError("exception field read")
                return super().__getattribute__(name)

        self.assertTrue(self.ns["_can_retry_push_connect"](chained(Legitimate(), Cause(errno.EHOSTUNREACH, "x"))))
        self.assertEqual(reads, [])

    def test_unknown_body_types_cannot_enable_fallback(self):
        class BytesSubclass(bytes):
            pass

        class Stream:
            @property
            def __class__(self):
                raise AssertionError("body class read")

        for data in (bytearray(b"x"), memoryview(b"x"), BytesSubclass(b"x"), Stream(), iter([b"x"]), "x"):
            with self.subTest(body_type=type(data).__name__):
                self.actions = [failed()]
                before = len(self.pools)
                with self.assertRaises(NewConnectionError):
                    self.send(data=data)
                self.assertEqual(len(self.pools), before + 1)

    def test_none_body_can_fallback(self):
        self.actions = [failed(), FakeResponse()]
        self.send(data=None)
        self.assertEqual(len(self.pools), 2)

    def test_stream_error_after_headers_sent_does_not_replay(self):
        events = []

        class Stream:
            @property
            def __class__(self):
                raise AssertionError("unknown body class read")

            def read(self):
                events.append("fake-pool-body-read")
                raise failed()

        def fake_send(kwargs):
            events.append("fake-pool-headers-sent")
            kwargs["body"].read()

        self.actions = [fake_send]
        with self.assertRaises(NewConnectionError):
            self.send(data=Stream())
        self.assertEqual(events, ["fake-pool-headers-sent", "fake-pool-body-read"])
        self.assertEqual(len(self.pools), 1)
        self.assertEqual(len(self.dns_calls), 1)
        self.assertClosed()

    def test_response_read_failure_cannot_retry_even_connection_shaped(self):
        response = FakeResponse(chunks=[b"partial", failed()])
        self.actions = [response]
        with self.assertRaises(NewConnectionError):
            self.send()
        self.assertEqual(len(self.pools), 1)
        self.assertTrue(response.closed)
        self.assertClosed()

    def test_response_close_failure_still_closes_pool_without_replaying_post(self):
        close_error = failed()

        class CloseFailure(FakeResponse):
            def close(self):
                self.closed = True
                raise close_error

        response = CloseFailure()
        self.actions = [response]
        with self.assertRaises(NewConnectionError) as caught:
            self.send()
        self.assertIs(caught.exception, close_error)
        self.assertTrue(response.closed)
        self.assertEqual(len(self.pools), 1)
        self.assertEqual(len(self.requests), 1)
        self.assertClosed()

    def test_http_status_is_returned_without_retry(self):
        for code in (201, 400, 404, 410, 429, 500, 503):
            with self.subTest(status=code):
                self.actions = [FakeResponse(status=code)]
                before = len(self.pools)
                self.assertEqual(self.send().status_code, code)
                self.assertEqual(len(self.pools), before + 1)

    def test_post_redirect_compression_and_oversize_never_retry(self):
        for response in (FakeResponse(307, {"Location": "https://fcm.googleapis.com/other"}),
                         FakeResponse(headers={"Content-Encoding": "gzip"}),
                         FakeResponse(headers={"Content-Length": "64001"}),
                         FakeResponse(chunks=[b"x" * 64001])):
            self.actions = [response]
            before = len(self.pools)
            with self.assertRaises(self.ns["UnsafeURL"]):
                self.send()
            self.assertEqual(len(self.pools), before + 1)
            self.assertTrue(response.closed)
            self.assertClosed()

    def test_exact_64k_response_and_read_deadline(self):
        self.actions = [FakeResponse(chunks=[b"x" * 64000, b""])]
        self.assertEqual(len(self.send()._content), 64000)
        response = FakeResponse()
        self.actions = [(response, 15)]
        with self.assertRaises(TimeoutError):
            self.send()
        self.assertTrue(response.closed)

    def test_get_default_and_generic_post_remain_single_ip(self):
        for call in (lambda: self.ns["get"](self.url),
                     lambda: self.ns["request"](self.url, method="POST", data=b"x"),
                     lambda: self.ns["request"](self.url, _push_connect_fallback=True)):
            self.actions = [failed()]
            before = len(self.pools)
            with self.assertRaises(NewConnectionError):
                call()
            self.assertEqual(len(self.pools), before + 1)
        self.assertClosed()

    def test_get_redirect_default_still_resolves_each_hop(self):
        self.actions = [FakeResponse(302, {"Location": "/next"}), FakeResponse(status=200)]
        result = self.ns["get"](self.url)
        self.assertEqual(result.url, "https://fcm.googleapis.com/next")
        self.assertEqual(len(self.dns_calls), 2)
        self.assertEqual(len(self.pools), 2)
        self.assertClosed()

    def test_push_host_allowlist_before_dns(self):
        for url in ("https://evil.example/fake", "http://fcm.googleapis.com/fake",
                    "https://fcm.googleapis.com.evil.example/fake", "https://127.0.0.1/fake"):
            with self.assertRaises(self.ns["UnsafeURL"]):
                self.post(url, data=b"x")
        self.assertEqual(self.dns_calls, [])
        self.assertEqual(self.pools, [])


if __name__ == "__main__":
    unittest.main()
