"""Copy event coordinators from Dynamics onto Helper access groups."""

import logging
import re
import time

from utils.auth.groups import set_user_groups, sync_user_access
from utils.auth.permissions import FEATURES
from utils.magazine.scheduler import AccessGroup, AccessGroupMember, User, db

logger = logging.getLogger(__name__)

_LAST_SYNC = 0.0
_SYNC_INTERVAL_SECONDS = 300


def _username_from_email(email: str) -> str:
    base = re.sub(r'[^a-zA-Z0-9_-]', '_', email.split('@', 1)[0]).strip('_') or 'user'
    base = base[:70]
    if len(base) < 3:
        base = f"{base}_user"
    candidate = base
    suffix = 2
    while User.query.filter_by(username=candidate).first():
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


def sync_event_coordinators(crm, force=False) -> None:
    """Match Helper coordinator groups to the campaign's Dynamics contact list."""
    global _LAST_SYNC
    now = time.monotonic()
    if not force and _LAST_SYNC and now - _LAST_SYNC < _SYNC_INTERVAL_SECONDS:
        return
    campaigns = {
        (row.get("id") or "").strip(): (row.get("name") or "").strip()
        for row in (crm.get_open_campaigns() or [])
        if (row.get("id") or "").strip()
    }
    for group in AccessGroup.query.filter_by(role=User.ROLE_EVENT_COORDINATOR).all():
        cid = (group.assigned_campaign_id or "").strip()
        if cid and cid not in campaigns:
            campaigns[cid] = (group.assigned_campaign_name or cid).strip()
    for campaign_id, campaign_name in campaigns.items():
        _sync_campaign(crm, campaign_id, campaign_name)
    db.session.commit()
    _LAST_SYNC = now


def _sync_campaign(crm, campaign_id: str, campaign_name: str) -> None:
    rows = crm._make_request(
        "aha_campaign_eventcorrespondentset?$select=contactid,campaignid"
        f"&$filter=campaignid eq {campaign_id}&$top=100"
    ).get("value") or []
    contact_ids = [
        (row.get("contactid") or "").strip()
        for row in rows
        if (row.get("contactid") or "").strip()
    ]
    emails = _emails_for_contacts(crm, contact_ids)
    group = AccessGroup.query.filter_by(
        role=User.ROLE_EVENT_COORDINATOR,
        assigned_campaign_id=campaign_id,
    ).first()
    if not emails and group is None:
        return
    if group is None:
        group = AccessGroup(
            name=f"Event coordinators — {campaign_name or campaign_id}",
            role=User.ROLE_EVENT_COORDINATOR,
            assigned_campaign_id=campaign_id,
            assigned_campaign_name=campaign_name or campaign_id,
        )
        group.set_feature_permissions(
            {fid: fid in ('badges', 'registration', 'password_reset', 'seating') for fid in FEATURES}
        )
        db.session.add(group)
        db.session.flush()
    wanted_user_ids = set()
    for email in emails:
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user is None:
            user = User(
                username=_username_from_email(email),
                email=email,
                auth_provider='portal',
                is_active=True,
                role=User.ROLE_USER,
                is_admin=False,
            )
            db.session.add(user)
            db.session.flush()
        elif not user.is_active:
            user.is_active = True
        wanted_user_ids.add(user.id)
        already = AccessGroupMember.query.filter_by(
            user_id=user.id, group_id=group.id
        ).first()
        if already is None:
            current = [row.group_id for row in user.group_memberships]
            if group.id not in current:
                set_user_groups(user, current + [group.id], user.get_feature_permissions())
    for member in list(group.members or []):
        if member.user_id in wanted_user_ids or member.user is None:
            continue
        user = member.user
        db.session.delete(member)
        db.session.flush()
        db.session.expire(user, ['group_memberships'])
        if user.is_admin or any(
            row.group and row.group.role == User.ROLE_ADMIN
            for row in user.group_memberships
        ):
            continue
        sync_user_access(user, user.get_feature_permissions())


def _emails_for_contacts(crm, contact_ids) -> set:
    found = set()
    ids = list(dict.fromkeys(contact_ids))
    for start in range(0, len(ids), 20):
        chunk = ids[start:start + 20]
        filt = " or ".join(f"contactid eq {contact_id}" for contact_id in chunk)
        rows = crm._make_request(
            "contacts?$select=contactid,emailaddress1"
            f"&$filter={_quote_filter(filt)}&$top=20"
        ).get("value") or []
        for row in rows:
            email = (row.get("emailaddress1") or "").strip().lower()
            if email and "@" in email:
                found.add(email)
            else:
                logger.info(
                    "Event coordinator contact %s has no email and was not added",
                    row.get("contactid"),
                )
    return found


def _quote_filter(value: str) -> str:
    from urllib.parse import quote
    return quote(value, safe="")
