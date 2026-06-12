"""Badge canvas sizes, Avery registry, and layout/SVG scaling."""

from __future__ import annotations

import copy
import re

CANVAS_DPI = 96
BASE_AVERY = "5392"
BASE_CANVAS = (384, 288)
BASE_RECOMMENDED_MARGIN = 20

# Landscape width × height (inches), matching built-in SVG orientation.
# Sheet margins/gaps follow Microsoft Word Avery US Letter specs (KB Q149153)
# unless noted. Coordinates: x grows right from left edge; y grows down from top.
AVERY_TEMPLATES = {
    "5361": {
        # MS Word: 2.0"×3.25", 1×3, top 0.833", side 4.208", vert pitch 3.666"
        # Cards print in the RIGHT column of the sheet (large left margin).
        "name": "Avery 5361 - Self-Laminating ID Cards",
        "width": 3.25,
        "height": 2.0,
        "cols": 1,
        "rows": 3,
        "margin_left": 4.208,
        "margin_top": 0.833,
        "gap_horizontal": 0.0,
        "gap_vertical": 1.666,  # 3.666" pitch − 2.0" label height
        "size_category": "small",
        "is_avery_standard": True,
        "dropdown": True,
        "dropdown_order": 10,
    },
    "5390": {
        # Avery 5390 / Word 5383: 2.25"×3.5", 2×4, top 1.167", side 0.75"
        "name": "Avery 5390 - Name Badge Insert Refills",
        "width": 3.5,
        "height": 2.25,
        "cols": 2,
        "rows": 4,
        "margin_left": 0.75,
        "margin_top": 1.167,
        "gap_horizontal": 0.0,
        "gap_vertical": 0.0,
        "size_category": "small",
        "is_avery_standard": True,
        "dropdown": True,
        "dropdown_order": 20,
    },
    "5395": {
        # MS Word 5395/5095: 2.333"×3.375", 2×4, top 0.583", side 0.688"
        # horiz pitch 3.75", vert pitch 2.5"
        "name": "Avery 5395 - Flexible Adhesive Name Badges",
        "width": 3.375,
        "height": 2.333,
        "cols": 2,
        "rows": 4,
        "margin_left": 0.688,
        "margin_top": 0.583,
        "gap_horizontal": 0.375,
        "gap_vertical": 0.167,
        "size_category": "medium",
        "is_avery_standard": True,
        "dropdown": True,
        "dropdown_order": 30,
    },
    "5392": {
        # MS Word 5384 (5392 template family): 3.0"×4.0", 2×3, top 1.125", side 0.25"
        "name": "Avery 5392 - Name Badge Insert Refills",
        "width": 4.0,
        "height": 3.0,
        "cols": 2,
        "rows": 3,
        "margin_left": 0.25,
        "margin_top": 1.125,
        "gap_horizontal": 0.0,
        "gap_vertical": 0.0,
        "size_category": "standard",
        "is_avery_standard": True,
        "dropdown": True,
        "dropdown_order": 40,
    },
    "5035": {
        "name": "Custom Large — 5\" × 3.5\" (not Avery standard)",
        "width": 5.0,
        "height": 3.5,
        "cols": 1,
        "rows": 2,
        "margin_left": 1.75,
        "margin_top": 2.0,
        "gap_horizontal": 0.0,
        "gap_vertical": 0.0,
        "size_category": "large",
        "is_avery_standard": False,
        "dropdown": True,
        "dropdown_order": 50,
    },
    "8522": {
        # Avery 8522: 4.25"×6.0", 1×2 (same layout family as Word 5389)
        "name": "Avery 8522 - Vertical Style Name Badge Inserts",
        "width": 6.0,
        "height": 4.25,
        "cols": 1,
        "rows": 2,
        "margin_left": 1.25,
        "margin_top": 1.25,
        "gap_horizontal": 0.0,
        "gap_vertical": 0.0,
        "size_category": "xlarge",
        "is_avery_standard": True,
        "dropdown": True,
        "dropdown_order": 60,
    },
    "74459": {
        # Same 3"×4" / 2×3 layout as 5392 (Avery template family)
        "name": "Avery 74459 - Hanging Name Badges",
        "width": 4.0,
        "height": 3.0,
        "cols": 2,
        "rows": 3,
        "margin_left": 0.25,
        "margin_top": 1.125,
        "gap_horizontal": 0.0,
        "gap_vertical": 0.0,
        "size_category": "standard",
        "is_avery_standard": True,
        "dropdown": True,
        "dropdown_order": 45,
    },
    "8395": {
        "name": "Avery 8395 - Name Badge Labels",
        "width": 3.375,
        "height": 2.333,
        "cols": 2,
        "rows": 4,
        "margin_left": 0.688,
        "margin_top": 0.583,
        "gap_horizontal": 0.375,
        "gap_vertical": 0.167,
        "size_category": "medium",
        "is_avery_standard": True,
        "dropdown": False,
    },
    "5384": {
        "name": "Avery 5384 - Clip Style Name Badges",
        "width": 4.0,
        "height": 3.0,
        "cols": 2,
        "rows": 3,
        "margin_left": 0.25,
        "margin_top": 1.125,
        "gap_horizontal": 0.0,
        "gap_vertical": 0.0,
        "size_category": "standard",
        "is_avery_standard": True,
        "dropdown": False,
    },
}

