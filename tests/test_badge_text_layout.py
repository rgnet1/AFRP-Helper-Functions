"""Tests for badge text element positioning and font-size configuration."""

import re
import unittest

from utils.badges.badge_generator import _shrink_text_to_fit
from utils.badges.badge_sizes import scale_element_layout
from utils.badges.element_layout import (
    apply_element_layout,
    extract_layout_from_svg,
)

MINIMAL_BADGE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="384" height="288" viewBox="0 0 384 288">
  <text x="192" y="120" text-anchor="middle" font-size="28"
        data-shrink-to-fit="true" data-min-font-size="10" data-max-width="350"
        fill="#000">{{DISPLAY_NAME}}</text>
  <text x="192" y="150" text-anchor="middle" font-size="16"
        data-shrink-to-fit="true" data-min-font-size="10"
        fill="#4b904b">{{LOCAL_CLUB}}</text>
  <text x="192" y="175" text-anchor="middle" font-size="14"
        font-weight="bold" fill="#333">{{TABLE_NUMBER}}</text>
  <text x="5" y="215" text-anchor="start" font-size="10">{{SUBEVENT_1}}</text>
  <text x="5" y="230" text-anchor="start" font-size="10">{{SUBEVENT_2}}</text>
  <text x="5" y="245" text-anchor="start" font-size="10">{{SUBEVENT_3}}</text>
  <text x="5" y="260" text-anchor="start" font-size="10">{{SUBEVENT_4}}</text>
  <text x="334" y="203" text-anchor="middle" font-size="12">{{MEMBER_ID}}</text>
  <image x="304" y="208" width="60" height="60" href="{{QR_CODE}}"/>
  <text x="334" y="278" text-anchor="middle" font-size="9">{{MEAL_PREFERENCE}}</text>
