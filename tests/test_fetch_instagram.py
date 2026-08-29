import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_instagram import rsshub_error


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


if __name__ == "__main__":
    unittest.main()
