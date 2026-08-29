import importlib.util
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock
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
        if "openidconnect" in url:
            return FakeResponse({
                "sub": "115566778899",
                "email": "friend@gmail.com",
                "picture": "https://lh3.googleusercontent.com/a/google-avatar",
            })
        return FakeResponse({"username": "student123", "email": "student123@nycu.edu.tw"})


class AuthServerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "auth.sqlite3"
        self.directory_path = Path(self.tempdir.name) / "sources.json"
        self.config = auth_server.AuthConfig(
            client_id="client-id",
            client_secret="client-secret",
            google_client_id="google-client-id",
            google_client_secret="google-client-secret",
            feed_signing_key="test-feed-signing-key",
            public_base_url="https://chumei.example",
            database_path=self.db_path,
            cookie_secure=False,
        )
        self.http = FakeHTTP()
        self.store = auth_server.AuthStore(self.db_path, self.directory_path)
        app = auth_server.create_app(
            self.config,
            store=self.store,
            oauth_client=auth_server.NYCUOAuthClient(self.http),
            google_oauth_client=auth_server.GoogleOAuthClient(self.http),
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

    def test_priority_fetch_requests_require_login_and_use_known_sources(self):
        denied = self.client.post(
            "/auth/fetch-requests", json={"sourceId": "instagram:nthu_official"}
        )
        self.assertEqual(denied.status_code, 401)

        self._login()
        unknown = self.client.post(
            "/auth/fetch-requests", json={"sourceId": "shell:../../anything"}
        )
        self.assertEqual(unknown.status_code, 400)

        created = self.client.post(
            "/auth/fetch-requests", json={"sourceId": "instagram:nthu_official"}
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["request"]["sourceId"], "instagram:nthu_official")
        self.assertEqual(created.json()["request"]["status"], "pending")

        duplicate = self.client.post(
            "/auth/fetch-requests", json={"sourceId": "instagram:nthu_official"}
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()["code"], "duplicate")

        listing = self.client.get("/auth/fetch-requests")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["dailyLimit"], auth_server.FETCH_REQUEST_DAILY_LIMIT)
        self.assertEqual(len(listing.json()["requests"]), 1)

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

    def test_follow_names_use_current_directory_display_name(self):
        self.directory_path.write_text(
            json.dumps({"entries": [{"id": 5, "name": "交大電機系學會"}]}),
            encoding="utf-8",
        )
        self._login()
        response = self.client.post(
            "/auth/follows/sync",
            json={"orgs": [{"id": 5, "name": "電機系學會"}]},
        )
        self.assertEqual(response.json()["following"], [{"id": 5, "name": "交大電機系學會"}])

    def test_event_going_counter(self):
        """我要去：需登入、一人一場只算一次、可取消、計數公開。"""
        anon = self.client.get("/auth/events")
        self.assertEqual(anon.status_code, 200)
        self.assertFalse(anon.json()["authenticated"])
        self.assertEqual(anon.json()["counts"], {})

        denied = self.client.put("/auth/events/evt_abc123def456")
        self.assertEqual(denied.status_code, 401)

        self._login()
        marked = self.client.put("/auth/events/evt_abc123def456")
        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.json()["counts"]["evt_abc123def456"], 1)
        self.assertEqual(marked.json()["going"], ["evt_abc123def456"])

        # 重複標記不會灌水
        again = self.client.put("/auth/events/evt_abc123def456")
        self.assertEqual(again.json()["counts"]["evt_abc123def456"], 1)
        self.assertEqual(again.json()["summary"]["marks"], 1)

        # 未登入者也看得到計數
        self.client.post("/auth/logout")
        public = self.client.get("/auth/events")
        self.assertEqual(public.json()["counts"]["evt_abc123def456"], 1)
        self.assertFalse(public.json()["authenticated"])
        self.assertEqual(public.json()["going"], [])

        self._login()
        removed = self.client.delete("/auth/events/evt_abc123def456")
        self.assertEqual(removed.status_code, 200)
        self.assertNotIn("evt_abc123def456", removed.json()["counts"])
        self.assertEqual(removed.json()["going"], [])

    def test_event_going_rejects_bad_ids(self):
        self._login()
        for bad in ("../etc", "evt_XYZ", "abc123", "evt_" + "a" * 64):
            with self.subTest(bad=bad):
                response = self.client.put("/auth/events/" + bad)
                # 400＝格式擋掉；404＝路由層就不匹配（如含路徑分隔）
                self.assertIn(response.status_code, (400, 404), bad)
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM user_event_going").fetchone()[0], 0)

    def _google_login(self, return_to="/account/"):
        start = self.client.get(
            "/auth/google/start", params={"return_to": return_to}, follow_redirects=False
        )
        self.assertEqual(start.status_code, 302)
        parsed = urlparse(start.headers["location"])
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.geturl().split("?", 1)[0], auth_server.GOOGLE_AUTHORIZE_URL)
        self.assertEqual(query["scope"], ["openid email profile"])
        self.assertEqual(query["client_id"], ["google-client-id"])
        self.assertEqual(
            query["redirect_uri"], ["https://chumei.example/auth/google/callback"]
        )
        return self.client.get(
            "/auth/google/callback",
            params={"code": "google-code", "state": query["state"][0]},
            follow_redirects=False,
        )

    def test_google_login_creates_account_with_google_identity(self):
        callback = self._google_login("/events/")
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(callback.headers["location"], "/events/")
        me = self.client.get("/auth/me").json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["provider"], "google")
        self.assertEqual(me["user"]["email"], "friend@gmail.com")
        self.assertEqual(
            me["user"]["avatarUrl"],
            "/auth/avatar/friend",
        )
        self.assertEqual(me["user"]["avatarSource"], "google")
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT provider, subject FROM oauth_identities"
            ).fetchone()
        self.assertEqual(row, ("google", "115566778899"))
        token_url = self.http.token_calls[-1][0]
        self.assertEqual(token_url, auth_server.GOOGLE_TOKEN_URL)

    def test_google_and_nycu_logins_are_separate_accounts(self):
        self._login()
        self.client.cookies.clear()
        self._google_login()
        with closing(sqlite3.connect(self.db_path)) as conn:
            n_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            providers = sorted(
                r[0] for r in conn.execute("SELECT provider FROM oauth_identities")
            )
        self.assertEqual(n_users, 2)
        self.assertEqual(providers, ["google", "nycu"])

    def test_account_page_offers_both_login_options(self):
        page = self.client.get("/account/")
        self.assertIn("/auth/nycu/start", page.text)
        self.assertIn("/auth/google/start", page.text)

    def test_account_dashboard_lists_follows_and_going(self):
        self._login()
        self.client.put("/auth/follows/42", json={"name": "測試熱舞社"})
        self.client.put("/auth/events/evt_dashboard_test")
        page = self.client.get("/@student123").text
        self.assertIn("追蹤的單位", page)
        self.assertIn("測試熱舞社", page)
        self.assertIn('href="/org/42/"', page)
        self.assertIn("要去的活動", page)
        self.assertIn("編輯個人檔案", page)
        settings = self.client.get("/account/").text
        self.assertIn("我的回報", settings)
        self.assertIn("登出", settings)
        self.assertIn('href="/@student123"', settings)

    def test_profile_avatar_uses_gravatar_and_google_has_priority(self):
        self._login()
        gravatar = auth_server._gravatar_url("student123@nycu.edu.tw")
        me = self.client.get("/auth/me").json()["user"]
        self.assertEqual(me["avatarUrl"], "/auth/avatar/student123")
        self.assertEqual(me["avatarSource"], "nycu_gravatar")
        profile = self.store.user_by_handle("student123")
        self.assertEqual(profile["avatar_url"], gravatar)
        self.assertEqual(profile["_avatar_candidates"], [(gravatar, "nycu_gravatar")])
        self.assertIn('src="/auth/avatar/student123"', self.client.get("/@student123").text)

        self._link("google")
        me = self.client.get("/auth/me").json()["user"]
        self.assertEqual(
            me["avatarUrl"], "/auth/avatar/student123"
        )
        self.assertEqual(me["avatarSource"], "google")
        self.assertIn('src="/auth/avatar/student123"', self.client.get("/@student123").text)

        profile = self.store.user_by_handle("student123")
        self.assertEqual(
            [source for _url, source in profile["_avatar_candidates"]],
            ["google", "google_gravatar", "nycu_gravatar"],
        )

    def test_avatar_proxy_serves_images_from_the_same_origin(self):
        self._google_login()
        upstream = mock.Mock(
            content=b"avatar-bytes",
            headers={"content-type": "image/png"},
        )
        upstream.raise_for_status.return_value = None
        with mock.patch.object(auth_server.requests, "get", return_value=upstream) as get:
            response = self.client.get("/auth/avatar/friend")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"avatar-bytes")
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["cache-control"], "private, max-age=300")
        self.assertEqual(
            get.call_args.args[0], "https://lh3.googleusercontent.com/a/google-avatar"
        )

    def test_avatar_proxy_falls_back_through_google_and_nycu_gravatars(self):
        self._login()
        self._link("google")
        profile = self.store.user_by_handle("student123")
        candidates = profile["_avatar_candidates"]
        self.assertEqual(
            [source for _url, source in candidates],
            ["google", "google_gravatar", "nycu_gravatar"],
        )

        missing = mock.Mock()
        missing.raise_for_status.side_effect = auth_server.requests.HTTPError("missing")
        found = mock.Mock(
            content=b"nycu-gravatar",
            headers={"content-type": "image/png"},
        )
        found.raise_for_status.return_value = None
        responses = [missing, missing, found]
        with mock.patch.object(auth_server.requests, "get", side_effect=responses) as get:
            response = self.client.get("/auth/avatar/student123")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"nycu-gravatar")
        self.assertEqual(
            [call.args[0] for call in get.call_args_list],
            [url for url, _source in candidates],
        )

    def test_unsafe_google_avatar_url_is_not_rendered(self):
        unsafe_http = type(
            "UnsafeHTTP",
            (),
            {
                "get": lambda *args, **kwargs: FakeResponse({
                    "sub": "1",
                    "email": "friend@gmail.com",
                    "picture": "https://evil.example/avatar",
                })
            },
        )()
        subject, email, avatar = auth_server.GoogleOAuthClient(unsafe_http).profile("token")
        self.assertEqual((subject, email, avatar), ("1", "friend@gmail.com", None))

    def test_profile_is_public_unless_disabled(self):
        self._login()
        self.assertEqual(self.client.get("/auth/me").json()["user"]["handle"], "student123")
        anon = TestClient(self.client.app)
        self.assertEqual(anon.get("/@student123").status_code, 200)
        self.assertNotIn("編輯個人檔案", anon.get("/@student123").text)
        self.assertEqual(anon.get("/@Student123", follow_redirects=False).status_code, 301)
        self.assertEqual(anon.get("/@nobody").status_code, 404)
        self.client.post("/auth/profile", data={"display_name": "Sky", "handle": "student123"})
        self.assertEqual(anon.get("/@student123").status_code, 404)
        self.assertEqual(self.client.get("/@student123").status_code, 200)
        self.assertIn("不公開", self.client.get("/@student123").text)

    def test_handles_are_auto_assigned_and_unique(self):
        self._login()
        self.client.cookies.clear()
        self._google_login()
        me = self.client.get("/auth/me").json()["user"]
        self.assertEqual(me["handle"], "friend")
        self.assertEqual(me["profileUrl"], "/@friend")
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE users SET handle = NULL WHERE handle = 'friend'")
            conn.execute("INSERT INTO users(id, display_name, email, handle, created_at, updated_at) "
                         "VALUES ('x', 'Dup', 'student123@other.tw', NULL, 1, 1)")
            conn.commit()
        auth_server.AuthStore(self.db_path, self.directory_path)  # 重新初始化會補代號
        with closing(sqlite3.connect(self.db_path)) as conn:
            handles = sorted(r[0] for r in conn.execute("SELECT handle FROM users"))
        self.assertEqual(handles, ["friend", "student123", "student1232"])

    def _link(self, provider="google"):
        start = self.client.get(
            f"/auth/{provider}/start", params={"link": "1"}, follow_redirects=False
        )
        self.assertEqual(start.status_code, 302)
        query = parse_qs(urlparse(start.headers["location"]).query)
        code = "google-code" if provider == "google" else "authorization-code"
        return self.client.get(
            f"/auth/{provider}/callback",
            params={"code": code, "state": query["state"][0]},
            follow_redirects=False,
        )

    def test_link_google_to_nycu_account(self):
        self._login()
        callback = self._link("google")
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(callback.headers["location"], "/account/?link=ok")
        me = self.client.get("/auth/me").json()
        self.assertEqual(me["user"]["providers"], ["nycu", "google"])
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM users").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT count(*) FROM oauth_identities").fetchone()[0], 2
            )
        page = self.client.get("/account/").text
        self.assertIn("已綁定學校與 Google 帳號", page)
        self.assertIn("解除綁定", page)

    def test_link_merges_existing_account_data(self):
        # Google 帳號先自己用過：有追蹤與參加標記
        self._google_login()
        self.client.put("/auth/follows/7", json={"name": "谷歌社"})
        self.client.put("/auth/events/evt_abc123")
        self.client.cookies.clear()
        # 學校帳號另外用過，之後把 Google 綁進來
        self._login()
        self.client.put("/auth/follows/9", json={"name": "交大社"})
        callback = self._link("google")
        self.assertEqual(callback.headers["location"], "/account/?link=merged")
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM users").fetchone()[0], 1)
        follows = self.client.get("/auth/follows").json()
        self.assertEqual(sorted(f["id"] for f in follows["following"]), [7, 9])
        going = self.client.get("/auth/events").json()
        self.assertIn("evt_abc123", going["going"])
        # 之後再用 Google 登入，回到同一個帳號
        self.client.cookies.clear()
        self._google_login()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM users").fetchone()[0], 1)

    def test_link_again_is_idempotent(self):
        self._login()
        self._link("google")
        callback = self._link("google")
        self.assertEqual(callback.headers["location"], "/account/?link=already")

    def test_link_requires_login(self):
        start = self.client.get(
            "/auth/google/start", params={"link": "1"}, follow_redirects=False
        )
        self.assertEqual(start.status_code, 401)

    def test_unlink_keeps_last_identity(self):
        self._login()
        fail = self.client.post(
            "/auth/unlink", data={"provider": "nycu"}, follow_redirects=False
        )
        self.assertEqual(fail.headers["location"], "/account/?link=unlink_fail")
        self._link("google")
        ok = self.client.post(
            "/auth/unlink", data={"provider": "google"}, follow_redirects=False
        )
        self.assertEqual(ok.headers["location"], "/account/?link=unlinked")
        me = self.client.get("/auth/me").json()
        self.assertEqual(me["user"]["providers"], ["nycu"])

    def test_profile_handle_is_unique_and_validated(self):
        self._login()
        ok = self.client.post(
            "/auth/profile", data={"display_name": " Sky  Hong ", "handle": "@Sky_01", "public": "1"},
            follow_redirects=False,
        )
        self.assertEqual(ok.headers["location"], "/account/?profile=ok")
        me = self.client.get("/auth/me").json()["user"]
        self.assertEqual(me["displayName"], "Sky Hong")
        self.assertEqual(me["handle"], "sky_01")
        self.assertIn("@sky_01", self.client.get("/account/").text)
        self.assertEqual(self.client.get("/@sky_01").status_code, 200)
        bad = self.client.post(
            "/auth/profile", data={"display_name": "Sky", "handle": "no-dash"},
            follow_redirects=False,
        )
        self.assertEqual(bad.headers["location"], "/account/?profile=bad_handle")
        self.client.cookies.clear()
        self._google_login()
        taken = self.client.post(
            "/auth/profile", data={"display_name": "Friend", "handle": "sky_01"},
            follow_redirects=False,
        )
        self.assertEqual(taken.headers["location"], "/account/?profile=handle_taken")

    def test_calendar_feed_is_private_and_rotatable(self):
        self._login()
        page = self.client.get("/account/").text
        match = re.search(r"/auth/calendar/([A-Za-z0-9_-]+)\.ics", page)
        self.assertIsNotNone(match)
        token = match.group(1)
        feed = self.client.get(f"/auth/calendar/{token}.ics")
        self.assertEqual(feed.status_code, 200)
        self.assertTrue(feed.headers["content-type"].startswith("text/calendar"))
        self.assertIn("BEGIN:VCALENDAR", feed.text)
        self.assertIn("X-WR-CALNAME:竹梅 student123 已追蹤", feed.text)
        self.assertIn("NAME:竹梅 student123 已追蹤", feed.text)
        self.assertIn("BEGIN:VTIMEZONE", feed.text)
        self.assertIn("X-WR-CALDESC:", feed.text)
        self.assertIn("X-APPLE-CALENDAR-COLOR:", feed.text)
        self.client.post("/auth/profile", data={"display_name": "Sky", "handle": "sky_cal"})
        self.assertIn("X-WR-CALNAME:竹梅 sky_cal 已追蹤",
                      self.client.get(f"/auth/calendar/{token}.ics").text)
        if auth_server.EVENTS_DATA_PATH.exists():
            events = json.loads(auth_server.EVENTS_DATA_PATH.read_text())["events"]
            real = next(e for e in events if auth_server.EVENT_ID_RE.fullmatch(e["id"]))
            self.client.put(f"/auth/events/{real['id']}")
            feed = self.client.get(f"/auth/calendar/{token}.ics")
            self.assertIn(f"UID:{real['id']}@chumei.observe.tw", feed.text)
        self.assertEqual(self.client.get("/auth/calendar/nope.ics").status_code, 404)
        self.client.post("/auth/calendar/rotate", follow_redirects=False)
        self.assertEqual(self.client.get(f"/auth/calendar/{token}.ics").status_code, 404)
        new_token = re.search(r"/auth/calendar/([A-Za-z0-9_-]+)\.ics",
                              self.client.get("/account/").text).group(1)
        self.assertNotEqual(new_token, token)
        self.assertEqual(self.client.get(f"/auth/calendar/{new_token}.ics").status_code, 200)

    def test_saved_feed_crud_keeps_signed_url_stable_until_rotation(self):
        self._login()
        created = self.client.post(
            "/auth/saved-feeds",
            json={
                "name": "光復社團活動",
                "rule": {
                    "school": "nycu",
                    "categories": ["talk", "workshop"],
                    "campuses": ["nycu-guangfu"],
                    "organizers": ["club"],
                    "followed": False,
                },
            },
        )
        self.assertEqual(created.status_code, 201)
        feed = created.json()["feed"]
        self.assertIn("/feeds/s/", feed["ics"])
        self.assertTrue(feed["rss"].endswith(".xml"))
        self.assertIn("光復社團活動", self.client.get("/account/").text)
        self.assertIn("我要去行事曆", self.client.get("/account/").text)

        original_url = feed["ics"]
        updated = self.client.patch(
            f"/auth/saved-feeds/{feed['id']}",
            json={"name": "改名後", "rule": {**feed["rule"], "categories": ["expo"]}},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["feed"]["ics"], original_url)
        self.assertEqual(updated.json()["feed"]["name"], "改名後")

        rotated = self.client.post(
            f"/auth/saved-feeds/{feed['id']}/rotate",
            headers={"Accept": "application/json"},
        )
        self.assertEqual(rotated.status_code, 200)
        self.assertNotEqual(rotated.json()["feed"]["ics"], original_url)
        self.assertEqual(self.client.get(urlparse(original_url).path).status_code, 404)

        deleted = self.client.delete(f"/auth/saved-feeds/{feed['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/auth/saved-feeds").json()["feeds"], [])

    def test_public_and_saved_feeds_apply_and_across_multi_select_filters(self):
        events_path = Path(self.tempdir.name) / "events.json"
        events = [
            {"id": "evt_a11111", "title": "官方演講", "school": "nycu", "category": "演講",
             "campus": "nycu-guangfu", "organizer_type": "official", "org_id": 1,
             "start_at": "2099-01-01T10:00:00+08:00", "organizer": "校方"},
            {"id": "evt_b22222", "title": "社團工作坊", "school": "nycu", "category": "工作坊",
             "campus": "nycu-guangfu", "organizer_type": "club", "org_id": 2,
             "start_at": "2099-01-02T10:00:00+08:00", "organizer": "測試社"},
            {"id": "evt_c33333", "title": "線上演講", "school": "nthu", "category": "演講",
             "campus": "online", "organizer_type": "club", "org_id": 3,
             "start_at": "2099-01-03T10:00:00+08:00", "organizer": "另一社"},
        ]
        events_path.write_text(json.dumps({"events": events}), encoding="utf-8")
        with mock.patch.object(auth_server, "EVENTS_DATA_PATH", events_path):
            auth_server._events_cache.update({"mtime": None, "byid": {}})
            public = self.client.get(
                "/feeds/custom.ics",
                params={
                    "school": "nycu",
                    "categories": "talk,workshop",
                    "campuses": "nycu-guangfu",
                    "organizers": "club",
                },
            )
            self.assertEqual(public.status_code, 200)
            self.assertIn("UID:evt_b22222@chumei.observe.tw", public.text)
            self.assertNotIn("UID:evt_a11111@chumei.observe.tw", public.text)
            self.assertNotIn("UID:evt_c33333@chumei.observe.tw", public.text)
            self.assertTrue(self.client.get(
                "/feeds/custom.xml?school=nycu&categories=workshop"
            ).headers["content-type"].startswith("application/rss+xml"))
            self.assertEqual(
                self.client.get("/feeds/custom.ics?categories=not-real").status_code, 400
            )

            self._login()
            self.client.put("/auth/follows/2", json={"name": "測試社"})
            created = self.client.post(
                "/auth/saved-feeds",
                json={
                    "name": "我追蹤的光復活動",
                    "rule": {
                        "school": "nycu", "categories": ["talk", "workshop"],
                        "campuses": ["nycu-guangfu"], "organizers": ["club"],
                        "followed": True,
                    },
                },
            ).json()["feed"]
            signed = self.client.get(urlparse(created["ics"]).path)
            self.assertEqual(signed.status_code, 200)
            self.assertIn("UID:evt_b22222@chumei.observe.tw", signed.text)
            self.client.delete("/auth/follows/2")
            self.assertNotIn(
                "UID:evt_b22222@chumei.observe.tw",
                self.client.get(urlparse(created["ics"]).path).text,
            )
        auth_server._events_cache.update({"mtime": None, "byid": {}})

    def test_saved_feeds_require_login_and_preserve_subscribe_return(self):
        self.assertEqual(self.client.get("/auth/saved-feeds").status_code, 401)
        page = self.client.get(
            "/account/", params={"return_to": "/subscribe/?resume=1#custom"}
        ).text
        self.assertIn("return_to=/subscribe/%3Fresume%3D1%23custom", page)

        self._login()
        invalid = self.client.post(
            "/auth/saved-feeds",
            json={"name": "無效訂閱", "rule": {"followed": "false"}},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_unknown_provider_is_rejected(self):
        self.assertEqual(
            self.client.get("/auth/github/start", follow_redirects=False).status_code, 404
        )
        self.assertEqual(
            self.client.get("/auth/github/callback", follow_redirects=False).status_code, 404
        )

    def test_unconfigured_google_returns_503_but_nycu_still_works(self):
        config = auth_server.AuthConfig(
            client_id="client-id",
            client_secret="client-secret",
            public_base_url="https://chumei.example",
            database_path=Path(self.tempdir.name) / "nycu-only.sqlite3",
            cookie_secure=False,
        )
        with TestClient(auth_server.create_app(config)) as client:
            self.assertEqual(
                client.get("/auth/google/start", follow_redirects=False).status_code, 503
            )
            self.assertEqual(
                client.get("/auth/nycu/start", follow_redirects=False).status_code, 302
            )
            page = client.get("/account/")
            self.assertIn("/auth/nycu/start", page.text)
            self.assertNotIn("/auth/google/start", page.text)

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
