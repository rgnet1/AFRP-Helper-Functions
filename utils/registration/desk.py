"""Staff tools for my.afrp.org passwords and event-guest sign-ups."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import secrets
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from urllib.parse import quote as url_quote

import requests

from utils.auth.campaign_access import (
    CampaignAccessDenied,
    user_campaign_is_restricted,
)
from utils.registration.membership import (
    MEMBERSHIP_NAV,
    TYPE_CODES,
    age_failure,
    choose_spouse,
    cover_list,
    event_requirements,
    load_categories,
    load_household,
    person_is_covered,
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


def _choice_labels(raw) -> list:
    text = (raw or "").strip()
    if not text:
        return []
    if "~" in text:
        parts = text.split("~")
    elif ";" in text:
        parts = text.split(";")
    elif "," in text:
        parts = text.split(",")
    else:
        parts = [text]
    return [part.strip() for part in parts if part and part.strip()]


# Meal and allergy questions stay paired when the banquet renames them
# ("meal preference" / "dinner entree", "food allergies" / "dietary restrictions").
# A score under this line is a different question, so its answer is not copied.
_QUESTION_THRESHOLD = 0.62
_CHOICE_THRESHOLD = 0.7
_MEAL_WORDS = frozenset({
    "meal", "meals", "dinner", "dinners", "entree", "entrees", "dish", "dishes",
    "menu", "menus", "cuisine", "lunch", "lunches", "supper", "breakfast", "brunch",
})
_ALLERGY_WORDS = frozenset({
    "allergy", "allergies", "allergic", "allergen", "allergens", "dietary", "diet",
    "diets", "restriction", "restrictions", "intolerance", "intolerances",
    "intolerant", "sensitivity", "sensitivities",
})
_PREFERENCE_WORDS = frozenset({
    "preference", "preferences", "choice", "choices", "option", "options",
    "selection", "selections", "select", "choose",
})
_CHILD_WORDS = frozenset({"child", "children", "kid", "kids", "youth", "youths"})
_SYNONYM_GROUPS = (
    ("meal", _MEAL_WORDS),
    ("allergy", _ALLERGY_WORDS),
    ("preference", _PREFERENCE_WORDS),
    ("child", _CHILD_WORDS),
)
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "have", "has", "had", "having",
    "you", "your", "yours", "we", "our", "ours", "us", "i", "my", "me",
    "any", "some", "this", "that", "these", "those", "there",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "please", "should", "would", "could", "will", "can", "may", "if",
    "with", "about", "from", "into", "aware", "it", "its", "also",
    "let", "know", "list", "describe", "explain", "provide", "enter",
    "tell", "share", "specify", "include", "indicate", "additional",
    "other", "others", "need", "needed", "needs",
})


def _normalize_words(text: str) -> str:
    """Lowercase, drop punctuation, and collapse whitespace."""
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^\w\s]", " ", folded.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _meaningful_tokens(text: str) -> list:
    return [
        token for token in _normalize_words(text).split()
        if len(token) > 1 and token not in _STOP_WORDS
    ]


def _concepts(text: str) -> set:
    found = set()
    for token in _meaningful_tokens(text):
        grouped = False
        for name, group in _SYNONYM_GROUPS:
            if token in group:
                found.add(name)
                grouped = True
                break
        if not grouped:
            found.add(token)
    return found


def _question_kind(text: str) -> str:
    tokens = set(_meaningful_tokens(text))
    if tokens & _ALLERGY_WORDS:
        return "allergy"
    if tokens & _MEAL_WORDS:
        return "meal"
    return ""


def _jaccard(left: set, right: set) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _question_score(left: str, right: str) -> float:
    """How likely these two prompts are the same kind of question."""
    jaccard = _jaccard(_concepts(left), _concepts(right))
    sequence = SequenceMatcher(None, _normalize_words(left), _normalize_words(right)).ratio()
    left_kind = _question_kind(left)
    right_kind = _question_kind(right)
    if left_kind and right_kind and left_kind != right_kind:
        base = min(jaccard, 0.35)
    elif left_kind and right_kind:
        base = 0.42 + (0.58 * jaccard)
    elif left_kind or right_kind:
        base = jaccard if jaccard >= 0.8 else min(jaccard, 0.35)
    else:
        base = max(jaccard, sequence)
    return base + (0.001 * sequence)


def _choice_score(answer: str, choice: str) -> float:
    if _normalize_words(answer) == _normalize_words(choice):
        return 1.0
    left = _concepts(answer)
    right = _concepts(choice)
    overlap = len(left & right) if left and right else 0
    sequence = SequenceMatcher(
        None, _normalize_words(answer), _normalize_words(choice)
    ).ratio()
    if not overlap:
        return sequence if sequence >= 0.9 else 0.0
    jaccard = overlap / len(left | right)
    containment = overlap / min(len(left), len(right))
    return max(jaccard, 0.92 * containment, sequence)


def _choice_for_answer(answer: str, choices: list):
    """Return the offered choice to select, and a note when none is close."""
    text = re.sub(r"\s+", " ", (answer or "")).strip()
    if not text:
        return "", ""
    if not choices:
        return text, ""
    for choice in choices:
        if _normalize_words(choice) == _normalize_words(text):
            return choice, ""
    best = ""
    best_score = 0.0
    for choice in choices:
        score = _choice_score(text, choice)
        if score > best_score or (score == best_score and best and len(choice) < len(best)):
            best_score = score
            best = choice
    if best and best_score >= _CHOICE_THRESHOLD:
        return best, ""
    return "", text


def _assign_question_pairs(scores: list, threshold: float) -> Dict[int, int]:
    """One source per destination. The pairing is the one with the highest total."""
    if not scores or not scores[0]:
        return {}
    dest_count = len(scores)
    source_count = len(scores[0])
    if min(dest_count, source_count) > 12:
        return _greedy_question_pairs(scores, threshold)
    if source_count <= dest_count:
        return _mask_question_pairs(scores, threshold)
    transposed = [
        [scores[dest][source] for dest in range(dest_count)]
        for source in range(source_count)
    ]
    flipped = _mask_question_pairs(transposed, threshold)
    return {dest: source for source, dest in flipped.items()}


def _mask_question_pairs(scores: list, threshold: float) -> Dict[int, int]:
    dest_count = len(scores)
    source_count = len(scores[0])
    width = 1 << source_count
    negative = -1e9
    score_at = [[negative] * width for _ in range(dest_count + 1)]
    picked = [[-2] * width for _ in range(dest_count + 1)]
    score_at[0][0] = 0.0
    for dest in range(dest_count):
        row = scores[dest]
        for mask in range(width):
            current = score_at[dest][mask]
            if current <= negative / 2:
                continue
            if current > score_at[dest + 1][mask]:
                score_at[dest + 1][mask] = current
                picked[dest + 1][mask] = -1
            for source in range(source_count):
                bit = 1 << source
                if mask & bit:
                    continue
                weight = row[source]
                if weight < threshold:
                    continue
                nxt = mask | bit
                total = current + weight
                if total > score_at[dest + 1][nxt]:
                    score_at[dest + 1][nxt] = total
                    picked[dest + 1][nxt] = source
    best_mask = 0
    best_score = score_at[dest_count][0]
    for mask in range(1, width):
        if score_at[dest_count][mask] > best_score:
            best_score = score_at[dest_count][mask]
            best_mask = mask
    assignment: Dict[int, int] = {}
    mask = best_mask
    for dest in range(dest_count, 0, -1):
        source = picked[dest][mask]
        if source is None or source < -1:
            break
        if source >= 0:
            assignment[dest - 1] = source
            mask &= ~(1 << source)
    return assignment


def _greedy_question_pairs(scores: list, threshold: float) -> Dict[int, int]:
    edges = []
    for dest, row in enumerate(scores):
        for source, weight in enumerate(row):
            if weight >= threshold:
                edges.append((weight, dest, source))
    edges.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_dest = set()
    used_source = set()
    assignment: Dict[int, int] = {}
    for _weight, dest, source in edges:
        if dest in used_dest or source in used_source:
            continue
        used_dest.add(dest)
        used_source.add(source)
        assignment[dest] = source
    return assignment


def carry_question_answers(source_questions, destination_questions) -> list:
    """Copy each saved source answer onto one blank destination question of the same kind.

    The prompts do not have to use the same words. Each source answer is used
    once, for the destination it fits best. Choice lists keep an offered
    choice; when nothing offered is close, the answer stays blank and
    previous_answer records what was saved before.
    """
    carried = []
    for row in destination_questions or []:
        copied = dict(row)
        copied.pop("previous_answer", None)
        carried.append(copied)
    open_indexes = [
        index for index, row in enumerate(carried)
        if not (row.get("answer") or "").strip() and (row.get("question") or "").strip()
    ]
    sources = [
        row for row in (source_questions or [])
        if (row.get("answer") or "").strip() and (row.get("question") or "").strip()
    ]
    if not open_indexes or not sources:
        return carried
    scores = [
        [
            _question_score(carried[index].get("question") or "", source.get("question") or "")
            for source in sources
        ]
        for index in open_indexes
    ]
    for dest_slot, source_slot in _assign_question_pairs(scores, _QUESTION_THRESHOLD).items():
        dest = carried[open_indexes[dest_slot]]
        source_answer = (sources[source_slot].get("answer") or "").strip()
        matched, previous = _choice_for_answer(source_answer, dest.get("choices") or [])
        dest["answer"] = matched
        if previous:
            dest["previous_answer"] = previous
    return carried


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
        if (event_id or "").strip().lower() != (parent_id or "").strip().lower() and not on_parent:
            raise RegistrationError(
                "Sign this person up for the main event before a sub-event."
            )
        rules = event_requirements(self.crm, event_id)
        household = load_household(self.crm, contact_id)
        self_person = next(
            (person for person in household if person.get("id") == contact_id),
            {"id": contact_id, "age": None},
        )
        if rules["membership_required"]:
            year = self.convention_year(parent_id)
            if not person_is_covered(self.crm, contact_id, year):
                raise RegistrationError(
                    f"This person needs a paid AFRP membership for {year} "
                    "before they can join this event."
                )
        age_message = age_failure(rules, self_person)
        if age_message:
            raise RegistrationError(age_message)

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

    def event_requirements(self, event_id: str, contact_id: str = "") -> dict:
        """Questions and seating tables for one event."""
        question_filter = f"_aha_campaign_value eq {event_id}"
        question_rows = self.crm._make_request(
            "aha_eventformquestionses?$select=aha_eventformquestionsid,aha_newcolumn,"
            "aha_choicelabels,aha_questiontype,aha_isrequiredquestion,aha_ismultilinetext,"
            "aha_displayorder"
            f"&$filter={url_quote(question_filter)}&$top=50"
        ).get("value") or []
        formatted = "@OData.Community.Display.V1.FormattedValue"
        questions = []
        for row in question_rows:
            text = (row.get("aha_newcolumn") or "").strip()
            if not text or not row.get("aha_eventformquestionsid"):
                continue
            questions.append({
                "id": row.get("aha_eventformquestionsid"),
                "question": text,
                "choices": _choice_labels(row.get("aha_choicelabels")),
                "required": bool(row.get("aha_isrequiredquestion")),
                "multiline": bool(row.get("aha_ismultilinetext")),
                "order": row.get("aha_displayorder") or 0,
                "type": row.get(f"aha_questiontype{formatted}") or "",
            })
        questions.sort(key=lambda item: (item["order"], item["question"]))
        return {"questions": questions, "tables": self.live_tables(event_id, contact_id)}

    def event_questions(self, event_id: str, contact_id: str = "") -> list:
        """Questions for one sub-event. Saved answers match on question id, not wording."""
        question_rows = self.crm._make_request(
            "aha_eventformquestionses?$select=aha_eventformquestionsid,aha_newcolumn,"
            "aha_choicelabels,aha_questiontype,aha_isrequiredquestion,aha_ismultilinetext,"
            "aha_displayorder"
            f"&$filter={url_quote(f'_aha_campaign_value eq {event_id}')}&$top=50"
        ).get("value") or []
        answers = {}
        contact_id = (contact_id or "").strip()
        if contact_id:
            response_rows = self.crm._make_request(
                "aha_eventformresponseses?$select=aha_guestresponse,_aha_formquestion_value"
                "&$filter="
                + url_quote(
                    f"_aha_contact_value eq {contact_id} and _aha_campaign_value eq {event_id}"
                )
                + "&$top=50"
            ).get("value") or []
            for row in response_rows:
                question_key = (row.get("_aha_formquestion_value") or "").lower()
                if question_key:
                    answers[question_key] = row.get("aha_guestresponse") or ""
        formatted = "@OData.Community.Display.V1.FormattedValue"
        questions = []
        for row in question_rows:
            text = (row.get("aha_newcolumn") or "").strip()
            question_id = row.get("aha_eventformquestionsid")
            if not text or not question_id:
                continue
            questions.append({
                "id": question_id,
                "question": text,
                "choices": _choice_labels(row.get("aha_choicelabels")),
                "required": bool(row.get("aha_isrequiredquestion")),
                "multiline": bool(row.get("aha_ismultilinetext")),
                "order": row.get("aha_displayorder") or 0,
                "type": row.get(f"aha_questiontype{formatted}") or "",
                "answer": answers.get(str(question_id).lower(), ""),
            })
        questions.sort(key=lambda item: (item["order"], item["question"]))
        return questions

    def questions_for_move(self, event_id: str, contact_id: str = "", from_event_id: str = "") -> list:
        """Destination questions, with blank answers filled from the banquet being left."""
        questions = self.event_questions(event_id, contact_id)
        source_id = (from_event_id or "").strip()
        if not source_id or source_id.lower() == (event_id or "").strip().lower():
            return questions
        source = self.event_questions(source_id, contact_id)
        return carry_question_answers(source, questions)

    def live_tables(self, event_id: str, contact_id: str = "", include_people: bool = False, with_reservations: bool = True) -> list:
        """Tables for one event with a live seat count, not the delayed rollup.

        Occupancy is the number of active reservations. A VIP or reserved table
        stays selectable for staff while it has an open chair. A full table is
        not, except the contact's own current seat. Names come from that same
        reservation list when include_people is set, so the chart does not
        ask Dynamics twice.
        """
        table_rows = self.crm._make_request(
            "aha_seatingtables?$select=aha_seatingtableid,aha_name,aha_numberofchairs,"
            "aha_isreservedforvips,crca7_tablenumberint"
            f"&$filter={url_quote(f'_aha_event_value eq {event_id} and statecode eq 0')}"
            "&$top=200"
        ).get("value") or []
        reservations = []
        if with_reservations:
            reservation_filter = url_quote(f"_aha_event_value eq {event_id} and statecode eq 0")
            path = (
                "aha_tablereservations?$select=_aha_table_value,_aha_contact_value"
                f"&$filter={reservation_filter}"
            )
            if include_people:
                path += "&$expand=aha_Contact($select=fullname,emailaddress1)"
            try:
                reservations = self.crm._paginate(path)
            except Exception:
                if not include_people:
                    raise
                reservations = self.crm._paginate(
                    "aha_tablereservations?$select=_aha_table_value,_aha_contact_value"
                    f"&$filter={reservation_filter}"
                )
        seated = {}
        people = {}
        current_table = ""
        contact_key = (contact_id or "").lower()
        for row in reservations:
            table_key = (row.get("_aha_table_value") or "").lower()
            if not table_key:
                continue
            seated[table_key] = seated.get(table_key, 0) + 1
            if contact_key and (row.get("_aha_contact_value") or "").lower() == contact_key:
                current_table = table_key
            if include_people:
                contact = row.get("aha_Contact") or {}
                people.setdefault(table_key, []).append({
                    "id": row.get("_aha_contact_value") or "",
                    "name": contact.get("fullname") or "Guest",
                    "email": contact.get("emailaddress1") or "",
                    "table_id": row.get("_aha_table_value") or "",
                })
        from utils.registration.seating import table_kind
        tables = []
        for row in table_rows:
            table_id = row.get("aha_seatingtableid")
            if not table_id:
                continue
            chairs = int(row.get("aha_numberofchairs") or 0)
            taken = seated.get(table_id.lower(), 0)
            current = table_id.lower() == current_table
            open_seats = max(0, chairs - taken) if chairs else None
            kind = table_kind(row.get("aha_name") or "")
            tables.append({
                "id": table_id,
                "name": row.get("aha_name") or "Table",
                "number": row.get("crca7_tablenumberint"),
                "kind": kind["kind"],
                "kind_label": kind["kind_label"],
                "kind_detail": kind["kind_detail"],
                "chairs": chairs,
                "seated": taken,
                "open_seats": open_seats,
                "vip": bool(row.get("aha_isreservedforvips")),
                "current": current,
                "available": current or open_seats is None or open_seats > 0,
                "people": people.get(table_id.lower(), []) if include_people else [],
            })
        tables.sort(key=lambda item: (not item["current"], item["name"]))
        return tables

    def preference_forms(self, contact_id: str, parent_id: str, event_names: dict) -> list:
        """Questions and the contact's saved answers for the main event and sub-events."""
        ids = [event_id for event_id in (event_names or {}) if event_id]
        if parent_id and parent_id not in ids:
            ids.insert(0, parent_id)
        if not ids:
            return []
        question_filter = " or ".join(f"_aha_campaign_value eq {event_id}" for event_id in ids)
        question_rows = self.crm._make_request(
            "aha_eventformquestionses?$select=aha_eventformquestionsid,aha_newcolumn,"
            "aha_choicelabels,aha_ismultilinetext,aha_displayorder,_aha_campaign_value"
            f"&$filter={url_quote(question_filter)}&$top=200"
        ).get("value") or []
        response_filter = (
            f"_aha_contact_value eq {contact_id} and ("
            + " or ".join(f"_aha_campaign_value eq {event_id}" for event_id in ids)
            + ")"
        )
        response_rows = self.crm._make_request(
            "aha_eventformresponseses?$select=aha_guestresponse,_aha_formquestion_value,"
            "_aha_campaign_value"
            f"&$filter={url_quote(response_filter)}&$top=200"
        ).get("value") or []
        answers = {
            (row.get("_aha_formquestion_value") or "").lower(): (row.get("aha_guestresponse") or "")
            for row in response_rows
        }
        table_filter = " or ".join(
            f"_aha_event_value eq {event_id}" for event_id in ids
        )
        table_rows = self.crm._make_request(
            "aha_seatingtables?$select=aha_seatingtableid,aha_name,_aha_event_value,"
            "aha_numberofchairs,aha_isreservedforvips"
            f"&$filter={url_quote(f'statecode eq 0 and ({table_filter})')}&$top=200"
        ).get("value") or []
        seat_rows = self.crm._paginate(
            "aha_tablereservations?$select=_aha_table_value,_aha_event_value,_aha_contact_value"
            f"&$filter={url_quote(f'statecode eq 0 and ({table_filter})')}"
        )
        chosen_tables = {}
        seated_counts = {}
        contact_key = (contact_id or "").lower()
        for row in seat_rows:
            event_key = (row.get("_aha_event_value") or "").lower()
            table_key = (row.get("_aha_table_value") or "").lower()
            if event_key and table_key:
                seated_counts[(event_key, table_key)] = seated_counts.get((event_key, table_key), 0) + 1
            if contact_key and (row.get("_aha_contact_value") or "").lower() == contact_key and event_key:
                chosen_tables[event_key] = row.get("_aha_table_value") or ""
        grouped = {}
        for event_id in ids:
            grouped[event_id.lower()] = {
                "event_id": event_id,
                "event_name": (event_names or {}).get(event_id) or (event_names or {}).get(event_id.lower()) or "Event",
                "questions": [],
                "tables": [],
                "table_id": chosen_tables.get(event_id.lower(), ""),
            }
        for row in question_rows:
            event_id = (row.get("_aha_campaign_value") or "").lower()
            bucket = grouped.get(event_id)
            text = (row.get("aha_newcolumn") or "").strip()
            question_id = row.get("aha_eventformquestionsid")
            if not bucket or not text or not question_id:
                continue
            bucket["questions"].append({
                "id": question_id,
                "question": text,
                "choices": _choice_labels(row.get("aha_choicelabels")),
                "multiline": bool(row.get("aha_ismultilinetext")),
                "order": row.get("aha_displayorder") or 0,
                "answer": answers.get(question_id.lower(), ""),
            })
        for row in table_rows:
            event_id = (row.get("_aha_event_value") or "").lower()
            bucket = grouped.get(event_id)
            if not bucket or not row.get("aha_seatingtableid"):
                continue
            chairs = int(row.get("aha_numberofchairs") or 0)
            table_id = row.get("aha_seatingtableid")
            taken = seated_counts.get((event_id, table_id.lower()), 0)
            current = (chosen_tables.get(event_id) or "").lower() == table_id.lower()
            open_seats = max(0, chairs - taken) if chairs else None
            bucket["tables"].append({
                "id": table_id,
                "name": row.get("aha_name") or "Table",
                "chairs": chairs,
                "seated": taken,
                "open_seats": open_seats,
                "vip": bool(row.get("aha_isreservedforvips")),
                "current": current,
                "available": current or open_seats is None or open_seats > 0,
            })
        forms = []
        for event_id in ids:
            bucket = grouped[event_id.lower()]
            bucket["questions"].sort(key=lambda item: (item["order"], item["question"]))
            bucket["tables"].sort(key=lambda item: item["name"])
            if bucket["questions"] or bucket["tables"]:
                forms.append(bucket)
        return forms

    def save_signup_details(self, contact_id: str, event_id: str, answers, table_id: str = "") -> None:
        """Write form answers and a table seat after the sign-up is saved."""
        for answer in answers or []:
            question_id = (answer.get("question_id") or "").strip()
            response = (answer.get("response") or "").strip()
            if not question_id:
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
            if not response:
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
        self._claim_table(contact_id, event_id, table_id)

    def _claim_table(self, contact_id: str, event_id: str, table_id: str) -> None:
        """Move this person to a table only if a seat is still open."""
        table_id = (table_id or "").strip()
        if not table_id:
            return
        before = {row["id"].lower(): row for row in self.live_tables(event_id, contact_id)}
        target = before.get(table_id.lower())
        if not target:
            raise RegistrationError("That table is not on this event.")
        if target["current"]:
            return
        if not target["available"]:
            raise RegistrationError(
                f"{target['name']} is full ({target['seated']} of {target['chairs']}). Choose another table."
            )
        filt = (
            f"_aha_contact_value eq {contact_id} and _aha_event_value eq {event_id} "
            "and statecode eq 0"
        )
        existing = self.crm._make_request(
            "aha_tablereservations?$select=aha_tablereservationid,_aha_table_value"
            f"&$filter={url_quote(filt)}&$top=1"
        ).get("value") or []
        table_bind = {"aha_Table@odata.bind": f"/aha_seatingtables({table_id})"}
        created_id = ""
        previous_table = ""
        if existing and existing[0].get("aha_tablereservationid"):
            previous_table = existing[0].get("_aha_table_value") or ""
            self._send(
                "PATCH",
                f"aha_tablereservations({existing[0]['aha_tablereservationid']})",
                table_bind,
            )
            reservation_id = existing[0]["aha_tablereservationid"]
        else:
            created = self._send(
                "POST",
                "aha_tablereservations",
                {
                    "aha_name": "Seat",
                    "aha_Contact@odata.bind": f"/contacts({contact_id})",
                    "aha_Event@odata.bind": f"/campaigns({event_id})",
                    **table_bind,
                },
            )
            reservation_id = created.get("aha_tablereservationid") or ""
            created_id = reservation_id
        after = {row["id"].lower(): row for row in self.live_tables(event_id, contact_id)}
        updated = after.get(table_id.lower())
        if updated and updated["chairs"] and updated["seated"] > updated["chairs"]:
            if created_id:
                self._send("DELETE", f"aha_tablereservations({created_id})", None)
            elif previous_table:
                self._send(
                    "PATCH",
                    f"aha_tablereservations({reservation_id})",
                    {"aha_Table@odata.bind": f"/aha_seatingtables({previous_table})"},
                )
            raise RegistrationError(
                f"{target['name']} was just taken. Choose another table."
            )

    def _active_reservation(self, contact_id: str, event_id: str) -> Optional[dict]:
        """The one active chair for this person on this sub-event, if they have one."""
        filt = (
            f"_aha_contact_value eq {contact_id} and _aha_event_value eq {event_id} "
            "and statecode eq 0"
        )
        rows = self.crm._make_request(
            "aha_tablereservations?$select=aha_tablereservationid,_aha_table_value"
            f"&$filter={url_quote(filt)}&$top=1"
        ).get("value") or []
        if not rows or not rows[0].get("aha_tablereservationid"):
            return None
        return {
            "id": rows[0].get("aha_tablereservationid") or "",
            "table_id": rows[0].get("_aha_table_value") or "",
        }

    def _end_reservation(self, reservation_id: str) -> None:
        """Take this chair out of the active seating list."""
        if reservation_id:
            self._send("DELETE", f"aha_tablereservations({reservation_id})", None)

    def _restore_reservation(self, contact_id: str, event_id: str, table_id: str) -> None:
        """Put a chair back when the destination claim did not stick."""
        table_id = (table_id or "").strip()
        if not table_id:
            return
        self._send(
            "POST",
            "aha_tablereservations",
            {
                "aha_name": "Seat",
                "aha_Contact@odata.bind": f"/contacts({contact_id})",
                "aha_Event@odata.bind": f"/campaigns({event_id})",
                "aha_Table@odata.bind": f"/aha_seatingtables({table_id})",
            },
        )

    def _transfer_seat(self, contact_id: str, from_event_id: str, to_event_id: str, table_id: str) -> None:
        """Leave the source banquet, then claim a chair on the destination banquet.

        The source chair is ended before the destination write, so the person
        is never seated at both. If the destination claim fails, the source
        chair is written back.
        """
        source = self._active_reservation(contact_id, from_event_id)
        if source and source.get("id"):
            self._end_reservation(source["id"])
        try:
            self._claim_table(contact_id, to_event_id, table_id)
        except Exception:
            if source and source.get("table_id"):
                try:
                    self._restore_reservation(contact_id, from_event_id, source["table_id"])
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Could not restore seat for %s on %s", contact_id, from_event_id
                    )
            raise

    def apply_seat_moves(self, event_id: str, moves) -> dict:
        """Move each person, stopping at the first failure.

        A move on one sub-event uses _claim_table. A move between sub-events
        ends the source chair and claims the destination, then stores that
        banquet's answers by question id. The same person keeps the last
        destination in the list. Moves that already succeeded stay written.
        """
        if not isinstance(moves, list) or not moves:
            return {"applied": [], "error": "Choose a person and a table", "failed_contact_id": ""}
        collapsed: List[dict] = []
        seen: Dict[str, int] = {}
        for move in moves:
            if not isinstance(move, dict):
                return {"applied": [], "error": "Choose a person and a table", "failed_contact_id": ""}
            contact_id = (move.get("contact_id") or "").strip()
            table_id = (move.get("table_id") or "").strip()
            from_event_id = (move.get("from_event_id") or event_id or "").strip()
            to_event_id = (move.get("to_event_id") or event_id or "").strip()
            answers = move.get("answers") if isinstance(move.get("answers"), list) else []
            entry = {
                "contact_id": contact_id,
                "table_id": table_id,
                "from_event_id": from_event_id,
                "to_event_id": to_event_id,
                "answers": answers,
            }
            key = contact_id.lower()
            if key and key in seen:
                collapsed[seen[key]] = entry
                continue
            if key:
                seen[key] = len(collapsed)
            collapsed.append(entry)
        applied: List[str] = []
        for move in collapsed:
            contact_id = move["contact_id"]
            table_id = move["table_id"]
            from_event_id = move["from_event_id"]
            to_event_id = move["to_event_id"]
            if not contact_id or not table_id:
                return {
                    "applied": applied,
                    "error": "Choose a person and a table",
                    "failed_contact_id": contact_id,
                }
            try:
                if from_event_id.lower() == to_event_id.lower():
                    self._claim_table(contact_id, to_event_id, table_id)
                else:
                    self._transfer_seat(contact_id, from_event_id, to_event_id, table_id)
                    if move["answers"]:
                        self.save_signup_details(contact_id, to_event_id, move["answers"], "")
            except RegistrationError as exc:
                return {"applied": applied, "error": str(exc), "failed_contact_id": contact_id}
            except Exception:
                logging.getLogger(__name__).exception("Seat move failed for %s", contact_id)
                return {
                    "applied": applied,
                    "error": "Could not change the seat",
                    "failed_contact_id": contact_id,
                }
            applied.append(contact_id)
        return {"applied": applied, "error": "", "failed_contact_id": ""}

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

    def purchase_membership(
        self,
        contact_id: str,
        category_id: str,
        year: int,
        spouse_id: str = "",
        confirmed_child_ids: Optional[set] = None,
        transaction_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> dict:
        """Create one paid membership and associate the household it covers."""
        categories = {item["id"]: item for item in load_categories(self.crm)}
        category = categories.get(category_id)
        if not category:
            raise RegistrationError("Choose a membership level")
        household = load_household(self.crm, contact_id)
        self_person = next((person for person in household if person.get("id") == contact_id), None)
        if not self_person:
            raise RegistrationError("That person could not be loaded")
        role = self_person.get("relationship") or ""
        spouse, _spouse_error = choose_spouse(household)
        if spouse and role in ("Self", "Spouse") and category["name"] != "Family":
            raise RegistrationError(
                "This household has a spouse, so Self and Spouse must be a Family membership. "
                "Individual is not available."
            )
        covered, error = cover_list(
            category["name"],
            self_person,
            household,
            confirmed_child_ids=confirmed_child_ids,
            spouse_id=spouse_id,
        )
        if error or not covered:
            raise RegistrationError(error or "Nobody can be covered by this membership")
        type_code = TYPE_CODES.get(category["name"])
        body = {
            "msnfp_name": f"Membership {year}",
            "aha_year": int(year),
            "msnfp_startdate": f"{int(year)}-01-01",
            "msnfp_enddate": f"{int(year)}-12-31",
            "statuscode": MEMBERSHIP_PAID,
            "statecode": STATE_ACTIVE,
            "aha_cost": float(category["cost"] or 0),
            "aha_contactsassociated": ", ".join(
                person.get("name") or person["id"] for person in covered
            ),
            "aha_numberofcontactsassociated": len(covered),
            "aha_MembershipCategory@odata.bind": (
                f"/msnfp_membershipcategories({category_id})"
            ),
        }
        if type_code is not None:
            body["crca7_membershiptype"] = type_code
        if profile_id:
            body["aha_AuthorizenetProfile@odata.bind"] = (
                f"/aha_authorizenetprofiles({profile_id})"
            )
        if transaction_id:
            body["aha_msnfp_Transaction@odata.bind"] = (
                f"/msnfp_transactions({transaction_id})"
            )
        created = self._send("POST", "msnfp_memberships", body)
        membership_id = created.get("msnfp_membershipid") or ""
        if not membership_id:
            raise RegistrationError("Dynamics did not return the new membership")
        for person in covered:
            if not person.get("id"):
                continue
            self._send(
                "POST",
                f"msnfp_memberships({membership_id})/{MEMBERSHIP_NAV}/$ref",
                {"@odata.id": f"{self.crm.crm_url}/api/data/v9.2/contacts({person['id']})"},
            )
        return {
            "id": membership_id,
            "name": created.get("msnfp_name") or body["msnfp_name"],
            "covered": [person.get("name") or person["id"] for person in covered],
        }

    def record_membership_receipt(
        self,
        contact_id: str,
        profile_id: str,
        amount,
        transaction_id: str,
        campaign_id: str = "",
    ) -> Optional[str]:
        body = {
            "msnfp_name": f"Membership {transaction_id}",
            "msnfp_amount": float(amount),
            "aha_totalamount": float(amount),
            "aha_authorizetransactionid": transaction_id,
            "aha_Contact@odata.bind": f"/contacts({contact_id})",
            "msnfp_receiptoncontactid@odata.bind": f"/contacts({contact_id})",
        }
        if campaign_id:
            body["msnfp_OriginatingCampaignId@odata.bind"] = f"/campaigns({campaign_id})"
        if profile_id:
            body["aha_AuthorizenetProfile@odata.bind"] = (
                f"/aha_authorizenetprofiles({profile_id})"
            )
        created = self._send("POST", "msnfp_transactions", body)
        return created.get("msnfp_transactionid")

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
