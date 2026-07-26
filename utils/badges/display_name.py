"""Display name formatting for {{DISPLAY_NAME}} badge placeholders."""

import re

DEFAULT_DISPLAY_NAME_CONFIG = {
    "include_title": False,
    "include_middle": True,
    "include_maiden": True,
    "parentheses_middle": False,
    "parentheses_maiden": True,
}


def normalize_display_name_config(config: dict | None) -> dict:
    """Return a complete config dict with boolean values and known defaults."""
    merged = dict(DEFAULT_DISPLAY_NAME_CONFIG)
    if not config:
        return merged
    for key in DEFAULT_DISPLAY_NAME_CONFIG:
        if key in config:
            merged[key] = bool(config[key])
    return merged


def format_display_name_part(value: str, use_parentheses: bool) -> str:
    if not value:
        return ""
    return f"({value})" if use_parentheses else value


def _name_tokens(text: str) -> list[str]:
    return [token for token in re.split(r"\s+", text.strip()) if token]


def _upper_text(text: str) -> str:
    return text.strip().upper()


def _upper_token(token: str) -> str:
    return token.rstrip(".").upper()


def _is_female(gender: str | None) -> bool:
    if not gender:
        return False
    return _upper_text(gender) in ("FEMALE", "F", "2")


def _name_fields_overlap(left: str, right: str) -> bool:
    """True when two name fields match or one contains the other (case-insensitive)."""
    left_u = _upper_text(left)
    right_u = _upper_text(right)
    if not left_u or not right_u:
        return False
    if left_u == right_u:
        return True
    return left_u in right_u or right_u in left_u


def _strip_maiden_from_first(first: str, maiden: str) -> str:
    """Remove maiden tokens embedded in first name (common for married women in CRM)."""
    if not first.strip() or not maiden.strip():
        return first
    kept = [
        token
        for token in _name_tokens(first)
        if not _name_fields_overlap(token, maiden)
        and not any(_name_fields_overlap(token, maiden_token) for maiden_token in _name_tokens(maiden))
    ]
    return " ".join(kept) if kept else first


def dedupe_display_name_parts(
    first: str,
    middle: str,
    maiden: str,
    last: str,
    *,
    gender: str | None = None,
) -> tuple[str, str, str, str]:
    """Drop name parts that repeat information already present elsewhere."""
    if first.strip() and last.strip() and _upper_text(first) == _upper_text(last):
        return first, middle, maiden, last

    is_female = _is_female(gender)

    if is_female and maiden:
        first = _strip_maiden_from_first(first, maiden)

    if maiden and last and _name_fields_overlap(maiden, last):
        maiden = ""

    if maiden and middle and _name_fields_overlap(maiden, middle):
        if is_female:
            middle = ""
        else:
            maiden = ""

    if middle and first:
        first_tokens = _name_tokens(first)
        middle_clean = middle.strip()
        middle_norm = _upper_token(middle_clean)
        last_first_token = _upper_token(first_tokens[-1]) if first_tokens else ""

        if middle_norm and _name_fields_overlap(middle_norm, last_first_token):
            middle = ""
        elif len(middle_norm) == 1 and len(first_tokens) > 1:
            if last_first_token.startswith(middle_norm):
                middle = ""
        else:
            middle_tokens = _name_tokens(middle_clean)
            if middle_tokens and all(
                any(
                    _name_fields_overlap(middle_token, first_token)
                    for first_token in first_tokens
                )
                for middle_token in middle_tokens
            ):
                middle = ""

    return first, middle, maiden, last


def _part_enabled(placeholder: str, field_visibility: dict | None) -> bool:
    if not field_visibility or placeholder not in field_visibility:
        return True
    return field_visibility[placeholder] is not False


def build_display_name(
    row: dict,
    column_mappings: dict,
    config: dict | None = None,
    *,
    value_getter,
    field_visibility: dict | None = None,
) -> str:
    """Build the full display name from row data and template formatting rules."""
    cfg = normalize_display_name_config(config)
    title = (
        value_getter("{{TITLE}}", "Title")
        if _part_enabled("{{TITLE}}", field_visibility)
        else ""
    )
    first = (
        value_getter("{{FIRST_NAME}}", "First Name")
        if _part_enabled("{{FIRST_NAME}}", field_visibility)
        else ""
    )
    middle = (
        value_getter("{{MIDDLE_NAME}}", "Middle Name")
        if _part_enabled("{{MIDDLE_NAME}}", field_visibility)
        else ""
    )
    maiden = (
        value_getter("{{MAIDEN_NAME}}", "Maiden Name")
        if _part_enabled("{{MAIDEN_NAME}}", field_visibility)
        else ""
    )
    last = (
        value_getter("{{LAST_NAME}}", "Last Name")
        if _part_enabled("{{LAST_NAME}}", field_visibility)
        else ""
    )
    gender = str(row.get("Gender", "") or "").strip()

    first, middle, maiden, last = dedupe_display_name_parts(
        first, middle, maiden, last, gender=gender
    )

    parts = []
    if cfg["include_title"] and title:
        parts.append(title)
    if first:
        parts.append(first)
    if cfg["include_middle"] and middle:
        parts.append(format_display_name_part(middle, cfg["parentheses_middle"]))
    if cfg["include_maiden"] and maiden:
        parts.append(format_display_name_part(maiden, cfg["parentheses_maiden"]))
    if last:
        parts.append(last)
    return " ".join(parts)
