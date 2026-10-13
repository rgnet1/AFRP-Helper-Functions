"""Tests for Power Pages portal token validation and whitelist."""

import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from utils.auth.login_gate import resolve_user_for_portal
from utils.auth.permissions import path_is_public
from utils.auth.portal_implicit import (
    PortalTokenError,
    build_portal_bridge_url,
    portal_callback_state_ok,
    reset_public_key_cache,
    reset_used_tokens,
    verify_portal_id_token,
)

PORTAL_ENV = {"PORTAL_OAUTH_CLIENT_ID": "afrp-helper", "PORTAL_BASE_URL": "https://my.afrp.org"}


def _rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key, public_pem


def _portal_token(private_key, **claims):
    payload = {
        "iss": "https://my.afrp.org",
        "aud": "afrp-helper",
        "email": "staff@example.com",
        "nonce": "n" * 20,
        "state": "s" * 20,
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    payload.update(claims)
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, private_key, algorithm="RS256")


class PortalTokenTests(unittest.TestCase):
    def setUp(self):
        reset_public_key_cache()
        reset_used_tokens()

    def test_token_without_nonce_claim_is_accepted(self):
        private_key, public_pem = _rsa_keypair()
        token = _portal_token(private_key, nonce=None, iss="my.afrp.org")
        with patch.dict("os.environ", PORTAL_ENV, clear=False):
            identity = verify_portal_id_token(
                token,
                expected_nonce="n" * 20,
                issued_after=time.time(),
                public_key_pem=public_pem,
            )
        self.assertEqual(identity["email"], "staff@example.com")

    def test_replayed_token_is_rejected(self):
        private_key, public_pem = _rsa_keypair()
        token = _portal_token(private_key)
        with patch.dict("os.environ", PORTAL_ENV, clear=False):
            verify_portal_id_token(token, public_key_pem=public_pem)
            with self.assertRaises(PortalTokenError):
                verify_portal_id_token(token, public_key_pem=public_pem)

    def test_token_issued_before_sign_in_started_is_rejected(self):
        private_key, public_pem = _rsa_keypair()
        token = _portal_token(private_key, iat=int(time.time()) - 600)
        with patch.dict("os.environ", PORTAL_ENV, clear=False):
            with self.assertRaises(PortalTokenError):
                verify_portal_id_token(
                    token,
                    issued_after=time.time(),
                    public_key_pem=public_pem,
                )

    def test_verify_accepts_valid_token(self):
        private_key, public_pem = _rsa_keypair()
        token = _portal_token(private_key)
        env = {
            "PORTAL_OAUTH_CLIENT_ID": "afrp-helper",
            "PORTAL_BASE_URL": "https://my.afrp.org",
        }
        with patch.dict("os.environ", env, clear=False):
            identity = verify_portal_id_token(
                token,
                expected_state="s" * 20,
                expected_nonce="n" * 20,
                public_key_pem=public_pem,
            )
        self.assertEqual(identity["email"], "staff@example.com")

    def test_verify_accepts_bare_host_issuer(self):
        private_key, public_pem = _rsa_keypair()
        token = _portal_token(private_key, iss="my.afrp.org")
        env = {"PORTAL_OAUTH_CLIENT_ID": "afrp-helper", "PORTAL_BASE_URL": "https://my.afrp.org"}
        with patch.dict("os.environ", env, clear=False):
            identity = verify_portal_id_token(
                token,
                expected_nonce="n" * 20,
                public_key_pem=public_pem,
            )
        self.assertEqual(identity["email"], "staff@example.com")

    def test_verify_rejects_wrong_audience(self):
        private_key, public_pem = _rsa_keypair()
        token = _portal_token(private_key, aud="other-client")
        env = {"PORTAL_OAUTH_CLIENT_ID": "afrp-helper", "PORTAL_BASE_URL": "https://my.afrp.org"}
        with patch.dict("os.environ", env, clear=False):
            with self.assertRaises(PortalTokenError):
                verify_portal_id_token(
                    token,
                    expected_nonce="n" * 20,
                    public_key_pem=public_pem,
                )

    def test_build_bridge_url_points_at_portal_page_not_token_get(self):
        env = {"PORTAL_OAUTH_CLIENT_ID": "afrp-helper", "PORTAL_BASE_URL": "https://my.afrp.org"}
        with patch.dict("os.environ", env, clear=False):
            url = build_portal_bridge_url(
                "http://localhost:5066/auth/portal/callback",
                "a" * 20,
                "b" * 20,
            )
        self.assertIn("https://my.afrp.org/afrp-helper-auth?", url)
        self.assertNotIn("/_services/auth/token?", url)
        self.assertIn("redirect_uri", url)
        self.assertIn("afrp-helper", url)


class PortalCallbackStateTests(unittest.TestCase):
    def test_missing_or_wrong_state_is_rejected(self):
        self.assertFalse(portal_callback_state_ok(None, "abc"))
        self.assertFalse(portal_callback_state_ok("abc", None))
        self.assertFalse(portal_callback_state_ok("", "abc"))
        self.assertFalse(portal_callback_state_ok("abc", "xyz"))

    def test_matching_state_is_accepted(self):
        self.assertTrue(portal_callback_state_ok("abc123", "abc123"))


class PortalWhitelistTests(unittest.TestCase):
    def _user_query(self, rows):
        query = MagicMock()
        query.filter.return_value.all.return_value = rows
        module = types.ModuleType("utils.magazine.scheduler")
        module.User = MagicMock()
        module.User.query = query
        return patch.dict(sys.modules, {"utils.magazine.scheduler": module})

    def test_whitelisted_email_is_allowed(self):
        user = MagicMock()
        user.email = "staff@example.com"
        user.is_active = True
        with self._user_query([user]):
            found = resolve_user_for_portal("staff@example.com")
        self.assertIs(found, user)


class PortalPublicPathTests(unittest.TestCase):
    def test_portal_routes_are_public(self):
        self.assertTrue(path_is_public("/auth/portal/login"))
        self.assertTrue(path_is_public("/auth/portal/callback"))


if __name__ == "__main__":
    unittest.main()
