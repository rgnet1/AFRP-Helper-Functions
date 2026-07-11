"""Badge template element positioning (corner logos, QR, sub-event blocks)."""

import re

from utils.badges.badge_sizes import ensure_square_qr_image_tags

BADGE_WIDTH = 384
BADGE_HEIGHT = 288
LAYOUT_MARGIN = 20  # legacy single-margin default
RECOMMENDED_MARGINS = {"top": 20, "right": 20, "bottom": 20, "left": 20}
RECOMMENDED_CORNER_MARGINS = {
    "top_left": {"horizontal": 20, "vertical": 20},
    "top_right": {"horizontal": 20, "vertical": 20},
    "bottom_left": {"horizontal": 20, "vertical": 20},
    "bottom_right": {"horizontal": 20, "vertical": 20},
}
CORNER_MARGIN_KEYS = ("top_left", "top_right", "bottom_left", "bottom_right")
PRESET_TO_CORNER = {
    "top-left": "top_left",
    "top-right": "top_right",
    "bottom-left": "bottom_left",
    "bottom-right": "bottom_right",
}
SUBEVENT_LINE_HEIGHT = 15
SUBEVENT_PLACEHOLDERS = [f"{{{{SUBEVENT_{i}}}}}" for i in range(1, 5)]

IMAGE_LAYOUT_KEYS = ("{{CLUB_LOGO}}", "{{AFRP_LOGO}}", "{{QR_CODE}}")
QR_COMPANION_PLACEHOLDERS = ("{{MEMBER_ID}}", "{{MEAL_PREFERENCE}}")
DEFAULT_IMAGE_PRESETS = {
    "{{CLUB_LOGO}}": "top-left",
    "{{AFRP_LOGO}}": "top-right",
    "{{QR_CODE}}": "bottom-right",
}

PRESET_ZONES = (
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "bottom-center",
    "custom",
)


def _parse_svg_size(svg_content: str) -> tuple[float, float]:
    viewbox = re.search(r'viewBox\s*=\s*"([^"]+)"', svg_content, re.IGNORECASE)
    if viewbox:
        parts = viewbox.group(1).replace(",", " ").split()
        if len(parts) >= 4:
            return float(parts[2]), float(parts[3])
    w = re.search(r'\bwidth\s*=\s*"([\d.]+)', svg_content, re.IGNORECASE)
    h = re.search(r'\bheight\s*=\s*"([\d.]+)', svg_content, re.IGNORECASE)
    if w and h:
        return float(w.group(1)), float(h.group(1))
    return float(BADGE_WIDTH), float(BADGE_HEIGHT)


def margins_from_layout(layout: dict | None) -> dict:
    """Return normalized top/right/bottom/left margins derived from corner settings."""
    corners = corner_margins_from_layout(layout)
    return {
        "top": corners["top_left"]["vertical"],
        "right": corners["top_right"]["horizontal"],
        "bottom": corners["bottom_left"]["vertical"],
        "left": corners["top_left"]["horizontal"],
    }


def _merge_corner_margins(saved: dict | None) -> dict:
    merged = {
        key: dict(RECOMMENDED_CORNER_MARGINS[key]) for key in CORNER_MARGIN_KEYS
    }
    if not saved:
        return merged
    for key in CORNER_MARGIN_KEYS:
        corner = saved.get(key) or {}
        if isinstance(corner, dict):
            merged[key] = {
                **merged[key],
                **{
                    k: corner[k]
                    for k in ("horizontal", "vertical")
                    if k in corner
                },
            }
    return merged


def _margins_dict_to_corners(margins: dict) -> dict:
    m = {**RECOMMENDED_MARGINS, **(margins or {})}
    return {
        "top_left": {"horizontal": m["left"], "vertical": m["top"]},
        "top_right": {"horizontal": m["right"], "vertical": m["top"]},
        "bottom_left": {"horizontal": m["left"], "vertical": m["bottom"]},
        "bottom_right": {"horizontal": m["right"], "vertical": m["bottom"]},
    }


def corner_margins_from_layout(layout: dict | None) -> dict:
    """Return per-corner horizontal/vertical insets from a layout dict."""
    if not layout:
        return _merge_corner_margins(None)
    if layout.get("corner_margins"):
        return _merge_corner_margins(layout["corner_margins"])
    if layout.get("margins"):
        return _margins_dict_to_corners(layout["margins"])
    return _merge_corner_margins(None)


def _corner_for_preset(preset: str) -> str | None:
    return PRESET_TO_CORNER.get(preset)


def _bottom_vertical_inset(corner_margins: dict) -> float:
    bl = corner_margins["bottom_left"]["vertical"]
    br = corner_margins["bottom_right"]["vertical"]
    return (bl + br) / 2.0