</svg>"""


def _text_tag(svg: str, placeholder: str) -> str:
    match = re.search(
        rf"<text\b[^>]*>\s*{re.escape(placeholder)}\s*</text>",
        svg,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"Missing text tag for {placeholder}"
    return match.group(0)


def _attr(tag: str, name: str) -> str | None:
    match = re.search(rf'\b{name}\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
    return match.group(1) if match else None


def _float_attr(tag: str, name: str) -> float:
    value = _attr(tag, name)
    assert value is not None, f"Missing attribute {name}"
    return float(value)


class TestExtractTextLayout(unittest.TestCase):
    def test_extract_seeds_text_keys_with_font_and_shrink_flags(self):
        layout = extract_layout_from_svg(MINIMAL_BADGE_SVG)
        self.assertIn("{{DISPLAY_NAME}}", layout)
        self.assertEqual(layout["{{DISPLAY_NAME}}"]["fontSize"], 28.0)
        self.assertTrue(layout["{{DISPLAY_NAME}}"]["shrinkToFit"])
        self.assertEqual(layout["{{LOCAL_CLUB}}"]["fontSize"], 16.0)
        self.assertTrue(layout["{{LOCAL_CLUB}}"]["shrinkToFit"])
        self.assertEqual(layout["{{TABLE_NUMBER}}"]["fontSize"], 14.0)
        self.assertNotIn("shrinkToFit", layout["{{TABLE_NUMBER}}"])
        self.assertEqual(layout["subevents"]["fontSize"], 10.0)
        self.assertNotIn("{{MEMBER_ID}}", layout)
        self.assertNotIn("{{MEAL_PREFERENCE}}", layout)


class TestApplyTextLayout(unittest.TestCase):
    def test_custom_display_name_position_and_font_size(self):
        layout = {
            "corner_margins": extract_layout_from_svg(MINIMAL_BADGE_SVG)["corner_margins"],
            "{{DISPLAY_NAME}}": {
                "x": 50,
                "y": 80,
                "textAnchor": "start",
                "preset": "custom",
                "fontSize": 32,
            },
        }
        out = apply_element_layout(MINIMAL_BADGE_SVG, layout)
        tag = _text_tag(out, "{{DISPLAY_NAME}}")
        self.assertEqual(_float_attr(tag, "x"), 50)
        self.assertEqual(_float_attr(tag, "y"), 80)
        self.assertEqual(_attr(tag, "text-anchor"), "start")
        self.assertEqual(_float_attr(tag, "font-size"), 32)
        self.assertIsNone(_attr(tag, "data-max-width"))

    def test_table_number_literal_font_size(self):
        layout = {
            "corner_margins": extract_layout_from_svg(MINIMAL_BADGE_SVG)["corner_margins"],
            "{{TABLE_NUMBER}}": {
                "x": 100,
                "y": 200,
                "textAnchor": "middle",
                "preset": "custom",
                "fontSize": 18,
            },
        }
        out = apply_element_layout(MINIMAL_BADGE_SVG, layout)
        tag = _text_tag(out, "{{TABLE_NUMBER}}")
        self.assertEqual(_attr(tag, "font-size"), "18")
        self.assertNotIn('data-shrink-to-fit="true"', tag)

    def test_subevent_block_custom_position_and_font_size(self):
        layout = {
            "corner_margins": extract_layout_from_svg(MINIMAL_BADGE_SVG)["corner_margins"],
            "subevents": {
                "preset": "custom",
                "x": 40,
                "baseY": 180,
                "lineHeight": 12,
                "textAnchor": "start",
                "fontSize": 11,
            },
        }
        out = apply_element_layout(MINIMAL_BADGE_SVG, layout)
        for index, ph in enumerate(
            ["{{SUBEVENT_1}}", "{{SUBEVENT_2}}", "{{SUBEVENT_3}}", "{{SUBEVENT_4}}"]
        ):
            tag = _text_tag(out, ph)
            self.assertEqual(_float_attr(tag, "x"), 40)
            self.assertEqual(_float_attr(tag, "y"), 180 + index * 12)
            self.assertEqual(_float_attr(tag, "font-size"), 11)

    def test_detached_member_id_not_moved_by_qr_companions(self):
        layout = extract_layout_from_svg(MINIMAL_BADGE_SVG)
        layout["{{QR_CODE}}"]["x"] = 250
        layout["{{QR_CODE}}"]["y"] = 180
        layout["{{QR_CODE}}"]["preset"] = "custom"
        layout["{{QR_CODE}}"]["companions"] = {
            "{{MEAL_PREFERENCE}}": {"position": "below", "gap": 8}
        }
        layout["{{MEMBER_ID}}"] = {
            "x": 120,
            "y": 90,
            "textAnchor": "middle",
            "preset": "custom",
            "fontSize": 14,
        }
        out = apply_element_layout(MINIMAL_BADGE_SVG, layout)
        tag = _text_tag(out, "{{MEMBER_ID}}")
        self.assertEqual(_float_attr(tag, "x"), 120)
        self.assertEqual(_float_attr(tag, "y"), 90)


class TestShrinkBaseFontSize(unittest.TestCase):
    def test_short_name_uses_base_font_size(self):
        layout = {
            "corner_margins": extract_layout_from_svg(MINIMAL_BADGE_SVG)["corner_margins"],
            "{{DISPLAY_NAME}}": {
                "x": 192,
                "y": 120,
                "textAnchor": "middle",
                "preset": "custom",
                "fontSize": 36,
            },
        }
        svg = apply_element_layout(MINIMAL_BADGE_SVG, layout)
        svg = svg.replace("{{DISPLAY_NAME}}", "Jane Doe")
        out = _shrink_text_to_fit(svg)
        tag = re.search(r"<text[^>]*>Jane Doe</text>", out).group(0)
        self.assertEqual(_attr(tag, "font-size"), "36")

    def test_long_name_shrinks_from_base_font_size(self):
        layout = {
            "corner_margins": extract_layout_from_svg(MINIMAL_BADGE_SVG)["corner_margins"],
            "{{DISPLAY_NAME}}": {
                "x": 192,
                "y": 120,
                "textAnchor": "middle",
                "preset": "custom",
                "fontSize": 36,
            },
        }
        svg = apply_element_layout(MINIMAL_BADGE_SVG, layout)
        long_name = "Alexandria Montgomery Worthington III"
        svg = svg.replace("{{DISPLAY_NAME}}", long_name)
        out = _shrink_text_to_fit(svg)
        tag = re.search(rf"<text[^>]*>{re.escape(long_name)}</text>", out).group(0)
        fitted = float(_attr(tag, "font-size"))
        self.assertLess(fitted, 36)
        self.assertGreaterEqual(fitted, 10)


class TestScaleTextLayout(unittest.TestCase):
    def test_scales_text_positions_and_font_sizes(self):
        layout = {
            "corner_margins": extract_layout_from_svg(MINIMAL_BADGE_SVG)["corner_margins"],
            "{{DISPLAY_NAME}}": {
                "x": 192,
                "y": 120,
                "fontSize": 28,
                "preset": "custom",
            },
            "subevents": {
                "x": 5,
                "baseY": 215,
                "lineHeight": 15,
                "fontSize": 10,
                "preset": "custom",
            },
        }
        scaled = scale_element_layout(layout, (384, 288), (768, 576))
        self.assertEqual(scaled["{{DISPLAY_NAME}}"]["x"], 384.0)
        self.assertEqual(scaled["{{DISPLAY_NAME}}"]["y"], 240.0)
        self.assertEqual(scaled["{{DISPLAY_NAME}}"]["fontSize"], 56.0)
        self.assertEqual(scaled["subevents"]["fontSize"], 20.0)


if __name__ == "__main__":
    unittest.main()
