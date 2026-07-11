"""
Dynamics CRM field mappings discovered for stats aggregation.

Entity sets:
  - contacts: all people AFRP knows
  - msnfp_memberships: yearly membership records (nav: crca7_Membership on contact)
  - campaigns: events / conventions
  - crca7_eventguests: event attendance

Membership (msnfp_memberships):
  - aha_year: membership year (e.g. 2024)
  - statuscode 124700002: Paid
  - crca7_membershiptype: option set (Individual, Family, Student, ...)
  - aha_cost: dues amount
  - _crca7_contact_value: linked contact (often null for 2025+ bulk MEM-- rows)
  - aha_contactsassociated: associated contact name(s), comma-separated — use for linking

Contact engagement "tags" (aha_seatingtablerole, semicolon-separated):
  - "General" only => not engaged
  - "General; Board Seating", "General; Leadership", etc. => engaged

Convention identification:
  - name contains "Convention" AND year in name
  - aha_proposedstart year must match membership year
"""

MEMBERSHIP_ENTITY = "msnfp_memberships"
MEMBERSHIP_STATUS_PAID = 124700002
MEMBERSHIP_NAV_EXPAND = "crca7_Membership"

CONTACT_TAG_FIELD = "aha_seatingtablerole"
CONTACT_LOCAL_CLUB_FIELD = "_aha_localclub2_value"
CONTACT_MEMBER_ID_FIELD = "aha_memberid"
CONTACT_HOUSEHOLD_FIELD = "_aha_householdid_value"
CONTACT_HEAD_OF_HOUSEHOLD_FIELD = "crca7_aretheheadofhousehold"

CAMPAIGN_DATE_START = "aha_proposedstart"
CONVENTION_NAME_TOKEN = "Convention"
