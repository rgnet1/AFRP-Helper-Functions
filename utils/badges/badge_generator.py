"""
Badge Generator Module
Generates print-ready PDF badges from Excel data using SVG templates.
"""

import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
import pandas as pd
import os
import json
import re
import shutil
from io import BytesIO
from PIL import Image
import base64
import logging
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
import copy
import pickle
from concurrent.futures import ProcessPoolExecutor, as_completed

from utils.badges.background_templates import resolve_background_path
from utils.badges.element_layout import apply_element_layout
from utils.badges.badge_sizes import (
    AVERY_TEMPLATES,
    prepare_svg_for_avery,
    resolve_avery_code,
    list_dropdown_templates,
    ensure_square_qr_image_tags,
    resolve_element_layout_for_canvas,
    canvas_pixels,
    canvas_pixels_print,
)
from utils.badges.display_name import build_display_name, normalize_display_name_config
from utils.badges.meal_options import (
    apply_meal_preference_mapping,
    build_meal_preference_value,
)

logger = logging.getLogger(__name__)

# Placeholders like {{FIRST_NAME}} — must match after logo substitution (paths are not matched).
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_0-9]+\}\}")
# Match <text> with optional XML namespace prefix (ElementTree emits ns0:text
# for the split dynamic layer).
TEXT_TAG_RE = re.compile(
    r"<(?:\w+:)?text\b([^>]*)>([^<]*)</(?:\w+:)?text>", re.IGNORECASE
)
VIEWBOX_RE = re.compile(r'viewBox\s*=\s*"([^"]*)"', re.IGNORECASE)
SVG_WIDTH_RE = re.compile(r'\bwidth\s*=\s*"([\d.]+)', re.IGNORECASE)
DEFAULT_MIN_SHRINK_FONT_SIZE = 10.0

CLUB_LOGO_PLACEHOLDER = "{{CLUB_LOGO}}"
AFRP_LOGO_PLACEHOLDER = "{{AFRP_LOGO}}"
QR_CODE_PLACEHOLDER = "{{QR_CODE}}"
DISPLAY_NAME_PLACEHOLDER = "{{DISPLAY_NAME}}"
FIELD_VISIBILITY_KEY = "_field_visibility"
MAX_STAGED_LOGO_EDGE = 512
IMAGE_TAG_RE = re.compile(r"<image\b[^>]*/?>", re.IGNORECASE | re.DOTALL)


def probe_image_dimensions(image_path):
    """Return (width, height) for a raster or SVG image file, or None if unknown."""
    if not image_path or not os.path.exists(image_path):
        return None, None

    ext = os.path.splitext(image_path)[1].lower()
    if ext == ".svg":
        try:
            root = ET.parse(image_path).getroot()
            view_box = root.get("viewBox")
            if view_box:
                parts = view_box.replace(",", " ").split()
                if len(parts) == 4:
                    return float(parts[2]), float(parts[3])
            w = _parse_svg_length(root.get("width"))
            h = _parse_svg_length(root.get("height"))
            if w and h:
                return w, h
        except Exception as e:
            logger.warning("Could not parse SVG dimensions for %s: %s", image_path, e)
        return None, None

    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logger.warning("Could not probe image dimensions for %s: %s", image_path, e)
        return None, None


def _parse_svg_length(value):
    """Parse an SVG length attribute (e.g. '384', '384px') to a float."""
    if not value:
        return None
    match = re.match(r"^([\d.]+)", str(value).strip())
    return float(match.group(1)) if match else None


def _image_tag_pattern(placeholder):
    return re.compile(
        r"<image\b(?P<body>[^>]*?(?:href|xlink:href)\s*=\s*[\"']"
        + re.escape(placeholder)
        + r"[\"'][^>]*?)/?>",
        re.DOTALL | re.IGNORECASE,
    )


