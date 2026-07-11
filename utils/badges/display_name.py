"""Display name formatting for {{DISPLAY_NAME}} badge placeholders."""

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
