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
        "category": "演講",
        "source": {"source_id": "ig_ee_nthu", "post_id": "1"},
    }
    value.update(overrides)
    return value


ORG_SIDS = {5: {"ig_ee_nthu"}, 47: {"fb_nycuartscenter"}}


class MatchTest(unittest.TestCase):
    def match(self, prefs, ev=None):
        return pc.event_matches(ev or event(), pc.normalize_prefs(prefs), ORG_SIDS)

    def test_empty_prefs_match_everything(self):
        self.assertTrue(self.match({}))

    def test_school_filter(self):
        self.assertTrue(self.match({"schools": ["nthu"]}))
        self.assertFalse(self.match({"schools": ["nycu"]}))
        self.assertTrue(self.match({"schools": ["nycu"]}, event(school="both")))
        self.assertEqual(pc.normalize_prefs({"schools": ["nthu", "nycu"]})["schools"], [])

    def test_interest_groups_are_or(self):
        self.assertTrue(self.match({"cats": ["演講"]}))
        self.assertFalse(self.match({"cats": ["表演"]}))
        self.assertTrue(self.match({"cats": ["表演"], "keywords": ["半導體"]}))
        self.assertTrue(self.match({"orgs": [{"id": 5, "name": "電機系學會"}]}))
        self.assertFalse(self.match({"orgs": [{"id": 47, "name": "藝文中心"}]}))

    def test_keyword_case_insensitive(self):
        self.assertTrue(self.match({"keywords": ["ai"]}))
        self.assertTrue(self.match({"keywords": ["台達"]}))
        self.assertFalse(self.match({"keywords": ["羽球"]}))

    def test_school_and_interest_combine_as_and(self):
        self.assertFalse(self.match({"schools": ["nycu"], "cats": ["演講"]}))


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
        pc.upsert_sub(self.SUB, prefs={"cats": ["演講"]})
        record = pc.get_sub(self.SUB["endpoint"])
        self.assertEqual(record["prefs"]["cats"], ["演講"])
        # 更新訂閱但不帶 prefs → 偏好保留
        pc.upsert_sub(self.SUB, prefs=None)
        self.assertEqual(pc.get_sub(self.SUB["endpoint"])["prefs"]["cats"], ["演講"])
        self.assertTrue(pc.remove_sub(self.SUB["endpoint"]))
        self.assertIsNone(pc.get_sub(self.SUB["endpoint"]))

    def test_migrate_keeps_prefs(self):
        pc.upsert_sub(self.SUB, prefs={"keywords": ["爵士"]})
        new_sub = {"endpoint": "https://push.example/new", "keys": {"p256dh": "k2", "auth": "a2"}}
        pc.upsert_sub(new_sub, prefs=None, migrate_from=self.SUB["endpoint"])
        self.assertIsNone(pc.get_sub(self.SUB["endpoint"]))
        self.assertEqual(pc.get_sub(new_sub["endpoint"])["prefs"]["keywords"], ["爵士"])


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
