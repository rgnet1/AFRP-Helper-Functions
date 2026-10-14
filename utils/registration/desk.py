"""Staff tools for my.afrp.org passwords and event-guest sign-ups."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import quote as url_quote

import requests

from utils.auth.campaign_access import (
    CampaignAccessDenied,
    user_campaign_is_restricted,
)
from utils.registration.payments import (
    ChargeQuote,
    PaymentDeclined,
    hosted_payment_token,
    default_profile_ref,
    inherit_merchant,
    load_event,
    load_profile,
    quote_add,
    quote_move,
)

# Event guest status reasons observed on crca7_eventguest.
STATUS_PAID = 104020002
STATUS_INACTIVE = 2
STATE_ACTIVE = 0
STATE_INACTIVE = 1

# Power Pages local accounts use ASP.NET Identity V2: one 0x00 marker byte,
# a 16-byte salt, and a 32-byte PBKDF2-HMAC-SHA1 subkey. The iteration count
# is fixed at 1,000 and is not stored in the hash.
_IDENTITY_ITERATIONS = 1000
_IDENTITY_SALT_BYTES = 16
_IDENTITY_SUBKEY_BYTES = 32


class RegistrationError(Exception):
    """A registration-desk action could not be completed."""


class ContactMatches(list):
    """Contacts from one shared lookup. truncated means more rows were left out."""

    def __init__(self, items=None, truncated=False):
        super().__init__(items or [])
        self.truncated = truncated


class HostedCheckout:
    """Card entry happens on Authorize.net. CRM changes wait until it succeeds."""

    def __init__(self, token: str, quote: ChargeQuote):
        self.token = token
        self.quote = quote


def hash_portal_password(password: str) -> str:
    """Return an ASP.NET Identity V2 password hash, which is what my.afrp.org checks."""
    salt = os.urandom(_IDENTITY_SALT_BYTES)
    subkey = hashlib.pbkdf2_hmac(
        "sha1",
        password.encode("utf-8"),
        salt,
        _IDENTITY_ITERATIONS,
        dklen=_IDENTITY_SUBKEY_BYTES,
    )
    payload = bytes([0x00]) + salt + subkey
    return base64.b64encode(payload).decode("ascii")


def _quote(value: str) -> str:
    return (value or "").replace("'", "''")


def _crm_date(value) -> Optional[date]:
    text = (value or "")[:10]
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


MEMBERSHIP_PAID = 124700002


class RegistrationDesk:
    """Read and update contacts and event guests through Dynamics."""

    def __init__(self, crm_client):
        self.crm = crm_client

    def parent_events_for(self, user) -> List[dict]:
        campaigns = self.crm.get_open_campaigns() or []
        if not user_campaign_is_restricted(user):
            return campaigns
        allowed = {
            (item or "").strip().lower()
            for item in (user.allowed_campaign_ids() or [])
        }
        return [
            row for row in campaigns
            if (row.get("id") or "").strip().lower() in allowed
        ]

    def sub_events(self, parent_id: str) -> List[dict]:
        return self.crm.get_sub_events(parent_id) or []

    def _require_parent(self, user, parent_id: str) -> None:
        from utils.auth.campaign_access import assert_campaign_access
        assert_campaign_access(user, parent_id)

    def _event_ids(self, parent_id: str) -> set:
        ids = {(parent_id or "").strip().lower()}
        for row in self.sub_events(parent_id):
            if row.get("id"):
                ids.add(row["id"].strip().lower())
        return ids

    def _require_event(self, user, parent_id: str, event_id: str) -> None:
        self._require_parent(user, parent_id)
        if (event_id or "").strip().lower() not in self._event_ids(parent_id):
            raise CampaignAccessDenied("That event is not part of the selected campaign")

    def find_contacts(self, email: str = "", first_name: str = "", last_name: str = "") -> ContactMatches:
        """Find contacts by email, first name, or last name. One field is enough."""
        address = (email or "").strip().lower()
        first = (first_name or "").strip()
        last = (last_name or "").strip()
        if not address and not first and not last:
            raise RegistrationError("Enter an email, first name, or last name")
        if address and "@" not in address:
            raise RegistrationError("Enter a full email address")
        clauses = []
        if address:
            clauses.append(f"emailaddress1 eq '{_quote(address)}'")
        if first:
            clauses.append(f"contains(firstname,'{_quote(first)}')")
        if last:
            clauses.append(f"contains(lastname,'{_quote(last)}')")
        filt = " and ".join(clauses)
        rows = self.crm._make_request(
            "contacts?$select=contactid,fullname,firstname,lastname,emailaddress1,"
            "aha_memberid,_aha_householdid_value,adx_identity_passwordhash,"
            "adx_identity_username"
            f"&$filter={url_quote(filt)}&$top=31"
        ).get("value") or []
        matches = []
        for row in rows:
            if address and (row.get("emailaddress1") or "").strip().lower() != address:
                continue
            if first and first.lower() not in (row.get("firstname") or "").lower():
                continue
            if last and last.lower() not in (row.get("lastname") or "").lower():
                continue
            contact_id = row.get("contactid")
            providers = self._identity_providers(contact_id)
            matches.append({
                "id": contact_id,
                "name": row.get("fullname") or "",
                "email": row.get("emailaddress1") or "",
                "member_id": row.get("aha_memberid") or "",
                "household_id": row.get("_aha_householdid_value") or "",
                "has_local_password": bool(row.get("adx_identity_passwordhash")),
                "username": row.get("adx_identity_username") or "",
                "google_sign_in": any(
                    "google" in (name or "").lower() for name in providers
                ),
                "identity_providers": providers,
            })
        truncated = len(rows) > 30
        return ContactMatches(matches[:30], truncated=truncated)

    def _identity_providers(self, contact_id: str) -> List[str]:
        if not contact_id:
            return []
        try:
            rows = self.crm._make_request(
                "adx_externalidentities?$select=adx_identityprovidername"
                f"&$filter=_adx_contactid_value eq {contact_id}&$top=10"
            ).get("value") or []
        except Exception:
            return []
        return [
            row.get("adx_identityprovidername")
            for row in rows
            if row.get("adx_identityprovidername")
        ]

    def household(self, household_id: str) -> List[dict]:
        if not household_id:
            return []
        rows = self.crm._make_request(
            "contacts?$select=contactid,fullname,emailaddress1,aha_memberid,"
            "crca7_aretheheadofhousehold"
            f"&$filter=_aha_householdid_value eq {household_id}&$top=30"
        ).get("value") or []
        people = []
        for row in rows:
            people.append({
                "id": row.get("contactid"),
                "name": row.get("fullname") or "",
                "email": row.get("emailaddress1") or "",
                "member_id": row.get("aha_memberid") or "",
                "head": bool(row.get("crca7_aretheheadofhousehold")),
            })
        people.sort(key=lambda person: (not person["head"], person["name"]))
        return people

    def guests_for_contact(self, contact_id: str, parent_id: str) -> List[dict]:
        filt = (
            f"_crca7_existingcontact_value eq {contact_id} and "
            f"(crca7_Event/campaignid eq {parent_id} or "
            f"crca7_Event/_aha_parentcampaign_value eq {parent_id})"
        )
        rows = self.crm._make_request(
            "crca7_eventguests?$select=crca7_eventguestid,statuscode,statecode,"
            "_crca7_event_value,_aha_transaction_value"
            f"&$filter={url_quote(filt)}&$top=100"
        ).get("value") or []
        guests = []
        for row in rows:
            guests.append({
                "id": row.get("crca7_eventguestid"),
                "event_id": row.get("_crca7_event_value") or "",
                "event_name": row.get(
                    "_crca7_event_value@OData.Community.Display.V1.FormattedValue"
                ) or "",
                "status": row.get(
                    "statuscode@OData.Community.Display.V1.FormattedValue"
                ) or "",
                "status_code": row.get("statuscode"),
                "active": row.get("statecode") == STATE_ACTIVE,
                "has_payment": bool(row.get("_aha_transaction_value")),
            })
        return guests

    def contact_on_event(self, user, contact_id: str, parent_id: str) -> bool:
        """True when this contact already has a guest row in the coordinator's event."""
        if not user_campaign_is_restricted(user):
            return True
        self._require_parent(user, parent_id)
        return any(
            (guest.get("event_id") or "").strip().lower() in self._event_ids(parent_id)
            for guest in self.guests_for_contact(contact_id, parent_id)
        )

    def set_local_password(self, user, contact_id: str, password: str) -> None:
        """Set a portal password for any contact. Coordinators and admins only."""
        is_admin = bool(getattr(user, "is_admin", False))
        coordinator = getattr(user, "is_event_coordinator", None)
        is_coordinator = bool(coordinator()) if callable(coordinator) else False
        if not is_admin and not is_coordinator:
            raise CampaignAccessDenied(
                "Only event coordinators and admins can reset a portal password"
            )
        self._send(
            "PATCH",
            f"contacts({contact_id})",
            {
                "adx_identity_passwordhash": hash_portal_password(password),
                "adx_identity_securitystamp": secrets.token_hex(16),
                "adx_identity_logonenabled": True,
                "adx_identity_accessfailedcount": 0,
                "adx_identity_lockoutenddate": None,
            },
        )

    def campaign_date_bounds(self, campaign_ids) -> List[dict]:
        """Start and end dates for coordinator password windows."""
        bounds = []
        for campaign_id in campaign_ids or []:
            cid = (campaign_id or "").strip()
            if not cid:
                continue
            row = self.crm._make_request(
                f"campaigns({cid})?$select=name,aha_proposedstart,aha_proposedend"
            )
            bounds.append({
                "name": row.get("name") or "",
                "start": _crm_date(row.get("aha_proposedstart")),
                "end": _crm_date(row.get("aha_proposedend")),
            })
        return bounds

    def convention_year(self, parent_id: str) -> int:
        row = self.crm._make_request(
            f"campaigns({parent_id})?$select=aha_proposedstart"
        )
        start = _crm_date(row.get("aha_proposedstart"))
        if not start:
            raise RegistrationError(
                "This event has no start date, so membership cannot be checked."
            )
        return start.year

    def has_paid_membership(self, contact_id: str, year: int) -> bool:
        filt = (
            f"_crca7_contact_value eq {contact_id} and aha_year eq {year} "
            f"and statuscode eq {MEMBERSHIP_PAID}"
        )
        rows = self.crm._make_request(
            "msnfp_memberships?$select=msnfp_membershipid"
            f"&$filter={url_quote(filt)}&$top=1"
        ).get("value") or []
        return bool(rows)

    def _on_parent(self, guests: List[dict], parent_id: str) -> bool:
        parent = (parent_id or "").strip().lower()
        return any(
            guest.get("active")
            and guest.get("status_code") == STATUS_PAID
            and (guest.get("event_id") or "").strip().lower() == parent
            for guest in guests
        )

    def _require_new_signup_rules(self, contact_id: str, parent_id: str, event_id: str, guests: List[dict]) -> None:
        """Membership for a first sign-up, and the main event before any sub-event."""
        on_parent = self._on_parent(guests, parent_id)
        on_convention = any(
            guest.get("active") and guest.get("status_code") == STATUS_PAID
            for guest in guests
        )
        if not on_convention:
            year = self.convention_year(parent_id)
            if not self.has_paid_membership(contact_id, year):
                raise RegistrationError(
                    f"This person needs a paid AFRP membership for {year} "
                    "before they can join this convention."
                )
        if (event_id or "").strip().lower() != (parent_id or "").strip().lower() and not on_parent:
            raise RegistrationError(
                "Sign this person up for the main event before a sub-event."
            )

    def add_guest(
        self,
        user,
        contact_id: str,
        parent_id: str,
        event_id: str,
        transaction_id: Optional[str] = None,
    ) -> None:
        self._require_event(user, parent_id, event_id)
        existing = self.guests_for_contact(contact_id, parent_id)
        self._require_new_signup_rules(contact_id, parent_id, event_id, existing)
        for guest in existing:
            if (
                (guest.get("event_id") or "").strip().lower() == event_id.strip().lower()
                and guest.get("active")
                and guest.get("status_code") == STATUS_PAID
            ):
                raise RegistrationError("This person is already signed up for that event")
        body = {
            "crca7_ExistingContact@odata.bind": f"/contacts({contact_id})",
            "crca7_Event@odata.bind": f"/campaigns({event_id})",
            "statecode": STATE_ACTIVE,
            "statuscode": STATUS_PAID,
        }
        if transaction_id:
            body["aha_Transaction@odata.bind"] = f"/msnfp_transactions({transaction_id})"
        self._send("POST", "crca7_eventguests", body)

    def event_requirements(self, event_id: str) -> dict:
        """Questions and seating tables for one event."""
        question_filter = f"_aha_campaign_value eq {event_id}"
        question_rows = self.crm._make_request(
            "aha_eventformquestionses?$select=aha_eventformquestionsid,aha_newcolumn,"
            "aha_choicelabels,aha_questiontype,aha_isrequiredquestion,aha_ismultilinetext,"
            "aha_displayorder"
            f"&$filter={url_quote(question_filter)}&$top=50"
        ).get("value") or []
        from utils.dynamics_crm import parse_choice_labels
        formatted = "@OData.Community.Display.V1.FormattedValue"
        questions = []
        for row in question_rows:
            text = (row.get("aha_newcolumn") or "").strip()
            if not text or not row.get("aha_eventformquestionsid"):
                continue
            questions.append({
                "id": row.get("aha_eventformquestionsid"),
                "question": text,
                "choices": parse_choice_labels(row.get("aha_choicelabels")),
                "required": bool(row.get("aha_isrequiredquestion")),
                "multiline": bool(row.get("aha_ismultilinetext")),
                "order": row.get("aha_displayorder") or 0,
                "type": row.get(f"aha_questiontype{formatted}") or "",
            })
        questions.sort(key=lambda item: (item["order"], item["question"]))
        table_filter = f"_aha_event_value eq {event_id} and statecode eq 0"
        table_rows = self.crm._make_request(
            "aha_seatingtables?$select=aha_seatingtableid,aha_name,"
            "aha_numberofchairs,aha_numberofseatsfilled"
            f"&$filter={url_quote(table_filter)}&$top=100"
        ).get("value") or []
        tables = []
        for row in table_rows:
            if not row.get("aha_seatingtableid"):
                continue
            chairs = row.get("aha_numberofchairs") or 0
            filled = row.get("aha_numberofseatsfilled") or 0
            tables.append({
                "id": row.get("aha_seatingtableid"),
                "name": row.get("aha_name") or "Table",
                "open_seats": max(0, int(chairs) - int(filled)) if chairs else None,
            })
        tables.sort(key=lambda item: item["name"])
        return {"questions": questions, "tables": tables}

    def save_signup_details(self, contact_id: str, event_id: str, answers, table_id: str = "") -> None:
        """Write form answers and a table seat after the sign-up is saved."""
        for answer in answers or []:
            question_id = (answer.get("question_id") or "").strip()
            response = (answer.get("response") or "").strip()
            if not question_id or not response:
                continue
            filt = (
                f"_aha_contact_value eq {contact_id} and "
                f"_aha_formquestion_value eq {question_id}"
            )
            existing = self.crm._make_request(
                "aha_eventformresponseses?$select=aha_eventformresponsesid"
                f"&$filter={url_quote(filt)}&$top=1"
            ).get("value") or []
            if existing and existing[0].get("aha_eventformresponsesid"):
                self._send(
                    "PATCH",
                    f"aha_eventformresponseses({existing[0]['aha_eventformresponsesid']})",
                    {"aha_guestresponse": response},
                )
                continue
            self._send(
                "POST",
                "aha_eventformresponseses",
                {
                    "aha_guestresponse": response,
                    "aha_Contact@odata.bind": f"/contacts({contact_id})",
                    "aha_Campaign@odata.bind": f"/campaigns({event_id})",
                    "aha_FormQuestion@odata.bind": (
                        f"/aha_eventformquestionses({question_id})"
                    ),
                },
            )
        table_id = (table_id or "").strip()
        if not table_id:
            return
        filt = (
            f"_aha_contact_value eq {contact_id} and _aha_event_value eq {event_id}"
        )
        existing = self.crm._make_request(
            "aha_tablereservations?$select=aha_tablereservationid"
            f"&$filter={url_quote(filt)}&$top=1"
        ).get("value") or []
        table_bind = {"aha_Table@odata.bind": f"/aha_seatingtables({table_id})"}
        if existing and existing[0].get("aha_tablereservationid"):
            self._send(
                "PATCH",
                f"aha_tablereservations({existing[0]['aha_tablereservationid']})",
                table_bind,
            )
            return
        self._send(
            "POST",
            "aha_tablereservations",
            {
                "aha_name": "Seat",
                "aha_Contact@odata.bind": f"/contacts({contact_id})",
                "aha_Event@odata.bind": f"/campaigns({event_id})",
                **table_bind,
            },
        )

    def priced_events(self, parent_id: str) -> dict:
        """Cost and merchant account for the parent event and each sub-event."""
        events = {}
        parent = load_event(self.crm, parent_id)
        if not parent.profile_id:
            fallback = default_profile_ref(self.crm)
            parent.profile_id = fallback.get("id")
            parent.profile_name = fallback.get("name") or parent.profile_name
        events[parent_id.lower()] = parent
        for sub in self.sub_events(parent_id):
            if not sub.get("id"):
                continue
            child = load_event(self.crm, sub["id"], parent_id)
            events[sub["id"].lower()] = inherit_merchant(child, parent)
        return events

    def quote_for_move(self, parent_id: str, from_event_id: str, to_event_id: str) -> ChargeQuote:
        prices = self.priced_events(parent_id)
        return quote_move(prices[from_event_id.lower()], prices[to_event_id.lower()])

    def quote_for_add(self, parent_id: str, event_id: str, people: int) -> ChargeQuote:
        event = self.priced_events(parent_id)[event_id.lower()]
        return quote_add([event] * max(people, 1))

    def collect(
        self,
        contact_id: str,
        quote: ChargeQuote,
        *,
        skip_payment: bool,
        return_url: str = "",
        cancel_url: str = "",
        communicator_url: str = "",
    ):
        """Open Authorize.net's card form. Saved cards are never charged."""
        if skip_payment or not quote.charges:
            return None
        if not (return_url or "").startswith("https://"):
            raise PaymentDeclined(
                "Authorize.net will not open a card form on this address. "
                "Open Helper with https, then try again. Or check Do not charge."
            )
        profile = load_profile(self.crm, quote.profile_id)
        token = hosted_payment_token(
            profile,
            quote.amount,
            return_url,
            cancel_url,
            communicator_url,
        )
        return HostedCheckout(token=token, quote=quote)

    def record_transaction(
        self,
        contact_id: str,
        event_id: str,
        profile_id: str,
        amount,
        transaction_id: str,
    ) -> Optional[str]:
        """Write the Authorize.net receipt. Returns the Dynamics transaction id."""
        created = self._send(
            "POST",
            "msnfp_transactions",
            {
                "msnfp_name": f"Event change {transaction_id}",
                "msnfp_amount": float(amount),
                "aha_totalamount": float(amount),
                "aha_authorizetransactionid": transaction_id,
                "aha_Contact@odata.bind": f"/contacts({contact_id})",
                "msnfp_receiptoncontactid@odata.bind": f"/contacts({contact_id})",
                "msnfp_OriginatingCampaignId@odata.bind": f"/campaigns({event_id})",
            },
        )
        return created.get("msnfp_transactionid")

    def move_guest(self, user, guest_id: str, parent_id: str, event_id: str) -> None:
        guest = self._guest(guest_id)
        current_event = guest.get("_crca7_event_value") or ""
        self._require_event(user, parent_id, current_event)
        self._require_event(user, parent_id, event_id)
        contact_id = guest.get("_crca7_existingcontact_value") or ""
        current = current_event.strip().lower()
        dest = (event_id or "").strip().lower()
        parent = (parent_id or "").strip().lower()
        guests = self.guests_for_contact(contact_id, parent_id) if contact_id else []
        if current == parent and dest != parent:
            other_subs = [
                row for row in guests
                if row.get("active")
                and row.get("status_code") == STATUS_PAID
                and (row.get("event_id") or "").strip().lower() != parent
                and row.get("id") != guest_id
            ]
            if other_subs:
                raise RegistrationError(
                    "Remove the other sign-ups before moving this person off the main event."
                )
            raise RegistrationError(
                "Keep the main event. Add the sub-event instead of moving the main sign-up."
            )
        if dest != parent and not self._on_parent(guests, parent_id):
            raise RegistrationError(
                "Sign this person up for the main event before a sub-event."
            )
        self._send(
            "PATCH",
            f"crca7_eventguests({guest_id})",
            {"crca7_Event@odata.bind": f"/campaigns({event_id})"},
        )

    def remove_guest(self, user, guest_id: str, parent_id: str) -> None:
        guest = self._guest(guest_id)
        self._require_event(user, parent_id, guest.get("_crca7_event_value") or "")
        self._send(
            "PATCH",
            f"crca7_eventguests({guest_id})",
            {"statecode": STATE_INACTIVE, "statuscode": STATUS_INACTIVE},
        )

    def _guest(self, guest_id: str) -> dict:
        return self.crm._make_request(
            "crca7_eventguests({})?$select=crca7_eventguestid,_crca7_event_value,"
            "_crca7_existingcontact_value,statuscode,statecode".format(guest_id)
        )

    def _send(self, method: str, endpoint: str, data: Optional[dict]) -> dict:
        url = f"{self.crm.crm_url}/api/data/v9.2/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.crm.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Prefer": "return=representation",
        }
        if method in ("PATCH", "DELETE"):
            headers["If-Match"] = "*"
        response = requests.request(
            method,
            url,
            headers=headers,
            json=data,
            timeout=60,
        )
        if response.status_code >= 400:
            detail = ""
            try:
                detail = ((response.json().get("error") or {}).get("message") or "")[:240]
            except ValueError:
                detail = (response.text or "")[:240]
            raise RegistrationError(detail or "Dynamics rejected the update")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}
