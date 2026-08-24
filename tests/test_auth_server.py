import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from starlette.testclient import TestClient


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("auth_server", ROOT / "scripts" / "auth_server.py")
auth_server = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = auth_server
spec.loader.exec_module(auth_server)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHTTP:
    def __init__(self):
        self.token_calls = []
        self.profile_calls = []

    def post(self, url, data, timeout):
        self.token_calls.append((url, data, timeout))
        return FakeResponse({"access_token": "school-token"})

    def get(self, url, headers, timeout):
        self.profile_calls.append((url, headers, timeout))
        return FakeResponse({"username": "student123", "email": "student123@nycu.edu.tw"})


class AuthServerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "auth.sqlite3"
        self.config = auth_server.AuthConfig(
            client_id="client-id",
            client_secret="client-secret",
            public_base_url="https://chumei.example",
            database_path=self.db_path,
            cookie_secure=False,
        )
        self.http = FakeHTTP()
        self.store = auth_server.AuthStore(self.db_path)
        app = auth_server.create_app(
            self.config,
            store=self.store,
            oauth_client=auth_server.NYCUOAuthClient(self.http),
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.tempdir.cleanup()

    def _login(self, return_to="/account/"):
        start = self.client.get(
            "/auth/nycu/start", params={"return_to": return_to}, follow_redirects=False
        )
        self.assertEqual(start.status_code, 302)
        parsed = urlparse(start.headers["location"])
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.geturl().split("?", 1)[0], auth_server.NYCU_AUTHORIZE_URL)
        self.assertEqual(query["scope"], ["profile"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        callback = self.client.get(
            "/auth/nycu/callback",
            params={"code": "authorization-code", "state": query["state"][0]},
            follow_redirects=False,
        )
        return callback

    def test_complete_login_creates_account_and_session(self):
        callback = self._login("/events/")
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(callback.headers["location"], "/events/")
        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json()["authenticated"])
        self.assertEqual(me.json()["user"]["provider"], "nycu")
        self.assertEqual(me.json()["user"]["email"], "student123@nycu.edu.tw")
        self.assertEqual(self.http.token_calls[0][1]["client_secret"], "client-secret")
        self.assertIn("code_verifier", self.http.token_calls[0][1])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM users").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM oauth_identities").fetchone()[0], 1)

    def test_repeat_login_reuses_identity(self):
        self._login()
        self._login()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM users").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM sessions").fetchone()[0], 2)

    def test_state_is_one_time_and_must_match_cookie(self):
        start = self.client.get("/auth/nycu/start", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        bad = self.client.get(
            "/auth/nycu/callback",
            params={"code": "code", "state": "wrong"},
            follow_redirects=False,
        )
        self.assertEqual(bad.status_code, 400)
        good = self.client.get(
            "/auth/nycu/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )
        self.assertEqual(good.status_code, 303)
        replay = self.client.get(
            "/auth/nycu/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )
        self.assertEqual(replay.status_code, 400)

    def test_external_return_url_is_rejected(self):
        callback = self._login("//evil.example/path")
        self.assertEqual(callback.headers["location"], "/account/")

    def test_logout_revokes_local_session(self):
        self._login()
        response = self.client.post("/auth/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertFalse(self.client.get("/auth/me").json()["authenticated"])

    def test_account_page_uses_shared_site_shell(self):
        response = self.client.get("/account/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="site-header"', response.text)
        self.assertIn('class="site-nav"', response.text)
        self.assertIn('class="account-page"', response.text)
        self.assertIn('class="site-footer"', response.text)
        self.assertIn('<script src="/assets/app.js"></script>', response.text)
        self.assertNotIn('class="auth-body"', response.text)

    def test_login_merges_local_follows_and_counts_unique_accounts(self):
        unauthenticated = self.client.post("/auth/follows/sync", json={"orgs": []})
        self.assertEqual(unauthenticated.status_code, 401)

        self._login()
        merged = self.client.post(
            "/auth/follows/sync",
            json={
                "orgs": [
                    {"id": 5, "name": "清大電機系學會"},
                    {"id": "47", "name": "陽明交大藝文中心"},
                    {"id": 5, "name": "重複項目"},
                    {"id": "invalid", "name": "無效"},
                ]
            },
        )
        self.assertEqual(merged.status_code, 200)
        payload = merged.json()
        self.assertEqual([org["id"] for org in payload["following"]], [5, 47])
        self.assertEqual(payload["counts"], {"5": 1, "47": 1})
        self.assertEqual(
            payload["summary"], {"accounts": 1, "follows": 2, "organizations": 2}
        )

        repeated = self.client.put("/auth/follows/5", json={"name": "清大電機系學會"})
        self.assertEqual(repeated.json()["counts"]["5"], 1)
        removed = self.client.delete("/auth/follows/5")
        self.assertNotIn("5", removed.json()["counts"])
        self.assertEqual(removed.json()["summary"]["follows"], 1)

        self.client.post("/auth/logout")
        public = self.client.get("/auth/follows").json()
        self.assertFalse(public["authenticated"])
        self.assertEqual(public["following"], [])
        self.assertEqual(public["counts"], {"47": 1})

    def test_unconfigured_server_is_safe(self):
        config = auth_server.AuthConfig(
            client_id="",
            client_secret="",
            database_path=Path(self.tempdir.name) / "unconfigured.sqlite3",
            cookie_secure=False,
        )
        with TestClient(auth_server.create_app(config)) as client:
            self.assertEqual(client.get("/auth/nycu/start").status_code, 503)
            self.assertFalse(client.get("/auth/health").json()["configured"])


if __name__ == "__main__":
    unittest.main()
