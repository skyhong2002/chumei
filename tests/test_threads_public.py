"""Focused AST/fake public transport tests; no product/config/network imports."""
from __future__ import annotations

import ast
import contextlib
import datetime as dt
import email.utils
import html
import http.cookiejar
import io
import json
from pathlib import Path
import re
import socket
import ssl
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch, Mock
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


PROFILE = b'"LSD",[],{"token":"PUBLIC_SYNTHETIC"};"initial_thread_count":5,"user_id":"123"'
SCRIPT = b'BarcelonaProfileThreadsTabRefetchableDirectQuery_threadsRelayOperation" exports="555" name:"__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider"'


def payload(*posts):
    return {"data": {"mediaData": {"edges": [{"node": {"thread_items": [{"post": post} for post in posts]}}]}}}


def post(code="ABC123", username="example", **kwargs):
    return {"pk": "987654321", "code": code, "user": {"username": username},
            "taken_at": 1700000000, "caption": {"text": "synthetic announcement"}, **kwargs}


class Response:
    def __init__(self, data=b"", headers=None):
        self.data = data.encode() if isinstance(data, str) else data
        self.headers = headers or {}
        self.status = 200
        self.closed = False

    def read(self, size):
        raw, self.data = self.data[:size], self.data[size:]
        return raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


class Fixture(unittest.TestCase):
    def setUp(self):
        for owner, name in ((socket, "socket"), (socket, "getaddrinfo"),
                            (socket, "create_connection"), (ssl, "SSLContext")):
            guard = patch.object(owner, name, side_effect=AssertionError("real network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        self.now = 0
        self.actions, self.calls, self.health, self.errors, self.appended = [], [], [], [], []
        owner = self

        class Opener:
            def open(self, request, timeout):
                owner.calls.append((request, timeout))
                action = owner.actions.pop(0)
                if isinstance(action, tuple):
                    action, duration = action
                    owner.now += duration
                if isinstance(action, Exception):
                    raise action
                return action

        self.opener = Opener()
        self.build = patch.object(urllib.request, "build_opener", return_value=self.opener)
        self.build.start()
        self.addCleanup(self.build.stop)
        self.source = {"username": "example"}
        self.ns = {}
        path = Path(__file__).resolve().parents[1] / "scripts/threads_public.py"
        exec(compile(path.read_text(), str(path), "exec"), self.ns)
        # Load only pure parsing/main definitions: no product imports or state access.
        self.social = {"argparse": __import__("argparse"), "json": json, "re": re, "sys": sys,
                       "time": SimpleNamespace(time=lambda: 0, sleep=lambda _: None),
                       "random": SimpleNamespace(uniform=lambda *args: 0),
                       "now_iso": lambda: "2026-10-19T00:00:00+00:00",
                       "strip_html": lambda text: re.sub(r"<[^>]*>", "", text),
                       "fetch_threads_source": self.ns["fetch_threads_source"],
                       "ROOT": Path("/synthetic"), "RAW_SOURCE": "rsshub-social",
                       "SCHEDULE_STATE": Path("/synthetic/schedule"),
                       "ROUTES": {"threads": "/threads/{u}", "x": "/twitter/user/{u}"},
                       "POST_ID_RES": {"threads": re.compile(r"/(?:post|t)/([\w-]+)"),
                                       "x": re.compile(r"/status/(\d+)")}}
        social_path = path.with_name("fetch_social.py")
        nodes = [node for node in ast.parse(social_path.read_text()).body
                 if isinstance(node, ast.FunctionDef) and node.name in {"main", "parse_feed"}]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(social_path), "exec"), self.social)
        self.ns["time"] = SimpleNamespace(monotonic=lambda: self.now)

    def graphql_actions(self, profile=PROFILE, posts=None):
        return [Response(profile), Response(json.dumps(payload(*(posts or [post()]))))]

    def fetch(self, **kwargs):
        return self.ns["fetch_threads_source"](self.source, rsshub_url="https://rss.invalid/threads/example", limit=kwargs.get("limit", 10), parse_rss=self.social["parse_feed"])

    def http_error(self, url="https://rss.invalid/threads/example", code=503, location=None):
        body = io.BytesIO(b"synthetic upstream undefined.url")
        error = urllib.error.HTTPError(url, code, "synthetic", {"Location": location} if location else {}, body)
        return error, body


