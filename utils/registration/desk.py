"""Staff tools for my.afrp.org passwords and event-guest sign-ups."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import struct
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

# ASP.NET Core Identity V3 (Power Pages local accounts). 10,000 is the
# iteration count those portal hashes were created with.
_IDENTITY_ITERATIONS = 10000


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
    """Return an ASP.NET Identity V3 password hash (base64)."""
    salt = os.urandom(16)
    subkey = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _IDENTITY_ITERATIONS,
        dklen=32,
    )
    payload = bytearray(13 + len(salt) + len(subkey))
    payload[0] = 0x01
    payload[1:5] = struct.pack(">I", 1)  # HMAC-SHA256
    payload[5:9] = struct.pack(">I", _IDENTITY_ITERATIONS)
    payload[9:13] = struct.pack(">I", len(salt))
    payload[13:13 + len(salt)] = salt
    payload[13 + len(salt):] = subkey
    return base64.b64encode(payload).decode("ascii")


def _quote(value: str) -> str:
    return (value or "").replace("'", "''")


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
