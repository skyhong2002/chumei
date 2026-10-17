"""Offline delivery faults: synthetic subscriptions, private temp state, no pushes."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import publish_push as pp
import push_delivery as pd
import push_common as pc

TODAY = date.today()


def event(identifier="event-a", **changes):
    value = {
        "id": identifier, "title": f"Fixture {identifier}", "school": "nthu",
        "start_at": (TODAY + timedelta(days=1)).isoformat() + "T19:00:00+08:00",
        "source": {"posted_at": TODAY.isoformat(), "source_id": "fixture-org"},
    }
    value.update(changes)
    return value


def subscriptions(*names, user_id=None):
    return {name: {"name": name, "prefs": {"mode": "all"},
                   "sub": {"endpoint": f"https://push.example.invalid/{name}"},
                   **({"user_id": user_id} if user_id else {})} for name in names}


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "publish.json"
        self.state = pd.migrate({})
        self.events = [event()]
        self.subs = subscriptions("a", "b")
        self.now = 10000

    def save(self, state):
        pd.save(state, self.path)

    def queue(self):
        pp.queue_events(self.subs, pp.pending_events(self.events, self.state), self.state, {}, {})
        self.save(self.state)

    def deliver(self, sender=None, **changes):
        options = dict(today=TODAY, clock=lambda: self.now, checkpoint=self.save)
        options.update(changes)
        with mock.patch.object(pc, "send_push", side_effect=sender) as send, \
                contextlib.redirect_stderr(io.StringIO()):
            stats = pp.send_deliveries(self.subs, self.events, self.state, {}, **options)
        return stats, send

    def reload(self):
        self.state = pd.load(self.path)

    def jobs(self):
        return list(self.state["deliveries"].values())

    def test_partial_success_survives_restart_and_only_failed_device_retries(self):
        self.queue()

        def first(record, payload, **kwargs):
            if record["name"] == "b":
                raise TimeoutError("synthetic timeout")

        stats, _ = self.deliver(first)
        self.assertEqual((stats["sent"], stats["failed"]), (1, 1))
        self.reload()
        devices = self.state["sent"]["event-a"]["devices"]
        self.assertEqual(devices["a"]["status"], "sent")
        self.assertEqual(devices["b"]["status"], "retry")
        self.assertNotIn("sent_at", devices["b"])
        self.assertNotIn("sent_at", self.state["sent"]["event-a"])
        _, send = self.deliver()
        send.assert_not_called()  # Immediate retries respect persisted backoff.
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver()
        self.assertEqual([c.args[0]["name"] for c in send.call_args_list], ["b"])
        self.reload()
        self.assertEqual(self.state["sent"]["event-a"]["status"], "complete")
        _, send = self.deliver()
        send.assert_not_called()

    def test_individual_event_receipts_do_not_repeat_successful_siblings(self):
        self.events = [event(f"event-{n}") for n in range(3)]
        self.subs = subscriptions("a")
        self.queue()

        def first(record, payload, **kwargs):
            if payload["tag"] == "chumei-event-1":
                raise TimeoutError()

        stats, _ = self.deliver(first)
        self.assertEqual((stats["sent"], stats["failed"]), (2, 1))
        self.reload()
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver()
        self.assertEqual([c.args[1]["tag"] for c in send.call_args_list], ["chumei-event-1"])

    def test_digest_membership_is_frozen_and_every_member_gets_a_receipt(self):
        self.events = [event(f"event-{n}") for n in range(4)]
        self.queue()

        def first(record, payload, **kwargs):
            if record["name"] == "b":
                raise TimeoutError()

        self.deliver(first)
        self.reload()
        self.events.append(event("new-event"))
        self.queue()
        self.assertEqual(len(self.jobs()), 4)  # Two original digests, two new singles.
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver()
        digest_calls = [c for c in send.call_args_list if c.args[1]["tag"].startswith("chumei-digest-")]
        self.assertEqual(len(digest_calls), 1)
        self.assertEqual(digest_calls[0].args[0]["name"], "b")
        self.assertIn("4 場", digest_calls[0].args[1]["title"])
        for item in self.events:
            devices = self.state["sent"][item["id"]]["devices"]
            self.assertEqual({d["status"] for d in devices.values()}, {"sent"})

    def test_retry_budget_is_durable_and_exhaustion_is_never_sent(self):
        self.subs = subscriptions("a")
        self.queue()
        for attempt in range(1, pd.MAX_ATTEMPTS + 1):
            _, send = self.deliver(lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
            send.assert_called_once()
            self.reload()
            job = self.jobs()[0]
            self.assertEqual(job["attempts"], attempt)
            if attempt < pd.MAX_ATTEMPTS:
                self.assertEqual(job["next_attempt_at"] - self.now, pd.retry_delay(attempt))
                self.assertLessEqual(pd.retry_delay(attempt), pd.RETRY_MAX_SECONDS)
            self.now = job["next_attempt_at"]
        self.assertEqual(self.jobs()[0]["status"], "exhausted")
        device = self.state["sent"]["event-a"]["devices"]["a"]
        self.assertEqual(device["status"], "exhausted")
        self.assertNotIn("sent_at", device)
        self.now += 100000
        _, send = self.deliver()
        send.assert_not_called()

    def test_gone_prunes_and_prevents_all_later_jobs_for_same_endpoint(self):
        self.events = [event("one"), event("two")]
        self.queue()

        def sender(record, payload, **kwargs):
            if record["name"] == "a":
                raise pc.PushGone(record["sub"]["endpoint"])

        with mock.patch.object(pc, "prune_endpoint") as prune:
            stats, send = self.deliver(sender)
        prune.assert_called_once_with(self.subs["a"]["sub"]["endpoint"])
        self.assertEqual([c.args[0]["name"] for c in send.call_args_list], ["a", "b", "b"])
        self.assertEqual((stats["gone"], stats["sent"]), (1, 2))
        self.reload()
        with mock.patch.object(pc, "prune_endpoint") as prune:
            _, send = self.deliver()
        send.assert_not_called()
        prune.assert_called_once()  # Retry an earlier prune failure, without pushing.
        for entry in self.state["sent"].values():
            self.assertEqual(entry["devices"]["a"]["status"], "gone")

    def test_save_failure_before_intent_blocks_network(self):
        self.queue()
        with mock.patch.object(pc, "send_push") as send:
            with self.assertRaises(OSError):
                pp.send_deliveries(self.subs, self.events, self.state, {}, today=TODAY,
                                   checkpoint=mock.Mock(side_effect=OSError("synthetic disk failure")))
        send.assert_not_called()
        self.reload()
        self.assertEqual([job["attempts"] for job in self.jobs()], [0, 0])

    def test_receipt_journal_recovers_after_snapshot_replacement_failure(self):
        self.queue()
        original = pd._atomic_write

        def write(path, data):
            if path == self.path and any(j["status"] == "sent" for j in json.loads(data)["deliveries"].values()):
                raise OSError("synthetic snapshot failure")
            return original(path, data)

        with mock.patch.object(pd, "_atomic_write", side_effect=write), \
                mock.patch.object(pc, "send_push") as send:
            with self.assertRaises(OSError):
                pp.send_deliveries(self.subs, self.events, self.state, {}, today=TODAY,
                                   clock=lambda: self.now, checkpoint=self.save)
        send.assert_called_once()  # Abort before the second recipient.
        self.assertTrue(pd.journal_path(self.path).exists())
        self.reload()
        self.assertEqual(self.state["sent"]["event-a"]["devices"]["a"]["status"], "sent")
        _, send = self.deliver()
        self.assertEqual([c.args[0]["name"] for c in send.call_args_list], ["b"])
        self.assertFalse(pd.journal_path(self.path).exists())

    def test_backup_with_older_journal_uses_newer_snapshot_receipts(self):
        self.queue()
        old = self.path.read_text()
        self.deliver()
        pd.journal_path(self.path).write_text(old)
        self.reload()
        _, send = self.deliver()
        send.assert_not_called()
        self.assertEqual({job["status"] for job in self.jobs()}, {"sent"})

    def test_valid_journal_recovers_a_corrupt_snapshot(self):
        self.queue()
        self.deliver()
        pd.journal_path(self.path).write_bytes(self.path.read_bytes())
        self.path.write_text("{torn snapshot")
        self.reload()
        _, send = self.deliver()
        send.assert_not_called()

    def test_crash_during_send_is_uncertain_and_respects_backoff_after_restart(self):
        self.subs = subscriptions("a")
        self.queue()
        with self.assertRaises(KeyboardInterrupt):
            self.deliver(lambda *a, **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.reload()
        self.assertEqual(self.jobs()[0]["status"], "sending")
        self.assertEqual(self.jobs()[0]["attempts"], 1)
        self.assertNotIn("sent_at", self.state["sent"]["event-a"]["devices"]["a"])
        _, send = self.deliver()
        send.assert_not_called()
        self.now += pd.RETRY_BASE_SECONDS
        self.deliver()
        self.reload()
        self.assertEqual((self.jobs()[0]["status"], self.jobs()[0]["attempts"]), ("sent", 2))

    def test_interruption_after_final_intent_does_not_exceed_budget(self):
        self.subs = subscriptions("a")
        self.queue()
        job = self.jobs()[0]
        job.update(attempts=pd.MAX_ATTEMPTS, status="sending", next_attempt_at=self.now + 1800)
        self.save(self.state)
        self.reload()
        _, send = self.deliver()
        send.assert_not_called()
        self.assertEqual(self.jobs()[0]["status"], "exhausted")

    def test_expired_rejected_removed_and_unsubscribed_jobs_are_cancelled(self):
        cases = (
            lambda: self.events[0].update(start_at=(TODAY - timedelta(days=1)).isoformat()),
            lambda: self.events[0].update(status="rejected"),
            lambda: self.events.clear(),
            lambda: self.subs.clear(),
        )
        for change in cases:
            with self.subTest(change=change):
                self.state = pd.migrate({})
                self.events = [event()]
                self.subs = subscriptions("a")
                self.queue()
                change()
                _, send = self.deliver()
                send.assert_not_called()
                self.reload()
                self.assertEqual(self.jobs()[0]["status"], "cancelled")

    def test_digest_drops_expired_member_without_replaying_delivered_events(self):
        self.subs = subscriptions("a")
        self.events = [event(f"event-{n}") for n in range(4)]
        self.queue()
        self.events[0]["status"] = "rejected"
        _, send = self.deliver()
        send.assert_called_once()
        self.assertIn("3 場", send.call_args.args[1]["title"])
        self.assertEqual(self.state["sent"]["event-0"]["devices"]["a"]["status"], "cancelled")
        self.assertEqual(self.state["sent"]["event-1"]["devices"]["a"]["status"], "sent")

    def test_no_matching_recipients_is_a_durable_replay_fence(self):
        self.subs = {"a": {"prefs": {"mode": "following", "orgs": []}}}
        self.queue()
        self.reload()
        self.assertEqual(self.state["sent"]["event-a"]["reason"], "no_recipients")
        self.subs = subscriptions("new-device")
        self.queue()
        _, send = self.deliver()
        send.assert_not_called()

    def test_reminder_partial_success_retries_only_failed_device_even_for_old_posts(self):
        self.events[0]["source"]["posted_at"] = (TODAY - timedelta(days=100)).isoformat()
        self.subs = subscriptions("a", "b", user_id="fixture-user")
        going = {"fixture-user": ["event-a"]}
        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
        self.save(self.state)

        def first(record, payload, **kwargs):
            if record["name"] == "b":
                raise TimeoutError()

        with mock.patch.object(pc, "send_push", side_effect=first), contextlib.redirect_stderr(io.StringIO()):
            pp.send_deliveries(self.subs, self.events, self.state, going, today=TODAY,
                               clock=lambda: self.now, checkpoint=self.save)
        self.reload()
        entry = self.state["reminders"]["fixture-user:event-a"]
        self.assertEqual(entry["devices"]["a"]["status"], "sent")
        self.assertEqual(entry["devices"]["b"]["status"], "retry")
        self.assertEqual(pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY), 0)
        self.now += pd.RETRY_BASE_SECONDS
        with mock.patch.object(pc, "send_push") as send:
            pp.send_deliveries(self.subs, self.events, self.state, going,
                               today=TODAY + timedelta(days=1), clock=lambda: self.now, checkpoint=self.save)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0]["name"], "b")
        self.assertTrue(send.call_args.args[1]["title"].startswith("今天："))
        self.assertEqual(send.call_args.kwargs["ttl"], 6 * 3600)

    def test_reminder_withdrawn_or_device_unbound_cancels_without_send(self):
        for withdrawn in (True, False):
            with self.subTest(withdrawn=withdrawn):
                self.state = pd.migrate({})
                self.subs = subscriptions("a", user_id="fixture-user")
                going = {"fixture-user": ["event-a"]}
                pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
                if withdrawn:
                    going.clear()
                else:
                    self.subs["a"]["user_id"] = "different-user"
                with mock.patch.object(pc, "send_push") as send:
                    pp.send_deliveries(self.subs, self.events, self.state, going, today=TODAY,
                                       clock=lambda: self.now, checkpoint=self.save)
                send.assert_not_called()
                self.assertEqual(self.jobs()[0]["status"], "cancelled")

    def test_legacy_migration_preserves_all_historical_fences_and_alias_reminders(self):
        legacy = {"version": 1, "sent": {"event-a": {"sent_at": "old"}, "empty": {}},
                  "reminders": {"fixture-user:old-alias": {"sent_at": "old"}}}
        self.path.write_text(json.dumps(legacy))
        self.reload()
        self.assertEqual(self.state["version"], 2)
        self.assertEqual(self.state["deliveries"], {})
        self.events += [event("empty"), event("canonical", merged_event_ids=["old-alias"])]
        self.assertEqual([e["id"] for e in pp.pending_events(self.events, self.state)], ["canonical"])
        self.subs = subscriptions("a", user_id="fixture-user")
        self.assertEqual(pp.queue_reminders(self.subs, self.events,
                                           {"fixture-user": ["old-alias", "canonical"]},
                                           self.state, today=TODAY), 0)
        self.save(self.state)
        self.reload()
        self.assertEqual(self.state["sent"], legacy["sent"])

    def test_legacy_baseline_alias_does_not_replay_as_new_canonical_event(self):
        self.state = pd.migrate({"sent": {"old-event": {"baselined_at": "old"}}})
        self.events = [event("canonical", merged_event_ids=["old-event"])]
        self.assertEqual(pp.pending_events(self.events, self.state), [])

    def test_merged_event_does_not_repeat_successful_device_from_an_alias_job(self):
        self.subs = subscriptions("a")
        self.events = [event("old-one"), event("old-two")]
        self.queue()

        def first(record, payload, **kwargs):
            if payload["tag"] == "chumei-old-two":
                raise TimeoutError()

        self.deliver(first)
        self.reload()
        self.events = [event("canonical", merged_event_ids=["old-one", "old-two"])]
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver()
        send.assert_not_called()
        self.assertEqual(self.state["sent"]["old-two"]["devices"]["a"]["status"], "sent")

    def test_reminder_merger_keeps_existing_receipts_and_deduplicates_aliases(self):
        self.subs = subscriptions("a", user_id="fixture-user")
        going = {"fixture-user": ["event-a"]}
        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
        self.events = [event("canonical", merged_event_ids=["event-a"])]
        going = {"fixture-user": ["event-a", "canonical"]}
        self.assertEqual(pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY), 0)
        with mock.patch.object(pc, "send_push") as send:
            pp.send_deliveries(self.subs, self.events, self.state, going, today=TODAY,
                               clock=lambda: self.now, checkpoint=self.save)
        send.assert_called_once()
        self.assertIn("/canonical/", send.call_args.args[1]["url"])

    def test_receipts_and_errors_do_not_store_endpoint_or_provider_message(self):
        self.subs = subscriptions("a")
        self.queue()
        secret_marker = "private-provider-endpoint-token"
        captured = io.StringIO()
        with mock.patch.object(pc, "send_push", side_effect=TimeoutError(secret_marker)), \
                contextlib.redirect_stderr(captured):
            pp.send_deliveries(self.subs, self.events, self.state, {}, today=TODAY,
                               clock=lambda: self.now, checkpoint=self.save)
        text = self.path.read_text() + captured.getvalue()
        self.assertNotIn(secret_marker, text)
        self.assertNotIn(self.subs["a"]["sub"]["endpoint"], text)


class PublisherBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state" / "publish.json"
        self.events = [event()]
        patches = {
            "STATE_PATH": self.path, "load_events": lambda: self.events,
            "is_silent_hour": lambda: False,
        }
        for name, replacement in patches.items():
            patch = mock.patch.object(pp, name, replacement)
            patch.start()
            self.addCleanup(patch.stop)
        for name, value in (("push_enabled", True), ("load_subs", {"subs": subscriptions("a")}),
                            ("account_going", {}), ("account_follows", {}), ("load_org_sids", {})):
            patch = mock.patch.object(pc, name, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(pc, "send_push")
        self.send = patch.start()
        self.addCleanup(patch.stop)
        self.output = io.StringIO()
        for redirect in (contextlib.redirect_stdout(self.output), contextlib.redirect_stderr(self.output)):
            redirect.__enter__()
            self.addCleanup(redirect.__exit__, None, None, None)

    def main(self, *args):
        with mock.patch.object(sys, "argv", ["publish_push.py", *args]):
            return pp.main()

    def test_first_run_baseline_sends_nothing_and_is_preserved(self):
        self.assertEqual(self.main(), 0)
        self.send.assert_not_called()
        self.assertIn("baselined_at", pd.load(self.path)["sent"]["event-a"])
        self.assertEqual(self.main(), 0)
        self.send.assert_not_called()

    def test_dry_run_creates_no_state_or_lock_or_receipts(self):
        self.assertEqual(self.main("--dry-run"), 0)
        self.assertFalse(self.path.parent.exists())
        pd.save(pd.migrate({}), self.path)
        before = self.path.read_bytes()
        self.assertEqual(self.main("--dry-run"), 0)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(Path(str(self.path) + ".lock").exists())
        self.send.assert_not_called()

    def test_quiet_hours_hold_both_new_events_and_existing_retries(self):
        state = pd.migrate({})
        pp.queue_events(subscriptions("a"), self.events, state, {}, {})
        pd.save(state, self.path)
        before = self.path.read_bytes()
        with mock.patch.object(pp, "is_silent_hour", return_value=True):
            self.assertEqual(self.main(), 0)
        self.send.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        with mock.patch.object(pp, "is_silent_hour", return_value=True):
            self.assertEqual(self.main("--ignore-quiet-hours"), 0)
        self.send.assert_called_once()

    def test_publish_lock_rejects_overlapping_senders(self):
        pd.save(pd.migrate({}), self.path)
        with pd.publisher_lock(self.path) as acquired:
            self.assertTrue(acquired)
            self.assertEqual(self.main(), 0)
        self.send.assert_not_called()
        self.assertEqual(pd.load(self.path)["sent"], {})

    def test_main_retries_existing_outbox_even_when_no_new_events(self):
        pd.save(pd.migrate({}), self.path)
        self.send.side_effect = TimeoutError()
        self.assertEqual(self.main(), 1)
        state = pd.load(self.path)
        self.assertNotIn("last_success_at", state)
        self.assertEqual(pp.pending_events(self.events, state), [])
        self.send.reset_mock(side_effect=True)
        due = next(iter(state["deliveries"].values()))["next_attempt_at"]
        with mock.patch.object(pp.time, "time", return_value=due):
            self.assertEqual(self.main(), 0)
        self.send.assert_called_once()
        self.assertIn("last_success_at", pd.load(self.path))

    def test_account_database_failure_does_not_advance_or_cancel_state(self):
        state = pd.migrate({})
        subs = subscriptions("a", user_id="fixture-user")
        pp.queue_reminders(subs, self.events, {"fixture-user": ["event-a"]}, state, today=TODAY)
        pd.save(state, self.path)
        before = self.path.read_bytes()
        with mock.patch.object(pc, "load_subs", return_value={"subs": subs}), \
                mock.patch.object(pc, "account_going", side_effect=OSError("fixture DB unavailable")):
            self.assertEqual(self.main(), 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.send.assert_not_called()

    def test_journal_recovers_baseline_even_when_snapshot_never_existed(self):
        state = pd.migrate({"sent": {"event-a": {"baselined_at": "old"}}})
        original = pd._atomic_write

        def write(path, data):
            if path == self.path:
                raise OSError("synthetic failure")
            original(path, data)

        with mock.patch.object(pd, "_atomic_write", side_effect=write):
            with self.assertRaises(OSError):
                pd.save(state, self.path)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.main(), 0)
        self.send.assert_not_called()

    def test_corrupt_journal_fails_closed_instead_of_using_stale_snapshot(self):
        pd.save(pd.migrate({}), self.path)
        pd.journal_path(self.path).write_text("{not valid json")
        self.assertEqual(self.main(), 1)
        self.send.assert_not_called()

    def test_future_version_fails_closed(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"version": 999, "sent": {}}')
        self.assertEqual(self.main(), 1)
        self.send.assert_not_called()

    def test_state_files_are_private(self):
        pd.save(pd.migrate({}), self.path)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)


class GoneStatusTest(unittest.TestCase):
    def test_strict_account_query_fails_for_missing_or_corrupt_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.sqlite3"
            with mock.patch.object(pc, "_auth_db_path", return_value=path):
                self.assertEqual(pc.account_going(), {})
                with self.assertRaises(OSError):
                    pc.account_going(strict=True)
                path.write_text("synthetic broken DB")
                self.assertEqual(pc.account_follows(), {})
                with self.assertRaises(OSError):
                    pc.account_follows(strict=True)

    def test_actual_helper_classifies_404_and_410_as_gone(self):
        from pywebpush import WebPushException
        import requests
        record = {"sub": {"endpoint": "https://fcm.googleapis.com/synthetic-fixture"}}
        for status in (404, 410, 429, 500):
            with self.subTest(status=status):
                response = requests.Response()
                response.status_code = status
                error = WebPushException("fixture error", response=response)
                expected = pc.PushGone if status in (404, 410) else WebPushException
                with mock.patch("safe_outbound.validate_push_endpoint"), \
                        mock.patch("pywebpush.webpush", side_effect=error):
                    with self.assertRaises(expected):
                        pc.send_push(record, {"title": "fixture"})


if __name__ == "__main__":
    unittest.main()
