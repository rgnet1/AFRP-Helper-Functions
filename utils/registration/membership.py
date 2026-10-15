"""Yearly AFRP membership products, household coverage, and purchase."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from urllib.parse import quote as url_quote

MEMBERSHIP_PAID = 124700002
MEMBERSHIP_NEXT_YEAR_MONTH = 10
CHILD_AGE = 18
RELATION_SELF = "Self"
RELATION_SPOUSE = "Spouse"
RELATION_CHILD = frozenset({"Son", "Daughter"})

# Option values on msnfp_membership.crca7_membershiptype.
TYPE_CODES = {
    "Al-Manara Lion": 104020000,
    "Patron": 104020001,
    "Family": 104020002,
    "Individual": 104020003,
    "Junior Al-Manara Lion": 104020004,
    "AFRP-Guest": 104020005,
    "Student": 124700001,
}

# Audience taken from msnfp_membershipcategories.crca7_description.
# self_min/self_max are inclusive. None means no bound.
CATEGORY_RULES = {
    "Individual": {"spouse": False, "children": False, "member": True},
    "Student": {"spouse": False, "children": False, "member": True, "self_min": 18, "self_max": 25},
    "Family": {"spouse": True, "children": True, "member": True},
    "Junior Al-Manara Lion": {
        "spouse": True, "children": True, "member": True, "self_under": 30,
    },
    "Al-Manara Lion": {
        "spouse": True, "children": True, "member": True, "self_at_least": 30,
    },
    "Patron": {"spouse": True, "children": True, "member": True},
    "AFRP-Guest": {"spouse": False, "children": False, "member": False},
}


def membership_years(today: date) -> list[int]:
    """Years staff may sell. Next year opens on October 1, matching the portal."""
    years = [today.year]
    if today.month >= MEMBERSHIP_NEXT_YEAR_MONTH:
        years.append(today.year + 1)
    return years


def category_rule(name: str) -> dict:
    return dict(CATEGORY_RULES.get(name) or {"spouse": False, "children": False, "member": True})


def age_on(birthday: date, today: date) -> int:
    years = today.year - birthday.year
    if (today.month, today.day) < (birthday.month, birthday.day):
        years -= 1
    return years


def parse_crm_date(value) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def person_age(person: dict, today: Optional[date] = None) -> Optional[float]:
    raw = person.get("age")
    if raw is not None and raw != "":
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    birthday = person.get("birthday")
    if isinstance(birthday, date):
        return float(age_on(birthday, today or date.today()))
    parsed = parse_crm_date(birthday)
    if parsed:
        return float(age_on(parsed, today or date.today()))
    return None


def is_child(person: dict, today: Optional[date] = None) -> bool:
    if (person.get("relationship") or "") in RELATION_CHILD:
        return True
    age = person_age(person, today)
    return age is not None and age < CHILD_AGE


def self_qualifies(category_name: str, self_person: dict, today: Optional[date] = None) -> tuple[bool, str]:
    rule = category_rule(category_name)
    age = person_age(self_person, today)
    bounded = any(key in rule for key in ("self_min", "self_max", "self_under", "self_at_least"))
    if bounded and age is None:
        return False, "Age is missing, so this level cannot be checked."
    if rule.get("self_min") is not None and age < rule["self_min"]:
        return False, f"This level starts at age {rule['self_min']}."
    if rule.get("self_max") is not None and age > rule["self_max"]:
        return False, f"This level ends at age {rule['self_max']}."
    if rule.get("self_under") is not None and age >= rule["self_under"]:
        return False, f"This level is for people under {rule['self_under']}."
    if rule.get("self_at_least") is not None and age < rule["self_at_least"]:
        return False, f"This level starts at age {rule['self_at_least']}."
    return True, ""


def choose_spouse(household: list[dict], chosen_id: str = "") -> tuple[Optional[dict], str]:
    spouses = [
        person for person in household
        if (person.get("relationship") or "") == RELATION_SPOUSE
    ]
    if not spouses:
        return None, ""
    if chosen_id:
        match = next((person for person in spouses if person.get("id") == chosen_id), None)
        if match:
            return match, ""
    if len(spouses) == 1:
        return spouses[0], ""
    return None, "This household has more than one spouse. Choose which one this membership covers."


def coverage_anchor(category_name: str, purchaser: dict, household: list[dict]) -> dict:
    """Household levels cover the household Self, not an adult child who starts the purchase."""
    rule = category_rule(category_name)
    if rule.get("spouse") or rule.get("children"):
        marked = next(
            (person for person in household if (person.get("relationship") or "") == RELATION_SELF),
            None,
        )
        if marked:
            return marked
    return purchaser


def cover_list(
    category_name: str,
    self_person: dict,
    household: list[dict],
    confirmed_child_ids: Optional[set] = None,
    spouse_id: str = "",
    today: Optional[date] = None,
) -> tuple[list[dict], str]:
    """People this purchase associates. Empty list means the purchase cannot proceed."""
    anchor = coverage_anchor(category_name, self_person, household)
    ok, reason = self_qualifies(category_name, anchor, today)
    if not ok:
        return [], reason
    rule = category_rule(category_name)
    covered = [anchor]
    if rule.get("spouse"):
        spouse, spouse_error = choose_spouse(household, spouse_id)
        if spouse_error:
            return [], spouse_error
        if spouse and spouse.get("id") != anchor.get("id"):
            covered.append(spouse)
    if rule.get("children"):
        confirmed = confirmed_child_ids or set()
        covered_ids = {person.get("id") for person in covered}
        for person in household:
            if person.get("id") in covered_ids:
                continue
            if not is_child(person, today):
                continue
            age = person_age(person, today)
            if age is None:
                if person.get("id") not in confirmed:
                    continue
            elif age >= CHILD_AGE:
                continue
            covered.append(person)
            covered_ids.add(person.get("id"))
    return covered, ""


def membership_satisfies_requirement(category_name: str) -> bool:
    return bool(category_rule(category_name).get("member"))


def _under_18(person: dict, today: Optional[date] = None) -> bool:
    age = person_age(person, today)
    return age is not None and age < CHILD_AGE


def _by_cost(category: dict) -> float:
    try:
        return float(category.get("cost") or 0)
    except (TypeError, ValueError):
        return 0.0


def _member_first(options: list[dict]) -> list[dict]:
    members = [item for item in options if membership_satisfies_requirement(item.get("name") or "")]
    return members or options


def individual_choices(person: dict, categories: list[dict], today: Optional[date] = None) -> list[dict]:
    """Levels that cover only this person. Household plans are not choices for an adult child."""
    choices = []
    for category in categories:
        rule = category_rule(category.get("name") or "")
        if rule.get("spouse") or rule.get("children"):
            continue
        covered, error = cover_list(category.get("name") or "", person, [person], today=today)
        if covered and not error:
            choices.append(category)
    choices.sort(key=_by_cost)
    return choices


def household_choices(
    household: list[dict],
    categories: list[dict],
    spouse_id: str = "",
    today: Optional[date] = None,
) -> list[tuple[dict, list[dict]]]:
    """Family and the more expensive household levels, cheapest first."""
    purchaser = next(
        (person for person in household if (person.get("relationship") or "") == RELATION_SELF),
        household[0] if household else None,
    )
    if not purchaser:
        return []
    choices = []
    for category in categories:
        rule = category_rule(category.get("name") or "")
        if not (rule.get("spouse") or rule.get("children")):
            continue
        covered, error = cover_list(
            category.get("name") or "",
            purchaser,
            household,
            spouse_id=spouse_id,
            today=today,
        )
        if covered and not error:
            choices.append((category, covered))
    choices.sort(key=lambda item: _by_cost(item[0]))
    return choices


def recommend_purchases(
    selected_ids: set,
    household: list[dict],
    categories: list[dict],
    spouse_id: str = "",
    today: Optional[date] = None,
) -> list[dict]:
    """Cheapest memberships for the people selected in the household.

    Self alone is Individual, or Student at 18–25. Self and Spouse together are
    Family, and children under 18 ride on that Family plan. Any other selected
    adult gets their own Student or Individual membership.
    """
    selected = {str(item) for item in selected_ids if item}
    people = [person for person in household if str(person.get("id")) in selected]
    if not people:
        return []
    self_person = next(
        (person for person in household if (person.get("relationship") or "") == RELATION_SELF),
        None,
    )
    spouse, _spouse_error = choose_spouse(household, spouse_id)
    selected_children = [person for person in people if _under_18(person, today)]
    spouse_exists = spouse is not None
    selected_self_or_spouse = any(
        (person.get("relationship") or "") in (RELATION_SELF, RELATION_SPOUSE)
        for person in people
    )
    force_family = spouse_exists and selected_self_or_spouse
    use_family = bool(selected_children) or force_family
    plans = []
    covered_ids = set()
    if use_family:
        options = household_choices(household, categories, spouse_id, today)
        if force_family:
            options = [item for item in options if (item[0].get("name") or "") == "Family"]
        member_options = [
            item for item in options
            if membership_satisfies_requirement(item[0].get("name") or "")
        ]
        pool = member_options or options
        if pool:
            category, covered = pool[0]
            plans.append({
                "recommended": category.get("name") or "",
                "category_id": category.get("id"),
                "cost": category.get("cost") or 0,
                "people": covered,
                "options": [item[0] for item in pool],
                "locked": force_family,
                "hint": (
                    "A spouse is in this household, so this must be Family."
                    if force_family
                    else "Cheapest household membership they qualify for."
                ),
            })
            covered_ids = {str(person.get("id")) for person in covered}
    for person in people:
        if str(person.get("id")) in covered_ids:
            continue
        if _under_18(person, today):
            continue
        options = _member_first(individual_choices(person, categories, today))
        if not options:
            plans.append({
                "recommended": "",
                "category_id": "",
                "people": [person],
                "options": [],
                "hint": f"{person.get('name') or 'This person'} does not qualify for a membership.",
            })
            continue
        category = options[0]
        age = person_age(person, today)
        if category.get("name") == "Student":
            hint = "Cheapest at ages 18–25."
        else:
            hint = "Cheapest for one adult."
        if age is not None and 18 <= age <= 25 and category.get("name") != "Student":
            hint = "Cheapest membership this person qualifies for."
        plans.append({
            "recommended": category.get("name") or "",
            "category_id": category.get("id"),
            "cost": category.get("cost") or 0,
            "people": [person],
            "options": options,
            "locked": False,
            "hint": hint,
        })
    return plans


MEMBERSHIP_NAV = "aha_Contact_msnfp_membership_msnfp_membership"


def _category_name(row: dict) -> str:
    return (
        row.get("_aha_membershipcategory_value@OData.Community.Display.V1.FormattedValue")
        or ""
    )


def person_is_covered(crm, contact_id: str, year: int) -> bool:
    """True when a paid Member membership for this year is linked to the person."""
    year_filter = f"aha_year eq {int(year)} and statuscode eq {MEMBERSHIP_PAID}"
    select = "msnfp_membershipid,_aha_membershipcategory_value"
    linked = crm._make_request(
        f"contacts({contact_id})/{MEMBERSHIP_NAV}?$select={select}"
        f"&$filter={url_quote(year_filter)}"
    ).get("value") or []
    direct = crm._make_request(
        f"msnfp_memberships?$select={select}"
        f"&$filter={url_quote(f'_crca7_contact_value eq {contact_id} and {year_filter}')}"
        "&$top=10"
    ).get("value") or []
    for row in linked + direct:
        name = _category_name(row)
        if name == "AFRP-Guest":
            continue
        if name and not membership_satisfies_requirement(name):
            continue
        return True
    return False


def load_categories(crm) -> list[dict]:
    rows = crm._make_request(
        "msnfp_membershipcategories?$select=msnfp_membershipcategoryid,msnfp_name,"
        "aha_cost,aha_applicablefor,crca7_description,statecode"
        "&$filter=statecode eq 0"
    ).get("value") or []
    categories = []
    for row in rows:
        name = row.get("msnfp_name") or ""
        categories.append({
            "id": row.get("msnfp_membershipcategoryid"),
            "name": name,
            "cost": row.get("aha_cost") or 0,
            "description": row.get("crca7_description") or "",
            "applicable_for": row.get(
                "aha_applicablefor@OData.Community.Display.V1.FormattedValue"
            ) or "",
            "member": membership_satisfies_requirement(name),
        })
    categories.sort(key=lambda item: (not item["member"], item["name"]))
    return categories


def _person_from_row(row: dict) -> dict:
    birthday = row.get("aha_birthday") or row.get("birthdate")
    return {
        "id": row.get("contactid"),
        "name": row.get("fullname") or "",
        "email": row.get("emailaddress1") or "",
        "relationship": row.get(
            "aha_relationshiptype@OData.Community.Display.V1.FormattedValue"
        ) or "",
        "age": row.get("crca7_age"),
        "birthday": birthday,
        "head": bool(row.get("crca7_aretheheadofhousehold")),
    }


def load_household(crm, contact_id: str) -> list[dict]:
    select = (
        "contactid,fullname,emailaddress1,crca7_age,aha_birthday,birthdate,"
        "aha_relationshiptype,_aha_householdid_value,crca7_aretheheadofhousehold"
    )
    row = crm._make_request(f"contacts({contact_id})?$select={select}")
    household_id = row.get("_aha_householdid_value")
    if not household_id:
        return [_person_from_row(row)]
    rows = crm._make_request(
        f"contacts?$select={select}"
        f"&$filter={url_quote(f'_aha_householdid_value eq {household_id}')}&$top=30"
    ).get("value") or []
    people = [_person_from_row(item) for item in rows] or [_person_from_row(row)]
    people.sort(key=lambda person: (person.get("id") != contact_id, not person["head"], person["name"]))
    return people


def event_requirements(crm, event_id: str) -> dict:
    row = crm._make_request(
        f"campaigns({event_id})?$select=name,aha_requirepaidafrpmembers,"
        "aha_hasagerestriction,aha_minimumage,aha_maximumage"
    )
    return {
        "name": row.get("name") or "",
        "membership_required": bool(row.get("aha_requirepaidafrpmembers")),
        "age_restricted": bool(row.get("aha_hasagerestriction")),
        "min_age": row.get("aha_minimumage"),
        "max_age": row.get("aha_maximumage"),
    }


def age_failure(rules: dict, person: dict) -> str:
    if not rules.get("age_restricted"):
        return ""
    age = person_age(person)
    if age is None:
        return f"{rules.get('name') or 'This event'} has an age limit and this person's age is missing."
    low = rules.get("min_age")
    high = rules.get("max_age")
    if low is not None and age < float(low):
        return f"{rules.get('name') or 'This event'} is for ages {low} and up."
    if high is not None and age > float(high):
        return f"{rules.get('name') or 'This event'} is for ages {high} and under."
    return ""


def money_cost(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))
