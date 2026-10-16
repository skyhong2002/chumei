import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_rpage

LIST_URL = "https://dsa.site.nthu.edu.tw/p/403-1000-1-1.php"
DETAIL_URL = "https://dsa.site.nthu.edu.tw/p/406-1000-1,r1.php"
DETAIL_HTML = "<html><body><div class='mpgdetail'><p>活動內容</p></div></body></html>"


def response(url, status=200, *, location=None, body=""):
    result = requests.Response()
    result.url, result.status_code = url, status
    result.headers["content-type"] = "text/html; charset=utf-8"
    if location:
        result.headers["location"] = location
    result._content = body.encode()
    result.encoding = "utf-8"
    return result


class FakeSession(requests.Session):
    """Serves canned responses; any unknown URL is a network failure."""

    def __init__(self, pages):
        super().__init__()
        self.pages, self.requested = pages, []

    def get(self, url, **kwargs):
        self.requested.append(url)
        if url not in self.pages:
            raise requests.ConnectionError(f"no route to {url}")
        return self.pages[url]


class FetchDetailTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(fetch_rpage, "_last_request_at", None)
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep = mock.patch.object(fetch_rpage.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_follows_redirects_within_nthu_rpage(self):
        moved = "https://dsa.site.nthu.edu.tw/p/406-1000-2,r1.php"
        session = FakeSession({
            DETAIL_URL: response(DETAIL_URL, 302, location="/p/406-1000-2,r1.php"),
            moved: response(moved, body=DETAIL_HTML),
        })
        document, final_url = fetch_rpage.fetch_detail(session, DETAIL_URL)
        self.assertEqual((document, final_url), (DETAIL_HTML, moved))

    def test_offsite_redirect_is_rejected_without_requesting_the_target(self):
        session = FakeSession({
            DETAIL_URL: response(DETAIL_URL, 302, location="https://docs.google.com/forms/d/x/viewform"),
        })
        with self.assertRaisesRegex(fetch_rpage.OffsiteRedirect, "docs.google.com"):
            fetch_rpage.fetch_detail(session, DETAIL_URL)
        self.assertEqual(session.requested, [DETAIL_URL])

    def test_server_errors_stay_request_failures(self):
        session = FakeSession({DETAIL_URL: response(DETAIL_URL, 503)})
        with self.assertRaises(requests.HTTPError):
            fetch_rpage.fetch_detail(session, DETAIL_URL)

    def test_redirect_loops_stop(self):
        session = FakeSession({DETAIL_URL: response(DETAIL_URL, 302, location=DETAIL_URL)})
        with self.assertRaises(requests.TooManyRedirects):
            fetch_rpage.fetch_detail(session, DETAIL_URL)
        self.assertEqual(len(session.requested), fetch_rpage.MAX_REDIRECTS + 1)


class SeenStateTests(unittest.TestCase):
    """Runs main() twice against canned pages to observe what the second run requests."""

    OFFSITE_URL = "https://dsa.site.nthu.edu.tw/p/406-1000-2,r1.php"
    FLAKY_URL = "https://dsa.site.nthu.edu.tw/p/406-1000-3,r1.php"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        sources = root / "bulletin_sources.csv"
        sources.write_text("source_id,name,type,school,org_type,url,extra\n"
                           f"nthu_dsa,清大課外組,rpage_list,nthu,official,{LIST_URL},\n")
        self.seen_path = root / "seen" / "rpage.json"
        self.inbox_path = root / "inbox" / "rpage.jsonl"
        list_html = "".join(
            f"<div class='mbox'><a href='{url}'>{title}</a><i class='mdate'>2026-10-0{index}</i></div>"
            for index, (url, title) in enumerate(
                [(DETAIL_URL, "社團博覽會"), (self.OFFSITE_URL, "報名表單"), (self.FLAKY_URL, "講座")], 1)
        )
        # FLAKY_URL is absent from the canned pages, so it always fails with a network error.
        self.pages = {
            LIST_URL: response(LIST_URL, body=list_html),
            DETAIL_URL: response(DETAIL_URL, body=DETAIL_HTML),
            self.OFFSITE_URL: response(self.OFFSITE_URL, 302, location="https://reurl.cc/abc"),
        }
        for patcher in (
            mock.patch.object(fetch_rpage, "SOURCES_PATH", sources),
            mock.patch.object(fetch_rpage, "SEEN_PATH", self.seen_path),
            mock.patch.object(fetch_rpage, "INBOX_PATH", self.inbox_path),
            mock.patch.object(fetch_rpage, "_last_request_at", None),
            mock.patch.object(fetch_rpage.time, "sleep"),
            mock.patch("source_status.record_fetch"),
            mock.patch.object(sys, "argv", ["fetch_rpage.py", "--max-pages", "1"]),
            mock.patch("sys.stderr", new_callable=io.StringIO),
            mock.patch("sys.stdout", new_callable=io.StringIO),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self):
        session = FakeSession(self.pages)
        with mock.patch.object(fetch_rpage.requests, "Session", return_value=session):
            self.assertEqual(fetch_rpage.main(), 0)
        return session.requested

    def test_offsite_rejection_is_remembered_but_transient_failures_retry(self):
        self.assertEqual(self.run_main(), [LIST_URL, DETAIL_URL, self.OFFSITE_URL, self.FLAKY_URL])
        seen = json.loads(self.seen_path.read_text())
        self.assertEqual(seen["nthu_dsa|2"], fetch_rpage.REJECTED_OFFSITE)
        self.assertNotIn("nthu_dsa|3", seen)
        self.assertEqual(len(self.inbox_path.read_text().splitlines()), 1)

        self.assertEqual(self.run_main(), [LIST_URL, self.FLAKY_URL])
        self.assertEqual(len(self.inbox_path.read_text().splitlines()), 1)
        self.assertEqual(fetch_rpage.load_seen(self.seen_path)["nthu_dsa|2"],
                         fetch_rpage.REJECTED_OFFSITE)


if __name__ == "__main__":
    unittest.main()
