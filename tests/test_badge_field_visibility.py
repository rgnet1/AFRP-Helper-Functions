"""Tests that unchecked badge designer fields are omitted from rendered output."""

import tempfile
import unittest

from utils.badges.badge_generator import (
    AFRP_LOGO_PLACEHOLDER,
    CLUB_LOGO_PLACEHOLDER,
    DISPLAY_NAME_PLACEHOLDER,
    QR_CODE_PLACEHOLDER,
    _apply_column_mappings,
    _build_display_name,
    _field_visibility_from_layout,
    _image_tag_pattern,
    _is_field_enabled,
    _replace_qr_placeholder,
    _strip_remaining_placeholders,
)

SAMPLE_ROW = {
    "First Name": "Sarah",
    "Middle Name": "Marie",
    "Last Name": "Khoury",
    "Maiden Name": "Smith",
    "Member ID": "ID-01234",
    "Local Club": "Detroit",
    "Table Number": "Table 12",
    "Meal Preference": "Vegetarian",
    "QR Code": "member-123",
    "Grand Banquet": "yes",
}

FULL_MAPPINGS = {
    DISPLAY_NAME_PLACEHOLDER: "First Name",
    "{{MEMBER_ID}}": "Member ID",
    "{{LOCAL_CLUB}}": "Local Club",
    "{{TABLE_NUMBER}}": "Table Number",
    "{{MEAL_PREFERENCE}}": "Meal Preference",
    "{{SUBEVENT_1}}": "Grand Banquet",
    "{{FIRST_NAME}}": "First Name",
    QR_CODE_PLACEHOLDER: "QR Code",
}

BADGE_SVG = """<svg xmlns="http://www.w3.org/2000/svg">
  <text>{{DISPLAY_NAME}}</text>
  <text>{{MEMBER_ID}}</text>
  <text>{{LOCAL_CLUB}}</text>
  <text>{{TABLE_NUMBER}}</text>
  <text>{{MEAL_PREFERENCE}}</text>
  <text>{{SUBEVENT_1}}</text>
  <text>{{FIRST_NAME}}</text>
  <image xlink:href="{{QR_CODE}}" x="0" y="0" width="50" height="50"/>
  <image xlink:href="{{AFRP_LOGO}}" x="0" y="0" width="30" height="30"/>
  <image xlink:href="{{CLUB_LOGO}}" x="0" y="0" width="30" height="30"/>
</svg>"""


def render_badge_content(svg_content, row, column_mappings, field_visibility=None):
    """Mirror the dynamic badge render path used for PDF output."""
    with tempfile.TemporaryDirectory() as temp_dir:
        out = _apply_column_mappings(
            svg_content,
            row,
            column_mappings,
            field_visibility=field_visibility,
        )
        out = _replace_qr_placeholder(
            out,
            row,
            temp_dir,
            0,
            column_mappings,
            field_visibility,
        )
        for placeholder, filename in (
            (AFRP_LOGO_PLACEHOLDER, "afrp.png"),
            (CLUB_LOGO_PLACEHOLDER, "club.png"),
        ):
            if _is_field_enabled(placeholder, column_mappings, field_visibility):
                out = out.replace(placeholder, filename)
            else:
                out = _image_tag_pattern(placeholder).sub("", out)
        return _strip_remaining_placeholders(out)


