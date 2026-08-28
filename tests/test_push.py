"""Web Push 測試：偏好比對、訂閱儲存、以及不靠瀏覽器的端到端加密驗證——
偽造一個帶真 P-256 金鑰的訂閱、endpoint 指向本地 HTTP sink，
用 pywebpush 實發後以 http_ece 解密，確認 VAPID 標頭與 payload 完整。"""

import base64
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import push_common as pc


def event(**overrides):
    value = {
        "id": "evt_x",
        "title": "AI 半導體趨勢講座",
        "summary": "從製程談到系統",
        "description": "",
        "organizer": "清大電機系學會",
        "venue": "台達館",
        "school": "nthu",
        "campus": "nthu-main",
        "organizer_type": "club",
        "reg": "required",
        "fee": "free",
        "category": "演講",
        "source": {"source_id": "ig_ee_nthu", "post_id": "1"},
    }
    value.update(overrides)
    return value


ORG_SIDS = {5: {"ig_ee_nthu"}, 47: {"fb_nycuartscenter"}}


class RuleTest(unittest.TestCase):
    """規則引擎：單條規則內各維度 AND、規則之間 OR、not 否決。"""

    def match(self, prefs, ev=None):
        return pc.event_matches(ev or event(), pc.normalize_prefs(prefs), ORG_SIDS)

    def test_no_rules_matches_everything(self):
        self.assertTrue(self.match({}))

    def test_notification_modes(self):
        followed = {"orgs": [{"id": 5, "name": "電機系學會"}]}
        self.assertTrue(self.match({**followed, "mode": "following"}))
        self.assertFalse(
            self.match(
                {**followed, "mode": "following"},
                event(source={"source_id": "other"}),
            )
        )
        self.assertTrue(
            self.match(
                {**followed, "mode": "all"},
                event(source={"source_id": "other"}),
            )
        )
        custom = {**followed, "mode": "custom", "rules": [{"cats": ["表演"]}]}
        self.assertTrue(self.match(custom, event(category="表演", source={"source_id": "other"})))
        self.assertFalse(self.match(custom, event(category="展覽", source={"source_id": "other"})))

    def test_empty_following_and_custom_modes_match_nothing(self):
        self.assertFalse(self.match({"mode": "following"}))
        self.assertFalse(self.match({"mode": "custom"}))

    def test_dimensions_are_and_within_a_rule(self):
        rule = {"schools": ["nthu"], "cats": ["演講"]}
        self.assertTrue(self.match({"rules": [rule]}))
        self.assertFalse(self.match({"rules": [rule]}, event(school="nycu")))
        self.assertFalse(self.match({"rules": [rule]}, event(category="表演")))

    def test_values_within_a_dimension_are_or(self):
        rule = {"cats": ["演講", "表演"]}
        self.assertTrue(self.match({"rules": [rule]}))
        self.assertTrue(self.match({"rules": [rule]}, event(category="表演")))
        self.assertFalse(self.match({"rules": [rule]}, event(category="展覽")))

    def test_rules_are_or(self):
        rules = [{"schools": ["nycu"]}, {"cats": ["演講"]}]
        self.assertTrue(self.match({"rules": rules}))
        self.assertTrue(self.match({"rules": rules}, event(school="nycu", category="表演")))
        self.assertFalse(self.match({"rules": rules}, event(school="nthu", category="表演")))

    def test_exclusions_veto(self):
        # (清大 AND 演講) - 付費
        rule = {"schools": ["nthu"], "cats": ["演講"], "not": {"fee": ["paid"]}}
        self.assertTrue(self.match({"rules": [rule]}, event(fee="free")))
        self.assertFalse(self.match({"rules": [rule]}, event(fee="paid")))

    def test_keyword_exclusion(self):
        rule = {"keywords": ["AI"], "not": {"keywords": ["招生"]}}
        self.assertTrue(self.match({"rules": [rule]}))
        self.assertFalse(self.match({"rules": [rule]}, event(title="AI 招生說明會")))

    def test_both_school_events_match_either_school(self):
        self.assertTrue(self.match({"rules": [{"schools": ["nycu"]}]}, event(school="both")))

    def test_followed_orgs_bypass_rules(self):
        prefs = {"orgs": [{"id": 5, "name": "電機系學會"}], "rules": [{"schools": ["nycu"]}]}
        self.assertTrue(self.match(prefs))                       # 來源屬於追蹤單位
        self.assertFalse(self.match(prefs, event(source={"source_id": "other"})))

    def test_campus_and_org_type(self):
        self.assertTrue(self.match({"rules": [{"campuses": ["nthu-main"]}]}))
        self.assertFalse(self.match({"rules": [{"campuses": ["nycu-guangfu"]}]}))
        self.assertTrue(self.match({"rules": [{"orgTypes": ["club"]}]}))
        self.assertFalse(self.match({"rules": [{"orgTypes": ["official"]}]}))

    def test_all_values_selected_means_unrestricted(self):
        self.assertEqual(pc.normalize_rule({"fee": ["free", "paid"]})["fee"], [])

    def test_legacy_flat_prefs_become_one_rule(self):
        prefs = pc.normalize_prefs({"schools": ["nthu"], "cats": ["演講"]})
        self.assertEqual(prefs["mode"], "custom")
        self.assertEqual(len(prefs["rules"]), 1)
        self.assertEqual(prefs["rules"][0]["schools"], ["nthu"])
        self.assertTrue(pc.event_matches(event(), prefs, ORG_SIDS))
        self.assertFalse(pc.event_matches(event(school="nycu"), prefs, ORG_SIDS))

    def test_legacy_orgs_derive_following_mode(self):
        prefs = pc.normalize_prefs({"orgs": [{"id": 5, "name": "電機系學會"}]})
        self.assertEqual(prefs["mode"], "following")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self._orig = (pc.PUSH_DIR, pc.SUBS_PATH, pc.LOCK_PATH)
        pc.PUSH_DIR = tmp_path
        pc.SUBS_PATH = tmp_path / "subscriptions.json"
        pc.LOCK_PATH = tmp_path / "subscriptions.lock"

    def tearDown(self):
        pc.PUSH_DIR, pc.SUBS_PATH, pc.LOCK_PATH = self._orig
        self.tmp.cleanup()

    SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}

    def test_upsert_get_remove(self):
        pc.upsert_sub(self.SUB, prefs={"rules": [{"cats": ["演講"]}]})
        record = pc.get_sub(self.SUB["endpoint"])
        self.assertEqual(record["prefs"]["rules"][0]["cats"], ["演講"])
        # 更新訂閱但不帶 prefs → 偏好保留
        pc.upsert_sub(self.SUB, prefs=None)
        self.assertEqual(pc.get_sub(self.SUB["endpoint"])["prefs"]["rules"][0]["cats"], ["演講"])
        self.assertTrue(pc.remove_sub(self.SUB["endpoint"]))
        self.assertIsNone(pc.get_sub(self.SUB["endpoint"]))

    def test_migrate_keeps_prefs(self):
        pc.upsert_sub(self.SUB, prefs={"rules": [{"keywords": ["爵士"]}]})
        new_sub = {"endpoint": "https://push.example/new", "keys": {"p256dh": "k2", "auth": "a2"}}
        pc.upsert_sub(new_sub, prefs=None, migrate_from=self.SUB["endpoint"])
        self.assertIsNone(pc.get_sub(self.SUB["endpoint"]))
        self.assertEqual(pc.get_sub(new_sub["endpoint"])["prefs"]["rules"][0]["keywords"], ["爵士"])

    def test_subscription_stats_are_anonymous_device_counts(self):
        pc.upsert_sub(self.SUB, prefs={})
        pc.upsert_sub(
            {"endpoint": "https://push.example/with-org", "keys": {"p256dh": "k2", "auth": "a2"}},
            prefs={"orgs": [{"id": 5, "name": "電機系學會"}]},
        )
        pc.upsert_sub(
            {"endpoint": "https://push.example/with-rule", "keys": {"p256dh": "k3", "auth": "a3"}},
            prefs={"rules": [{"schools": ["nycu"]}]},
        )
        self.assertEqual(
            pc.subscription_stats(),
            {"devices": 3, "withOrganizations": 1, "withRules": 1, "linked": 0},
        )


