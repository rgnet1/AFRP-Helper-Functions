---
name: afrp-membership
description: Documents AFRP yearly membership products, household coverage, age rules, and how a paid membership satisfies a campaign that requires one. Use when changing membership purchase, event sign-up eligibility, spouse or child coverage, or queries against msnfp_memberships and msnfp_membershipcategories.
---

# AFRP membership

A yearly membership is `msnfp_memberships`. The product menu is `msnfp_membershipcategories`. Helper purchase and the event gate live in `utils/registration/membership.py` and `utils/registration/desk.py`.

This is not `contacts.aha_activemember` and not `contacts._crca7_membership_value`. Those fields are often empty on a real paid membership.

## Who is covered

Coverage is the many-to-many `aha_Contact_msnfp_membership_msnfp_membership` (intersect entity `aha_contact_msnfp_membership`).

A person is covered for a calendar year when they are linked to a membership with:

- `aha_year` equal to that year
- `statuscode` `124700002` (Paid)
- category `aha_applicablefor` **Member**

`AFRP-Guest` is `aha_applicablefor` AFRP Guest. It does not satisfy `campaigns.aha_requirepaidafrpmembers`.

`_crca7_contact_value` on the membership is a legacy payer lookup. Do not use it as the only coverage test. Family rows often leave it null.

## Household logic

Coverage follows `contacts.aha_relationshiptype` on the household, not the person who opened the page. Roles: Self, Spouse, Son, Daughter, Adult. Everyone in one household shares `_aha_householdid_value`.

Family, Junior Al-Manara Lion, Al-Manara Lion, and Patron always start from the household **Self**, then add one **Spouse**, then add children **under 18**. A Son or Daughter who is 18 or older is never on those memberships. That stays true when the adult child is the one starting the purchase.

Example: Samir is Self (57), Joyce is Spouse (53), Jenna is Daughter (28), Rami is Son (25), Ramzey is Son (30). Ramzey opens Family. The membership applies only to **Samir and Joyce**. There is no one under 18. Ramzey is not included.

- Two people with relationship Spouse block the purchase until staff pick one. An Adult is not a spouse.
- A child is Son or Daughter, or anyone under 18. A child with no age stays off until staff confirm them.
- Age is `crca7_age`. If that is empty, use `aha_birthday`, then `birthdate`.
- Individual and Student cover only the person being purchased for. They do not pull in the household Self.

## Purchase steps

Match the my.afrp.org membership purchase. It is two steps.

1. Staff choose which people in the household to buy for. The person who opened the page starts checked. Someone already covered for the selected year stays unchecked.
2. The page splits that selection into memberships and preselects the cheapest qualifying level. Staff can switch to another level that still qualifies. Each membership names who it applies to, and that note must be confirmed before save.

Cheapest split:

- One adult alone is **Individual**. At ages 18–25, **Student** is cheaper, so preselect Student.
- If the selection includes the household Self or the Spouse, and a Spouse exists, the membership is **Family** and Individual is not a choice. That Family plan applies to the Self, the Spouse, and children under 18, even when only one of the adults was checked.
- A selected child under 18 is covered by that **Family** plan, not by a membership of their own. Family still applies to the household Self and Spouse.
- A Son or Daughter age 18 or older is a separate membership: Student at 18–25, otherwise Individual.
- Al-Manara, Junior Al-Manara, and Patron stay available as more expensive household levels. They are not the preselected choice when Family qualifies.

Before the purchase is saved, the page must name that exact list. Staff confirm it. Do not describe Family as covering "this purchase" when the buyer is an adult child.

## Products

Read price and audience from `msnfp_membershipcategories` (`aha_cost`, `aha_applicablefor`, `crca7_description`). Do not hardcode prices in new code. The rules below match those descriptions.

| Category | Who qualifies | Who is associated |
|----------|----------------|-------------------|
| Individual | the purchaser, any age | that person only |
| Student | the purchaser, age 18 through 25 | that person only |
| Family | household Self, any age | Self, one Spouse, children under 18 |
| Junior Al-Manara Lion | household Self under 30 | Self, one Spouse, children under 18 |
| Al-Manara Lion | household Self age 30 or older | Self, one Spouse, children under 18 |
| Patron | household Self, any age | Self, one Spouse, children under 18 |
| AFRP-Guest | the purchaser, any age | that person only, and it is not a Member product |

The membership year is January 1 through December 31 (`msnfp_startdate`, `msnfp_enddate`) and `aha_year`. Event checks use the main event’s `aha_proposedstart` year. Staff pick the year on the membership page. The current year is always offered. Next year is offered from October 1 in America/Los_Angeles, the same window as my.afrp.org. A year outside that list is rejected.

## Event gate

On `campaigns`, for the main event and each sub-event:

| Field | Meaning |
|-------|---------|
| `aha_requirepaidafrpmembers` | This sign-up needs a paid Member membership for the main event’s year |
| `aha_hasagerestriction` plus `aha_minimumage` / `aha_maximumage` | Age window for that campaign |
| `aha_isthissubeventregistrationrequired` | Not a membership rule. It does not create a banquet sign-up |

Check the flag on the campaign being joined, including a later sub-event. Being signed up for the meeting already does not skip the check.

Charge with the hosted Authorize.net page. Never charge `aha_authorizecustomerid`. The merchant account is the org default `aha_authorizenetprofiles` row (`aha_isdefault`). The receipt is `msnfp_transactions`, bound on the membership as `aha_msnfp_Transaction`.

## Writes

One paid membership row, then associate each covered contact:

`POST msnfp_memberships({id})/aha_Contact_msnfp_membership_msnfp_membership/$ref`

`{"@odata.id": "{crm}/api/data/v9.2/contacts({contactid})"}`

Set `aha_contactsassociated` to the covered names and `aha_numberofcontactsassociated` to that count. Set `crca7_membershiptype` to the matching option (Individual `104020003`, Family `104020002`, Student `124700001`, Al-Manara Lion `104020000`, Patron `104020001`, Junior Al-Manara Lion `104020004`, AFRP-Guest `104020005`).