class ThreadsFallbackTests(Fixture):
    def test_healthy_rsshub_never_calls_public_fallback(self):
        self.actions = [Response("<rss><channel><item><guid>https://www.threads.com/t/ABC123</guid><link>https://www.threads.com/@example/post/ABC123</link></item></channel></rss>")]
        rows, avatar, backend = self.fetch()
        self.assertEqual(rows[0]["post_id"], "ABC123")
        self.assertEqual(backend, "RSSHub")
        self.assertEqual(len(self.calls), 1)

    def test_healthy_rss_preserves_avatar_without_public_request(self):
        self.actions = [Response("<rss><channel><image><url>https://cdn.example/a.jpg?x=1&amp;y=2</url></image></channel></rss>")]
        self.assertEqual(self.fetch(), ([], "https://cdn.example/a.jpg?x=1&y=2", "RSSHub"))
        self.assertEqual(len(self.calls), 1)

    def test_http_rsshub_failure_uses_one_public_query(self):
        error, body = self.http_error()
        self.actions = [error, *self.graphql_actions()]
        rows, avatar, backend = self.fetch()
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual([req.get_method() for req, _ in self.calls], ["GET", "GET", "POST"])
        self.assertTrue(body.closed)

    def test_bad_xml_uses_fallback_but_empty_valid_feed_does_not(self):
        self.actions = [Response(b"broken"), *self.graphql_actions()]
        self.assertEqual(len(self.fetch()[0]), 1)
        before = len(self.calls)
        self.actions = [Response("<rss><channel/></rss>")]
        self.assertEqual(self.fetch()[0], [])
        self.assertEqual(len(self.calls), before + 1)

    def test_canonical_profile_redirect_updates_query_origin(self):
        error, body = self.http_error("https://www.threads.com/@example", 301, "https://threads.com/@example/")
        self.actions = [error, *self.graphql_actions()]
        rows = self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(rows), 1)
        self.assertTrue(body.closed)
        query = self.calls[-1][0]
        self.assertEqual(query.full_url, "https://threads.com/graphql/query")
        self.assertEqual(query.get_header("Origin"), "https://threads.com")
        self.assertEqual(self.calls[1][0].get_header("X-fb-lsd"), None)

    def test_profile_redirects_reject_cross_host_user_credentials_query_and_http(self):
        redirect = self.ns["_threads_profile_redirect"]
        for target in ("https://evil.example/@example", "http://threads.com/@example", "https://threads.com/@other",
                       "https://user:pass@threads.com/@example", "https://threads.com:444/@example",
                       "https://threads.com/@example?token=x", "https://threads.com/@example#x"):
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                redirect("https://www.threads.com/@example", target)

    def test_profile_redirect_budget_no_fourth_request(self):
        errors = [self.http_error("https://www.threads.com/@example", 302, "https://threads.com/@example")[0] for _ in range(3)]
        self.actions = errors
        with self.assertRaises(RuntimeError):
            self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(self.calls), 3)

    def test_combined_source_request_bound_includes_two_profile_redirects(self):
        rss, _ = self.http_error()
        redirect1, _ = self.http_error("https://www.threads.com/@example", 301, "https://threads.com/@example")
        redirect2, _ = self.http_error("https://threads.com/@example", 301, "https://www.threads.com/@example/")
        profile = PROFILE + b'<script src="https://static.cdninstagram.com/one.js"></script><script src="https://static.cdninstagram.com/two.js"></script>'
        self.actions = [rss, redirect1, redirect2, Response(profile), Response(b"none"),
                        Response(b"none"), Response(json.dumps(payload(post())))]
        self.assertEqual(len(self.fetch()[0]), 1)
        self.assertEqual(len(self.calls), 7)

    def test_post_and_cdn_redirects_are_not_followed(self):
        error, body = self.http_error("https://www.threads.com/graphql/query", 307, "https://threads.com/graphql/query")
        self.actions = [Response(PROFILE), error]
        with self.assertRaises(RuntimeError):
            self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(body.closed)
        error, body = self.http_error("https://static.cdninstagram.com/one.js", 302, "https://evil.example/script.js")
        profile = PROFILE + b'<script src="https://static.cdninstagram.com/one.js"></script>'
        self.actions = [Response(profile), error, Response(json.dumps(payload(post())))]
        self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(self.calls), 5)
        self.assertTrue(body.closed)
        self.assertFalse(any("evil.example" in req.full_url for req, _ in self.calls))

    def test_only_two_cdn_scripts_and_no_ephemeral_headers(self):
        profile = PROFILE + b''.join(f'<script src="https://static.cdninstagram.com/{i}.js"></script>'.encode() for i in range(5))
        self.actions = [Response(profile), Response(b"no metadata"), Response(b"no metadata"), Response(json.dumps(payload(post())))]
        self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual([r.full_url for r, _ in self.calls[1:3]], ["https://static.cdninstagram.com/4.js", "https://static.cdninstagram.com/3.js"])
        for request, _ in self.calls[1:3]:
            self.assertEqual(set(dict(request.header_items())), {"User-agent", "Accept-encoding"})
        form = urllib.parse.parse_qs(self.calls[-1][0].data.decode())
        self.assertEqual(form["doc_id"], [self.ns["THREADS_GRAPHQL_FALLBACK_DOC_ID"]])

    def test_query_metadata_is_cached_without_profile_tokens(self):
        profile = PROFILE + b'<script src="https://static.cdninstagram.com/current.js"></script>'
        self.actions = [Response(profile), Response(SCRIPT), Response(json.dumps(payload(post()))), *self.graphql_actions(profile)]
        self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(self.calls), 5)
        self.assertNotIn("PUBLIC_SYNTHETIC", repr(self.ns["_THREADS_QUERY_METADATA_CACHE"]))
        self.assertEqual(urllib.parse.parse_qs(self.calls[-1][0].data.decode())["doc_id"], ["555"])

    def test_budget_spans_rsshub_and_public_requests(self):
        self.actions = [(Response(b"broken"), 21), (Response(PROFILE), 9)]
        with self.assertRaises(RuntimeError):
            self.fetch()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([timeout for _, timeout in self.calls], [10, 9])

    def test_response_cap_and_compression_fail_without_query(self):
        self.ns["THREADS_MAX_RESPONSE_BYTES"] = 20
        response = Response(b"x" * 21)
        self.actions = [response]
        with self.assertRaises(RuntimeError):
            self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertTrue(response.closed)
        self.assertEqual(len(self.calls), 1)
        self.actions = [Response(PROFILE, {"Content-Encoding": "gzip"})]
        with self.assertRaises(RuntimeError):
            self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(self.calls), 2)

    def test_normalization_preserves_legacy_shortcode(self):
        xml = "<rss><channel><item><guid>https://www.threads.com/t/ABC123</guid><link>https://www.threads.com/@example/post/ABC123</link></item></channel></rss>"
        legacy = list(self.social["parse_feed"](xml, "threads"))
        direct = self.ns["normalize_threads_posts"](self.source, payload(post()), limit=10)
        self.assertEqual(legacy[0]["post_id"], direct[0]["post_id"])
        self.assertEqual(len({row["post_id"] for row in legacy + direct}), 1)
        self.assertNotIn("987654321", direct[0]["post_id"])

    def test_normalization_keeps_authored_unique_posts_media_and_limit(self):
        media = {"image_versions2": {"candidates": [{"url": "https://cdn.example/image.jpg"}]},
                 "video_versions": [{"url": "https://cdn.example/video.mp4"}]}
        rows = self.ns["normalize_threads_posts"](self.source, payload(post(**media), post(), post("REPLY", "other"), post("SECOND")), limit=10)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["images"], ["https://cdn.example/image.jpg"])
        self.assertEqual(rows[0]["posted_at"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(len(self.ns["normalize_threads_posts"](self.source, payload(*[post(str(i)) for i in range(20)]), limit=100)), 15)

    def test_invalid_media_and_code_do_not_make_unsafe_rows(self):
        bad_media = {"image_versions2": {"candidates": [{"url": "javascript:alert(1)"}]}}
        rows = self.ns["normalize_threads_posts"](self.source, payload(post(**bad_media), post("../../bad"), {"code": "MISSINGAUTHOR"}), limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["images"], [])

    def test_missing_errors_and_malformed_shapes_are_not_empty_success(self):
        for value in ({}, {"errors": [{"message": "PRIVATE_SYNTHETIC"}]}, {"data": {"mediaData": {"edges": [None]}}}, []):
            with self.subTest(shape=type(value).__name__), self.assertRaises(RuntimeError) as caught:
                self.ns["normalize_threads_posts"](self.source, value, limit=1)
            self.assertNotIn("PRIVATE_SYNTHETIC", str(caught.exception))
        self.assertEqual(self.ns["normalize_threads_posts"](self.source, {"data": {"mediaData": {"edges": []}}}, limit=1), [])

    def test_missing_profile_metadata_never_requests_query(self):
        self.actions = [Response(b"logged out page without metadata")]
        with self.assertRaises(RuntimeError):
            self.ns["fetch_threads_graphql"](self.source, limit=1)
        self.assertEqual(len(self.calls), 1)

    def test_invalid_username_makes_no_request(self):
        for username in ("../other", "user?token=x", "a/b", "@", "a" * 31):
            with self.assertRaises(RuntimeError):
                self.ns["fetch_threads_graphql"]({**self.source, "username": username}, limit=1)
        self.assertEqual(self.calls, [])


class SocialIntegrationTests(Fixture):
    def run_main(self, *, platform="threads", due=True, seen=False):
        ns = self.social
        self.persisted = {"version": 1, "accounts": {"threads:example": {"consecutive_failures": 3}}}
        self.seen = Mock()
        self.seen.has.return_value = seen
        self.rows = [{"platform": platform, "username": "example", "name": "synthetic official", "school": "nthu", "org_type": "school"}]
        self.append = Mock(side_effect=lambda _, rows: len(rows))
        ns.update({"load_env": Mock(return_value={"CHUMEI_RSSHUB_BASE": "https://rss.invalid"}),
                   "read_sources_csv": Mock(return_value=self.rows),
                   "load_schedule": Mock(return_value=self.persisted),
                   "select_due": Mock(side_effect=lambda keys, *args, **kwargs: keys if due else []),
                   "SeenState": Mock(return_value=self.seen), "append_inbox": self.append,
                   "save_schedule": Mock(), "mark_success": Mock(), "mark_failure": Mock(),
                   "record_fetch": Mock(), "record_api_call": Mock(), "log_error": Mock(),
                   "requests": SimpleNamespace(get=Mock(side_effect=AssertionError("unexpected X/RSS request"))),
                   "rsshub_error": Mock(return_value=None)})
        with patch.object(sys, "argv", ["fetch_social.py", "--max-accounts", "1"]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return ns["main"]()

    def test_public_success_preserves_source_identity_and_metadata(self):
        error, _ = self.http_error()
        self.actions = [error, *self.graphql_actions()]
        self.assertEqual(self.run_main(), 0)
        row = self.append.call_args.args[1][0]
        self.assertEqual((row["source_id"], row["post_id"], row["raw_source"]), ("threads_example", "ABC123", "rsshub-social"))
        self.assertEqual((row["source_name"], row["school"], row["org_type"]), ("synthetic official", "nthu", "school"))
        self.social["mark_success"].assert_called_once_with(self.persisted, "threads:example", interval_hours=20, jitter_hours=3)
        self.social["record_fetch"].assert_called_once_with("threads:example", backend="Threads public logged-out", ok=True, items=1)
        self.social["mark_failure"].assert_not_called()
        self.seen.add.assert_called_once_with("threads_example", "ABC123")

    def test_existing_seen_shortcode_is_not_appended_again(self):
        error, _ = self.http_error()
        self.actions = [error, *self.graphql_actions()]
        self.assertEqual(self.run_main(seen=True), 0)
        self.assertEqual(self.append.call_args.args[1], [])
        self.seen.add.assert_not_called()

    def test_cooldown_makes_no_requests_or_state_mutation(self):
        self.assertEqual(self.run_main(due=False), 0)
        self.assertEqual(self.calls, [])
        self.social["SeenState"].assert_not_called()
        self.social["save_schedule"].assert_not_called()
        self.social["mark_success"].assert_not_called()
        self.social["mark_failure"].assert_not_called()

    def test_both_fail_record_failure_and_existing_backoff(self):
        error, _ = self.http_error()
        self.actions = [error, Response(b"no metadata")]
        self.assertEqual(self.run_main(), 1)
        self.social["mark_failure"].assert_called_once_with(self.persisted, "threads:example")
        self.social["mark_success"].assert_not_called()
        self.social["save_schedule"].assert_called_once()
        self.assertFalse(self.social["record_fetch"].call_args.kwargs["ok"])
        self.append.assert_not_called()
        self.seen.save.assert_not_called()

    def test_x_never_uses_threads_transport(self):
        self.assertEqual(self.run_main(platform="x"), 1)
        self.social["requests"].get.assert_called_once_with("https://rss.invalid/twitter/user/example", params={"limit": 5}, timeout=90)
        self.assertEqual(self.calls, [])

    def test_http_attempt_usage_distinguishes_primary_failure_and_public_success(self):
        error, _ = self.http_error()
        self.actions = [error, *self.graphql_actions()]
        self.assertEqual(self.run_main(), 0)
        calls = self.social["record_api_call"].call_args_list
        self.assertEqual([(c.args[0], c.kwargs["ok"], c.kwargs["source_count"]) for c in calls],
                         [("RSSHub", False, 1), ("Threads public logged-out", True, 1), ("Threads public logged-out", True, 0)])

    def test_public_request_usage_is_exposed_in_status_summary(self):
        path = Path(__file__).resolve().parents[1] / "scripts/source_status.py"
        node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "api_usage_summary")
        ns = {"time": SimpleNamespace(time=lambda: 1000), "_usage_rows": lambda: [
            {"service": "Threads public logged-out", "ts": 999, "requestCount": 2, "sourceCount": 1, "ok": True}]}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
        public = ns["api_usage_summary"](now=1000)["Threads public logged-out"]
        self.assertEqual((public["requests24h"], public["sources24h"], public["errors24h"]), (2, 1, 0))
        self.assertEqual(public["cost30dUsd"], 0)

    def test_source_batch_limit_is_unchanged(self):
        self.run_main(due=False)
        self.assertEqual(self.social["select_due"].call_args.args, (["threads:example"], self.persisted, 1))

    def test_fallback_backend_is_reported(self):
        error, _ = self.http_error()
        self.actions = [error, *self.graphql_actions()]
        rows, avatar, backend = self.fetch()
        self.assertEqual((len(rows), avatar, backend), (1, "", "Threads public logged-out"))

if __name__ == "__main__":
    unittest.main()