QR_PLACEHOLDER = "{{QR_CODE}}"
IMAGE_TAG_RE = re.compile(r"<image\b[^>]*/?>", re.IGNORECASE | re.DOTALL)

AVERY_ALIASES = {
    "8395": "5395",
    "5384": "5392",
    "35392": "5392",
}

_NUMERIC_ATTRS_IMAGE = ("x", "y", "width", "height")
_NUMERIC_ATTRS_TEXT = ("x", "y", "font-size")
_NUMERIC_DATA_ATTRS = ("data-max-width", "data-min-font-size")


def resolve_avery_code(code: str) -> str:
    """Return canonical Avery code (resolves aliases)."""
    if not code:
        return BASE_AVERY
    resolved = AVERY_ALIASES.get(code, code)
    if resolved not in AVERY_TEMPLATES:
        return BASE_AVERY
    return resolved


def get_template_spec(avery_code: str) -> dict:
    code = resolve_avery_code(avery_code)
    return AVERY_TEMPLATES[code]


def validate_avery_sheet_layout(
    spec: dict, page_w: float = 8.5, page_h: float = 11.0
) -> dict:
    """Verify a template fits on letter paper; return computed dimensions."""
    cols = spec["cols"]
    rows = spec["rows"]
    w = spec["width"]
    h = spec["height"]
    ml = spec["margin_left"]
    mt = spec["margin_top"]
    gh = spec.get("gap_horizontal", 0)
    gv = spec.get("gap_vertical", 0)
    content_w = ml + cols * w + (cols - 1) * gh
    content_h = mt + rows * h + (rows - 1) * gv
    right_margin = page_w - content_w
    bottom_margin = page_h - content_h
    return {
        "content_width": round(content_w, 4),
        "content_height": round(content_h, 4),
        "right_margin": round(right_margin, 4),
        "bottom_margin": round(bottom_margin, 4),
        "fits_width": content_w <= page_w + 0.01,
        "fits_height": content_h <= page_h + 0.01,
    }


def canvas_pixels(avery_code: str) -> tuple[int, int]:
    spec = get_template_spec(avery_code)
    return round(spec["width"] * CANVAS_DPI), round(spec["height"] * CANVAS_DPI)


def canvas_inches(avery_code: str) -> tuple[float, float]:
    spec = get_template_spec(avery_code)
    return float(spec["width"]), float(spec["height"])


