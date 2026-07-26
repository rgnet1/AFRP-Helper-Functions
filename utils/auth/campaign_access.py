"""Campaign-scoped access control for Event Coordinator users."""

from __future__ import annotations


class CampaignAccessDenied(Exception):
    """Raised when a user attempts to access a campaign outside their scope."""

    def __init__(self, message: str = "Access denied for this campaign"):
        super().__init__(message)
        self.message = message


def _normalize_campaign_id(campaign_id: str | None) -> str:
    return (campaign_id or "").strip().lower()


def user_campaign_is_restricted(user) -> bool:
    if user is None:
        return False
    return bool(getattr(user, "campaign_access_restricted", lambda: False)())


def user_allowed_parent_campaign_id(user) -> str | None:
    if not user_campaign_is_restricted(user):
        return None
    cid = getattr(user, "assigned_campaign_id", None)
    return (cid or "").strip() or None


def campaign_access_metadata(user) -> dict:
    """Metadata for badge UI and API responses."""
    restricted = user_campaign_is_restricted(user)
    assigned_id = user_allowed_parent_campaign_id(user) if restricted else None
    assigned_name = None
    if restricted:
        assigned_name = getattr(user, "assigned_campaign_name", None) or None
    return {
        "restricted": restricted,
        "assigned_campaign_id": assigned_id,
        "assigned_campaign_name": assigned_name,
    }


def assert_campaign_access(user, campaign_id: str | None) -> None:
    """Raise CampaignAccessDenied if user may not access this parent campaign."""
    if not user_campaign_is_restricted(user):
        return

    allowed = user_allowed_parent_campaign_id(user)
    if not allowed:
        raise CampaignAccessDenied("No campaign assigned to this account")

    requested = _normalize_campaign_id(campaign_id)
    if not requested:
        raise CampaignAccessDenied("Campaign is required")

    if requested != _normalize_campaign_id(allowed):
        raise CampaignAccessDenied("Access denied for this campaign")


def assert_sub_event_access(
    user,
    parent_campaign_id: str | None,
    sub_event_id: str | None,
    crm_client,
) -> None:
    """Ensure sub-event belongs to the allowed parent campaign."""
    assert_campaign_access(user, parent_campaign_id)

    sub_event_id = (sub_event_id or "").strip()
    if not sub_event_id:
        return

    if not user_campaign_is_restricted(user):
        return

    sub_events = crm_client.get_sub_events(parent_campaign_id)
    allowed_ids = {_normalize_campaign_id(item.get("id")) for item in sub_events}
    if _normalize_campaign_id(sub_event_id) not in allowed_ids:
        raise CampaignAccessDenied("Access denied for this sub-event")


def annotate_campaigns_for_user(user, campaigns: list) -> list:
    """Return campaign dicts with selectable flag for UI grey-out."""
    meta = campaign_access_metadata(user)
    assigned = _normalize_campaign_id(meta.get("assigned_campaign_id"))
    restricted = meta.get("restricted", False)
    annotated = []
    for campaign in campaigns or []:
        item = dict(campaign)
        cid = _normalize_campaign_id(item.get("id"))
        if restricted:
            item["selectable"] = cid == assigned
        else:
            item["selectable"] = True
        annotated.append(item)
    return annotated