class _Sink(BaseHTTPRequestHandler):
    received = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _Sink.received = {
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": self.rfile.read(length),
        }
        self.send_response(201)
        self.end_headers()

    def log_message(self, *args):
        pass


class EndToEndCryptoTest(unittest.TestCase):
    """不靠瀏覽器驗證 send_push 全鏈：VAPID 簽章標頭存在、payload 可用訂閱私鑰解回原文。"""

    def test_send_and_decrypt(self):
        import http_ece
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        # 偽瀏覽器端金鑰
        browser_key = ec.generate_private_key(ec.SECP256R1())
        p256dh = browser_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        auth = b"0123456789abcdef"
        b64u = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()

        server = HTTPServer(("127.0.0.1", 0), _Sink)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            record = {"sub": {
                "endpoint": f"http://127.0.0.1:{server.server_port}/sink",
                "keys": {"p256dh": b64u(p256dh), "auth": b64u(auth)},
            }}
            payload = {"title": "測試", "body": "端到端", "url": "/subscribe/"}
            pc.ensure_vapid()
            pc.send_push(record, payload, ttl=60)
        finally:
            server.shutdown()

        received = _Sink.received
        self.assertIsNotNone(received)
        self.assertIn("vapid", received["headers"].get("authorization", "").lower())
        self.assertEqual(received["headers"].get("content-encoding"), "aes128gcm")
        clear = http_ece.decrypt(
            received["body"], private_key=browser_key, auth_secret=auth, version="aes128gcm"
        )
        self.assertEqual(json.loads(clear), payload)


