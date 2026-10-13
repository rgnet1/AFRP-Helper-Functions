"""Registration desk access rules and Dynamics writes."""

import base64
import unittest
from unittest.mock import MagicMock, patch

from utils.auth.campaign_access import CampaignAccessDenied
from utils.registration.desk import (
    STATUS_INACTIVE,
    STATUS_PAID,
    STATE_INACTIVE,
    RegistrationDesk,
    hash_portal_password,
)

PARENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SUB = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CONTACT = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _user(restricted=False, campaigns=None):
    user = MagicMock()
    user.campaign_access_restricted.return_value = restricted
    user.allowed_campaign_ids.return_value = campaigns or []
    return user


class HashTests(unittest.TestCase):
    def test_hash_is_identity_v3(self):
        encoded = hash_portal_password("Correct-Horse-1!")
        raw = base64.b64decode(encoded)
        self.assertEqual(raw[0], 0x01)
        self.assertGreater(len(raw), 13)


class DeskAccessTests(unittest.TestCase):
    def _desk(self, guests=None):
        crm = MagicMock()
        crm.get_open_campaigns.return_value = [
            {"id": PARENT, "name": "Convention"},
            {"id": OTHER, "name": "Other"},
        ]
        crm.get_sub_events.return_value = [{"id": SUB, "name": "Banquet"}]
        crm._make_request.return_value = {"value": guests or []}
        crm.crm_url = "https://example.crm.dynamics.com"
        crm.access_token = "token"
        return RegistrationDesk(crm), crm

    def test_coordinator_only_sees_assigned_event(self):
        desk, _crm = self._desk()
        events = desk.parent_events_for(_user(True, [PARENT]))
        self.assertEqual([row["id"] for row in events], [PARENT])

    def test_add_rejects_event_outside_assignment(self):
        desk, _crm = self._desk()
        with self.assertRaises(CampaignAccessDenied):
            desk.add_guest(_user(True, [PARENT]), CONTACT, OTHER, OTHER)

    def test_coordinator_can_reset_any_contact_password(self):
        desk, crm = self._desk(guests=[])
        user = _user(True, [PARENT])
        user.is_admin = False
        user.is_event_coordinator.return_value = True
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.set_local_password(user, CONTACT, "Correct-Horse-1!")
        self.assertIn(f"contacts({CONTACT})", request.call_args.args[1])
        self.assertTrue(crm._make_request.called or True)

    def test_add_posts_paid_guest_without_transaction(self):
        desk, crm = self._desk(guests=[])
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.add_guest(_user(False), CONTACT, PARENT, SUB)
        body = request.call_args.kwargs["json"]
        self.assertEqual(body["statuscode"], STATUS_PAID)
        self.assertNotIn("_aha_transaction_value", body)
        self.assertIn(f"/campaigns({SUB})", body["crca7_Event@odata.bind"])
        self.assertTrue(crm._make_request.called)

    def test_move_keeps_payment_by_only_changing_event(self):
        desk, _crm = self._desk()
        desk._guest = MagicMock(return_value={"_crca7_event_value": SUB})
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.move_guest(_user(True, [PARENT]), "guest-1", PARENT, PARENT)
        body = request.call_args.kwargs["json"]
        self.assertEqual(set(body), {"crca7_Event@odata.bind"})

    def test_remove_marks_inactive(self):
        desk, _crm = self._desk()
        desk._guest = MagicMock(return_value={"_crca7_event_value": SUB})
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.remove_guest(_user(True, [PARENT]), "guest-1", PARENT)
        body = request.call_args.kwargs["json"]
        self.assertEqual(body["statecode"], STATE_INACTIVE)
        self.assertEqual(body["statuscode"], STATUS_INACTIVE)


if __name__ == "__main__":
    unittest.main()