def _read_image_tag_attrs(image_tag):
    def _attr(name):
        m = re.search(rf'\b{name}\s*=\s*"([^"]*)"', image_tag, re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    return {
        "x": _attr("x") or 0.0,
        "y": _attr("y") or 0.0,
        "width": _attr("width"),
        "height": _attr("height"),
    }


def _is_qr_image_tag(tag: str) -> bool:
    if QR_CODE_PLACEHOLDER in tag:
        return True
    href = re.search(
        r'(?:href|xlink:href)\s*=\s*"([^"]+)"', tag, re.IGNORECASE
    )
    return bool(href and re.search(r"qr_.*\.png", href.group(1), re.IGNORECASE))


def _uniform_badge_scale(svg_w, svg_h, badge_w, badge_h) -> float:
    """Single scale factor mapping SVG user units to PDF points (uniform)."""
    if not svg_w or not svg_h:
        return 1.0
    scale_x = badge_w / svg_w
    scale_y = badge_h / svg_h
    if abs(scale_x - scale_y) > 0.02:
        logger.warning(
            "SVG/badge aspect mismatch (%.2fx%.2f svg vs %.2fpt x %.2fpt badge); "
            "using uniform scale %.4f",
            svg_w,
            svg_h,
            badge_w,
            badge_h,
            min(scale_x, scale_y),
        )
    return min(scale_x, scale_y)


def _logo_slot_rect(svg_content, placeholder, img_w, img_h):
    """Contain-fit logo box in SVG user units, or None if slot/image missing."""
    if not img_w or not img_h:
        return None
    match = _image_tag_pattern(placeholder).search(svg_content)
    if not match:
        return None
    attrs = _read_image_tag_attrs(match.group(0))
    slot_w, slot_h = attrs["width"], attrs["height"]
    if not slot_w or not slot_h:
        return None
    scale = min(slot_w / img_w, slot_h / img_h)
    draw_w = img_w * scale
    draw_h = img_h * scale
    draw_x = attrs["x"] + (slot_w - draw_w) / 2
    draw_y = attrs["y"] + (slot_h - draw_h) / 2
    return draw_x, draw_y, draw_w, draw_h


def _strip_logo_image_tags(svg_content):
    for placeholder in (CLUB_LOGO_PLACEHOLDER, AFRP_LOGO_PLACEHOLDER):
        svg_content = _image_tag_pattern(placeholder).sub("", svg_content)
    return svg_content


def _svg_canvas_size(svg_content):
    w = _svg_canvas_width(svg_content)
    viewbox = VIEWBOX_RE.search(svg_content)
    h = 288.0
    if viewbox:
        parts = viewbox.group(1).replace(",", " ").split()
        if len(parts) == 4:
            try:
                h = float(parts[3])
            except ValueError:
                pass
    height_match = re.search(r'\bheight\s*=\s*"([\d.]+)', svg_content, re.IGNORECASE)
    if height_match:
        try:
            h = float(height_match.group(1))
        except ValueError:
            pass
    return w, h


def _svg_rect_to_pdf_points(rect, svg_w, svg_h, badge_w, badge_h):
    """Map SVG top-left rect to ReportLab coords inside a badge cell."""
    x, y, w, h = rect
    scale = _uniform_badge_scale(svg_w, svg_h, badge_w, badge_h)
    x_pt = x * scale
    w_pt = w * scale
    h_pt = h * scale
    y_pt = badge_h - (y + h) * scale
    return x_pt, y_pt, w_pt, h_pt


def _fit_image_in_slot(svg_content, placeholder, img_w, img_h):
    """Resize an <image> slot so svglib draws the logo without stretching.

    svglib ignores preserveAspectRatio and always stretches to width/height, so we
    pre-compute a box with the image's true aspect ratio fitted inside the
    template slot (object-fit: contain) and centered.
    """
    if not img_w or not img_h:
        return svg_content

    match = _image_tag_pattern(placeholder).search(svg_content)
    if not match:
        logger.warning("Could not find %s image tag in SVG", placeholder)
        return svg_content

    original_tag = match.group(0)
    fitted = _logo_slot_rect(svg_content, placeholder, img_w, img_h)
    if not fitted:
        logger.warning("Could not read slot dimensions for %s", placeholder)
        return svg_content
    draw_x, draw_y, draw_w, draw_h = fitted
    slot_attrs = _read_image_tag_attrs(original_tag)
    slot_w = slot_attrs["width"] or draw_w
    slot_h = slot_attrs["height"] or draw_h

    new_tag = (
        f'<image x="{draw_x:g}" y="{draw_y:g}" '
        f'width="{draw_w:g}" height="{draw_h:g}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'href="{placeholder}"/>'
    )
    logger.info(
        "Fitted %s in slot %.0fx%.0f -> %.1fx%.1f at (%.1f, %.1f) "
        "(source %.0fx%.0f)",
        placeholder,
        slot_w,
        slot_h,
        draw_w,
        draw_h,
        draw_x,
        draw_y,
        img_w,
        img_h,
    )
    return svg_content.replace(original_tag, new_tag, 1)


def validate_template_club_logo(svg_template_path, club_logo_path=None):
    """Validate club logo configuration; missing logos are allowed (rendered blank)."""
    try:
        with open(svg_template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return f"Cannot read SVG template: {e}"

    if CLUB_LOGO_PLACEHOLDER in content and not (
        club_logo_path and os.path.exists(club_logo_path)
    ):
        logger.warning(
            "Template %s includes %s but no club logo is configured; "
            "badges will be generated with a blank club logo slot",
            svg_template_path,
            CLUB_LOGO_PLACEHOLDER,
        )
    return None


def _stage_logo_file(source_path, dest_path, max_edge=MAX_STAGED_LOGO_EDGE):
    """Stage a logo for alpha-aware PDF compositing (preserve transparency)."""
    ext = os.path.splitext(source_path)[1].lower()

    if ext == ".svg":
        dest_path = os.path.splitext(dest_path)[0] + ".png"
        try:
            import cairosvg
            png_data = cairosvg.svg2png(url=source_path, output_width=max_edge)
            with Image.open(BytesIO(png_data)) as img:
                img = img.convert("RGBA")
                img.save(dest_path, format="PNG")
            return dest_path
        except Exception as e:
            logger.warning("Could not rasterize SVG logo %s: %s", source_path, e)
            shutil.copyfile(source_path, dest_path)
            return dest_path

    with Image.open(source_path) as img:
        if img.mode == "P":
            img = img.convert("RGBA" if "transparency" in img.info else "RGB")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        w, h = img.size
        if max(w, h) > max_edge:
            scale = max_edge / max(w, h)
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.LANCZOS,
            )
        if ext in (".jpg", ".jpeg"):
            if img.mode == "RGBA":
                img = img.convert("RGB")
            img.save(dest_path, format="JPEG")
        else:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            out = dest_path if ext == ".png" else os.path.splitext(dest_path)[0] + ".png"
            img.save(out, format="PNG")
            dest_path = out
    return dest_path


def _subtree_has_placeholder(elem: ET.Element) -> bool:
    xml = ET.tostring(elem, encoding="unicode", method="xml")
    return PLACEHOLDER_RE.search(xml) is not None


def _static_prune(elem: ET.Element):
    """Keep only SVG subtrees with no mail-merge placeholders (static layer)."""
    if not _subtree_has_placeholder(elem):
        return copy.deepcopy(elem)
    new_el = ET.Element(elem.tag, dict(elem.attrib))
    if elem.text:
        new_el.text = PLACEHOLDER_RE.sub("", elem.text)
    else:
        new_el.text = elem.text
    new_el.tail = elem.tail
    for k, v in list(new_el.attrib.items()):
        if v and PLACEHOLDER_RE.search(v):
            del new_el.attrib[k]
    for child in elem:
        pruned = _static_prune(child)
        if pruned is not None:
            new_el.append(pruned)
    if len(new_el) == 0 and not (new_el.text and str(new_el.text).strip()):
        return None
    return new_el


def _elem_has_own_placeholder(elem: ET.Element) -> bool:
    parts = []
    if elem.text:
        parts.append(elem.text)
    if elem.tail:
        parts.append(elem.tail)
    for v in elem.attrib.values():
        if v:
            parts.append(v)
    return any(PLACEHOLDER_RE.search(p) for p in parts)


def _dynamic_prune(elem: ET.Element):
    """Keep only subtrees that still contain at least one placeholder (dynamic layer)."""
    if not _subtree_has_placeholder(elem):
        return None
    pruned_children = []
    for child in elem:
        p = _dynamic_prune(child)
        if p is not None:
            pruned_children.append(p)
    if not _elem_has_own_placeholder(elem) and not pruned_children:
        return None
    new_el = ET.Element(elem.tag, dict(elem.attrib))
    new_el.text = elem.text
    new_el.tail = elem.tail
    for p in pruned_children:
        new_el.append(p)
    return new_el


def split_template_svg(svg_text: str) -> tuple[str, str]:
    """Split full SVG into (static_xml, dynamic_xml) sharing the same root dimensions."""
    root = ET.fromstring(svg_text.strip())
    static_el = _static_prune(root)
    dynamic_el = _dynamic_prune(root)
    if static_el is None or dynamic_el is None:
        raise ValueError("split_template_svg produced empty static or dynamic layer")
    return (
        ET.tostring(static_el, encoding="unicode"),
        ET.tostring(dynamic_el, encoding="unicode"),
    )


def _generate_qr_code_bytes(data: str):
    """Module-level QR generator for picklable worker processes."""
    if not data:
        return None
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(str(data))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _row_value_str(row: dict, col_name: str) -> str:
    if col_name not in row:
        return ""
    val = row[col_name]
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    return str(val)


_OPTIONAL_NAME_SENTINELS = frozenset({"nan", "none", "null", "n/a", "na"})


def _clean_optional_name_part(value: str) -> str:
    """Treat spreadsheet/CRM sentinels as blank for optional name fields."""
    cleaned = value.strip()
    if cleaned.lower() in _OPTIONAL_NAME_SENTINELS:
        return ""
    return cleaned


def _collapse_empty_maiden_parentheses(svg_content: str) -> str:
    """Drop empty or sentinel-only parentheses left after maiden-name substitution."""
    svg_content = re.sub(r"\s*\(\s*\)\s*", " ", svg_content)
    svg_content = re.sub(
        r"\s*\(\s*(?:nan|none|null|n/?a)\s*\)\s*",
        " ",
        svg_content,
        flags=re.IGNORECASE,
    )
    return re.sub(r"  +", " ", svg_content)


def _parse_svg_attr(attrs: str, name: str, default=None):
    match = re.search(rf'\b{re.escape(name)}\s*=\s*"([^"]*)"', attrs, re.IGNORECASE)
    return match.group(1) if match else default


def _reportlab_font_name(font_family: str, font_weight: str) -> str:
    family = (font_family or "Arial").lower().strip()
    bold = str(font_weight or "").lower() in ("bold", "700", "800", "900", "bolder")
    if "times" in family:
        return "Times-Bold" if bold else "Times-Roman"
    if "courier" in family:
        return "Courier-Bold" if bold else "Courier"
    return "Helvetica-Bold" if bold else "Helvetica"


def _svg_canvas_width(svg_content: str) -> float:
    viewbox = VIEWBOX_RE.search(svg_content)
    if viewbox:
        parts = viewbox.group(1).replace(",", " ").split()
        if len(parts) == 4:
            try:
                return float(parts[2])
            except ValueError:
                pass
    width = SVG_WIDTH_RE.search(svg_content)
    return float(width.group(1)) if width else 384.0


def _max_text_width(
    x_value: str,
    text_anchor: str,
    svg_width: float,
    explicit_max_width: str,
) -> float:
    margin = 12.0
    if explicit_max_width:
        try:
            return float(explicit_max_width)
        except ValueError:
            pass
    try:
        x = float(x_value) if x_value is not None else svg_width / 2
    except ValueError:
        x = svg_width / 2
    anchor = (text_anchor or "start").lower()
    if anchor == "middle":
        return max(2 * min(x - margin, svg_width - x - margin), 0.0)
    if anchor == "end":
        return max(x - margin, 0.0)
    return max(svg_width - x - margin, 0.0)


def _shrink_text_to_fit(svg_content: str) -> str:
    """Shrink font-size on opt-in <text> elements so content stays on one line."""
    svg_width = _svg_canvas_width(svg_content)

    def _replace_text(match: re.Match) -> str:
        attrs, text = match.group(1), match.group(2).strip()
        if not text:
            return match.group(0)

        shrink_flag = (_parse_svg_attr(attrs, "data-shrink-to-fit", "") or "").lower()
        if shrink_flag not in ("true", "1", "yes"):
            return match.group(0)

        try:
            font_size = float(_parse_svg_attr(attrs, "font-size", "12"))
        except ValueError:
            font_size = 12.0
        try:
            min_font_size = float(
                _parse_svg_attr(attrs, "data-min-font-size", str(DEFAULT_MIN_SHRINK_FONT_SIZE))
            )
        except ValueError:
            min_font_size = DEFAULT_MIN_SHRINK_FONT_SIZE

        max_width = _max_text_width(
            _parse_svg_attr(attrs, "x"),
            _parse_svg_attr(attrs, "text-anchor"),
            svg_width,
            _parse_svg_attr(attrs, "data-max-width"),
        )
        if max_width <= 0:
            return match.group(0)

        font_name = _reportlab_font_name(
            _parse_svg_attr(attrs, "font-family"),
            _parse_svg_attr(attrs, "font-weight"),
        )

        # svglib/system fonts render slightly wider than the Helvetica metrics
        # ReportLab uses for estimation, so keep a safety margin.
        usable_width = max_width * 0.90

        fitted_size = font_size
        while fitted_size > min_font_size and stringWidth(text, font_name, fitted_size) > usable_width:
            fitted_size -= 0.5
        fitted_size = max(fitted_size, min_font_size)

        if fitted_size >= font_size:
            return match.group(0)

        if re.search(r"\bfont-size\s*=", attrs, re.IGNORECASE):
            new_attrs = re.sub(
                r'font-size\s*=\s*"[^"]*"',
                f'font-size="{fitted_size:g}"',
                attrs,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            new_attrs = f'{attrs} font-size="{fitted_size:g}"'

        logger.debug(
            "Shrunk badge text %r from %spt to %spt (max width %.0f)",
            text[:50],
            font_size,
            fitted_size,
            max_width,
        )
        return f"<text{new_attrs}>{text}</text>"

    return TEXT_TAG_RE.sub(_replace_text, svg_content)


def _finalize_svg_content(svg_content: str) -> str:
    svg_content = _collapse_empty_maiden_parentheses(svg_content)
    return _shrink_text_to_fit(svg_content)


def _field_visibility_from_layout(layout: dict | None) -> dict:
    if not layout:
        return {}
    raw = layout.get(FIELD_VISIBILITY_KEY)
    return raw if isinstance(raw, dict) else {}


def _is_field_enabled(
    placeholder: str,
    column_mappings: dict,
    field_visibility: dict | None,
) -> bool:
    """Match badge designer preview toggles in final badge output."""
    if field_visibility and placeholder in field_visibility:
        return field_visibility[placeholder] is not False
    if placeholder in column_mappings:
        return True
    if placeholder == QR_CODE_PLACEHOLDER:
        return False
    if placeholder.startswith("{{SUBEVENT_"):
        return False
    if placeholder in (
        AFRP_LOGO_PLACEHOLDER,
        CLUB_LOGO_PLACEHOLDER,
        DISPLAY_NAME_PLACEHOLDER,
    ):
        return True
    return True


def _mapped_row_value(row: dict, column_mappings: dict, placeholder: str, default_column: str) -> str:
    column = column_mappings.get(placeholder, default_column)
    if isinstance(column, list):
        return ""
    return _clean_optional_name_part(_row_value_str(row, column))


def _build_display_name(
    row: dict,
    column_mappings: dict,
    display_name_config: dict | None = None,
    field_visibility: dict | None = None,
) -> str:
    """Full name for {{DISPLAY_NAME}} using template formatting rules."""
    def value_getter(placeholder: str, default_column: str) -> str:
        return _mapped_row_value(row, column_mappings, placeholder, default_column)

    return build_display_name(
        row,
        column_mappings,
        display_name_config,
        value_getter=value_getter,
        field_visibility=field_visibility,
    )


def _apply_column_mappings(
    svg_content: str,
    row: dict,
    column_mappings: dict,
    display_name_config: dict | None = None,
    meal_preference_mappings: dict | None = None,
    meal_preference_sources: dict | None = None,
    field_visibility: dict | None = None,
) -> str:
    if DISPLAY_NAME_PLACEHOLDER in svg_content:
        if _is_field_enabled(
            DISPLAY_NAME_PLACEHOLDER, column_mappings, field_visibility
        ):
            svg_content = svg_content.replace(
                DISPLAY_NAME_PLACEHOLDER,
                _build_display_name(
                    row,
                    column_mappings,
                    display_name_config,
                    field_visibility,
                ),
            )
        else:
            svg_content = svg_content.replace(DISPLAY_NAME_PLACEHOLDER, "")
    for placeholder, column_name in column_mappings.items():
        if placeholder == QR_CODE_PLACEHOLDER:
            continue
        if not _is_field_enabled(placeholder, column_mappings, field_visibility):
            continue
        if isinstance(column_name, list):
            sub_events = []
            for col in column_name:
                v = _row_value_str(row, col)
                if v:
                    event_name = col.split(" ~ ")[-1] if " ~ " in col else col
                    sub_events.append(event_name)
            value = "\n".join(sub_events)
        else:
            value = _row_value_str(row, column_name)
        if placeholder == "{{MEAL_PREFERENCE}}":
            if meal_preference_sources:
                value = build_meal_preference_value(
                    row, meal_preference_sources, meal_preference_mappings
                )
            else:
                value = apply_meal_preference_mapping(value, meal_preference_mappings)
        if placeholder in svg_content:
            svg_content = svg_content.replace(placeholder, value)
    return _collapse_empty_maiden_parentheses(svg_content)


def _replace_qr_placeholder(
    svg_content: str,
    row: dict,
    temp_dir: str,
    row_index,
    column_mappings: dict | None = None,
    field_visibility: dict | None = None,
) -> str:
    if QR_CODE_PLACEHOLDER not in svg_content:
        return svg_content

    if not _is_field_enabled(QR_CODE_PLACEHOLDER, column_mappings or {}, field_visibility):
        return _image_tag_pattern(QR_CODE_PLACEHOLDER).sub("", svg_content)

    replaced = False
    qr_data = row.get("QR Code", "")
    if qr_data is not None and qr_data != "":
        try:
            if pd.isna(qr_data):
                qr_data = ""
        except Exception:
            pass
    if qr_data:
        buf = _generate_qr_code_bytes(str(qr_data))
        if buf:
            fn = f"qr_{row_index}.png"
            with open(os.path.join(temp_dir, fn), "wb") as qf:
                qf.write(buf.getvalue())
            svg_content = svg_content.replace("{{QR_CODE}}", fn)
            replaced = True
    if not replaced:
        svg_content = svg_content.replace("{{QR_CODE}}", "")
    return ensure_square_qr_image_tags(svg_content)


def _strip_remaining_placeholders(svg_content: str) -> str:
    remaining = set(PLACEHOLDER_RE.findall(svg_content))
    if remaining:
        logger.warning(
            "Final cleanup removing %s remaining placeholders: %s",
            len(remaining),
            remaining,
        )
    for token in remaining:
        svg_content = svg_content.replace(token, "")
    return svg_content


def _render_dynamic_drawing(args: dict):
    """Picklable worker: render dynamic-only SVG for one row; returns (row_index, pickle_bytes|None, err|None)."""
    row_index = args["row_index"]
    temp_dir = args["temp_dir"]
    dynamic_path = args["dynamic_svg_path"]
    column_mappings = args["column_mappings"]
    display_name_config = args.get("display_name_config")
    meal_preference_mappings = args.get("meal_preference_mappings")
    meal_preference_sources = args.get("meal_preference_sources")
    field_visibility = args.get("field_visibility")
    row = args["row"]
    badge_w = args["badge_width"]
    badge_h = args["badge_height"]
    try:
        with open(dynamic_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
        svg_content = _apply_column_mappings(
            svg_content,
            row,
            column_mappings,
            display_name_config,
            meal_preference_mappings,
            meal_preference_sources,
            field_visibility,
        )
        svg_content = _replace_qr_placeholder(
            svg_content, row, temp_dir, row_index, column_mappings, field_visibility
        )
        svg_content = _strip_remaining_placeholders(svg_content)
        svg_content = _finalize_svg_content(svg_content)
        out_svg = os.path.join(temp_dir, f"badge_dynamic_{row_index}.svg")
        with open(out_svg, "w", encoding="utf-8") as wf:
            wf.write(svg_content)
        drawing = svg2rlg(out_svg)
        if os.path.exists(out_svg):
            os.remove(out_svg)
        if not drawing:
            return (row_index, None, "svg2rlg returned None")
        return (
            row_index,
            pickle.dumps(drawing, protocol=pickle.HIGHEST_PROTOCOL),
            None,
        )
    except Exception as e:
        logger.error(
            "Error rendering dynamic badge row_index=%s: %s",
            row_index,
            e,
            exc_info=True,
        )
        return (row_index, None, str(e))

class BadgeGenerator:
    """Generate print-ready badges from Excel data using SVG templates."""

    AVERY_TEMPLATES = AVERY_TEMPLATES
    
    def __init__(self, excel_file, svg_template_path, column_mappings, 
                 afrp_logo_path, club_logo_path=None, club_logo_width=None, 
                 club_logo_height=None, avery_template='5392', show_outlines=False,
                 background_id='white', backgrounds_folder=None, element_layout=None,
                 display_name_config=None, meal_preference_mappings=None,
                 meal_preference_sources=None):
        """
        Initialize the badge generator.
        
        Args:
            excel_file: Path to processed Excel file
            svg_template_path: Path to SVG template file
            column_mappings: Dict mapping placeholders to Excel columns
            afrp_logo_path: Path to default AFRP logo
            club_logo_path: Optional path to club-specific logo
            avery_template: Avery template code (default: 5392)
            show_outlines: Draw badge outlines for alignment testing
            background_id: Badge background template id (default white)
            backgrounds_folder: Root path for badge_background_templates/
            element_layout: Optional dict of corner/sub-event position overrides
            display_name_config: Optional dict of {{DISPLAY_NAME}} formatting rules
            meal_preference_mappings: Optional dict mapping raw meal responses to badge labels
            meal_preference_sources: Optional per-event source toggles for meal badge text
        """
        self.excel_file = excel_file
        self.svg_template_path = svg_template_path
        self.column_mappings = column_mappings
        self.element_layout = element_layout or {}
        self.field_visibility = _field_visibility_from_layout(self.element_layout)
        self.display_name_config = normalize_display_name_config(display_name_config)
        self.meal_preference_mappings = meal_preference_mappings or {}
        self.meal_preference_sources = meal_preference_sources or {}
        # Resolve logo paths to absolute paths up-front so they survive any
        # later os.chdir() the caller might do (e.g. the /pull-process-generate
        # endpoint chdir's into a temp working dir while preprocessing).
        self.afrp_logo_path = os.path.abspath(afrp_logo_path) if afrp_logo_path else None
        self.club_logo_path = os.path.abspath(club_logo_path) if club_logo_path else None
        self.club_logo_width = club_logo_width
        self.club_logo_height = club_logo_height
        self.afrp_logo_width = None
        self.afrp_logo_height = None
        self.avery_template = resolve_avery_code(avery_template)
        self.show_outlines = show_outlines
        self.background_id = background_id or 'white'
        self.backgrounds_folder = backgrounds_folder
        self._bg_is_white = True
        self._bg_image_path = None
        self._bg_draw_path = None
        self._logo_draw_specs = []
        if self.backgrounds_folder:
            self._bg_is_white, self._bg_image_path = resolve_background_path(
                self.backgrounds_folder, self.background_id, self.avery_template
            )

        if self.afrp_logo_path and os.path.exists(self.afrp_logo_path):
            aw, ah = probe_image_dimensions(self.afrp_logo_path)
            if aw and ah:
                self.afrp_logo_width, self.afrp_logo_height = aw, ah
        if (
            (not self.club_logo_width or not self.club_logo_height)
            and self.club_logo_path
            and os.path.exists(self.club_logo_path)
        ):
            cw, ch = probe_image_dimensions(self.club_logo_path)
            if cw and ch:
                self.club_logo_width, self.club_logo_height = cw, ch

        # Filenames used inside each per-badge temp dir; populated by
        # _stage_static_assets(). Empty string => placeholder will be cleared.
        self._afrp_logo_filename = ''
        self._club_logo_filename = ''
        
        # Debug logging
        logger.info(f"BadgeGenerator initialized with:")
        logger.info(f"  - AFRP logo: {afrp_logo_path} (exists: {os.path.exists(afrp_logo_path) if afrp_logo_path else False})")
        logger.info(f"  - Club logo: {club_logo_path} (exists: {os.path.exists(club_logo_path) if club_logo_path else False})")
        if self.afrp_logo_width and self.afrp_logo_height:
            logger.info(f"  - AFRP logo dimensions: {self.afrp_logo_width}x{self.afrp_logo_height}")
        if self.club_logo_width and self.club_logo_height:
            logger.info(f"  - Club logo dimensions: {self.club_logo_width}x{self.club_logo_height}")
        logger.info(f"  - SVG template: {svg_template_path}")
        logger.info(f"  - Show outlines: {show_outlines}")
        logger.info(f"  - Background: {self.background_id} (white={self._bg_is_white})")
        
        # Load Excel data
        logger.info(f"Loading Excel file: {excel_file}")
        self.df = pd.read_excel(excel_file)
        logger.info(f"Loaded {len(self.df)} rows from Excel")
        
        # Validate template exists
        if self.avery_template not in self.AVERY_TEMPLATES:
            raise ValueError(f"Unknown Avery template: {avery_template}")

        self.template_spec = self.AVERY_TEMPLATES[self.avery_template]
        logger.info(f"Using template: {self.template_spec['name']}")

    def _read_scaled_base_svg(self) -> str:
        """Load built-in SVG scaled to the selected Avery canvas size."""
        with open(self.svg_template_path, "r", encoding="utf-8") as f:
            raw = f.read()
        return prepare_svg_for_avery(raw, self.avery_template)
    
    def generate_qr_code(self, data):
        """
        Generate QR code image from string data.
        
        Args:
            data: String data to encode in QR code
            
        Returns:
            BytesIO object containing PNG image
        """
        if not data or pd.isna(data):
            return None
            
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2
        )
        qr.add_data(str(data))
        qr.make(fit=True)
        
        img = qr.make_image(fill_color='black', back_color='white')
        
        # Convert to bytes
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        return img_bytes
    
    def image_to_base64(self, image_path):
        """
        Convert image file to base64 encoded string.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Base64 encoded string
        """
        if not image_path or not os.path.exists(image_path):
            return None
            
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to encode image {image_path}: {e}")
            return None
    
    def fit_logo_placeholders(self, svg_content):
        """Fit logo placeholders into their template slots without distortion."""
        if self.afrp_logo_width and self.afrp_logo_height:
            svg_content = _fit_image_in_slot(
                svg_content,
                AFRP_LOGO_PLACEHOLDER,
                self.afrp_logo_width,
                self.afrp_logo_height,
            )
        if self.club_logo_width and self.club_logo_height:
            svg_content = _fit_image_in_slot(
                svg_content,
                CLUB_LOGO_PLACEHOLDER,
                self.club_logo_width,
                self.club_logo_height,
            )
        elif CLUB_LOGO_PLACEHOLDER in svg_content and self.club_logo_path:
            logger.warning(
                "Club logo dimensions unknown for %s; logo may appear stretched",
                self.club_logo_path,
            )
        return svg_content
    
    def _stage_static_assets(self, temp_dir):
        """
        Copy AFRP and Club logos into ``temp_dir`` once per generation so each
        rendered SVG can reference them by relative filename.

        Using on-disk image files (instead of data: URIs embedded in the SVG)
        is significantly more reliable: ``svglib`` has full support for raster
        and SVG images referenced by relative path, but its inline data:-URI
        path only matches PNG/JPEG and silently drops other types (notably SVG
        club logos). It also avoids bloating every rendered SVG with a 400KB+
        base64 string per logo.
        """
        self._afrp_logo_filename = ''
        self._club_logo_filename = ''

        if self.afrp_logo_path and os.path.exists(self.afrp_logo_path):
            ext = os.path.splitext(self.afrp_logo_path)[1].lower() or ".png"
            filename = f"afrp_logo{ext}"
            try:
                staged_path = _stage_logo_file(
                    self.afrp_logo_path,
                    os.path.join(temp_dir, filename),
                )
                self._afrp_logo_filename = os.path.basename(staged_path)
                logger.info(
                    f"Staged AFRP logo: {self.afrp_logo_path} -> {self._afrp_logo_filename}"
                )
            except Exception as e:
                logger.error(f"Failed to stage AFRP logo {self.afrp_logo_path}: {e}")
        else:
            logger.warning(
                f"AFRP logo missing or not provided (path={self.afrp_logo_path}); "
                "the {{AFRP_LOGO}} placeholder will be left blank."
            )

        if self.club_logo_path and os.path.exists(self.club_logo_path):
            ext = os.path.splitext(self.club_logo_path)[1].lower() or ".png"
            filename = f"club_logo{ext}"
            try:
                staged_path = _stage_logo_file(
                    self.club_logo_path,
                    os.path.join(temp_dir, filename),
                )
                self._club_logo_filename = os.path.basename(staged_path)
                logger.info(
                    f"Staged club logo: {self.club_logo_path} -> {self._club_logo_filename}"
                )
            except Exception as e:
                logger.error(f"Failed to stage club logo {self.club_logo_path}: {e}")
        elif self.club_logo_path:
            logger.error(
                "Club logo file not found: %s — the %s placeholder will be blank",
                self.club_logo_path,
                CLUB_LOGO_PLACEHOLDER,
            )

    def _prepare_background_image(self, temp_dir):
        """Re-fit backgrounds to the target Avery canvas at print resolution.

        Uses 300 DPI pixel dimensions so the embedded raster stays sharp on paper;
        resizing to the 96 DPI layout canvas here would re-introduce blur.
        """
        self._bg_draw_path = None
        if self._bg_is_white or not self._bg_image_path:
            return
        target_w, target_h = canvas_pixels_print(self.avery_template)
        try:
            with Image.open(self._bg_image_path) as im:
                # Already sized for this canvas (or larger): draw as-is, don't
                # downscale a high-res source.
                if im.size == (target_w, target_h) or (
                    im.width >= target_w and im.height >= target_h
                ):
                    self._bg_draw_path = self._bg_image_path
                    return
                resized = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
                out_path = os.path.join(temp_dir, "_badge_background.png")
                resized.save(out_path, format="PNG")
                self._bg_draw_path = out_path
                logger.info(
                    "Resized background %s -> %dx%d for Avery %s",
                    self._bg_image_path,
                    target_w,
                    target_h,
                    self.avery_template,
                )
        except Exception as e:
            logger.warning(
                "Could not resize background %s: %s; using original",
                self._bg_image_path,
                e,
            )
            self._bg_draw_path = self._bg_image_path

    def _draw_badge_background(self, canvas_obj, badge_width, badge_height):
        if self._bg_is_white or not self._bg_image_path:
            canvas_obj.setFillColorRGB(1, 1, 1)
            canvas_obj.rect(0, 0, badge_width, badge_height, fill=1, stroke=0)
        else:
            bg_path = self._bg_draw_path or self._bg_image_path
            canvas_obj.drawImage(
                bg_path,
                0,
                0,
                badge_width,
                badge_height,
                preserveAspectRatio=False,
                anchor="sw",
                mask="auto",
            )

    def _draw_badge_logos(self, canvas_obj, temp_dir):
        for logo_path, x, y, w, h in self._logo_draw_specs:
            full_path = os.path.join(temp_dir, logo_path) if not os.path.isabs(logo_path) else logo_path
            if not full_path or not os.path.exists(full_path):
                continue
            ext = os.path.splitext(full_path)[1].lower()
            mask = "auto" if ext == ".png" else None
            canvas_obj.drawImage(
                full_path, x, y, w, h, preserveAspectRatio=True, anchor="sw", mask=mask
            )

    def _scale_drawing_to_badge(self, drawing, badge_width, badge_height):
        """Scale a ReportLab Drawing uniformly to fit the Avery badge cell."""
        scale = _uniform_badge_scale(
            drawing.width, drawing.height, badge_width, badge_height
        )
        scaled_w = drawing.width * scale
        scaled_h = drawing.height * scale
        offset_x = (badge_width - scaled_w) / 2
        offset_y = (badge_height - scaled_h) / 2
        drawing.scale(scale, scale)
        return offset_x, offset_y

    def render_svg_badge(self, row_data, temp_dir):
        """
        Render a single badge by replacing placeholders in SVG template.

        Args:
            row_data: Pandas Series containing data for one attendee
            temp_dir: Temporary directory for storing files

        Returns:
            Path to rendered SVG file
        """
        logger.debug(f"Rendering SVG for row {row_data.name}")
        logger.debug(f"Row data columns: {list(row_data.index)}")

        with open(self.svg_template_path, 'r', encoding='utf-8') as f:
            svg_content = prepare_svg_for_avery(f.read(), self.avery_template)

        svg_content = apply_element_layout(svg_content, self.element_layout)
        svg_content = self.fit_logo_placeholders(svg_content)

        logger.debug(f"SVG template length: {len(svg_content)} characters")

        row = row_data.to_dict()
        for placeholder, column_name in self.column_mappings.items():
            if placeholder == "{{QR_CODE}}":
                continue
            if not isinstance(column_name, list) and column_name not in row_data.index:
                logger.warning(
                    "Column '%s' not found in data for row %s",
                    column_name,
                    row_data.name,
                )

        svg_content = _apply_column_mappings(
            svg_content,
            row,
            self.column_mappings,
            self.display_name_config,
            self.meal_preference_mappings,
            self.meal_preference_sources,
            self.field_visibility,
        )
        svg_content = _replace_qr_placeholder(
            svg_content,
            row,
            temp_dir,
            row_data.name,
            self.column_mappings,
            self.field_visibility,
        )

        # AFRP logo and Club logo: just point at the staged file in temp_dir.
        # svglib will resolve the relative href against the SVG's directory.
        if _is_field_enabled(
            AFRP_LOGO_PLACEHOLDER, self.column_mappings, self.field_visibility
        ):
            svg_content = svg_content.replace(
                AFRP_LOGO_PLACEHOLDER, self._afrp_logo_filename
            )
        else:
            svg_content = _image_tag_pattern(AFRP_LOGO_PLACEHOLDER).sub("", svg_content)

        if _is_field_enabled(
            CLUB_LOGO_PLACEHOLDER, self.column_mappings, self.field_visibility
        ):
            svg_content = svg_content.replace(
                CLUB_LOGO_PLACEHOLDER, self._club_logo_filename
            )
        else:
            svg_content = _image_tag_pattern(CLUB_LOGO_PLACEHOLDER).sub("", svg_content)

        svg_content = _strip_remaining_placeholders(svg_content)
        svg_content = _finalize_svg_content(svg_content)

        temp_svg_path = os.path.join(temp_dir, f'badge_{row_data.name}.svg')
        with open(temp_svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)

        logger.debug(f"Saved rendered SVG to: {temp_svg_path}")
        logger.debug(f"Final SVG length: {len(svg_content)} characters")

        return temp_svg_path
    
    def generate_pdf(self, output_path, progress_callback=None):
        """
        Generate PDF with all badges arranged on Avery template sheets.
        
        Args:
            output_path: Path where PDF should be saved
            progress_callback: Optional callback function(current, total, message)
            
        Returns:
            Path to generated PDF file
        """
        logger.info(f"Generating PDF with {len(self.df)} badges")
        logger.info(f"Excel columns: {list(self.df.columns)}")
        logger.info(f"Column mappings: {self.column_mappings}")
        logger.info(f"SVG template: {self.svg_template_path}")
        logger.info(f"AFRP logo: {self.afrp_logo_path}")
        logger.info(f"Club logo: {self.club_logo_path}")
        logger.info(f"Output path: {output_path}")
        
        # Verify files exist
        if not os.path.exists(self.svg_template_path):
            raise FileNotFoundError(f"SVG template not found: {self.svg_template_path}")
        if not os.path.exists(self.afrp_logo_path):
            logger.warning(f"AFRP logo not found: {self.afrp_logo_path}")
        
        # Create canvas
        c = canvas.Canvas(output_path, pagesize=letter)
        page_width, page_height = letter
        
        # Get template specifications
        spec = self.template_spec
        badge_width = spec['width'] * inch
        badge_height = spec['height'] * inch
        cols = spec['cols']
        rows = spec['rows']
        margin_left = spec['margin_left'] * inch
        margin_top = spec['margin_top'] * inch
        gap_h = spec.get('gap_horizontal', 0) * inch
        gap_v = spec.get('gap_vertical', 0) * inch
        
        badges_per_page = cols * rows
        total_badges = len(self.df)
        
        logger.info(f"Badge dimensions: {badge_width/inch}\" x {badge_height/inch}\"")
        logger.info(f"Layout: {cols} x {rows} = {badges_per_page} per page")
        
        # Create temporary directory for SVG files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = os.path.abspath(temp_dir)
            logger.info(f"Using temporary directory: {temp_dir}")

            # Copy AFRP/Club logos into the temp dir once so every per-badge
            # SVG can reference them by relative filename.
            self._stage_static_assets(temp_dir)
            self._prepare_background_image(temp_dir)

            svg_base = self._read_scaled_base_svg()
            layout = resolve_element_layout_for_canvas(
                self.element_layout, canvas_pixels(self.avery_template)
            )
            svg_base = apply_element_layout(svg_base, layout)
            svg_fitted = self.fit_logo_placeholders(svg_base)
            svg_w, svg_h = _svg_canvas_size(svg_fitted)

            self._logo_draw_specs = []
            if self._club_logo_filename and _is_field_enabled(
                CLUB_LOGO_PLACEHOLDER, self.column_mappings, self.field_visibility
            ):
                club_rect = _logo_slot_rect(
                    svg_fitted, CLUB_LOGO_PLACEHOLDER,
                    self.club_logo_width, self.club_logo_height,
                )
                if club_rect:
                    self._logo_draw_specs.append(
                        (self._club_logo_filename,) + _svg_rect_to_pdf_points(
                            club_rect, svg_w, svg_h, badge_width, badge_height
                        )
                    )
            if self._afrp_logo_filename and _is_field_enabled(
                AFRP_LOGO_PLACEHOLDER, self.column_mappings, self.field_visibility
            ):
                afrp_rect = _logo_slot_rect(
                    svg_fitted, AFRP_LOGO_PLACEHOLDER,
                    self.afrp_logo_width, self.afrp_logo_height,
                )
                if afrp_rect:
                    self._logo_draw_specs.append(
                        (self._afrp_logo_filename,) + _svg_rect_to_pdf_points(
                            afrp_rect, svg_w, svg_h, badge_width, badge_height
                        )
                    )

            dynamic_xml = _strip_logo_image_tags(svg_fitted)
            dynamic_svg_path = os.path.join(temp_dir, "_dynamic_layer.svg")
            with open(dynamic_svg_path, "w", encoding="utf-8") as df:
                df.write(dynamic_xml)

            max_workers = int(
                os.environ.get(
                    "BADGE_GENERATOR_WORKERS",
                    min(4, os.cpu_count() or 4),
                )
            )
            max_workers = max(1, min(max_workers, 8))
            batch_size = max(1, int(os.environ.get("BADGE_GENERATOR_BATCH_SIZE", "100")))

            dynamic_by_index = {}
            if total_badges > 0:
                workers = min(max_workers, total_badges)
                row_items = list(self.df.iterrows())
                done = 0
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    for batch_start in range(0, len(row_items), batch_size):
                        batch = row_items[batch_start:batch_start + batch_size]
                        work_items = [
                            {
                                "row_index": idx,
                                "temp_dir": temp_dir,
                                "dynamic_svg_path": dynamic_svg_path,
                                "column_mappings": self.column_mappings,
                                "display_name_config": self.display_name_config,
                                "meal_preference_mappings": self.meal_preference_mappings,
                                "meal_preference_sources": self.meal_preference_sources,
                                "field_visibility": self.field_visibility,
                                "row": row.to_dict(),
                                "badge_width": badge_width,
                                "badge_height": badge_height,
                            }
                            for idx, row in batch
                        ]
                        futures = [
                            pool.submit(_render_dynamic_drawing, item) for item in work_items
                        ]
                        for fut in as_completed(futures):
                            row_index, pdata, err = fut.result()
                            if err:
                                logger.error(
                                    "Dynamic render failed for row_index=%s: %s",
                                    row_index,
                                    err,
                                )
                            elif pdata:
                                try:
                                    dynamic_by_index[row_index] = pickle.loads(pdata)
                                except Exception as pe:
                                    logger.error(
                                        "Failed to unpickle drawing row_index=%s: %s",
                                        row_index,
                                        pe,
                                        exc_info=True,
                                    )
                            done += 1
                            if progress_callback:
                                progress_callback(
                                    done,
                                    total_badges,
                                    f"Generated badge {done} of {total_badges}",
                                )

            badges_on_current_page = 0

            for index, row in self.df.iterrows():
                # Calculate position on page (index label order must match legacy behavior)
                badge_num = index % badges_per_page
                col = badge_num % cols
                row_pos = badge_num // cols

                # Calculate x, y position
                x = margin_left + col * (badge_width + gap_h)
                y = page_height - margin_top - (row_pos + 1) * badge_height - (row_pos * gap_v)

                try:
                    drawing = dynamic_by_index.get(index)
                    if drawing:
                        logger.debug(
                            "Compositing badge at PDF (%.2f\", %.2f\")",
                            x / inch,
                            y / inch,
                        )
                        c.saveState()
                        c.translate(x, y)
                        self._draw_badge_background(c, badge_width, badge_height)
                        self._draw_badge_logos(c, temp_dir)
                        ox, oy = self._scale_drawing_to_badge(
                            drawing, badge_width, badge_height
                        )
                        renderPDF.draw(drawing, c, ox, oy)
                        c.restoreState()
                    else:
                        logger.warning(
                            "No dynamic drawing for badge index=%s; skipping composite",
                            index,
                        )

                except Exception as e:
                    logger.error(
                        "Error compositing badge index=%s: %s",
                        index,
                        e,
                        exc_info=True,
                    )

                badges_on_current_page += 1
                page_is_full = badges_on_current_page == badges_per_page
                is_last_badge = (index + 1) == total_badges

                # Draw tear-line guides once per page (not once per badge).
                if self.show_outlines and (page_is_full or is_last_badge):
                    self._draw_cut_lines(c, page_width, page_height)

                if page_is_full and not is_last_badge:
                    c.showPage()
                    badges_on_current_page = 0
                    logger.debug("Starting new page after index=%s badges", index)

            # Save PDF
            c.save()
            logger.info(f"PDF saved to: {output_path}")
        
        return output_path

    def _draw_cut_lines(self, canvas_obj, page_width, page_height):
        """
        Draw unique badge boundary lines for the current Avery sheet.
        Lines are drawn once per page so only true tear/cut lines are shown.
        """
        spec = self.template_spec
        badge_width = spec['width'] * inch
        badge_height = spec['height'] * inch
        cols = spec['cols']
        rows = spec['rows']
        margin_left = spec['margin_left'] * inch
        margin_top = spec['margin_top'] * inch
        gap_h = spec.get('gap_horizontal', 0) * inch
        gap_v = spec.get('gap_vertical', 0) * inch

        # Preserve insertion order for deterministic rendering while deduplicating.
        unique_segments = OrderedDict()

        def add_segment(x1, y1, x2, y2):
            # Normalize direction so identical neighboring edges dedupe correctly.
            if (x1, y1) <= (x2, y2):
                key = (round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4))
            else:
                key = (round(x2, 4), round(y2, 4), round(x1, 4), round(y1, 4))
            unique_segments[key] = None

        for row_idx in range(rows):
            for col_idx in range(cols):
                x = margin_left + col_idx * (badge_width + gap_h)
                y = page_height - margin_top - (row_idx + 1) * badge_height - (row_idx * gap_v)

                # Rectangle edges for each label position.
                add_segment(x, y, x + badge_width, y)  # bottom
                add_segment(x, y + badge_height, x + badge_width, y + badge_height)  # top
                add_segment(x, y, x, y + badge_height)  # left
                add_segment(x + badge_width, y, x + badge_width, y + badge_height)  # right

        canvas_obj.saveState()
        canvas_obj.setStrokeColorRGB(0.8, 0.8, 0.8)  # Light gray guides
        canvas_obj.setLineWidth(0.5)

        for x1, y1, x2, y2 in unique_segments.keys():
            canvas_obj.line(x1, y1, x2, y2)

        canvas_obj.restoreState()
    
    @classmethod
    def get_available_templates(cls):
        """
        Get list of available Avery templates for the badge size dropdown.

        Returns:
            List of dicts with template information
        """
        return list_dropdown_templates()
    
    @staticmethod
    def extract_placeholders_from_svg(svg_path):
        """
        Extract placeholder strings from SVG template.
        
        Args:
            svg_path: Path to SVG template file
            
        Returns:
            List of placeholder strings found in the template
        """
        import re
        
        placeholders = set()
        pattern = r'\{\{([A-Z_]+)\}\}'
        
        try:
            with open(svg_path, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.findall(pattern, content)
                placeholders.update([f"{{{{{m}}}}}" for m in matches])
        except Exception as e:
            logger.error(f"Error extracting placeholders from {svg_path}: {e}")
        
        return sorted(list(placeholders))
