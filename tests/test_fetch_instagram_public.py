import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import requests


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_instagram_public
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


class DirectPathTests(unittest.TestCase):
    def run_main(self, fetch, *, budget=0.0, actor_items=(), host_open=True):
        rows = [{"username": name, "active": "true"} for name in ("a", "b", "c", "d")]
        self.schedule = {"version": 1, "accounts": {}}
        client = Mock()
        client.fetch.side_effect = fetch
        self.run_actor = Mock(return_value=({"usageTotalUsd": 0.01}, list(actor_items)))
        self.mark_failure = Mock()
        self.record_fetch = Mock()
        self.report_block = Mock()
        seen = MagicMock()
        seen.has.return_value = False
        patches = [
            patch.object(sys, "argv", ["fetch_instagram_public.py", "--max-accounts", "4"]),
            patch.object(fetch_instagram_public, "read_sources_csv", return_value=rows),
            patch.object(fetch_instagram_public, "load_schedule", return_value=self.schedule),
            patch.object(fetch_instagram_public, "save_schedule"),
            patch.object(fetch_instagram_public, "select_due", return_value=["a", "b", "c", "d"]),
            patch.object(fetch_instagram_public, "load_env", return_value={}),
            patch.object(fetch_instagram_public, "PublicWebClient", return_value=client),
            patch.object(fetch_instagram_public, "SeenState", return_value=seen),
            patch.object(fetch_instagram_public, "append_inbox", side_effect=lambda _, items: len(items)),
            patch.object(fetch_instagram_public, "save_avatar"),
            patch.object(fetch_instagram_public, "pool_status", return_value={}),
            patch.object(fetch_instagram_public, "round_budget_usd", return_value=budget),
            patch.object(fetch_instagram_public, "choose_token", return_value=("A", "token", {})),
            patch.object(fetch_instagram_public, "run_actor", self.run_actor),
            patch.object(fetch_instagram_public, "record_run"),
            patch.object(fetch_instagram_public, "record_api_call"),
            patch.object(fetch_instagram_public, "record_fetch", self.record_fetch),
            patch.object(fetch_instagram_public, "mark_failure", self.mark_failure),
            patch.object(fetch_instagram_public, "mark_success"),
            patch.object(fetch_instagram_public.ig_public_host, "wait_turn", return_value=host_open),
            patch.object(fetch_instagram_public.ig_public_host, "report_block", self.report_block),
        ]
        for item in patches:
            item.start()
        try:
            return fetch_instagram_public.main(), client
        finally:
            for item in reversed(patches):
                item.stop()

    def test_rate_limit_pauses_direct_path_without_penalizing_untried_accounts(self):
        def fetch(username, _limit):
            if username == "a":
                return None, []
            raise requests.HTTPError("Instagram public web HTTP 401 for @b: Please wait a few minutes")

        code, client = self.run_main(fetch)

        self.assertEqual(code, 0)
        self.assertEqual([call.args[0] for call in client.fetch.call_args_list], ["a", "b"])
        # The refusal blocks Harmonica's direct queries on this host too.
        self.report_block.assert_called_once_with("chumei")
        self.mark_failure.assert_not_called()
        self.run_actor.assert_not_called()
        failed = [call.args[0] for call in self.record_fetch.call_args_list if not call.kwargs["ok"]]
        self.assertEqual(failed, ["instagram:b", "instagram:c", "instagram:d"])

    def test_apify_fallback_is_limited_to_the_instagram_share(self):
        def fetch(username, _limit):
            raise requests.HTTPError("Instagram public web HTTP 401 for @a: Please wait a few minutes")

        item = {"username": "a", "latestPosts": [{"shortCode": "P1", "timestamp": "2026-10-01T00:00:00Z"}]}
        cost = fetch_instagram_public.SOURCE_COST_ESTIMATE_USD["instagram"]
        self.run_main(fetch, budget=2.5 * cost, actor_items=[item])

        self.assertEqual(self.run_actor.call_args.args[1], ["a", "b"])
        # b was sent to Apify but returned nothing; c and d were never tried.
        self.assertEqual([call.args[1] for call in self.mark_failure.call_args_list], ["b"])

    def test_host_block_from_another_collector_skips_direct_queries(self):
        _, client = self.run_main(lambda *_: None, host_open=False)
        client.fetch.assert_not_called()
        self.mark_failure.assert_not_called()

    def test_repeated_query_failures_stop_direct_requests_for_this_round(self):
        def fetch(username, _limit):
            raise RuntimeError(f"Instagram public web query failed for @{username}: execution error")

        _, client = self.run_main(fetch)

        self.assertEqual(client.fetch.call_count, fetch_instagram_public.DIRECT_MAX_CONSECUTIVE_FAILURES)
        self.report_block.assert_not_called()
        self.assertEqual([call.args[1] for call in self.mark_failure.call_args_list], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