def recommended_margins(avery_code: str) -> dict:
    """Recommended edge margins in canvas pixels for the given Avery code."""
    w, h = canvas_pixels(avery_code)
    base_w, base_h = BASE_CANVAS
    return {
        "top": round(BASE_RECOMMENDED_MARGIN * h / base_h),
        "right": round(BASE_RECOMMENDED_MARGIN * w / base_w),
        "bottom": round(BASE_RECOMMENDED_MARGIN * h / base_h),
        "left": round(BASE_RECOMMENDED_MARGIN * w / base_w),
    }


def margin_input_max(avery_code: str) -> int:
    w, h = canvas_pixels(avery_code)
    return max(20, round(min(w, h) * 0.25))


def _parse_image_tag_attrs(tag: str) -> dict:
    def _attr(name, default=None):
        m = re.search(rf'\b{name}\s*=\s*"([\d.]+)"', tag, re.IGNORECASE)
        if not m:
            return default
        try:
            return float(m.group(1))
        except ValueError:
            return default

    return {
        "x": _attr("x", 0.0),
        "y": _attr("y", 0.0),
        "width": _attr("width"),
        "height": _attr("height"),
    }


def _is_qr_image_tag(tag: str) -> bool:
    if QR_PLACEHOLDER in tag:
        return True
    href = re.search(r'(?:href|xlink:href)\s*=\s*"([^"]+)"', tag, re.IGNORECASE)
    return bool(href and re.search(r"qr_.*\.png", href.group(1), re.IGNORECASE))


def _set_image_tag_attr(tag: str, attr: str, value) -> str:
    if re.search(rf"\b{attr}\s*=", tag, re.IGNORECASE):
        return re.sub(
            rf'(\b{attr}\s*=\s*")[^"]*(")',
            rf"\g<1>{value}\g<2>",
            tag,
            count=1,
            flags=re.IGNORECASE,
        )
    return tag.replace("<image", f'<image {attr}="{value}"', 1)


def _square_image_tag(tag: str) -> str:
    """Force an image slot to a square (svglib stretches rasters to width/height)."""
    attrs = _parse_image_tag_attrs(tag)
    w, h = attrs.get("width"), attrs.get("height")
    if not w or not h or abs(w - h) < 0.05:
        return tag
    size = min(w, h)
    x = attrs["x"] + (w - size) / 2
    y = attrs["y"] + (h - size) / 2
    tag = _set_image_tag_attr(tag, "x", round(x, 2))
    tag = _set_image_tag_attr(tag, "y", round(y, 2))
    tag = _set_image_tag_attr(tag, "width", round(size, 2))
    tag = _set_image_tag_attr(tag, "height", round(size, 2))
    return tag


def ensure_square_qr_image_tags(svg_content: str) -> str:
    """Keep QR code slots square so svglib does not stretch them."""
    def repl(m):
        tag = m.group(0)
        if _is_qr_image_tag(tag):
            return _square_image_tag(tag)
        return tag

    return IMAGE_TAG_RE.sub(repl, svg_content)


def _scale_num(value, factor: float) -> float:
    if isinstance(value, (int, float)):
        return round(float(value) * factor, 1)
    return value