if __name__ == "__main__":
    unittest.main()


class AccountBindingTest(unittest.TestCase):
    """訂閱綁帳號：偏好跨裝置同步、追蹤以帳號為準、session 解析、「我要去」提醒。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self._orig = (pc.PUSH_DIR, pc.SUBS_PATH, pc.LOCK_PATH, pc.AUTH_DB_PATH)
        pc.PUSH_DIR = tmp_path
        pc.SUBS_PATH = tmp_path / "subscriptions.json"
        pc.LOCK_PATH = tmp_path / "subscriptions.lock"
        pc.AUTH_DB_PATH = tmp_path / "auth.sqlite3"

    def tearDown(self):
        pc.PUSH_DIR, pc.SUBS_PATH, pc.LOCK_PATH, pc.AUTH_DB_PATH = self._orig
        self.tmp.cleanup()

    @staticmethod
    def sub(n):
        return {"endpoint": f"https://push.example/{n}", "keys": {"p256dh": "k", "auth": "a"}}

    def test_prefs_propagate_across_devices_of_same_account(self):
        pc.upsert_sub(self.sub("a"), prefs={"mode": "custom", "rules": [{"cats": ["演講"]}]}, user_id="u1")
        pc.upsert_sub(self.sub("b"), prefs={"mode": "all"}, user_id="u1")
        pc.upsert_sub(self.sub("c"), prefs={"mode": "custom", "rules": [{"cats": ["表演"]}]}, user_id="u2")
        self.assertEqual(pc.get_sub(self.sub("a")["endpoint"])["prefs"]["mode"], "all")
        self.assertEqual(pc.get_sub(self.sub("c")["endpoint"])["prefs"]["mode"], "custom")
        # 登出後 subscribe → 解除綁定；None → 不動
        pc.upsert_sub(self.sub("a"), user_id="")
        self.assertNotIn("user_id", pc.get_sub(self.sub("a")["endpoint"]))
        pc.upsert_sub(self.sub("b"), prefs=None, user_id=None)
        self.assertEqual(pc.get_sub(self.sub("b")["endpoint"])["user_id"], "u1")
        self.assertEqual(pc.subscription_stats()["linked"], 2)

    def test_effective_prefs_use_account_follows(self):
        record = {"user_id": "u1", "prefs": pc.normalize_prefs({"mode": "following", "orgs": []})}
        follows = {"u1": [{"id": 5, "name": "電機系學會"}]}
        self.assertTrue(pc.event_matches(event(), pc.effective_prefs(record, follows), ORG_SIDS))
        self.assertFalse(pc.event_matches(event(), pc.effective_prefs(record, {}), ORG_SIDS))
        unlinked = {"prefs": record["prefs"]}
        self.assertFalse(pc.event_matches(event(), pc.effective_prefs(unlinked, follows), ORG_SIDS))

    def test_session_and_account_lookups_read_auth_db(self):
        import hashlib
        import sqlite3
        import time
        with sqlite3.connect(pc.AUTH_DB_PATH) as conn:
            conn.executescript(
                "CREATE TABLE sessions(token_hash TEXT, user_id TEXT, created_at INT, expires_at INT);"
                "CREATE TABLE user_org_follows(user_id TEXT, org_id INT, org_name TEXT, created_at INT, updated_at INT);"
                "CREATE TABLE user_event_going(user_id TEXT, event_id TEXT, created_at INT);"
            )
            now = int(time.time())
            conn.execute("INSERT INTO sessions VALUES (?, 'u1', ?, ?)",
                         (hashlib.sha256(b"tok").hexdigest(), now, now + 100))
            conn.execute("INSERT INTO sessions VALUES (?, 'u2', ?, ?)",
                         (hashlib.sha256(b"old").hexdigest(), now, now - 1))
            conn.execute("INSERT INTO user_org_follows VALUES ('u1', 5, '電機系學會', 1, 1)")
            conn.execute("INSERT INTO user_event_going VALUES ('u1', 'evt_a', 1)")
        self.assertEqual(pc.session_user_id("tok"), "u1")
        self.assertIsNone(pc.session_user_id("old"))
        self.assertIsNone(pc.session_user_id(None))
        self.assertEqual(pc.account_follows(), {"u1": [{"id": 5, "name": "電機系學會"}]})
        self.assertEqual(pc.account_going(), {"u1": ["evt_a"]})

    def test_reminders_go_to_all_devices_once(self):
        import publish_push
        from datetime import date, timedelta
        today = date(2026, 9, 1)
        pc.upsert_sub(self.sub("a"), prefs={}, user_id="u1")
        pc.upsert_sub(self.sub("b"), prefs={}, user_id="u1")
        pc.upsert_sub(self.sub("c"), prefs={}, user_id="u2")
        pc.upsert_sub(self.sub("d"), prefs={})
        subs = pc.load_subs()["subs"]
        events = [
            event(id="evt_tmr", title="明天的講座", start_at=(today + timedelta(days=1)).isoformat() + "T19:00:00+08:00"),
            event(id="evt_today", title="今天的講座", start_at=today.isoformat() + "T19:00:00+08:00"),
            event(id="evt_far", start_at=(today + timedelta(days=5)).isoformat() + "T19:00:00+08:00"),
        ]
        going = {"u1": ["evt_tmr", "evt_today", "evt_far"], "u3": ["evt_tmr"]}
        state = {}
        plan = publish_push.reminders_for(subs, events, going, state, today=today)
        got = {(uid, eid): (len(devs), payload["title"]) for uid, eid, devs, payload in plan}
        self.assertEqual(got, {
            ("u1", "evt_tmr"): (2, "明天：明天的講座"),
            ("u1", "evt_today"): (2, "今天：今天的講座"),
        })
        state["reminders"]["u1:evt_tmr"] = {"sent_at": "x"}
        plan = publish_push.reminders_for(subs, events, going, state, today=today)
        self.assertEqual([p[1] for p in plan], ["evt_today"])
