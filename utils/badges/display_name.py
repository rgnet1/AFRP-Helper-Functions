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


def build_display_name(
    row: dict,
    column_mappings: dict,
    config: dict | None = None,
    *,
    value_getter,
) -> str:
    """Build the full display name from row data and template formatting rules."""
    cfg = normalize_display_name_config(config)
    title = value_getter("{{TITLE}}", "Title")
    first = value_getter("{{FIRST_NAME}}", "First Name")
    middle = value_getter("{{MIDDLE_NAME}}", "Middle Name")
    maiden = value_getter("{{MAIDEN_NAME}}", "Maiden Name")
    last = value_getter("{{LAST_NAME}}", "Last Name")

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