class BadgeFieldVisibilityTests(unittest.TestCase):
    def test_all_mapped_fields_render_when_enabled(self):
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, FULL_MAPPINGS)
        self.assertIn("Sarah", rendered)
        self.assertIn("ID-01234", rendered)
        self.assertIn("Detroit", rendered)
        self.assertIn("Table 12", rendered)
        self.assertIn("Vegetarian", rendered)
        self.assertIn("qr_0.png", rendered)
        self.assertIn("afrp.png", rendered)
        self.assertIn("club.png", rendered)
        self.assertNotIn("{{", rendered)

    def test_text_field_removed_when_unmapped(self):
        mappings = dict(FULL_MAPPINGS)
        del mappings["{{MEMBER_ID}}"]
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, mappings)
        self.assertNotIn("ID-01234", rendered)
        self.assertNotIn("{{MEMBER_ID}}", rendered)

    def test_text_field_removed_when_field_visibility_false(self):
        mappings = dict(FULL_MAPPINGS)
        visibility = {"{{LOCAL_CLUB}}": False}
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, mappings, visibility)
        self.assertNotIn("Detroit", rendered)
        self.assertNotIn("{{LOCAL_CLUB}}", rendered)

    def test_table_number_removed_when_disabled(self):
        mappings = {k: v for k, v in FULL_MAPPINGS.items() if k != "{{TABLE_NUMBER}}"}
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, mappings)
        self.assertNotIn("Table 12", rendered)

    def test_meal_preference_removed_when_disabled(self):
        visibility = {"{{MEAL_PREFERENCE}}": False}
        rendered = render_badge_content(
            BADGE_SVG, SAMPLE_ROW, FULL_MAPPINGS, visibility
        )
        self.assertNotIn("Vegetarian", rendered)

    def test_subevent_removed_when_unmapped(self):
        mappings = {k: v for k, v in FULL_MAPPINGS.items() if k != "{{SUBEVENT_1}}"}
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, mappings)
        self.assertNotIn("{{SUBEVENT_1}}", rendered)

    def test_standalone_first_name_removed_when_unmapped(self):
        mappings = {k: v for k, v in FULL_MAPPINGS.items() if k != "{{FIRST_NAME}}"}
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, mappings)
        self.assertNotIn(">Sarah<", rendered)
        self.assertNotIn("{{FIRST_NAME}}", rendered)

    def test_qr_removed_when_unmapped(self):
        mappings = {k: v for k, v in FULL_MAPPINGS.items() if k != QR_CODE_PLACEHOLDER}
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, mappings)
        self.assertNotIn("qr_0.png", rendered)
        self.assertNotIn(QR_CODE_PLACEHOLDER, rendered)
        self.assertNotRegex(rendered, r"<image\b[^>]*qr_")

    def test_qr_removed_when_field_visibility_false(self):
        visibility = {QR_CODE_PLACEHOLDER: False}
        rendered = render_badge_content(
            BADGE_SVG, SAMPLE_ROW, FULL_MAPPINGS, visibility
        )
        self.assertNotIn("qr_0.png", rendered)
        self.assertNotIn(QR_CODE_PLACEHOLDER, rendered)

    def test_display_name_removed_when_disabled(self):
        visibility = {DISPLAY_NAME_PLACEHOLDER: False}
        rendered = render_badge_content(
            BADGE_SVG, SAMPLE_ROW, FULL_MAPPINGS, visibility
        )
        self.assertNotIn("Khoury", rendered)
        self.assertNotIn(DISPLAY_NAME_PLACEHOLDER, rendered)

    def test_display_name_omits_disabled_name_parts(self):
        visibility = {
            DISPLAY_NAME_PLACEHOLDER: True,
            "{{FIRST_NAME}}": False,
            "{{MAIDEN_NAME}}": False,
        }
        name = _build_display_name(SAMPLE_ROW, FULL_MAPPINGS, field_visibility=visibility)
        self.assertNotIn("Sarah", name)
        self.assertNotIn("Smith", name)
        self.assertIn("Marie", name)
        self.assertIn("Khoury", name)

    def test_afrp_logo_stripped_when_disabled(self):
        visibility = {AFRP_LOGO_PLACEHOLDER: False}
        rendered = render_badge_content(
            BADGE_SVG, SAMPLE_ROW, FULL_MAPPINGS, visibility
        )
        self.assertNotIn("afrp.png", rendered)
        self.assertNotIn(AFRP_LOGO_PLACEHOLDER, rendered)
        self.assertNotRegex(rendered, r"<image\b[^>]*afrp")

    def test_club_logo_stripped_when_disabled(self):
        visibility = {CLUB_LOGO_PLACEHOLDER: False}
        rendered = render_badge_content(
            BADGE_SVG, SAMPLE_ROW, FULL_MAPPINGS, visibility
        )
        self.assertNotIn("club.png", rendered)
        self.assertNotIn(CLUB_LOGO_PLACEHOLDER, rendered)
        self.assertNotRegex(rendered, r"<image\b[^>]*club")

    def test_field_visibility_loaded_from_element_layout(self):
        layout = {
            "_field_visibility": {
                QR_CODE_PLACEHOLDER: False,
                DISPLAY_NAME_PLACEHOLDER: True,
            }
        }
        self.assertEqual(
            _field_visibility_from_layout(layout),
            layout["_field_visibility"],
        )
        self.assertFalse(
            _is_field_enabled(
                QR_CODE_PLACEHOLDER,
                FULL_MAPPINGS,
                layout["_field_visibility"],
            )
        )

    def test_legacy_template_without_field_visibility_uses_column_mappings(self):
        mappings = {k: v for k, v in FULL_MAPPINGS.items() if k != "{{MEMBER_ID}}"}
        rendered = render_badge_content(BADGE_SVG, SAMPLE_ROW, mappings, None)
        self.assertNotIn("ID-01234", rendered)
        self.assertTrue(
            _is_field_enabled(DISPLAY_NAME_PLACEHOLDER, mappings, None)
        )
        mappings_no_qr = {
            k: v for k, v in FULL_MAPPINGS.items() if k != QR_CODE_PLACEHOLDER
        }
        self.assertFalse(
            _is_field_enabled(QR_CODE_PLACEHOLDER, mappings_no_qr, None)
        )


if __name__ == "__main__":
    unittest.main()
