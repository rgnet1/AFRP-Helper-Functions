"""Shared access groups. Members inherit the group's role and campaign."""

from utils.auth.permissions import FEATURES
from utils.magazine.scheduler import AccessGroup, AccessGroupMember, User, db


def sync_user_access(user, personal_permissions=None):
    """Copy group access onto the user row used by existing admin checks.

    Users with no groups keep the feature checkboxes passed in, and are not admins.
    """
    groups = user.access_groups()
    if any(group.role == User.ROLE_ADMIN for group in groups):
        user.apply_role(User.ROLE_ADMIN)
        return
    coordinators = [
        group for group in groups
        if group.role == User.ROLE_EVENT_COORDINATOR and group.assigned_campaign_id
    ]
    if coordinators:
        first = coordinators[0]
        user.apply_role(
            User.ROLE_EVENT_COORDINATOR,
            first.assigned_campaign_id,
            first.assigned_campaign_name,
        )
        return
    if groups:
        merged = {fid: False for fid in FEATURES}
        for group in groups:
            for feature_id, allowed in group.get_feature_permissions().items():
                merged[feature_id] = merged[feature_id] or bool(allowed)
        user.apply_role(User.ROLE_USER)
        user.set_feature_permissions(merged)
        return
    user.apply_role(User.ROLE_USER)
    user.set_feature_permissions(personal_permissions or {fid: False for fid in FEATURES})


def set_user_groups(user, group_ids, personal_permissions=None):
    """Replace this user's memberships, then refresh stored access."""
    wanted = {int(group_id) for group_id in group_ids}
    current = {row.group_id: row for row in list(user.group_memberships or [])}
    for group_id, row in current.items():
        if group_id not in wanted:
            db.session.delete(row)
    existing = set(current)
    if wanted:
        found = {
            group.id: group
            for group in AccessGroup.query.filter(AccessGroup.id.in_(wanted)).all()
        }
        missing = wanted - set(found)
        if missing:
            raise ValueError("Unknown access group")
        for group_id in wanted - existing:
            db.session.add(AccessGroupMember(user_id=user.id, group_id=group_id))
    db.session.flush()
    db.session.expire(user, ['group_memberships'])
    sync_user_access(user, personal_permissions)


def count_other_admins(exclude_user_id=None):
    """Active admins who would remain if exclude_user_id lost admin."""
    query = User.query.filter_by(is_admin=True, is_active=True)
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.count()
