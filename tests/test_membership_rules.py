"""Household coverage rules for AFRP membership products."""

import unittest

from datetime import date

from utils.registration.membership import (
    cover_list,
    membership_years,
    recommend_purchases,
    self_qualifies,
)


def person(pid, relationship, age):
    return {"id": pid, "name": pid, "relationship": relationship, "age": age}


class MembershipYearTests(unittest.TestCase):
    def test_next_year_opens_in_october(self):
        self.assertEqual(membership_years(date(2026, 9, 30)), [2026])
        self.assertEqual(membership_years(date(2026, 10, 1)), [2026, 2027])


class MembershipRuleTests(unittest.TestCase):
    def test_family_covers_spouse_and_young_children(self):
        household = [
            person("self", "Self", 40),
            person("spouse", "Spouse", 38),
            person("kid", "Daughter", 10),
            person("adult-child", "Son", 20),
            person("other", "Adult", 35),
        ]
        covered, error = cover_list("Family", household[0], household)
        self.assertEqual(error, "")
        self.assertEqual({item["id"] for item in covered}, {"self", "spouse", "kid"})

    def test_child_without_age_needs_confirmation(self):
        household = [
            person("self", "Self", 40),
            person("kid", "Son", None),
        ]
        covered, error = cover_list("Family", household[0], household)
        self.assertEqual([item["id"] for item in covered], ["self"])
        covered, error = cover_list(
            "Family", household[0], household, confirmed_child_ids={"kid"}
        )
        self.assertEqual({item["id"] for item in covered}, {"self", "kid"})
        self.assertEqual(error, "")

    def test_two_spouses_block_the_purchase(self):
        household = [
            person("self", "Self", 40),
            person("a", "Spouse", 38),
            person("b", "Spouse", 36),
        ]
        covered, error = cover_list("Family", household[0], household)
        self.assertEqual(covered, [])
        self.assertIn("spouse", error.lower())
        covered, error = cover_list("Family", household[0], household, spouse_id="b")
        self.assertEqual({item["id"] for item in covered}, {"self", "b"})

    def test_student_and_al_manara_age_gates(self):
        young = person("self", "Self", 22)
        older = person("self", "Self", 40)
        self.assertTrue(self_qualifies("Student", young)[0])
        self.assertFalse(self_qualifies("Student", older)[0])
        self.assertFalse(self_qualifies("Junior Al-Manara Lion", older)[0])
        self.assertTrue(self_qualifies("Junior Al-Manara Lion", young)[0])
        self.assertTrue(self_qualifies("Al-Manara Lion", older)[0])
        self.assertFalse(self_qualifies("Al-Manara Lion", young)[0])

    def test_family_bought_by_an_adult_son_covers_the_household_self(self):
        household = [
            person("samir", "Self", 57),
            person("joyce", "Spouse", 53),
            person("jenna", "Daughter", 28),
            person("rami", "Son", 25),
            person("ramzey", "Son", 30),
        ]
        covered, error = cover_list("Family", household[-1], household)
        self.assertEqual(error, "")
        self.assertEqual([item["id"] for item in covered], ["samir", "joyce"])

    def test_cheapest_plan_for_self_spouse_and_an_adult_son(self):
        household = [
            person("samir", "Self", 57),
            person("joyce", "Spouse", 53),
            person("jenna", "Daughter", 28),
            person("rami", "Son", 25),
            person("ramzey", "Son", 30),
        ]
        categories = [
            {"id": "student", "name": "Student", "cost": 35},
            {"id": "individual", "name": "Individual", "cost": 85},
            {"id": "family", "name": "Family", "cost": 150},
            {"id": "lion", "name": "Al-Manara Lion", "cost": 500},
            {"id": "guest", "name": "AFRP-Guest", "cost": 100},
        ]
        plans = recommend_purchases({"samir", "joyce", "rami", "ramzey"}, household, categories)
        by_level = {plan["recommended"]: {person["id"] for person in plan["people"]} for plan in plans}
        self.assertEqual(by_level["Family"], {"samir", "joyce"})
        self.assertEqual(by_level["Student"], {"rami"})
        self.assertEqual(by_level["Individual"], {"ramzey"})

    def test_self_alone_is_individual_and_a_student_is_student(self):
        household = [
            person("samir", "Self", 57),
            person("joyce", "Spouse", 53),
            person("rami", "Son", 25),
        ]
        categories = [
            {"id": "student", "name": "Student", "cost": 35},
            {"id": "individual", "name": "Individual", "cost": 85},
            {"id": "family", "name": "Family", "cost": 150},
        ]
        alone = recommend_purchases({"samir"}, household, categories)
        self.assertEqual(alone[0]["recommended"], "Family")
        self.assertEqual({person["id"] for person in alone[0]["people"]}, {"samir", "joyce"})
        self.assertEqual([option["name"] for option in alone[0]["options"]], ["Family"])
        spouse_only = recommend_purchases({"joyce"}, household, categories)
        self.assertEqual(spouse_only[0]["recommended"], "Family")
        self.assertTrue(spouse_only[0]["locked"])
        student = recommend_purchases({"rami"}, household, categories)
        self.assertEqual(student[0]["recommended"], "Student")

    def test_individual_is_only_the_purchaser(self):
        household = [person("self", "Self", 40), person("spouse", "Spouse", 38)]
        covered, error = cover_list("Individual", household[0], household)
        self.assertEqual(error, "")
        self.assertEqual([item["id"] for item in covered], ["self"])


if __name__ == "__main__":
    unittest.main()
