import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_instagram import PublicWebClient, rsshub_error
from ig_schedule import is_rate_limited


class RSSHubErrorTests(unittest.TestCase):
    def test_extracts_rsshub_error_message(self):
        response = Mock(status_code=503, url="http://rsshub/threads/missing")
        response.text = (
            '<p>Error Message:<br/><code class="details">'
            'NotFoundError: User ID not found</code></p><p>Route:</p>'
        )
        error = rsshub_error(response)
        self.assertEqual(
            str(error), "RSSHub: NotFoundError: User ID not found (HTTP 503)"
        )

    def test_success_has_no_error(self):
        response = Mock(status_code=200)
        self.assertIsNone(rsshub_error(response))



def _response(status, *, text="", payload=None):
    response = Mock(status_code=status, text=text or json.dumps(payload or {}))
    response.json.return_value = payload
    return response


def _timeline(*nodes):
    return {"data": {"xdt_api__v1__feed__user_timeline_graphql_connection": {
        "edges": [{"node": node} for node in nodes]}}}


class PublicWebClientTests(unittest.TestCase):
    def setUp(self):
        self.client = PublicWebClient("https://www.instagram.com")
        page = _response(200, text='..."LSD",[],{"token":"lsd-token"}...')

        def bootstrap(*_args, **_kwargs):
            self.client.session.cookies.set("csrftoken", "anon-csrf")
            self.client.session.cookies.set("mid", "anon-mid")
            return page

        get = patch.object(self.client.session, "get", side_effect=bootstrap)
        self.get = get.start()
        self.addCleanup(get.stop)

    def test_logged_out_query_parses_posts_without_an_account(self):
        user = {"username": "nthu_official", "profile_pic_url": "https://cdn.example/small.jpg",
                "hd_profile_pic_url_info": {"url": "https://cdn.example/avatar.jpg"}}
        payload = _timeline(
            {"code": "PINNED", "taken_at": 1600000000, "timeline_pinned_user_ids": [1], "user": user},
            {"code": "OLDER", "taken_at": 1788000000, "user": user,
             "image_versions2": {"candidates": [{"url": "https://cdn.example/older.jpg"}]}},
            {"code": "POST1", "taken_at": 1788537600, "user": user,
             "caption": {"text": " 校園活動 "},
             "carousel_media": [
                 {"image_versions2": {"candidates": [{"url": "https://cdn.example/1.jpg"}]}},
                 {"display_uri": "https://cdn.example/2.jpg"},
                 {"image_versions2": {"candidates": [{"url": "https://cdn.example/3.jpg"}]}},
             ]},
        )
        with patch.object(self.client.session, "post", return_value=_response(200, payload=payload)) as post:
            avatar, posts = self.client.fetch("nthu_official", 5)
            self.client.fetch("nthu_official", 5)

        self.assertEqual(avatar, "https://cdn.example/avatar.jpg")
        self.assertEqual([post["post_id"] for post in posts], ["POST1", "OLDER"])
        self.assertEqual(posts[0]["text"], "校園活動")
        self.assertEqual(posts[0]["images"], ["https://cdn.example/1.jpg", "https://cdn.example/2.jpg"])
        self.assertEqual(posts[1]["text"], "（純圖片貼文，內容見海報）")
        self.assertEqual(posts[0]["posted_at"], "2026-09-04T16:00:00+00:00")
        self.get.assert_called_once()  # the anonymous token is reused across profiles
        _, kwargs = post.call_args
        self.assertEqual(kwargs["data"]["lsd"], "lsd-token")
        self.assertEqual(kwargs["headers"]["X-CSRFToken"], "anon-csrf")
        self.assertEqual(json.loads(kwargs["data"]["variables"])["username"], "nthu_official")
        self.assertNotIn("sessionid", self.client.session.cookies.keys())

    def test_logged_out_block_is_reported_as_rate_limit(self):
        blocked = _response(401, payload={"message": "Please wait a few minutes before you try again.",
                                          "require_login": True})
        with patch.object(self.client.session, "post", return_value=blocked):
            with self.assertRaises(requests.HTTPError) as caught:
                self.client.fetch("nthuctm", 5)
        self.assertTrue(is_rate_limited(caught.exception))

    def test_rejected_query_is_not_mistaken_for_an_empty_profile(self):
        rejected = _response(200, payload={"errors": [{"message": "execution error"}], "data": None})
        with patch.object(self.client.session, "post", return_value=rejected):
            with self.assertRaisesRegex(RuntimeError, "execution error"):
                self.client.fetch("nthuctm", 5)

    def test_page_without_anonymous_token_fails_loudly(self):
        self.get.side_effect = None
        self.get.return_value = _response(200, text="<html>login</html>")
        with self.assertRaisesRegex(RuntimeError, "LSD"):
            self.client.fetch("nthuctm", 5)


if __name__ == "__main__":
    unittest.main()
