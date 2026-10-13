"""Tests for Google sign-in whitelist and Dynamics login gate."""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from utils.auth.google_oidc import GoogleOidcError, verify_id_token
from utils.auth.login_gate import contact_meets_gate, crm_allows_login, resolve_user_for_google
from utils.auth.permissions import path_is_public


def _user_query(rows, linked=None):
    query = MagicMock()
    query.filter_by.return_value.first.return_value = linked
    query.filter.return_value.all.return_value = rows
    module = types.ModuleType("utils.magazine.scheduler")
    module.User = MagicMock()
    module.User.query = query
    return patch.dict(sys.modules, {"utils.magazine.scheduler": module})


def _user(email="staff@example.com", google_sub=None, active=True):
    user = MagicMock()
    user.email = email
    user.google_sub = google_sub
    user.is_active = active
    return user


class GoogleTokenTests(unittest.TestCase):
    def test_verify_id_token_accepts_matching_audience(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "aud": "client-id",
            "iss": "https://accounts.google.com",
            "email_verified": "true",
            "email": "Staff@Example.com",
            "sub": "google-sub",
            "name": "Staff",
        }
        with patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "client-id"}, clear=False):
            with patch("utils.auth.google_oidc.requests.get", return_value=response):
                identity = verify_id_token("token")
        self.assertEqual(identity["email"], "staff@example.com")
        self.assertEqual(identity["sub"], "google-sub")

    def test_verify_id_token_rejects_wrong_audience(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "aud": "other",
            "iss": "https://accounts.google.com",
            "email_verified": "true",
            "email": "a@b.c",
            "sub": "sub",
        }
        with patch.dict("os.environ", {"GOOGLE_CLIENT_ID": "client-id"}, clear=False):
            with patch("utils.auth.google_oidc.requests.get", return_value=response):
                with self.assertRaises(GoogleOidcError):
                    verify_id_token("token")


class WhitelistTests(unittest.TestCase):
    def test_unknown_email_is_denied(self):
        with _user_query([]):
            self.assertIsNone(resolve_user_for_google("missing@example.com", "sub"))

    def test_whitelisted_email_is_allowed(self):
        user = _user()
        with _user_query([user]):
            found = resolve_user_for_google("staff@example.com", "new-sub")
        self.assertIs(found, user)

    def test_inactive_user_is_denied(self):
        user = _user(active=False)
        with _user_query([user]):
            self.assertIsNone(resolve_user_for_google("staff@example.com", "sub"))

    def test_mismatched_google_sub_is_denied(self):
        user = _user(google_sub="existing")
        with _user_query([user]):
            self.assertIsNone(resolve_user_for_google("staff@example.com", "other"))


class CrmGateTests(unittest.TestCase):
    def test_gate_off_allows_without_crm(self):
        with patch.dict("os.environ", {"CRM_LOGIN_GATE_ENABLED": "false"}, clear=False):
            self.assertTrue(crm_allows_login("anyone@example.com"))

    def test_contact_email_match_without_role(self):
        client = MagicMock()
        client._make_request.return_value = {
            "value": [{"contactid": "abc", "emailaddress1": "Staff@Example.com"}]
        }
        with patch.dict("os.environ", {"CRM_REQUIRED_WEB_ROLE_NAME": ""}, clear=False):
            self.assertTrue(contact_meets_gate("staff@example.com", crm_client=client))

    def test_required_web_role_must_be_linked(self):
        client = MagicMock()

        def _request(endpoint, method="GET", data=None):
            if endpoint.startswith("contacts"):
                return {"value": [{"contactid": "abc", "emailaddress1": "staff@example.com"}]}
            if endpoint.startswith("adx_webroles"):
                return {"value": [{"adx_webroleid": "role-1", "adx_name": "Administrators"}]}
            if "adx_webroleid eq role-1" in endpoint:
                return {"value": [{"adx_webrole_contactid": "link-1"}]}
            return {"value": []}

        client._make_request.side_effect = _request
        with patch.dict("os.environ", {"CRM_REQUIRED_WEB_ROLE_NAME": "Administrators"}, clear=False):
            self.assertTrue(contact_meets_gate("staff@example.com", crm_client=client))

    def test_crm_outage_fails_closed(self):
        with patch.dict(
            "os.environ",
            {"CRM_LOGIN_GATE_ENABLED": "true", "CRM_LOGIN_GATE_FAIL_OPEN": "false"},
            clear=False,
        ):
            with patch(
                "utils.auth.login_gate.contact_meets_gate",
                side_effect=RuntimeError("down"),
            ):
                self.assertFalse(crm_allows_login("staff@example.com"))


class PublicPathTests(unittest.TestCase):
    def test_google_callback_is_public(self):
        self.assertTrue(path_is_public("/auth/google/callback"))
        self.assertTrue(path_is_public("/auth/google/login"))


if __name__ == "__main__":
    unittest.main()
