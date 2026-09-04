import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_instagram_public import normalize_profile


class PublicInstagramTests(unittest.TestCase):
    def test_normalizes_nested_profile_posts(self):
        username, avatar, posts = normalize_profile({
            "username": "nthu_sa",
            "profilePicUrlHD": "https://cdn.example/avatar.jpg",
            "latestPosts": [{
                "shortCode": "ABC123",
                "url": "https://www.instagram.com/p/ABC123/",
                "timestamp": "2026-09-04T12:00:00.000Z",
                "caption": "社團博覽會",
                "images": ["https://cdn.example/one.jpg", "https://cdn.example/two.jpg"],
            }, {
                "shortCode": "PINNED",
                "timestamp": "2020-01-01T00:00:00.000Z",
                "isPinned": True,
            }],
        }, 5)
        self.assertEqual(username, "nthu_sa")
        self.assertEqual(avatar, "https://cdn.example/avatar.jpg")
        self.assertEqual(posts[0]["post_id"], "ABC123")
        self.assertEqual(posts[0]["text"], "社團博覽會")
        self.assertEqual(len(posts[0]["images"]), 2)
        self.assertEqual(len(posts), 1)


if __name__ == "__main__":
    unittest.main()
