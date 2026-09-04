import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_instagram import fetch_public_web, rsshub_error


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

    @patch("fetch_instagram.requests.get")
    def test_public_web_profile_needs_no_cookie_and_parses_posts(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {"data": {"user": {
            "profile_pic_url": "https://cdn.example/avatar.jpg",
            "edge_owner_to_timeline_media": {"edges": [{"node": {
                "shortcode": "POST1",
                "taken_at_timestamp": 1788537600,
                "display_url": "https://cdn.example/post.jpg",
                "edge_media_to_caption": {"edges": [{"node": {"text": "校園活動"}}]},
            }}]},
        }}}
        get.return_value = response

        avatar, posts = fetch_public_web("https://www.instagram.com", "nthu_official", 5)

        self.assertEqual(avatar, "https://cdn.example/avatar.jpg")
        self.assertEqual(posts[0]["post_id"], "POST1")
        self.assertEqual(posts[0]["text"], "校園活動")
        _, kwargs = get.call_args
        self.assertNotIn("Cookie", kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
