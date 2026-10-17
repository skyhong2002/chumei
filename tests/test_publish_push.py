"""Offline delivery faults: synthetic subscriptions, private temp state, no pushes."""

import contextlib
import copy
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
        self.real_load_subs = pc.load_subs
        patch = mock.patch.object(pc, "load_subs", side_effect=lambda: {"subs": self.subs})
        patch.start()
        self.addCleanup(patch.stop)

    def save(self, state):
        pd.save(state, self.path)

    def queue(self):
        pp.queue_events(self.subs, pp.pending_events(self.events, self.state), self.state, {}, {})
        self.save(self.state)

    def queue_older_events(self):
        self.queue()
        for job in self.jobs():
            job.pop("recipient_user_id")  # Earlier v2 job schema.
        self.save(self.state)
        self.reload()

    def deliver(self, sender=None, *, going=None, **changes):
        options = dict(today=TODAY, clock=lambda: self.now, checkpoint=self.save)
        options.update(changes)
        with mock.patch.object(pc, "send_push", side_effect=sender) as send, \
                contextlib.redirect_stderr(io.StringIO()):
            stats = pp.send_deliveries(self.subs, self.events, self.state, going or {}, **options)
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

    def test_reminder_alias_retry_inherits_success_for_same_user_and_device(self):
        self.subs = subscriptions("a", user_id="fixture-user")
        self.events = [event("old-one"), event("old-two")]
        going = {"fixture-user": ["old-one", "old-two"]}
        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)

        def partial(record, payload, **kwargs):
            if "/old-two/" in payload["url"]:
                raise TimeoutError()

        self.deliver(partial, going=going)
        self.reload()
        self.events = [event("canonical", merged_event_ids=["old-one", "old-two"])]
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver(going=going)
        send.assert_not_called()
        self.reload()
        self.assertEqual(self.state["reminders"]["fixture-user:old-two"]["devices"]["a"]["status"], "sent")

    def test_pending_reminder_aliases_merge_to_one_send_per_device(self):
        self.subs = subscriptions("a", "b", user_id="fixture-user")
        self.events = [event("old-one"), event("old-two")]
        going = {"fixture-user": ["old-one", "old-two"]}
        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
        self.events = [event("canonical", merged_event_ids=["old-one", "old-two"])]
        _, send = self.deliver(going=going)
        self.assertEqual([c.args[0]["name"] for c in send.call_args_list], ["a", "b"])
        self.assertEqual({c.args[1]["tag"] for c in send.call_args_list}, {"chumei-remind-canonical"})

    def test_reminder_alias_success_is_scoped_to_user_and_device(self):
        self.subs = subscriptions("a", "b", user_id="fixture-user")
        self.events = [event("old-one"), event("old-two")]
        going = {"fixture-user": ["old-one", "old-two"]}
        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
        self.state["reminders"]["other-user:old-one"] = {"sent_at": "old"}

        def fail_b(record, payload, **kwargs):
            if record["name"] == "b":
                raise TimeoutError()

        self.deliver(fail_b, going=going)
        self.reload()
        self.events = [event("canonical", merged_event_ids=["old-one", "old-two"])]
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver(going=going)
        self.assertEqual([c.args[0]["name"] for c in send.call_args_list], ["b"])

    def test_queued_merge_respects_all_legacy_memberships_for_events_and_reminders(self):
        for kind in ("event", "reminder"):
            for legacy in ({}, {"sent_at": "old"}, {"baselined_at": "old"}):
                for version in (1, 2):
                    with self.subTest(kind=kind, legacy=legacy, version=version):
                        bucket = "sent" if kind == "event" else "reminders"
                        identifier = "old-one" if kind == "event" else "fixture-user:old-one"
                        self.state = pd.migrate({"version": version, bucket: {identifier: copy.deepcopy(legacy)}})
                        self.subs = subscriptions("a", user_id="fixture-user")
                        self.events = [event("old-two")]
                        going = {"fixture-user": ["old-two"]}
                        if kind == "event":
                            self.queue()
                        else:
                            pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
                        self.save(self.state)
                        self.reload()
                        self.events = [event("canonical", merged_event_ids=["old-one", "old-two"])]
                        _, send = self.deliver(going=going)
                        send.assert_not_called()
                        self.assertEqual(self.jobs()[0]["status"], "cancelled")
                        self.assertEqual(self.state[bucket][identifier], legacy)

    def test_subscription_revocations_during_batch_are_read_from_current_store(self):
        for kind in ("event", "reminder"):
            for change in ("unsubscribe", "unlink", "rebind"):
                with self.subTest(kind=kind, change=change):
                    self.state = pd.migrate({})
                    self.subs = subscriptions("a", "b", user_id="fixture-user")
                    self.events = [event()]
                    going = {"fixture-user": ["event-a"]}
                    if kind == "event":
                        self.queue()
                    else:
                        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
                    store = Path(self.tmp.name) / "subscriptions.json"
                    store.write_text(json.dumps({"subs": self.subs}))

                    def revoke_b(record, payload, **kwargs):
                        current = json.loads(store.read_text())
                        if change == "unsubscribe":
                            current["subs"].pop("b")
                        elif change == "unlink":
                            current["subs"]["b"].pop("user_id")
                        else:
                            current["subs"]["b"]["user_id"] = "another-user"
                        store.write_text(json.dumps(current))

                    with mock.patch.object(pc, "SUBS_PATH", store), \
                            mock.patch.object(pc, "load_subs", side_effect=self.real_load_subs):
                        _, send = self.deliver(revoke_b, going=going)
                    self.assertEqual([c.args[0]["name"] for c in send.call_args_list], ["a"])
                    self.assertIn("b", self.subs)  # Initial snapshot was never mutated.
                    self.reload()
                    self.assertEqual(self.jobs()[1]["status"], "cancelled")

    def test_revalidation_follows_intent_checkpoint_and_does_not_add_new_devices(self):
        self.subs = subscriptions("a", user_id="fixture-user")
        self.queue()

        def checkpoint(state):
            self.save(state)
            self.subs = subscriptions("new-device", user_id="fixture-user")

        _, send = self.deliver(checkpoint=checkpoint)
        send.assert_not_called()
        self.assertEqual(self.jobs()[0]["status"], "cancelled")
        self.assertEqual(len(self.jobs()), 1)

    def test_subscription_read_failure_stops_batch_without_sending(self):
        self.queue()
        with mock.patch.object(pc, "load_subs", side_effect=OSError("synthetic read failure")), \
                mock.patch.object(pc, "send_push") as send:
            with self.assertRaises(OSError):
                pp.send_deliveries(self.subs, self.events, self.state, {}, checkpoint=self.save)
        send.assert_not_called()
        self.reload()
        self.assertEqual([j["status"] for j in self.jobs()], ["sending", "pending"])

    def test_retry_payload_survives_restart_and_metadata_changes(self):
        for kind in ("event", "digest", "reminder"):
            with self.subTest(kind=kind):
                self.state = pd.migrate({})
                self.subs = subscriptions("a", user_id="fixture-user")
                self.events = [event(str(n)) for n in range(4 if kind == "digest" else 1)]
                going = {"fixture-user": ["0"]}
                if kind == "reminder":
                    pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
                else:
                    self.queue()

                def timeout(record, payload, **kwargs):
                    # Payload is durable before any transport can observe it.
                    persisted = next(iter(pd.load(self.path)["deliveries"].values()))
                    self.assertEqual(persisted["payload"], payload)
                    raise TimeoutError()

                _, first = self.deliver(timeout, going=going)
                original = copy.deepcopy(first.call_args.args[1])
                self.reload()
                for item in self.events:
                    item.update(title="CHANGED TITLE", venue="CHANGED VENUE", summary="CHANGED SUMMARY",
                                start_at=item["start_at"].replace("19:00", "20:00"))
                self.now += pd.RETRY_BASE_SECONDS
                _, retry = self.deliver(going=going)
                retry.assert_called_once()
                self.assertEqual(retry.call_args.args[1], original)
                self.assertEqual(self.jobs()[0]["payload"], original)

    def test_digest_retry_removes_cancelled_member_using_frozen_content(self):
        self.subs = subscriptions("a")
        self.events = [event(str(n)) for n in range(4)]
        original = copy.deepcopy(self.events)
        self.queue()
        self.deliver(lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
        self.reload()
        self.events[0]["status"] = "rejected"
        for item in self.events:
            item["title"] = "CHANGED TITLE"
        self.events.append(event("later"))
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver()
        expected = pp.digest_payload(original[1:])
        expected["tag"] = f"chumei-digest-{self.jobs()[0]['id']}"
        self.assertEqual(send.call_args.args[1], expected)
        self.assertEqual(self.state["sent"]["0"]["devices"]["a"]["status"], "cancelled")
        self.assertNotIn("later", self.state["sent"])

    def test_reminder_rollover_changes_only_day_wording_in_frozen_payload(self):
        self.subs = subscriptions("a", user_id="fixture-user")
        going = {"fixture-user": ["event-a"]}
        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
        _, first = self.deliver(lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()), going=going)
        original = copy.deepcopy(first.call_args.args[1])
        self.reload()
        self.events[0].update(title="CHANGED TITLE", venue="CHANGED VENUE")
        self.now += pd.RETRY_BASE_SECONDS
        _, send = self.deliver(going=going, today=TODAY + timedelta(days=1))
        original["title"] = "今天" + original["title"][2:]
        self.assertEqual(send.call_args.args[1], original)

    def test_older_attempt_without_payload_is_held_unresolved_not_rebuilt(self):
        self.queue()
        job = self.jobs()[0]
        job.update(status="retry", attempts=1)
        self.save(self.state)
        self.reload()
        _, send = self.deliver()
        self.assertEqual([c.args[0]["name"] for c in send.call_args_list], ["b"])
        self.reload()
        held = self.jobs()[0]
        self.assertEqual((held["status"], held["reason"], held["attempts"]),
                         ("exhausted", "missing_frozen_payload", 1))
        self.assertNotIn("payload", held)

    def test_older_unattempted_job_freezes_binding_with_payload_and_reuses_both(self):
        for user_id in (None, "original-user"):
            for count in (1, 4):
                with self.subTest(user_id=user_id, count=count):
                    self.state = pd.migrate({})
                    self.subs = subscriptions("a", user_id=user_id)
                    self.events = [event(str(n)) for n in range(count)]
                    self.queue_older_events()
                    intents = []

                    def timeout(record, payload, **kwargs):
                        intents.append(next(iter(pd.load(self.path)["deliveries"].values())))
                        raise TimeoutError()

                    _, first = self.deliver(timeout)
                    first.assert_called_once()
                    original = copy.deepcopy(first.call_args.args[1])
                    self.assertEqual(intents[0]["recipient_user_id"], user_id)
                    self.assertEqual(intents[0]["payload"], original)
                    self.assertEqual((intents[0]["status"], intents[0]["attempts"]), ("sending", 1))
                    self.reload()
                    self.now = self.jobs()[0]["next_attempt_at"]
                    _, retry = self.deliver()
                    retry.assert_called_once()
                    self.assertEqual(retry.call_args.args[1], original)
                    self.reload()
                    self.assertEqual(self.jobs()[0]["recipient_user_id"], user_id)
                    self.assertEqual(self.jobs()[0]["status"], "sent")

    def test_older_event_retry_cannot_follow_rebound_unlinked_or_removed_device(self):
        for count in (1, 4):
            for change in ("rebind", "unlink", "unsubscribe", "link"):
                with self.subTest(count=count, change=change):
                    self.state = pd.migrate({})
                    original_user = None if change == "link" else "original-user"
                    self.subs = subscriptions("a", user_id=original_user)
                    self.events = [event(str(n)) for n in range(count)]
                    self.queue_older_events()
                    self.deliver(lambda *a, **kw: (_ for _ in ()).throw(TimeoutError()))
                    self.reload()
                    original = copy.deepcopy(self.jobs()[0]["payload"])
                    self.now = self.jobs()[0]["next_attempt_at"]
                    # A later invocation starts with a fresh subscriptions snapshot.
                    self.subs = subscriptions("a", user_id="different-user")
                    if change == "unlink":
                        self.subs["a"].pop("user_id")
                    elif change == "unsubscribe":
                        self.subs.clear()
                    self.subs.update(subscriptions("new-device", user_id="different-user"))
                    _, send = self.deliver()
                    send.assert_not_called()
                    self.reload()
                    held = self.jobs()[0]
                    self.assertEqual((held["status"], held["recipient_user_id"]),
                                     ("cancelled", original_user))
                    self.assertEqual(held["payload"], original)
                    self.queue()  # Neither a new account nor device can replay this cohort.
                    self.assertEqual(len(self.jobs()), 1)
                    for entry in self.state["sent"].values():
                        self.assertEqual(set(entry["devices"]), {"a"})
                        self.assertEqual(entry["devices"]["a"]["status"], "cancelled")
                        self.assertNotIn("sent_at", entry["devices"]["a"])

    def test_older_job_binding_survives_interrupted_intent_and_journal_recovery(self):
        for interruption in ("after_save", "snapshot_failure"):
            for rebind in (False, True):
                with self.subTest(interruption=interruption, rebind=rebind):
                    self.state = pd.migrate({})
                    self.subs = subscriptions("a", user_id="original-user")
                    self.queue_older_events()
                    original_write = pd._atomic_write

                    def write(path, data):
                        if interruption == "snapshot_failure" and path == self.path:
                            raise OSError("synthetic snapshot failure after intent journal")
                        return original_write(path, data)

                    def checkpoint(state):
                        self.save(state)
                        raise KeyboardInterrupt()

                    with mock.patch.object(pd, "_atomic_write", side_effect=write), \
                            mock.patch.object(pc, "send_push") as send:
                        with self.assertRaises(KeyboardInterrupt if interruption == "after_save" else OSError):
                            pp.send_deliveries(self.subs, self.events, self.state, {}, today=TODAY,
                                               clock=lambda: self.now, checkpoint=checkpoint)
                    send.assert_not_called()
                    self.reload()
                    held = self.jobs()[0]
                    self.assertEqual((held["recipient_user_id"], held["status"], held["attempts"]),
                                     ("original-user", "sending", 1))
                    original = copy.deepcopy(held["payload"])
                    self.now = held["next_attempt_at"]
                    self.subs = subscriptions("a", user_id="different-user" if rebind else "original-user")
                    _, retry = self.deliver()
                    if rebind:
                        retry.assert_not_called()
                        self.assertEqual(self.jobs()[0]["status"], "cancelled")
                    else:
                        retry.assert_called_once()
                        self.assertEqual(retry.call_args.args[1], original)
                    self.assertFalse(pd.journal_path(self.path).exists())

    def test_older_job_failed_intent_does_not_persist_a_partial_binding_upgrade(self):
        self.subs = subscriptions("a", user_id="original-user")
        self.queue_older_events()
        with mock.patch.object(pc, "send_push") as send, self.assertRaises(OSError):
            pp.send_deliveries(self.subs, self.events, self.state, {}, today=TODAY,
                               checkpoint=mock.Mock(side_effect=OSError("synthetic disk failure")))
        send.assert_not_called()
        self.reload()
        self.assertEqual(self.jobs()[0]["attempts"], 0)
        self.assertNotIn("payload", self.jobs()[0])
        self.assertNotIn("recipient_user_id", self.jobs()[0])

    def test_older_job_rebind_at_checkpoint_cannot_replace_first_observed_binding(self):
        self.subs = subscriptions("a", user_id="original-user")
        self.queue_older_events()

        def checkpoint(state):
            self.save(state)
            self.subs = subscriptions("a", user_id="different-user")

        _, send = self.deliver(checkpoint=checkpoint)
        send.assert_not_called()
        self.reload()
        self.assertEqual((self.jobs()[0]["status"], self.jobs()[0]["recipient_user_id"]),
                         ("cancelled", "original-user"))

    def test_older_reminder_retry_can_recover_binding_from_frozen_user_id(self):
        self.subs = subscriptions("a", user_id="original-user")
        going = {"original-user": ["event-a"]}
        pp.queue_reminders(self.subs, self.events, going, self.state, today=TODAY)
        self.deliver(lambda *a, **kw: (_ for _ in ()).throw(TimeoutError()), going=going)
        self.jobs()[0].pop("recipient_user_id")
        self.save(self.state)
        self.reload()
        self.now = self.jobs()[0]["next_attempt_at"]
        _, retry = self.deliver(going=going)
        retry.assert_called_once()
        self.reload()
        self.assertEqual(self.jobs()[0]["recipient_user_id"], "original-user")


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

    def test_old_attempt_with_payload_but_no_binding_requires_review_preserving_success(self):
        for count in (1, 4):
            for status in ("retry", "sending"):
                with self.subTest(count=count, status=status):
                    self.events = [event(str(n)) for n in range(count)]
                    state = pd.migrate({"last_success_at": "previous-success"})
                    subs = subscriptions("a", "b", user_id="original-user")
                    pp.queue_events(subs, self.events, state, {}, {})
                    successful, uncertain = state["deliveries"].values()
                    pd.finish(state, successful, "sent", "historical-success")
                    before = copy.deepcopy(state["sent"])
                    original = pp.frozen_payload(uncertain, self.events, uncertain["event_ids"], TODAY)
                    uncertain.pop("recipient_user_id")
                    uncertain.update(status=status, attempts=1)
                    pd.save(state, self.path)
                    self.send.reset_mock()
                    with mock.patch.object(pc, "load_subs", return_value={"subs": subs}):
                        self.assertEqual(self.main(), 1)
                        self.assertEqual(self.main(), 1)  # Exhaustion cannot reopen a cohort.
                    self.send.assert_not_called()
                    persisted = pd.load(self.path)
                    held = persisted["deliveries"][uncertain["id"]]
                    self.assertEqual((held["status"], held["reason"], held["attempts"]),
                                     ("exhausted", "missing_recipient_binding", 1))
                    self.assertEqual(held["payload"], original)
                    self.assertNotIn("recipient_user_id", held)
                    self.assertEqual(persisted["last_success_at"], "previous-success")
                    self.assertEqual(len(persisted["deliveries"]), 2)
                    for eid in uncertain["event_ids"]:
                        devices = persisted["sent"][eid]["devices"]
                        self.assertEqual(devices["a"], before[eid]["devices"]["a"])
                        self.assertEqual(devices["b"]["status"], "exhausted")
                        self.assertNotIn("sent_at", devices["b"])

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
