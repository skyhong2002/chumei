import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


submissions = _load("submissions")
auth_server = _load("auth_server")
process_submissions = _load("process_submissions")


class UrlTests(unittest.TestCase):
    def test_normalize_strips_tracking_and_aliases(self):
        self.assertEqual(
            submissions.normalize_url("instagram.com/p/AbC123/?igsh=xyz&utm_source=ig#x"),
            "https://www.instagram.com/p/AbC123/",
        )
        self.assertEqual(
            submissions.normalize_url(
                "instagram.com/nycu_leadership_club/?igsi=MXM0Y3MzaDllOWhzdA%3D%3D"
            ),
            "https://www.instagram.com/nycu_leadership_club/",
        )
        self.assertEqual(
            submissions.normalize_url("https://m.facebook.com/nthu.tw/posts/123?fbclid=1"),
            "https://www.facebook.com/nthu.tw/posts/123/",
        )
        self.assertEqual(submissions.normalize_url("https://threads.com/@nthu_official"),
                         "https://www.threads.net/@nthu_official/")
        self.assertIsNone(submissions.normalize_url("not a url"))
        self.assertIsNone(submissions.normalize_url("ftp://x.example/a"))
        self.assertIsNone(submissions.normalize_url(""))

    def test_classify(self):
        cases = {
            "https://www.instagram.com/p/AbC123/": ("ig_post", "AbC123"),
            "https://www.instagram.com/reel/XyZ/": ("ig_post", "XyZ"),
            "https://www.instagram.com/nthu_sa/": ("ig_profile", None),
            "https://www.facebook.com/nthu.tw/posts/123/": ("fb_post", "123"),
            "https://www.facebook.com/events/456/": ("fb_post", "event_456"),
            "https://www.facebook.com/share/p/abc/": ("fb_post", None),
            "https://www.facebook.com/nthu.tw/": ("fb_page", None),
            "https://www.facebook.com/groups/abc/": ("fb_group", None),
            "https://www.threads.net/@nthu_sa/post/C1/": ("threads_post", "C1"),
            "https://www.threads.net/@nthu_sa/": ("threads_profile", None),
            "https://x.com/nthu/status/1/": ("x_post", "1"),
            "https://chumei.observe.tw/event/evt_1/": ("chumei", None),
            "https://infonews.nycu.edu.tw/p/1/": ("web", None),
        }
        for url, (kind, post_id) in cases.items():
            info = submissions.classify_url(url)
            self.assertEqual(info["kind"], kind, url)
            self.assertEqual(info["post_id"], post_id, url)
        self.assertEqual(submissions.classify_url("https://www.instagram.com/NTHU_SA/")["handle"], "nthu_sa")


class FakeHTTP:
    def post(self, url, data, timeout):
        class R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"access_token": "t"}
        return R()

    def get(self, url, headers, timeout):
        class R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"username": "student123", "email": "student123@nycu.edu.tw"}
        return R()


class SubmissionApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db = Path(self.tempdir.name) / "auth.sqlite3"
        config = auth_server.AuthConfig(client_id="c", client_secret="s", database_path=db, cookie_secure=False)
        self.store = submissions.SubmissionStore(db)
        app = auth_server.create_app(
            config,
            store=auth_server.AuthStore(db, Path(self.tempdir.name) / "sources.json"),
            oauth_client=auth_server.NYCUOAuthClient(FakeHTTP()),
            submissions=self.store,
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.tempdir.cleanup()

    def _login(self):
        start = self.client.get("/auth/nycu/start", follow_redirects=False)
        from urllib.parse import parse_qs, urlparse
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        self.client.get("/auth/nycu/callback", params={"code": "c", "state": state}, follow_redirects=False)

    def test_requires_login(self):
        r = self.client.post("/auth/submissions", json={"url": "https://www.instagram.com/p/A/"})
        self.assertEqual(r.status_code, 401)
        public = self.client.get("/auth/submissions")
        self.assertEqual(public.status_code, 200)
        self.assertFalse(public.json()["authenticated"])

    def test_json_create_dedupe_and_limit(self):
        self._login()
        r = self.client.post("/auth/submissions", json={"url": "instagram.com/p/AbC/?igsh=1", "note": "清大天文社"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["submission"]["url"], "https://www.instagram.com/p/AbC/")
        self.assertEqual(r.json()["submission"]["status"], "pending")
        dup = self.client.post("/auth/submissions", json={"url": "https://www.instagram.com/p/AbC/"})
        self.assertEqual(dup.json()["code"], "dup")
        self.assertEqual(self.client.post("/auth/submissions", json={"url": "nope"}).status_code, 400)
        self.assertEqual(
            self.client.post("/auth/submissions", json={"url": "https://chumei.observe.tw/event/x/"}).json()["code"],
            "self",
        )
        for i in range(submissions.DAILY_LIMIT - 1):
            self.client.post("/auth/submissions", json={"url": f"https://example.org/e/{i}"})
        limited = self.client.post("/auth/submissions", json={"url": "https://example.org/e/last"})
        self.assertEqual(limited.status_code, 429)
        listed = self.client.get("/auth/submissions").json()
        self.assertEqual(len(listed["submissions"]), submissions.DAILY_LIMIT)
        self.assertTrue(all(s["mine"] for s in listed["submissions"]))
        first = next(s for s in listed["submissions"] if s["url"] == "https://www.instagram.com/p/AbC/")
        self.assertEqual(first["note"], "清大天文社")
        self.client.post("/auth/logout")
        public = self.client.get("/auth/submissions").json()
        self.assertEqual(len(public["submissions"]), submissions.DAILY_LIMIT)
        self.assertFalse(any(s["mine"] for s in public["submissions"]))
        self.assertFalse(any("note" in s for s in public["submissions"]))

    def test_form_post_redirects_and_account_page_lists(self):
        self._login()
        r = self.client.post(
            "/auth/submissions",
            content="url=https%3A%2F%2Fwww.facebook.com%2Fnthu.tw%2Fposts%2F9&note=hi",
            headers={"content-type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/submit/?submit=ok#submit")
        page = self.client.get("/submit/?submit=ok")
        self.assertIn('submit-card" id="submit"', page.text)
        self.assertIn("facebook.com/nthu.tw/posts/9", page.text)
        self.assertIn("待處理", page.text)
        self.assertIn("已收到", page.text)
        self.assertIn("你回報的", page.text)
        self.assertIn("備註：hi", page.text)

    def test_logged_out_account_page_shows_public_statuses_without_form(self):
        self._login()
        self.client.post("/auth/submissions", json={"url": "https://example.org/pub", "note": "secret"})
        self.client.post("/auth/logout")
        page = self.client.get("/submit/")
        self.assertIn('submit-card" id="submit"', page.text)
        self.assertIn("example.org/pub", page.text)
        self.assertNotIn('name="url"', page.text)
        self.assertNotIn("你回報的", page.text)
        self.assertNotIn("secret", page.text)
        self.assertIn("登入後回報連結", page.text)

    def test_account_page_shows_my_submissions_only(self):
        self._login()
        self.client.post("/auth/submissions", json={"url": "https://example.org/mine", "note": "我的備註"})
        page = self.client.get("/account/")
        self.assertIn("我的回報", page.text)
        self.assertIn("example.org/mine", page.text)
        self.assertIn("備註：我的備註", page.text)
        self.assertNotIn('name="url"', page.text)  # 表單搬去 /submit/


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = submissions.SubmissionStore(Path(self.tempdir.name) / "auth.sqlite3")
        self.index = {
            "by_id": {"evt_1": {"id": "evt_1", "title": "天文社迎新", "organizer": "清大天文社", "start_at": "2999-01-01T00:00:00+08:00"}},
            "by_source": {("rsshub", "OLD"): ["evt_1"]},
            "by_url": {},
            "events": [{"id": "evt_1", "title": "天文社迎新", "organizer": "清大天文社", "start_at": "2999-01-01T00:00:00+08:00"}],
            "generated_at": "2026-01-01T00:00:00+08:00",
        }
        self.ctx = {
            "events": self.index,
            "inbox": ({"https://www.instagram.com/p/OLD/": ("rsshub", "OLD")}, {"OLD": ("rsshub", "OLD")}),
            "handles": {"instagram": {"nthu_sa"}, "facebook": set(), "threads": set(), "twitter": set()},
            "orgs": {"ig_nthu_sa": 42, "rsshub": 7},
            "env": {},
            "needs_extract": False,
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def _run(self, url, **patches):
        sub = self.store.create("u1", submissions.normalize_url(url))
        with mock.patch.multiple(process_submissions, **(patches or {"UA": process_submissions.UA})):
            process_submissions.process_one(self.store, sub, self.ctx)
        return self.store.get(sub["id"])

    def test_tracked_facebook_urls_are_indexed_by_page_handle(self):
        rows = {
            "ig_accounts.csv": [],
            "fb_pages.csv": [{"page": "https://www.facebook.com/nycuwlef"}],
            "social_accounts.csv": [],
        }
        with mock.patch.object(
            process_submissions, "read_sources_csv", side_effect=lambda name: rows[name]
        ):
            handles = process_submissions.load_tracked_handles()
        self.assertIn("nycuwlef", handles["facebook"])

    def test_tracked_profile_links_to_its_org_page(self):
        got = self._run("https://www.instagram.com/nthu_sa/")
        self.assertEqual((got["status"], got["event_url"]), ("existing", "/org/42/"))

    def test_untracked_profile_is_added_without_human_review(self):
        added = []

        def fake_add(info, verdict, sub_id):
            added.append((info["platform"], info["handle"], verdict["name"]))
            return "ig_accounts.csv"

        got = self._run(
            "https://www.instagram.com/newclub/",
            fetch_account_preview=lambda url, info, env: ("新社團", ["9/20 迎新茶會"]),
            review_source_with_codex=lambda *a: {
                "relevant": True, "name": "清大新社團", "school": "nthu", "org_type": "club",
                "category_hint": "學術性", "reason": "清大社團，持續發活動資訊。", "confidence": 0.9},
            add_tracked_source=fake_add,
        )
        self.assertEqual(got["status"], "source_added")
        self.assertEqual(added, [("instagram", "newclub", "清大新社團")])
        self.assertIn("清大新社團", got["reason"])
        # 同一輪裡再回報一次同帳號不會重複寫入
        self.assertIn("newclub", self.ctx["handles"]["instagram"])
        # 建站前還沒有單位頁；建站後由 settle_source_added 補上連結，狀態與說明不變
        self.assertIsNone(got["event_url"])
        process_submissions.settle_source_added(self.store, {**self.ctx["orgs"], "ig_newclub": 99})
        after = self.store.get(got["id"])
        self.assertEqual((after["status"], after["event_url"], after["reason"]),
                         ("source_added", "/org/99/", got["reason"]))

    def test_added_profile_links_org_page_when_it_already_exists(self):
        got = self._run(
            "https://www.threads.net/@nthu_sa/",
            fetch_account_preview=lambda url, info, env: ("清大學生會", ["9/20 迎新"]),
            review_source_with_codex=lambda *a: {
                "relevant": True, "name": "清大學生會", "school": "nthu", "org_type": "gov",
                "category_hint": "", "reason": "官方帳號。", "confidence": 0.95},
            add_tracked_source=lambda info, verdict, sub_id: "social_accounts.csv",
        )
        self.ctx["orgs"]["threads_nthu_sa"] = 42
        process_submissions.settle_source_added(self.store, self.ctx["orgs"])
        self.assertEqual((got["status"], self.store.get(got["id"])["event_url"]), ("source_added", "/org/42/"))

    def test_unreachable_profile_is_rejected(self):
        got = self._run("https://www.instagram.com/ghost/",
                        fetch_account_preview=lambda url, info, env: ("", []))
        self.assertEqual(got["status"], "rejected")
        self.assertIn("抓不到", got["reason"])

    def test_missing_account_is_rejected(self):
        def gone(url, info, env):
            raise process_submissions.AccountNotFound("NotFoundError: User ID not found")

        got = self._run("https://www.instagram.com/gone/", fetch_account_preview=gone)
        self.assertEqual(got["status"], "rejected")
        self.assertIn("找不到", got["reason"])

    def test_transient_fetch_failure_retries_instead_of_rejecting(self):
        """抓取管線整條壞掉時每個帳號都讀不到，不能因此把正常投稿判成不收。"""
        def flaky(url, info, env):
            raise RuntimeError('RSSHub: FetchError: fetch failed')

        sub = self.store.create("u1", "https://www.instagram.com/flaky/")
        seen = []
        with mock.patch.object(process_submissions, "fetch_account_preview", flaky), \
             mock.patch.object(process_submissions, "MANUAL_REVIEW",
                               Path(self.tempdir.name) / "m.jsonl"):
            for _ in range(submissions.MAX_ATTEMPTS):
                process_submissions.process_one(self.store, self.store.get(sub["id"]), self.ctx)
                seen.append(self.store.get(sub["id"])["status"])
        self.assertEqual(seen, ["pending"] * (submissions.MAX_ATTEMPTS - 1) + ["manual"])

    def test_irrelevant_profile_is_rejected(self):
        got = self._run("https://www.instagram.com/someshop/",
                        fetch_account_preview=lambda url, info, env: ("某某商家", ["全面八折"]),
                        review_source_with_codex=lambda *a: {
                            "relevant": False, "name": "某某商家", "school": "external",
                            "org_type": "external", "category_hint": None,
                            "reason": "與清交校園活動無關。", "confidence": 0.9})
        self.assertEqual(got["status"], "rejected")

    def test_low_confidence_profile_still_goes_to_a_human(self):
        got = self._run("https://www.instagram.com/maybe/",
                        fetch_account_preview=lambda url, info, env: ("？", ["嗯"]),
                        review_source_with_codex=lambda *a: {
                            "relevant": True, "name": "不確定", "school": "both", "org_type": "club",
                            "category_hint": None, "reason": "看不出跟兩校的關係。", "confidence": 0.2},
                        MANUAL_REVIEW=Path(self.tempdir.name) / "manual.jsonl")
        self.assertEqual(got["status"], "manual")
        self.assertIn("maybe", (Path(self.tempdir.name) / "manual.jsonl").read_text())

    def test_already_covered_post_links_event(self):
        got = self._run("https://instagram.com/p/OLD/?igsh=x")
        self.assertEqual(got["status"], "existing")
        self.assertEqual(got["event_url"], "/event/evt_1/")

    def test_new_event_writes_inbox_and_accepts(self):
        content = {"title": "清大天文社觀星", "text": "9/20 19:00 成功湖畔觀星 " * 20, "images": [], "posted_at": None}
        verdict = {"relevant": True, "action": "new_event", "matched_event_id": None, "reason": "清大社團活動",
                   "confidence": 0.9, "organizer": "清大天文社", "school": "nthu", "org_type": "club", "posted_at": None}
        written = []
        got = self._run(
            "https://infonews.nycu.edu.tw/p/123/",
            fetch_content=lambda url, info: content,
            triage_with_codex=lambda *a, **k: verdict,
            append_inbox=lambda src, items: written.extend(items),
        )
        self.assertEqual(got["status"], "accepted")
        self.assertTrue(self.ctx["needs_extract"])
        self.assertEqual(written[0]["source_id"], "user_submission")
        self.assertEqual(written[0]["post_id"], got["id"])
        self.assertEqual(written[0]["school"], "nthu")
        self.assertIn("accepted_at", json.loads(got["verdict"]))

    def test_attach_reject_and_low_confidence(self):
        content = {"title": "x", "text": "y" * 200, "images": [], "posted_at": None}
        base = {"relevant": True, "matched_event_id": None, "reason": "r", "organizer": None,
                "school": "nthu", "org_type": "club", "posted_at": None}
        with mock.patch.object(process_submissions, "MANUAL_REVIEW", Path(self.tempdir.name) / "m.jsonl"):
            attach = self._run("https://example.org/a", fetch_content=lambda u, i: content,
                               triage_with_codex=lambda *a, **k: {**base, "action": "attach_to_existing",
                                                                   "matched_event_id": "evt_1", "confidence": 0.8})
            self.assertEqual((attach["status"], attach["event_url"]), ("existing", "/event/evt_1/"))
            reject = self._run("https://example.org/b", fetch_content=lambda u, i: content,
                               triage_with_codex=lambda *a, **k: {**base, "relevant": False, "action": "reject", "confidence": 0.9})
            self.assertEqual(reject["status"], "rejected")
            low = self._run("https://example.org/c", fetch_content=lambda u, i: content,
                            triage_with_codex=lambda *a, **k: {**base, "action": "new_event", "confidence": 0.3})
            self.assertEqual(low["status"], "manual")
            self.assertFalse(self.ctx["needs_extract"])

    def test_fetch_failure_retries_then_errors(self):
        def boom(url, info):
            raise RuntimeError("timeout")
        sub = self.store.create("u1", "https://example.org/dead/")
        for _ in range(submissions.MAX_ATTEMPTS):
            with mock.patch.object(process_submissions, "fetch_content", boom):
                process_submissions.process_one(self.store, self.store.get(sub["id"]), self.ctx)
        self.assertEqual(self.store.get(sub["id"])["status"], "error")

    def test_settle_marks_published_or_not_event(self):
        ok = self.store.create("u1", "https://example.org/ok/")
        none = self.store.create("u1", "https://example.org/none/")
        self.store.update(ok["id"], "accepted", "", verdict=json.dumps({"accepted_at": "2025-01-01T00:00:00+08:00"}))
        self.store.update(none["id"], "accepted", "")
        cache = {ok["id"]: {"events": [{"title": "活動 A", "status": "published"}]}, none["id"]: {"events": []}}
        self.index["by_source"][("user_submission", ok["id"])] = ["evt_9"]
        with mock.patch.object(process_submissions, "extracted_events_for", lambda sid: cache[sid].get("events")):
            process_submissions.settle_accepted(self.store, self.index)
        self.assertEqual(self.store.get(ok["id"])["status"], "published")
        self.assertEqual(self.store.get(ok["id"])["event_url"], "/event/evt_9/")
        self.assertEqual(self.store.get(none["id"])["status"], "not_event")


if __name__ == "__main__":
    unittest.main()