def scale_element_layout(
    layout: dict | None,
    from_wh: tuple[float, float],
    to_wh: tuple[float, float],
) -> dict:
    """Scale element_layout dict from one canvas size to another."""
    if not layout:
        return {}
    from_w, from_h = from_wh
    to_w, to_h = to_wh
    if from_w <= 0 or from_h <= 0:
        return copy.deepcopy(layout)
    sx = to_w / from_w
    sy = to_h / from_h
    if sx == 1.0 and sy == 1.0:
        return copy.deepcopy(layout)

    out = copy.deepcopy(layout)
    margins = out.get("margins")
    if isinstance(margins, dict):
        out["margins"] = {
            "top": _scale_num(margins.get("top", BASE_RECOMMENDED_MARGIN), sy),
            "right": _scale_num(margins.get("right", BASE_RECOMMENDED_MARGIN), sx),
            "bottom": _scale_num(margins.get("bottom", BASE_RECOMMENDED_MARGIN), sy),
            "left": _scale_num(margins.get("left", BASE_RECOMMENDED_MARGIN), sx),
        }

    for key, spec in list(out.items()):
        if key == "margins" or not isinstance(spec, dict):
            continue
        if key == "subevents":
            if "x" in spec:
                spec["x"] = _scale_num(spec["x"], sx)
            if "baseY" in spec:
                spec["baseY"] = _scale_num(spec["baseY"], sy)
            if "lineHeight" in spec:
                spec["lineHeight"] = _scale_num(spec["lineHeight"], sy)
            continue
        if "x" in spec:
            spec["x"] = _scale_num(spec["x"], sx)
        if "y" in spec:
            spec["y"] = _scale_num(spec["y"], sy)
        if "width" in spec:
            spec["width"] = _scale_num(spec["width"], sx)
        if "height" in spec:
            spec["height"] = _scale_num(spec["height"], sy)
        companions = spec.get("companions")
        if isinstance(companions, dict):
            for rel in companions.values():
                if "dx" in rel:
                    rel["dx"] = _scale_num(rel["dx"], sx)
                if "dy" in rel:
                    rel["dy"] = _scale_num(rel["dy"], sy)
    _square_qr_in_layout(out)
    return out


def _layout_canvas(layout: dict) -> tuple[float, float] | None:
    meta = layout.get("_canvas")
    if isinstance(meta, dict) and "width" in meta and "height" in meta:
        return float(meta["width"]), float(meta["height"])
    return None


def _infer_layout_canvas(
    layout: dict, target_wh: tuple[float, float]
) -> tuple[float, float]:
    stored = _layout_canvas(layout)
    if stored:
        return stored
    qr = layout.get("{{QR_CODE}}") or {}
    qw = qr.get("width")
    if isinstance(qw, (int, float)) and qw >= 55:
        return BASE_CANVAS
    return target_wh


def _square_qr_in_layout(layout: dict) -> None:
    qr = layout.get("{{QR_CODE}}")
    if not isinstance(qr, dict):
        return
    w = qr.get("width")
    h = qr.get("height")
    if not isinstance(w, (int, float)) or not isinstance(h, (int, float)):
        return
    if abs(w - h) < 0.05:
        return
    size = min(w, h)
    x = float(qr.get("x", 0)) + (w - size) / 2
    y = float(qr.get("y", 0)) + (h - size) / 2
    qr["x"] = round(x, 1)
    qr["y"] = round(y, 1)
    qr["width"] = round(size, 1)
    qr["height"] = round(size, 1)


def resolve_element_layout_for_canvas(
    layout: dict | None, target_wh: tuple[float, float]
) -> dict:
    """Scale saved element_layout to match the Avery canvas used for PDF/preview."""
    if not layout:
        return {}
    from_wh = _infer_layout_canvas(layout, target_wh)
    if from_wh != target_wh:
        out = scale_element_layout(layout, from_wh, target_wh)
    else:
        out = copy.deepcopy(layout)
    _square_qr_in_layout(out)
    return out


def _scale_attr_value(attr: str, value: str, sx: float, sy: float) -> str:
    try:
        num = float(value)
    except ValueError:
        return value
    if attr in ("x", "width", "data-max-width"):
        return str(round(num * sx, 2)).rstrip("0").rstrip(".")
    if attr in ("y", "height", "font-size", "data-min-font-size"):
        return str(round(num * sy, 2)).rstrip("0").rstrip(".")
    return value


def _replace_numeric_attr(tag: str, attr: str, sx: float, sy: float) -> str:
    pattern = re.compile(
        rf'(\b{re.escape(attr)}\s*=\s*")([\d.]+)(")',
        re.IGNORECASE,
    )

    def repl(m):
        scaled = _scale_attr_value(attr, m.group(2), sx, sy)
        return f'{m.group(1)}{scaled}{m.group(3)}'

    return pattern.sub(repl, tag)