def preset_position(
    preset: str,
    elem_w: float,
    elem_h: float,
    badge_w: float = BADGE_WIDTH,
    badge_h: float = BADGE_HEIGHT,
    corner_margins: dict | None = None,
    margins: dict | None = None,
) -> tuple[float, float]:
    if margins is not None and corner_margins is None:
        corner_margins = _margins_dict_to_corners(margins)
    c = corner_margins or RECOMMENDED_CORNER_MARGINS
    if preset == "top-left":
        corner = c["top_left"]
        return corner["horizontal"], corner["vertical"]
    if preset == "top-right":
        corner = c["top_right"]
        return badge_w - elem_w - corner["horizontal"], corner["vertical"]
    if preset == "bottom-left":
        corner = c["bottom_left"]
        return corner["horizontal"], badge_h - elem_h - corner["vertical"]
    if preset == "bottom-right":
        corner = c["bottom_right"]
        return badge_w - elem_w - corner["horizontal"], badge_h - elem_h - corner["vertical"]
    if preset == "bottom-center":
        return (badge_w - elem_w) / 2, badge_h - elem_h - _bottom_vertical_inset(c)
    raise ValueError(f"Unknown preset: {preset}")


def _subevent_anchor(
    preset: str, badge_w: float, corner_margins: dict
) -> tuple[float, str]:
    if preset == "top-left":
        return corner_margins["top_left"]["horizontal"], "start"
    if preset == "top-right":
        return badge_w - corner_margins["top_right"]["horizontal"], "end"
    if preset == "bottom-left":
        return corner_margins["bottom_left"]["horizontal"], "start"
    if preset == "bottom-right":
        return badge_w - corner_margins["bottom_right"]["horizontal"], "end"
    if preset == "bottom-center":
        return badge_w / 2, "middle"
    return corner_margins["top_left"]["horizontal"], "start"


def _subevent_base_y(
    preset: str,
    count: int,
    badge_h: float,
    line_height: float,
    corner_margins: dict,
) -> float:
    if preset == "top-left":
        return corner_margins["top_left"]["vertical"] + line_height
    if preset == "top-right":
        return corner_margins["top_right"]["vertical"] + line_height
    if preset == "bottom-left":
        return (
            badge_h
            - corner_margins["bottom_left"]["vertical"]
            - max(count, 1) * line_height
            + 4
        )
    if preset == "bottom-right":
        return (
            badge_h
            - corner_margins["bottom_right"]["vertical"]
            - max(count, 1) * line_height
            + 4
        )
    if preset == "bottom-center":
        return badge_h - _bottom_vertical_inset(corner_margins) - max(count, 1) * line_height + 4
    if preset.startswith("bottom"):
        return (
            badge_h
            - corner_margins["bottom_left"]["vertical"]
            - max(count, 1) * line_height
            + 4
        )
    if preset.startswith("top"):
        return corner_margins["top_left"]["vertical"] + line_height
    return (
        badge_h
        - corner_margins["bottom_left"]["vertical"]
        - max(count, 1) * line_height
        + 4
    )


def _set_tag_attr(tag: str, attr: str, value) -> str:
    if re.search(rf"\b{attr}\s*=", tag, re.IGNORECASE):
        return re.sub(
            rf"(\b{attr}\s*=\s*\")([^\"]*)(\")",
            rf"\g<1>{value}\g<3>",
            tag,
            count=1,
            flags=re.IGNORECASE,
        )
    return tag.replace("<image", f'<image {attr}="{value}"', 1).replace(
        "<text", f'<text {attr}="{value}"', 1
    )


