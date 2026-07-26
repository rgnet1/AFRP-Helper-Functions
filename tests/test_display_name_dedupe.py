"""Tests for display-name deduplication of overlapping CRM name fields."""

import unittest

from utils.badges.display_name import build_display_name, dedupe_display_name_parts


def _build(row: dict, config: dict | None = None) -> str:
    def value_getter(_placeholder: str, column: str) -> str:
        return str(row.get(column, ""))

    return build_display_name(row, {}, config, value_getter=value_getter)


class TestDisplayNameDedupe(unittest.TestCase):
    CONVENTION_CONFIG = {
        "include_title": True,
        "include_middle": True,
        "include_maiden": True,
        "parentheses_middle": False,
        "parentheses_maiden": True,
    }

    def test_hanna_hanania_crm_overlap(self):
        row = {
            "Title": "Mr.",
            "First Name": "Hanna Nader",
            "Middle Name": "N.",
            "Maiden Name": "Hanania",
            "Last Name": "Hanania",
            "Gender": "Male",
        }
        self.assertEqual(
            _build(row, self.CONVENTION_CONFIG),
            "Mr. Hanna Nader Hanania",
        )

    def test_normal_name_unchanged(self):
        row = {
            "Title": "Mrs.",
            "First Name": "Sarah",
            "Middle Name": "Marie",
            "Maiden Name": "Smith",
            "Last Name": "Khoury",
            "Gender": "Female",
        }
        self.assertEqual(
            _build(row, self.CONVENTION_CONFIG),
            "Mrs. Sarah Marie (Smith) Khoury",
        )

    def test_maiden_equal_to_last_is_omitted(self):
        row = {
            "First Name": "Gianna",
            "Middle Name": "",
            "Maiden Name": "Ajlouny",
            "Last Name": "Ajlouny",
            "Gender": "Female",
        }
        self.assertEqual(_build(row), "Gianna Ajlouny")

    def test_middle_duplicates_last_first_name_token(self):
        first, middle, maiden, last = dedupe_display_name_parts(
            "Ibrahim Shukri",
            "Shukri",
            "",
            "Ganim",
            gender="Male",
        )
        self.assertEqual((first, middle, maiden, last), ("Ibrahim Shukri", "", "", "Ganim"))

    def test_female_maiden_embedded_in_first_name(self):
        row = {
            "Title": "Mrs.",
            "First Name": "Mimi Nazzal",
            "Middle Name": "Nazzal",
            "Maiden Name": "Nazzal",
            "Last Name": "Petros",
            "Gender": "Female",
        }
        self.assertEqual(
            _build(row, self.CONVENTION_CONFIG),
            "Mrs. Mimi (Nazzal) Petros",
        )

    def test_female_maiden_in_first_without_middle(self):
        row = {
            "First Name": "Anoulla Salamy",
            "Middle Name": "Salamy",
            "Maiden Name": "Salamy",
            "Last Name": "Ryan",
            "Gender": "Female",
        }
        self.assertEqual(_build(row), "Anoulla (Salamy) Ryan")

    def test_skip_dedupe_when_first_equals_last(self):
        row = {
            "First Name": "Harb",
            "Middle Name": "J",
            "Maiden Name": "Harb",
            "Last Name": "HARB",
            "Gender": "Male",
        }
        self.assertEqual(_build(row), "Harb J (Harb) HARB")

    def test_dedupe_still_applies_when_first_differs_from_last(self):
        row = {
            "First Name": "MATTHEW",
            "Middle Name": "J",
            "Maiden Name": "HARB",
            "Last Name": "HARB",
            "Gender": "Male",
        }
        self.assertEqual(_build(row), "MATTHEW J HARB")

    def test_male_maiden_duplicates_middle_is_omitted(self):
        row = {
            "Title": "Mr.",
            "First Name": "Mathew",
            "Middle Name": "Farid",
            "Maiden Name": "farid",
            "Last Name": "Bishara",
            "Gender": "Male",
        }
        self.assertEqual(
            _build(row, self.CONVENTION_CONFIG),
            "Mr. Mathew Farid Bishara",
        )

    def test_female_maiden_contains_middle_keeps_parentheses(self):
        row = {
            "First Name": "Samira",
            "Middle Name": "Rose",
            "Maiden Name": "Rose Marie",
            "Last Name": "Khoury",
            "Gender": "Female",
        }
        self.assertEqual(_build(row), "Samira (Rose Marie) Khoury")

    def test_maiden_kept_when_middle_overlaps_but_first_equals_last(self):
        row = {
            "First Name": "Harb",
            "Middle Name": "Farid",
            "Maiden Name": "Farid",
            "Last Name": "HARB",
            "Gender": "Male",
        }
        self.assertEqual(_build(row), "Harb Farid (Farid) HARB")

    def test_template_respects_include_maiden_false(self):
        row = {
            "Title": "Mrs.",
            "First Name": "Mimi Nazzal",
            "Middle Name": "Nazzal",
            "Maiden Name": "Nazzal",
            "Last Name": "Petros",
            "Gender": "Female",
        }
        config = dict(self.CONVENTION_CONFIG)
        config["include_maiden"] = False
        config["include_middle"] = False
        self.assertEqual(_build(row, config), "Mrs. Mimi Petros")

    def test_template_respects_parentheses_maiden_false(self):
        row = {
            "First Name": "Sarah",
            "Middle Name": "Marie",
            "Maiden Name": "Smith",
            "Last Name": "Khoury",
            "Gender": "Female",
        }
        config = {
            "include_title": False,
            "include_middle": True,
            "include_maiden": True,
            "parentheses_middle": False,
            "parentheses_maiden": False,
        }
        self.assertEqual(_build(row, config), "Sarah Marie Smith Khoury")


if __name__ == "__main__":
    unittest.main()
