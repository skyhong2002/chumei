"""Focused AST/fake-class tests: no product imports, config, files or sockets.

Run with /usr/bin/python3 -I -B tests/test_push_failure_diagnostic.py.
Only candidate source is read. Runtime state/checkpoints stay in memory.
"""
import ast
import contextlib
import copy
from datetime import date, timedelta
import errno
import io
import json
from pathlib import Path
import socket
import ssl
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PRIVATE = "SYNTHETIC_PRIVATE https://private.invalid/path?token=secret"


class ConnectTimeoutError(Exception):
    pass


class NewConnectionError(ConnectTimeoutError):
    pass


class NameResolutionError(NewConnectionError):
    pass


class SSLError(Exception):
    pass


def extracted(filename, functions, constants=(), namespace=None):
    module = ast.parse((SCRIPTS / filename).read_text())
    chosen = [node for node in module.body
              if isinstance(node, ast.FunctionDef) and node.name in functions
              or isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets)]
    result = {} if namespace is None else namespace
    exec(compile(ast.Module(body=chosen, type_ignores=[]), filename, "exec"), result)
    return result


def chained(error, cause):
    error.__cause__ = cause
    return error


class Fixture(unittest.TestCase):
    def setUp(self):
        fake_package = ModuleType("urllib3")
        fake_package.__path__ = []
        fake_errors = ModuleType("urllib3.exceptions")
        for cls in (ConnectTimeoutError, NewConnectionError, NameResolutionError, SSLError):
            setattr(fake_errors, cls.__name__, cls)
        fake_package.exceptions = fake_errors
        replacements = {"urllib3": fake_package, "urllib3.exceptions": fake_errors}
        self.modules = patch.dict(sys.modules, replacements)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        # Fail if a future test/code edit attempts an actual socket/DNS/TLS call.
        for owner, attribute in ((socket, "socket"), (socket, "getaddrinfo"),
                                 (socket, "create_connection"), (ssl, "SSLContext")):
            guard = patch.object(owner, attribute, side_effect=AssertionError("real network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        self.ns = extracted("publish_push.py", {"failure_diagnostic", "clear_failure_diagnostic"},
                            namespace={"errno": errno})
        self.diagnose = self.ns["failure_diagnostic"]

    def assertFacts(self, error, category, number=None):
        facts = self.diagnose(error)
        self.assertEqual(facts, {"failure_cause": category, "socket_errno": number})
        self.assertNotIn(PRIVATE, json.dumps(facts))
        self.assertNotIn("private.invalid", json.dumps(facts))
        return facts

    def connection_failure(self, number=errno.ENETUNREACH):
        return chained(NewConnectionError(PRIVATE), OSError(number, PRIVATE, PRIVATE))


class DiagnosticTest(Fixture):
    def test_known_identity_and_subclass_precedence(self):
        self.assertFacts(self.connection_failure(), "new_connection", errno.ENETUNREACH)
        self.assertFacts(ConnectTimeoutError(PRIVATE), "connect_timeout")
        self.assertFacts(NameResolutionError(PRIVATE), "dns_resolution")
        self.assertFacts(SSLError(PRIVATE), "tls")
        # Matching a class name string must not grant known-class status.
        impostor = type("NewConnectionError", (Exception,), {})
        self.assertFacts(impostor(PRIVATE), "other")

    def test_outermost_known_class_and_wrapped_cause(self):
        wrapped = chained(RuntimeError(PRIVATE), self.connection_failure())
        self.assertFacts(wrapped, "new_connection", errno.ENETUNREACH)
        file_wrapper = chained(OSError(errno.EACCES, PRIVATE, PRIVATE), self.connection_failure())
        self.assertFacts(file_wrapper, "new_connection", errno.ENETUNREACH)
        opaque = chained(NewConnectionError(PRIVATE), chained(RuntimeError(PRIVATE), OSError(errno.EPERM, PRIVATE)))
        self.assertFacts(opaque, "new_connection")
        mixed = chained(NewConnectionError(PRIVATE), SSLError(PRIVATE))
        self.assertFacts(mixed, "new_connection")  # Outer class, TLS errno exclusion.
        mixed = chained(SSLError(PRIVATE), self.connection_failure())
        self.assertFacts(mixed, "tls")

    def test_successful_class_property_spoof_is_never_read(self):
        reads = []

        class Impersonator(Exception):
            @property
            def __class__(self):
                reads.append("class property read")
                return NewConnectionError

        error = chained(Impersonator(PRIVATE), OSError(errno.ENETUNREACH, PRIVATE))
        self.assertFacts(error, "other")
        self.assertEqual(reads, [])

    def test_dns_and_tls_errno_domains_cannot_collide_with_posix(self):
        # Positive synthetic EAI/h_errno deliberately collides with EPERM=1.
        for cause in (socket.gaierror(errno.EPERM, PRIVATE),
                      socket.herror(errno.EPERM, PRIVATE),
                      ssl.SSLError(ssl.SSL_ERROR_SSL, PRIVATE)):
            with self.subTest(cause_type=type(cause).__name__):
                self.assertFacts(chained(NewConnectionError(PRIVATE), cause), "new_connection")
                expected = "tls" if isinstance(cause, ssl.SSLError) else "dns_resolution"
                self.assertFacts(cause, expected)
        self.assertFacts(chained(NameResolutionError(PRIVATE), OSError(errno.EPERM, PRIVATE)), "dns_resolution")

    def test_errno_requires_known_connect_class_and_exact_allowlisted_int(self):
        for number in (True, False, "1", 0, -1, 123456789):
            self.assertFacts(self.connection_failure(number), "new_connection")
        for name in ("ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED", "ETIMEDOUT",
                     "EADDRNOTAVAIL", "EACCES", "EPERM", "ECONNRESET", "EAFNOSUPPORT"):
            number = getattr(errno, name)
            self.assertFacts(self.connection_failure(number), "new_connection", number)
        self.assertFacts(OSError(errno.EACCES, PRIVATE, PRIVATE), "other")

    def test_four_cause_links_are_bounded_and_cycles_fail_closed(self):
        leaf = OSError(errno.ENETUNREACH, PRIVATE)
        four = chained(RuntimeError(PRIVATE), chained(RuntimeError(PRIVATE),
                       chained(RuntimeError(PRIVATE), chained(NewConnectionError(PRIVATE), leaf))))
        self.assertFacts(four, "new_connection", errno.ENETUNREACH)
        self.assertFacts(chained(RuntimeError(PRIVATE), four), "other")
        cycle = self.connection_failure()
        cycle.__cause__.__cause__ = cycle
        self.assertFacts(cycle, "other")

    def test_text_args_properties_and_context_are_not_read(self):
        class Trap(OSError):
            def __str__(self): raise AssertionError("str read")
            def __repr__(self): raise AssertionError("repr read")
            def __getattribute__(self, name):
                if name in {"args", "filename", "filename2", "errno", "__cause__", "__context__"}:
                    raise AssertionError("exception field read")
                return super().__getattribute__(name)
        trap = Trap(errno.ECONNREFUSED, PRIVATE, PRIVATE)
        self.assertFacts(chained(NewConnectionError(PRIVATE), trap), "new_connection", errno.ECONNREFUSED)
        outer = RuntimeError(PRIVATE)
        outer.__context__ = self.connection_failure()
        self.assertFacts(outer, "other")

    def test_broken_class_attribute_and_diagnostic_internal_fault_fail_closed(self):
        class Broken(Exception):
            @property
            def __class__(self): raise RuntimeError(PRIVATE)
        self.assertFacts(Broken(PRIVATE), "other")
        with patch.object(errno, "ENETUNREACH", new=[]):
            self.assertFacts(self.connection_failure(), "other")
        with patch.dict(sys.modules, {"urllib3.exceptions": None}):
            self.assertFacts(RuntimeError(PRIVATE), "other")


class DeliveryIntegrationTest(Fixture):
    def setUp(self):
        super().setUp()
        self.reset_delivery()

    def reset_delivery(self):
        pure = extracted("push_delivery.py", {"group", "receipt", "finish", "legacy_fence", "retry_delay"},
                         {"TERMINAL", "MAX_ATTEMPTS", "RETRY_BASE_SECONDS", "RETRY_MAX_SECONDS"})
        self.pd = SimpleNamespace(**{name: value for name, value in pure.items() if name != "__builtins__"})
        self.today = date(2026, 10, 18)
        self.clock = 10000
        self.error = None
        self.calls, self.checkpoints, self.pruned = [], [], []
        self.subs = {"device": {"user_id": "fixture-user", "sub": {"endpoint": "https://synthetic.invalid/"}}}
        self.current_subs = self.subs
        self.events = [{"id": "event", "start_at": "2026-10-19T19:00:00+08:00"}]
        self.job = {"id": "job", "kind": "event", "device": "device", "event_ids": ["event"],
                    "user_id": None, "digest": False, "status": "pending", "attempts": 0,
                    "recipient_user_id": "fixture-user", "payload": {"body": "synthetic frozen payload"},
                    "failure_cause": "new_connection", "socket_errno": errno.ENETUNREACH,
                    "error_type": "historical-compatible-value"}
        self.state = {"sent": {"event": {"devices": {"device": {"status": "pending"}}}},
                      "reminders": {}, "deliveries": {"job": self.job}}
        class PushGone(Exception): pass
        self.pc = SimpleNamespace(load_subs=lambda: {"subs": self.current_subs},
                                  send_push=self.send, PushGone=PushGone, prune_endpoint=self.pruned.append)
        self.ns.update({"date": date, "timedelta": timedelta, "pd": self.pd, "pc": self.pc, "sys": sys,
                        "now_iso": lambda: "synthetic-stamp", "eligible_events": lambda events, today: events,
                        "frozen_payload": lambda job, *args: copy.deepcopy(job["payload"])})
        extracted("publish_push.py", {"send_deliveries"}, namespace=self.ns)

    def send(self, record, payload, **kwargs):
        self.calls.append((copy.deepcopy(record), copy.deepcopy(payload), kwargs))
        if self.error is not None:
            raise self.error

    def deliver(self):
        with contextlib.redirect_stderr(io.StringIO()):
            return self.ns["send_deliveries"](self.subs, self.events, self.state, {},
                        today=self.today, clock=lambda: self.clock,
                        checkpoint=lambda state: self.checkpoints.append(copy.deepcopy(state)))

    def assertCleared(self):
        self.assertNotIn("failure_cause", self.job)
        self.assertNotIn("socket_errno", self.job)

    def test_new_failure_then_unknown_then_sent_preserves_attempt_backoff_binding_payload(self):
        self.error = self.connection_failure()
        self.assertEqual(self.deliver(), {"sent": 0, "gone": 0, "failed": 1, "cancelled": 0})
        self.assertEqual((self.job["attempts"], self.job["next_attempt_at"]), (1, 11800))
        intent = self.checkpoints[0]["deliveries"]["job"]
        self.assertNotIn("failure_cause", intent)
        self.assertNotIn("socket_errno", intent)
        self.assertEqual((self.job["failure_cause"], self.job["socket_errno"]), ("new_connection", errno.ENETUNREACH))
        self.assertNotIn("sent_at", self.state["sent"]["event"]["devices"]["device"])
        before = copy.deepcopy(self.state)
        self.deliver()  # Backoff skip preserves old facts and does not send/checkpoint.
        self.assertEqual(self.state, before)
        self.assertEqual(len(self.calls), 1)
        self.clock = self.job["next_attempt_at"]
        self.error = ValueError(PRIVATE)
        self.deliver()
        self.assertEqual((self.job["attempts"], self.job["next_attempt_at"]), (2, 15400))
        self.assertEqual((self.job["failure_cause"], self.job["socket_errno"]), ("other", None))
        self.assertEqual(self.job["error_type"], "ValueError")
        self.clock = self.job["next_attempt_at"]
        self.error = None
        self.assertEqual(self.deliver()["sent"], 1)
        self.assertCleared()
        self.assertEqual((self.job["attempts"], self.job["next_attempt_at"]), (3, 22600))
        self.assertEqual(self.job["error_type"], "ValueError")  # Existing compatibility behavior.
        self.assertEqual(self.job["recipient_user_id"], "fixture-user")
        self.assertTrue(all(call[1] == {"body": "synthetic frozen payload"} and call[2] == {"ttl": 43200} for call in self.calls))
        self.assertEqual(self.state["sent"]["event"]["devices"]["device"]["status"], "sent")
        self.assertEqual(self.state["sent"]["event"]["status"], "complete")

    def test_future_gone_and_cancelled_transitions_clear_diagnostics(self):
        for outcome in ("gone", "missing_subscription", "inactive_event", "rebound"):
            with self.subTest(outcome=outcome):
                self.reset_delivery()
                if outcome == "gone": self.error = self.pc.PushGone(PRIVATE)
                elif outcome == "missing_subscription": self.subs.clear()
                elif outcome == "inactive_event": self.events.clear()
                else: self.current_subs = {"device": {"user_id": "changed-fixture-user"}}
                self.deliver()
                self.assertCleared()
                self.assertEqual(self.job["status"], "gone" if outcome == "gone" else "cancelled")
                self.assertEqual(len(self.calls), 1 if outcome == "gone" else 0)

    def test_diagnostic_fault_keeps_retry_checkpoint_and_original_error_type(self):
        self.error = self.connection_failure()
        with patch.object(errno, "ENETUNREACH", new=[]):
            stats = self.deliver()
        self.assertEqual((stats["failed"], self.job["status"], self.job["attempts"]), (1, "retry", 1))
        self.assertEqual((self.job["failure_cause"], self.job["socket_errno"]), ("other", None))
        self.assertEqual(self.job["error_type"], "NewConnectionError")
        self.assertEqual(len(self.checkpoints), 2)

    def test_existing_terminal_rows_are_not_backfilled_or_rewritten(self):
        self.job["status"] = "sent"
        self.job.pop("failure_cause")
        self.job.pop("socket_errno")
        before = copy.deepcopy(self.state)
        self.deliver()
        self.assertEqual(self.state, before)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.checkpoints, [])


if __name__ == "__main__":
    unittest.main()