def _find_image_tag(svg_content: str, placeholder: str) -> str | None:
    pattern = re.compile(
        rf"<image\b[^>]*\bhref\s*=\s*[\"']{re.escape(placeholder)}[\"'][^>]*/?>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(svg_content)
    return match.group(0) if match else None


def _parse_image_spec(tag: str) -> dict:
    def _attr(name, default=0.0):
        m = re.search(rf'\b{name}\s*=\s*"([\d.]+)"', tag, re.IGNORECASE)
        return float(m.group(1)) if m else default

    return {
        "x": _attr("x"),
        "y": _attr("y"),
        "width": _attr("width", 60),
        "height": _attr("height", 60),
        "preset": "custom",
    }


def _default_image_preset(placeholder: str) -> str:
    return DEFAULT_IMAGE_PRESETS.get(placeholder, "custom")


def _find_text_tag(svg_content: str, placeholder: str) -> str | None:
    pattern = re.compile(
        rf"(<text\b[^>]*>)\s*{re.escape(placeholder)}\s*(</text>)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(svg_content)
    return match.group(0) if match else None


def _parse_text_xy(tag: str) -> tuple[float, float, str]:
    x = re.search(r'\bx\s*=\s*"([\d.]+)"', tag, re.IGNORECASE)
    y = re.search(r'\by\s*=\s*"([\d.]+)"', tag, re.IGNORECASE)
    anchor = re.search(r'text-anchor\s*=\s*"([^"]+)"', tag, re.IGNORECASE)
    return (
        float(x.group(1)) if x else 0.0,
        float(y.group(1)) if y else 0.0,
        anchor.group(1) if anchor else "start",
    )


def _extract_qr_companions(svg_content: str, qr_spec: dict) -> dict:
    """Vertical offsets for text labels that stay centered above/below the QR image."""
    companions = {}
    qr_x = float(qr_spec.get("x", 0))
    qr_y = float(qr_spec.get("y", 0))
    qr_h = float(qr_spec.get("height", 60))
    qr_bottom = qr_y + qr_h

    for ph in QR_COMPANION_PLACEHOLDERS:
        tag = _find_text_tag(svg_content, ph)
        if not tag:
            continue
        _tx, ty, _text_anchor = _parse_text_xy(tag)
        if ph == "{{MEMBER_ID}}":
            gap = max(qr_y - ty, 5.0)
            companions[ph] = {"position": "above", "gap": round(gap, 1)}
        else:
            gap = max(ty - qr_bottom, 6.0)
            companions[ph] = {"position": "below", "gap": round(gap, 1)}
    return companions


def _companion_xy(
    ph: str,
    rel: dict,
    qr_x: float,
    qr_y: float,
    qr_width: float,
    qr_height: float,
) -> tuple[float, float]:
    """Place companion text centered on the QR box (legacy dx/dy layouts included)."""
    center_x = qr_x + qr_width / 2
    qr_bottom = qr_y + qr_height

    if rel.get("position") == "above":
        return center_x, qr_y - float(rel.get("gap", 5))
    if rel.get("position") == "below":
        return center_x, qr_bottom + float(rel.get("gap", 6))

    # Legacy layouts stored dx/dy from the QR top-left; ignore stale absolute dy
    # and hug the QR edges with standard gaps (fixes saved templates after resize).
    if ph == "{{MEMBER_ID}}":
        return center_x, qr_y - 5.0
    return center_x, qr_bottom + 10.0


def _apply_qr_companions(
    svg_content: str,
    qr_x: float,
    qr_y: float,
    companions: dict,
    qr_width: float = 60,
    qr_height: float = 60,
) -> str:
    if not companions:
        return svg_content
    result = svg_content
    for ph, rel in companions.items():
        tag = _find_text_tag(result, ph)
        if not tag:
            continue
        x, y = _companion_xy(ph, rel, qr_x, qr_y, qr_width, qr_height)
        updated = tag
        updated = _set_tag_attr(updated, "x", x)
        updated = _set_tag_attr(updated, "y", y)
        if re.search(r"text-anchor\s*=", updated, re.IGNORECASE):
            updated = re.sub(
                r'(text-anchor\s*=\s*")[^"]*(")',
                r'\g<1>middle\g<2>',
                updated,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            updated = updated.replace("<text", '<text text-anchor="middle"', 1)
        result = result.replace(tag, updated, 1)
    return result


def _find_subevent_tags(svg_content: str) -> list[tuple[str, str]]:
    found = []
    for ph in SUBEVENT_PLACEHOLDERS:
        pattern = re.compile(
            rf"(<text\b[^>]*>)\s*{re.escape(ph)}\s*(</text>)",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(svg_content)
        if match:
            found.append((ph, match.group(0)))
    return found


def extract_layout_from_svg(svg_content: str) -> dict:
    """Read default element positions from an SVG template."""
    badge_w, badge_h = _parse_svg_size(svg_content)
    corner_margins = corner_margins_from_layout(None)
    layout = {"corner_margins": corner_margins}

    for key in IMAGE_LAYOUT_KEYS:
        tag = _find_image_tag(svg_content, key)
        if tag:
            spec = _parse_image_spec(tag)
            spec["preset"] = _default_image_preset(key)
            if key == "{{QR_CODE}}":
                spec["companions"] = _extract_qr_companions(svg_content, spec)
            layout[key] = spec

    sub_tags = _find_subevent_tags(svg_content)
    if sub_tags:
        first_tag = sub_tags[0][1]
        x = re.search(r'\bx\s*=\s*"([\d.]+)"', first_tag, re.IGNORECASE)
        y = re.search(r'\by\s*=\s*"([\d.]+)"', first_tag, re.IGNORECASE)
        anchor = re.search(r'text-anchor\s*=\s*"([^"]+)"', first_tag, re.IGNORECASE)
        ys = []
        for _, tag in sub_tags:
            ym = re.search(r'\by\s*=\s*"([\d.]+)"', tag, re.IGNORECASE)
            if ym:
                ys.append(float(ym.group(1)))
        line_height = SUBEVENT_LINE_HEIGHT
        if len(ys) >= 2:
            line_height = ys[1] - ys[0]
        layout["subevents"] = {
            "preset": "custom",
            "x": float(x.group(1)) if x else corner_margins["bottom_left"]["horizontal"],
            "baseY": float(y.group(1)) if y else _subevent_base_y(
                "bottom-left", len(sub_tags), badge_h, line_height, corner_margins
            ),
            "lineHeight": line_height,
            "textAnchor": anchor.group(1) if anchor else "start",
        }

    return layout


def _apply_image_layout(
    svg_content: str, placeholder: str, spec: dict, corner_margins: dict
) -> str:
    tag = _find_image_tag(svg_content, placeholder)
    if not tag:
        return svg_content

    width = float(spec.get("width", 60))
    height = float(spec.get("height", 60))
    preset = spec.get("preset", "custom")
    badge_w, badge_h = _parse_svg_size(svg_content)
    if preset and preset != "custom":
        x, y = preset_position(
            preset, width, height, badge_w, badge_h, corner_margins=corner_margins
        )
    else:
        x = float(spec.get("x", corner_margins["top_left"]["horizontal"]))
        y = float(spec.get("y", corner_margins["top_left"]["vertical"]))

    if placeholder == "{{QR_CODE}}" and abs(width - height) > 0.05:
        size = min(width, height)
        x += (width - size) / 2
        y += (height - size) / 2
        width = height = size

    updated = tag
    updated = _set_tag_attr(updated, "x", x)
    updated = _set_tag_attr(updated, "y", y)
    updated = _set_tag_attr(updated, "width", width)
    updated = _set_tag_attr(updated, "height", height)
    result = svg_content.replace(tag, updated, 1)
    if placeholder == "{{QR_CODE}}" and spec.get("companions"):
        result = _apply_qr_companions(result, x, y, spec["companions"], width, height)
    return result


def _apply_subevent_layout(
    svg_content: str, spec: dict, badge_w: float, badge_h: float, corner_margins: dict
) -> str:
    sub_tags = _find_subevent_tags(svg_content)
    if not sub_tags:
        return svg_content

    line_height = float(spec.get("lineHeight", SUBEVENT_LINE_HEIGHT))
    preset = spec.get("preset", "custom")
    count = len(sub_tags)

    if preset and preset != "custom":
        x, text_anchor = _subevent_anchor(preset, badge_w, corner_margins)
        base_y = _subevent_base_y(preset, count, badge_h, line_height, corner_margins)
    else:
        x = float(spec.get("x", corner_margins["bottom_left"]["horizontal"]))
        base_y = float(
            spec.get(
                "baseY",
                _subevent_base_y(
                    "bottom-left", count, badge_h, line_height, corner_margins
                ),
            )
        )
        text_anchor = spec.get("textAnchor", "start")

    result = svg_content
    for index, (ph, tag) in enumerate(sub_tags):
        y = base_y + index * line_height
        updated = tag
        updated = _set_tag_attr(updated, "x", x)
        updated = _set_tag_attr(updated, "y", y)
        if re.search(r"text-anchor\s*=", updated, re.IGNORECASE):
            updated = re.sub(
                r'(text-anchor\s*=\s*")[^"]*(")',
                rf"\g<1>{text_anchor}\g<2>",
                updated,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            updated = updated.replace("<text", f'<text text-anchor="{text_anchor}"', 1)
        result = result.replace(tag, updated, 1)
    return result


def apply_element_layout(svg_content: str, layout: dict | None) -> str:
    """Apply saved corner / sub-event positions to SVG template text."""
    if not layout:
        return svg_content

    # AFRP logo is a fixed system asset — always honor top/right margins.
    afrp_spec = layout.get("{{AFRP_LOGO}}")
    if afrp_spec:
        afrp_spec["preset"] = "top-right"

    badge_w, badge_h = _parse_svg_size(svg_content)
    corner_margins = corner_margins_from_layout(layout)
    result = svg_content
    for key, spec in layout.items():
        if key in ("margins", "corner_margins") or not spec:
            continue
        if key == "subevents":
            result = _apply_subevent_layout(result, spec, badge_w, badge_h, corner_margins)
        elif key in IMAGE_LAYOUT_KEYS:
            result = _apply_image_layout(result, key, spec, corner_margins)
    return ensure_square_qr_image_tags(result)
