import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import llm_gateway as g


def response(status, body=None):
    r = mock.Mock(status_code=status, text=json.dumps(body or {}))
    r.json.return_value = body
    return r


class GatewayTests(unittest.TestCase):
    env = {"CHUMEI_LLM_API_KEY": "k", "CHUMEI_LLM_BASE_URL": "http://gw/v1/"}

    def test_aliases_default_without_concrete_models(self):
        self.assertEqual(g.extraction_model({}), "sky-fast")
        self.assertEqual(g.review_model({}), "sky-quality")
        self.assertEqual(g.review_model({"CHUMEI_REVIEW_MODEL": "x"}), "x")

    def test_strict_schema_images_and_resolved_model(self):
        body = {"model": "upstream-1", "choices": [{"message": {"content": "{}"}}]}
        with mock.patch.object(g.requests, "post", return_value=response(200, body)) as post:
            out = g.chat_json(self.env, "sky-fast", "sys", "hi", images=["data:image/jpeg;base64,AA"],
                              schema={"type": "object"}, schema_name="s")
        self.assertEqual(out, ("{}", "upstream-1"))
        url, kw = post.call_args[0][0], post.call_args[1]
        self.assertEqual(url, "http://gw/v1/chat/completions")
        self.assertEqual(kw["json"]["response_format"]["json_schema"]["strict"], True)
        self.assertEqual(kw["json"]["messages"][1]["content"][1]["image_url"]["url"], "data:image/jpeg;base64,AA")

    def test_retries_transient_then_succeeds(self):
        body = {"model": "m", "choices": [{"message": {"content": "{}"}}]}
        with mock.patch.object(g.requests, "post", side_effect=[response(503), response(200, body)]), \
                mock.patch.object(g.time, "sleep") as sleep:
            self.assertEqual(g.chat_json(self.env, "sky-fast", "s", "t"), ("{}", "m"))
        sleep.assert_called_once()

    def test_missing_key_fails_before_network(self):
        with mock.patch.object(g.requests, "post") as post, self.assertRaises(RuntimeError):
            g.chat_json({}, "sky-fast", "s", "t")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
