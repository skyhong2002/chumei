import sys
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


if __name__ == "__main__":
    unittest.main()