def scale_svg_content(
    svg_content: str,
    from_wh: tuple[float, float],
    to_wh: tuple[float, float],
) -> str:
    """Scale SVG viewBox and element coordinates/fonts to a new canvas size."""
    from_w, from_h = from_wh
    to_w, to_h = to_wh
    if from_w <= 0 or from_h <= 0 or (from_w == to_w and from_h == to_h):
        return svg_content

    sx = to_w / from_w
    sy = to_h / from_h
    result = svg_content

    def _scale_viewbox(m):
        parts = m.group(1).replace(",", " ").split()
        if len(parts) >= 4:
            ow, oh = float(parts[2]), float(parts[3])
            parts[2] = str(round(ow * sx, 2)).rstrip("0").rstrip(".")
            parts[3] = str(round(oh * sy, 2)).rstrip("0").rstrip(".")
        return f'viewBox="{" ".join(parts)}"'

    result = re.sub(
        r'viewBox\s*=\s*"([^"]+)"',
        _scale_viewbox,
        result,
        count=1,
        flags=re.IGNORECASE,
    )

    def _scale_wh_attr(attr: str, text: str) -> str:
        def repl(m):
            num = float(m.group(1))
            factor = sx if attr == "width" else sy
            val = round(num * factor, 2)
            s = str(val).rstrip("0").rstrip(".")
            return f'{attr}="{s}"'
        return re.sub(
            rf'\b{attr}\s*=\s*"([\d.]+)"',
            repl,
            text,
            count=1,
            flags=re.IGNORECASE,
        )

    result = _scale_wh_attr("width", result)
    result = _scale_wh_attr("height", result)

    tag_pattern = re.compile(r"<(image|text)\b[^>]*/?>", re.IGNORECASE | re.DOTALL)
    full_tag_pattern = re.compile(r"<(image|text)\b[^>]*/?>", re.IGNORECASE | re.DOTALL)

    def scale_tag(m):
        tag = m.group(0)
        elem = m.group(1).lower()
        attrs = _NUMERIC_ATTRS_IMAGE if elem == "image" else _NUMERIC_ATTRS_TEXT
        for attr in attrs:
            tag = _replace_numeric_attr(tag, attr, sx, sy)
        if elem == "text":
            for attr in _NUMERIC_DATA_ATTRS:
                tag = _replace_numeric_attr(tag, attr, sx, sy)
        if elem == "image" and _is_qr_image_tag(tag):
            tag = _square_image_tag(tag)
        return tag

    result = full_tag_pattern.sub(scale_tag, result)
    return ensure_square_qr_image_tags(result)


def prepare_svg_for_avery(svg_content: str, avery_code: str) -> str:
    """Scale base SVG from canonical 5392 canvas to target Avery canvas."""
    target = canvas_pixels(avery_code)
    if target == BASE_CANVAS:
        return svg_content
    return scale_svg_content(svg_content, BASE_CANVAS, target)


def list_dropdown_templates() -> list[dict]:
    """Templates shown in the badge size dropdown, sorted small → large."""
    items = []
    for code, spec in AVERY_TEMPLATES.items():
        if not spec.get("dropdown", False):
            continue
        w, h = canvas_pixels(code)
        items.append(
            {
                "code": code,
                "name": spec["name"],
                "size": f'{spec["width"]}\" x {spec["height"]}\"',
                "layout": f'{spec["cols"]} x {spec["rows"]}',
                "canvas_width": w,
                "canvas_height": h,
                "size_category": spec.get("size_category", "standard"),
                "is_avery_standard": spec.get("is_avery_standard", True),
                "dropdown_order": spec.get("dropdown_order", 100),
            }
        )
    items.sort(key=lambda t: (t["canvas_width"] * t["canvas_height"], t["dropdown_order"]))
    return items
