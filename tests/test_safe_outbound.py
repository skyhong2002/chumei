"""Network-free SSRF regression tests, including DNS rebinding and browser loads."""
import io
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

import urllib3

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import safe_outbound as so
import submissions


def dns(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


def response(body=b"ok", status=200, headers=None):
    return urllib3.HTTPResponse(body=io.BytesIO(body), status=status, headers=headers or {}, preload_content=False)


class SafeOutboundTests(unittest.TestCase):
    def test_rejects_private_urls_without_connection(self):
        urls = ["https://127.0.0.1/", "https://10.0.0.1/", "https://169.254.169.254/",
                "https://[::1]/", "https://[::ffff:127.0.0.1]/", "https://[64:ff9b::7f00:1]/",
                "https://user:pass@example.com/", "https://example.com:444/", "file:///etc/passwd",
                "https://example.com\\@127.0.0.1/", "https://localhost/", "https://box.local/"]
        with mock.patch.object(so.socket, "getaddrinfo") as resolver:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(so.UnsafeURL):
                    so.get(url)
            resolver.assert_not_called()
        for url in urls[:6]:
            self.assertIsNone(submissions.normalize_url(url))

    def test_rejects_mixed_and_private_dns(self):
        for answers in [dns("127.0.0.1"), dns("93.184.216.34") + dns("10.1.2.3")]:
            with mock.patch.object(so.socket, "getaddrinfo", return_value=answers), self.assertRaises(so.UnsafeURL):
                so.get("https://example.com/")

    def test_dns_rebinding_cannot_change_pinned_connection(self):
        pool = mock.Mock()
        pool.urlopen.return_value = response(headers={"Content-Type": "text/html; charset=utf-8"})
        with mock.patch.object(so.socket, "getaddrinfo", side_effect=[dns("93.184.216.34"), dns("127.0.0.1")]) as lookup, mock.patch.object(so.urllib3, "HTTPSConnectionPool", return_value=pool) as factory:
            result = so.get("https://example.com/a?b=c")
        self.assertEqual(result.text, "ok")
        self.assertEqual(lookup.call_count, 1)
        factory.assert_called_once_with("93.184.216.34", port=443, assert_hostname="example.com", server_hostname="example.com", cert_reqs="CERT_REQUIRED")
        self.assertEqual(pool.urlopen.call_args.args, ("GET", "/a?b=c"))
        self.assertEqual(pool.urlopen.call_args.kwargs["headers"]["Host"], "example.com")
        self.assertFalse(pool.urlopen.call_args.kwargs["redirect"])
        pool.close.assert_called_once()

    def test_empty_path_with_query_uses_valid_origin_form(self):
        pool = mock.Mock()
        pool.urlopen.return_value = response()
        with mock.patch.object(so.socket, "getaddrinfo", return_value=dns("93.184.216.34")), mock.patch.object(so.urllib3, "HTTPSConnectionPool", return_value=pool):
            so.get("https://example.com?x=1")
        self.assertEqual(pool.urlopen.call_args.args[1], "/?x=1")

    def test_dns_wait_has_deadline(self):
        future = mock.Mock()
        future.result.side_effect = so.FutureTimeout()
        with mock.patch.object(so, "_dns_slots") as slots, mock.patch.object(so._dns_executor, "submit", return_value=future):
            slots.acquire.return_value = True
            with self.assertRaises(TimeoutError):
                so.resolve_public("example.com", 443, timeout=0.01)
        self.assertLessEqual(future.result.call_args.kwargs["timeout"], 0.01)

    def test_redirect_to_private_or_rebound_dns_is_rejected(self):
        for location in ["https://127.0.0.1/", "https://example.com/next"]:
            pool = mock.Mock()
            pool.urlopen.return_value = response(status=302, headers={"Location": location})
            with mock.patch.object(so.socket, "getaddrinfo", side_effect=[dns("93.184.216.34"), dns("10.0.0.1")]), mock.patch.object(so.urllib3, "HTTPSConnectionPool", return_value=pool), self.assertRaises(so.UnsafeURL):
                so.get("https://example.com/")
            self.assertEqual(pool.urlopen.call_count, 1)

    def test_public_redirect_and_body_limits(self):
        pool = mock.Mock()
        pool.urlopen.side_effect = [response(status=302, headers={"Location": "/next"}), response(b"hello")]
        with mock.patch.object(so.socket, "getaddrinfo", return_value=dns("93.184.216.34")), mock.patch.object(so.urllib3, "HTTPSConnectionPool", return_value=pool):
            self.assertEqual(so.get("https://example.com/").url, "https://example.com/next")
        for res in [response(b"123456"), response(headers={"Content-Length": "99999"}), response(headers={"Content-Encoding": "gzip"})]:
            pool.urlopen.side_effect = None
            pool.urlopen.return_value = res
            with mock.patch.object(so.socket, "getaddrinfo", return_value=dns("93.184.216.34")), mock.patch.object(so.urllib3, "HTTPSConnectionPool", return_value=pool), self.assertRaises(so.UnsafeURL):
                so.get("https://example.com/", max_bytes=5)

    def test_push_allowlist_exact_hosts_and_redirect_disabled(self):
        for host in so.PUSH_HOSTS:
            self.assertTrue(so.validate_push_endpoint(f"https://{host}/endpoint"))
        for url in ["https://127.0.0.1/", "https://fcm.googleapis.com.evil.com/x", "https://evil.com/x", "http://fcm.googleapis.com/x"]:
            with self.assertRaises(so.UnsafeURL):
                so.validate_push_endpoint(url)
        pool = mock.Mock()
        pool.urlopen.return_value = response(status=307, headers={"Location": "https://example.com/"})
        with mock.patch.object(so.socket, "getaddrinfo", return_value=dns("142.250.1.1")), mock.patch.object(so.urllib3, "HTTPSConnectionPool", return_value=pool), self.assertRaises(so.UnsafeURL):
            so.PushSession().post("https://fcm.googleapis.com/x", data=b"encrypted")
        self.assertEqual(pool.urlopen.call_count, 1)

    def test_browser_never_uses_direct_network_for_subresources(self):
        browser = mock.Mock()
        context = so.secure_browser_context(browser)
        options = browser.new_context.call_args.kwargs
        self.assertTrue(options["offline"])
        self.assertFalse(options["java_script_enabled"])
        self.assertEqual(options["service_workers"], "block")
        callback = context.route.call_args.args[1]
        route = mock.Mock()
        route.request.method = "GET"
        route.request.resource_type = "image"
        route.request.url = "https://127.0.0.1/private.png"
        callback(route)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()
        route.fetch.assert_not_called()
        route = mock.Mock()
        route.request.method = "GET"
        route.request.resource_type = "stylesheet"
        route.request.url = "https://example.com/main.css"
        with mock.patch.object(so, "get") as get:
            get.return_value.content = b"body{color:black}"
            get.return_value.status_code = 200
            get.return_value.headers = {"Content-Type": "text/css"}
            callback(route)
        route.fulfill.assert_called_once()

    def test_submission_fetch_and_image_download_use_transport(self):
        import process_submissions
        import extract_events
        with mock.patch.object(so, "get", side_effect=so.UnsafeURL("blocked")) as get:
            with self.assertRaises(so.UnsafeURL):
                process_submissions.fetch_generic("https://127.0.0.1/")
            self.assertIsNone(extract_events.fetch_image_file("https://127.0.0.1/img", "/unused", 0))
        self.assertEqual(get.call_count, 2)


class PushAPITests(unittest.TestCase):
    def setUp(self):
        import push_server
        self.server = push_server
        push_server._send_times.clear()
        push_server._endpoint_times.clear()

    def test_rate_limits_endpoint_and_global_rotation(self):
        self.assertTrue(self.server.allow_send("a"))
        self.assertFalse(self.server.allow_send("a"))
        for n in range(29):
            self.assertTrue(self.server.allow_send(str(n)))
        self.assertFalse(self.server.allow_send("last"))
        with mock.patch.object(self.server.time, "monotonic", return_value=self.server.time.monotonic() + 61):
            self.assertTrue(self.server.allow_send("a"))

    def test_rejects_invalid_and_oversized_request_before_storage(self):
        from starlette.testclient import TestClient
        with TestClient(self.server.app) as client, mock.patch.object(self.server.pc, "upsert_sub") as store:
            for body in [[], {"subscription": {"endpoint": "https://127.0.0.1", "keys": {"auth": "a", "p256dh": "k"}}}, {"padding": "x" * 17000}]:
                self.assertEqual(client.post("/push/subscribe", json=body).status_code, 400)
            store.assert_not_called()
