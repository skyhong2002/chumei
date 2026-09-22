"""Credential migration must preserve existing tokens without any OS key store."""
import base64
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apify_contributions
import auth_server
import refresh_ig_cookie


class CredentialConfigTests(unittest.TestCase):
    def test_missing_settings_do_not_start_keychain_or_any_subprocess(self):
        with patch.object(auth_server, "load_env", return_value={}), \
             patch.object(apify_contributions, "load_env", return_value={}), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("OS key store accessed")):
            config = auth_server.AuthConfig.from_env()
            self.assertFalse(config.configured)
            self.assertFalse(config.google_configured)
            self.assertEqual(config.feed_signing_key, "")
            self.assertFalse(apify_contributions.encryption_available())
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                apify_contributions.encrypt_token("apify_api_" + "x" * 40)

    def test_explicit_env_credentials_win_and_trim_whitespace(self):
        env = {
            "CHUMEI_NYCU_OAUTH_CLIENT_ID": " nycu-id ",
            "CHUMEI_NYCU_OAUTH_CLIENT_SECRET": " oauth-secret ",
            "CHUMEI_GOOGLE_OAUTH_CLIENT_ID": " google-id ",
            "CHUMEI_GOOGLE_OAUTH_CLIENT_SECRET": " google-secret ",
            "CHUMEI_FEED_SIGNING_KEY": " feed-secret ",
            "CHUMEI_APIFY_CONTRIBUTION_KEY": " contribution-secret ",
        }
        with patch.object(auth_server, "load_env", return_value=env), \
             patch.object(apify_contributions, "load_env", return_value=env), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("OS key store accessed")):
            config = auth_server.AuthConfig.from_env()
            self.assertEqual((config.client_id, config.client_secret), ("nycu-id", "oauth-secret"))
            self.assertEqual((config.google_client_id, config.google_client_secret), ("google-id", "google-secret"))
            self.assertEqual(config.feed_signing_key, "feed-secret")
            self.assertEqual(apify_contributions.encryption_secret(), "contribution-secret")

    def test_pinning_effective_keys_preserves_old_feed_and_encrypted_token(self):
        oauth_secret = "fixture-original-oauth-secret"
        expected_feed_key = hashlib.sha256(("chumei-saved-feed-v1\0" + oauth_secret).encode()).hexdigest()
        # Encrypt with the pre-migration documented derivation, independently of the implementation.
        old_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(
            ("chumei-apify-contributions-v1\0" + oauth_secret).encode()).digest()))
        plaintext = "apify_api_" + "x" * 40
        ciphertext = old_fernet.encrypt(plaintext.encode()).decode()
        fallback_env = {"CHUMEI_NYCU_OAUTH_CLIENT_SECRET": oauth_secret}
        with patch.object(auth_server, "load_env", return_value=fallback_env), \
             patch.object(apify_contributions, "load_env", return_value=fallback_env):
            config = auth_server.AuthConfig.from_env()
            self.assertEqual(config.feed_signing_key, expected_feed_key)
            self.assertEqual(apify_contributions.encryption_secret(), oauth_secret)
            self.assertEqual(apify_contributions.decrypt_token(ciphertext), plaintext)
            old_feed_token = auth_server._saved_feed_token("a" * 24, config.feed_signing_key)
        migrated_env = {
            "CHUMEI_NYCU_OAUTH_CLIENT_SECRET": "fixture-rotated-oauth-secret",
            "CHUMEI_FEED_SIGNING_KEY": expected_feed_key,
            "CHUMEI_APIFY_CONTRIBUTION_KEY": oauth_secret,
        }
        with patch.object(auth_server, "load_env", return_value=migrated_env), \
             patch.object(apify_contributions, "load_env", return_value=migrated_env):
            config = auth_server.AuthConfig.from_env()
            self.assertEqual(auth_server._saved_feed_public_id(old_feed_token, config.feed_signing_key), "a" * 24)
            self.assertEqual(apify_contributions.decrypt_token(ciphertext), plaintext)

    def test_retired_cookie_command_has_no_operational_side_effects(self):
        with patch.object(subprocess, "Popen", side_effect=AssertionError("unexpected subprocess")), \
             patch.object(Path, "read_text", side_effect=AssertionError("unexpected credential read")), \
             self.assertRaisesRegex(SystemExit, "已停用"):
            refresh_ig_cookie.main()


if __name__ == "__main__":
    unittest.main()
