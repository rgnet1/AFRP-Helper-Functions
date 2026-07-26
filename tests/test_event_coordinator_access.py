"""Unit tests for Event Coordinator campaign access control."""

import unittest
from unittest.mock import MagicMock

from utils.auth.campaign_access import (
    CampaignAccessDenied,
    annotate_campaigns_for_user,
    assert_campaign_access,
    assert_sub_event_access,
    campaign_access_metadata,
    user_allowed_parent_campaign_id,
    user_campaign_is_restricted,
)


ASSIGNED_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "22222222-2222-2222-2222-222222222222"
SUB_EVENT_ID = "33333333-3333-3333-3333-333333333333"


def _coordinator(**overrides):
    user = MagicMock()
    user.is_admin = False
    user.is_event_coordinator.return_value = True
    user.campaign_access_restricted.return_value = True
    user.assigned_campaign_id = ASSIGNED_ID
    user.assigned_campaign_name = "Convention 2026"
    user.username = "coordinator"
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _standard_user():
    user = MagicMock()
    user.is_admin = False
    user.is_event_coordinator.return_value = False
    user.campaign_access_restricted.return_value = False
    user.assigned_campaign_id = None
    user.username = "standard"
    return user


class CampaignAccessHelperTests(unittest.TestCase):
    def test_coordinator_is_restricted(self):
        user = _coordinator()
        self.assertTrue(user_campaign_is_restricted(user))
        self.assertEqual(user_allowed_parent_campaign_id(user), ASSIGNED_ID)

    def test_standard_user_not_restricted(self):
        user = _standard_user()
        self.assertFalse(user_campaign_is_restricted(user))
        self.assertIsNone(user_allowed_parent_campaign_id(user))

    def test_assert_campaign_access_allows_assigned_campaign(self):
        assert_campaign_access(_coordinator(), ASSIGNED_ID)

    def test_assert_campaign_access_denies_other_campaign(self):
        with self.assertRaises(CampaignAccessDenied):
            assert_campaign_access(_coordinator(), OTHER_ID)

    def test_assert_campaign_access_ignores_standard_user(self):
        assert_campaign_access(_standard_user(), OTHER_ID)

    def test_assert_sub_event_access_valid_child(self):
        crm = MagicMock()
        crm.get_sub_events.return_value = [{"id": SUB_EVENT_ID, "name": "Banquet"}]
        assert_sub_event_access(_coordinator(), ASSIGNED_ID, SUB_EVENT_ID, crm)

    def test_assert_sub_event_access_denies_foreign_sub_event(self):
        crm = MagicMock()
        crm.get_sub_events.return_value = [{"id": SUB_EVENT_ID, "name": "Banquet"}]
        with self.assertRaises(CampaignAccessDenied):
            assert_sub_event_access(
                _coordinator(), ASSIGNED_ID, OTHER_ID, crm
            )

    def test_annotate_campaigns_marks_selectable_flags(self):
        campaigns = [
            {"id": ASSIGNED_ID, "name": "Mine"},
            {"id": OTHER_ID, "name": "Other"},
        ]
        annotated = annotate_campaigns_for_user(_coordinator(), campaigns)
        by_id = {item["id"]: item for item in annotated}
        self.assertTrue(by_id[ASSIGNED_ID]["selectable"])
        self.assertFalse(by_id[OTHER_ID]["selectable"])

    def test_campaign_access_metadata(self):
        meta = campaign_access_metadata(_coordinator())
        self.assertTrue(meta["restricted"])
        self.assertEqual(meta["assigned_campaign_id"], ASSIGNED_ID)
        self.assertEqual(meta["assigned_campaign_name"], "Convention 2026")


if __name__ == "__main__":
    unittest.main()
