"""Price event changes and charge the event's own Authorize.net account.

Merchant keys stay in Dynamics (`aha_authorizenetprofiles`). This module
never logs them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

import requests

AUTHORIZE_API_URL = "https://api.authorize.net/xml/v1/request.api"
HOSTED_FORM_URL = "https://accept.authorize.net/payment/payment"


class PaymentDeclined(Exception):
    """Authorize.net refused the charge. CRM must not change."""


class MissingMerchant(Exception):
    """The event has a price but no Authorize.net profile."""


@dataclass
class EventPrice:
    id: str
    name: str
    cost: Decimal
    profile_id: Optional[str]
    profile_name: str
    parent_id: Optional[str] = None


@dataclass
class ChargeQuote:
    amount: Decimal
    profile_id: Optional[str]
    profile_name: str
    accounts_differ: bool = False
    description: str = ""

    @property
    def charges(self) -> bool:
        return self.amount > 0


def money(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def quote_move(source: EventPrice, dest: EventPrice) -> ChargeQuote:
    """Price a change from one event to another."""
    same_account = bool(source.profile_id) and source.profile_id == dest.profile_id
    if source.profile_id and dest.profile_id and not same_account:
        amount = dest.cost if dest.cost > 0 else Decimal("0.00")
        if amount > 0 and not dest.profile_id:
            raise MissingMerchant(f"{dest.name} has no Authorize.net account")
        return ChargeQuote(
            amount=amount,
            profile_id=dest.profile_id,
            profile_name=dest.profile_name,
            accounts_differ=True,
            description=(
                f"Different payment accounts. Charge the full {dest.name} price "
                f"on {dest.profile_name}. The earlier payment is not refunded."
            ),
        )
    amount = dest.cost - source.cost
    if amount < 0:
        amount = Decimal("0.00")
    profile_id = dest.profile_id or source.profile_id
    profile_name = dest.profile_name or source.profile_name
    if amount > 0 and not profile_id:
        raise MissingMerchant(
            f"{dest.name} has a price but no Authorize.net account in CRM"
        )
    if amount == 0:
        description = "No charge. The price does not go up."
    else:
        description = f"Charge the ${amount} difference on {profile_name}."
    return ChargeQuote(
        amount=amount,
        profile_id=profile_id,
        profile_name=profile_name,
        description=description,
    )


def quote_add(events: list) -> ChargeQuote:
    """Price one or more new sign-ups. One merchant account per call."""
    if not events:
        return ChargeQuote(amount=Decimal("0.00"), profile_id=None, profile_name="")
    profile_ids = {event.profile_id for event in events if event.cost > 0}
    if len(profile_ids) > 1:
        raise MissingMerchant("These events use different payment accounts. Add them one at a time.")
    amount = sum((event.cost for event in events), Decimal("0.00"))
    profile_id = next((event.profile_id for event in events if event.profile_id), None)
    profile_name = next((event.profile_name for event in events if event.profile_name), "")
    if amount > 0 and not profile_id:
        raise MissingMerchant(
            f"{events[0].name} has a price but no Authorize.net account in CRM"
        )
    description = "No charge." if amount == 0 else f"Charge ${amount} on {profile_name}."
    return ChargeQuote(
        amount=amount,
        profile_id=profile_id,
        profile_name=profile_name,
        description=description,
    )


def default_profile_ref(crm) -> dict:
    """Id and name of the org default merchant account. Keys are loaded later."""
    rows = crm._make_request(
        "aha_authorizenetprofiles?$select=aha_authorizenetprofileid,aha_name"
        "&$filter=aha_isdefault eq true and statecode eq 0&$top=1"
    ).get("value") or []
    if not rows:
        return {"id": None, "name": ""}
    return {
        "id": rows[0].get("aha_authorizenetprofileid"),
        "name": rows[0].get("aha_name") or "",
    }


def inherit_merchant(event: EventPrice, parent: Optional[EventPrice]) -> EventPrice:
    """A sub-event with no account uses the main event's account."""
    if event.profile_id or parent is None or not parent.profile_id:
        return event
    if (event.id or "").lower() == (parent.id or "").lower():
        return event
    event.profile_id = parent.profile_id
    event.profile_name = parent.profile_name
    return event


def load_event(crm, event_id: str, parent_id: Optional[str] = None) -> EventPrice:
    """Read price and merchant account. A sub-event inherits its parent's account."""
    row = crm._make_request(
        "campaigns({})?$select=name,aha_eventcost,_aha_authorizenetprofile_value,"
        "_aha_parentcampaign_value".format(event_id)
    )
    profile_id = row.get("_aha_authorizenetprofile_value") or None
    profile_name = row.get(
        "_aha_authorizenetprofile_value@OData.Community.Display.V1.FormattedValue"
    ) or ""
    parent = parent_id or row.get("_aha_parentcampaign_value")
    if not profile_id and parent and parent != event_id:
        parent_row = crm._make_request(
            "campaigns({})?$select=_aha_authorizenetprofile_value".format(parent)
        )
        profile_id = parent_row.get("_aha_authorizenetprofile_value") or None
        profile_name = parent_row.get(
            "_aha_authorizenetprofile_value@OData.Community.Display.V1.FormattedValue"
        ) or profile_name
    return EventPrice(
        id=event_id,
        name=row.get("name") or "",
        cost=money(row.get("aha_eventcost")),
        profile_id=profile_id,
        profile_name=profile_name,
        parent_id=parent,
    )


def load_profile(crm, profile_id: str) -> dict:
    row = crm._make_request(
        "aha_authorizenetprofiles({})?$select=aha_name,aha_apiloginid,aha_transactionkey".format(
            profile_id
        )
    )
    login = (row.get("aha_apiloginid") or "").strip()
    key = (row.get("aha_transactionkey") or "").strip()
    if not login or not key:
        raise MissingMerchant("That event's Authorize.net profile has no API login")
    return {
        "id": profile_id,
        "name": row.get("aha_name") or "",
        "login": login,
        "key": key,
    }


def customer_payment_profile(crm, contact_id: str) -> Optional[str]:
    row = crm._make_request(
        "contacts({})?$select=aha_authorizecustomerid".format(contact_id)
    )
    customer_id = (row.get("aha_authorizecustomerid") or "").strip()
    return customer_id or None


def _gateway_error(payload: dict) -> str:
    txn = payload.get("transactionResponse") or {}
    errors = txn.get("errors") or []
    if errors and errors[0].get("errorText"):
        return errors[0]["errorText"]
    messages = ((payload.get("messages") or {}).get("message") or [])
    if messages and messages[0].get("text"):
        return messages[0]["text"]
    return "Authorize.net request failed"


def _authorize(body: dict, poster: Optional[Callable] = None) -> dict:
    send = poster or _post_authorize
    payload = send(body)
    messages = ((payload.get("messages") or {}).get("message") or [])
    result = (messages[0].get("code") if messages else "") or ""
    if result not in ("I00001",):
        raise PaymentDeclined(_gateway_error(payload))
    return payload


def _post_authorize(body: dict) -> dict:
    response = requests.post(AUTHORIZE_API_URL, json=body, timeout=60)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig")
    return json.loads(text)


def _card_expired(expiration: str) -> bool:
    """Authorize.net dates look like YYYY-MM. A missing date is not treated as expired."""
    text = (expiration or "").strip()
    if len(text) < 7 or text[4] != "-":
        return False
    try:
        year = int(text[:4])
        month = int(text[5:7])
    except ValueError:
        return False
    from datetime import date
    today = date.today()
    return (year, month) < (today.year, today.month)


def charge_saved_card(profile: dict, customer_profile_id: str, amount: Decimal, poster=None) -> str:
    """authCapture a stored card. Tries each card and skips expired ones."""
    lookup = _authorize(
        {
            "getCustomerProfileRequest": {
                "merchantAuthentication": {
                    "name": profile["login"],
                    "transactionKey": profile["key"],
                },
                "customerProfileId": customer_profile_id,
                "unmaskExpirationDate": True,
            }
        },
        poster,
    )
    profiles = ((lookup.get("profile") or {}).get("paymentProfiles") or [])
    usable = []
    for payment in profiles:
        card = ((payment.get("payment") or {}).get("creditCard") or {})
        if _card_expired(card.get("expirationDate") or ""):
            continue
        if payment.get("customerPaymentProfileId"):
            usable.append(payment)
    if not usable:
        raise PaymentDeclined("The saved card has expired")
    failures = []
    for payment in usable:
        result = _authorize(
            {
                "createTransactionRequest": {
                    "merchantAuthentication": {
                        "name": profile["login"],
                        "transactionKey": profile["key"],
                    },
                    "transactionRequest": {
                        "transactionType": "authCaptureTransaction",
                        "amount": f"{amount:.2f}",
                        "profile": {
                            "customerProfileId": customer_profile_id,
                            "paymentProfile": {
                                "paymentProfileId": payment["customerPaymentProfileId"]
                            },
                        },
                    },
                }
            },
            poster,
        )
        txn = result.get("transactionResponse") or {}
        if str(txn.get("responseCode")) == "1" and txn.get("transId"):
            return str(txn.get("transId"))
        failures.append(_gateway_error(result))
    raise PaymentDeclined(failures[-1] if failures else "The card was declined")


def hosted_payment_token(
    profile: dict,
    amount: Decimal,
    return_url: str,
    cancel_url: str,
    communicator_url: str,
    poster=None,
) -> str:
    """Token for Authorize.net's hosted form. The card is entered on their page."""
    settings = {
        "hostedPaymentReturnOptions": json.dumps(
            {
                "showReceipt": False,
                "url": return_url,
                "urlText": "Continue",
                "cancelUrl": cancel_url,
                "cancelUrlText": "Cancel",
            }
        ),
        "hostedPaymentIFrameCommunicatorUrl": json.dumps({"url": communicator_url}),
        "hostedPaymentButtonOptions": json.dumps({"text": "Pay"}),
        "hostedPaymentPaymentOptions": json.dumps(
            {"cardCodeRequired": True, "showCreditCard": True, "showBankAccount": False}
        ),
    }
    result = _authorize(
        {
            "getHostedPaymentPageRequest": {
                "merchantAuthentication": {
                    "name": profile["login"],
                    "transactionKey": profile["key"],
                },
                "transactionRequest": {
                    "transactionType": "authCaptureTransaction",
                    "amount": f"{amount:.2f}",
                },
                "hostedPaymentSettings": {
                    "setting": [
                        {"settingName": name, "settingValue": value}
                        for name, value in settings.items()
                    ]
                },
            }
        },
        poster,
    )
    token = result.get("token")
    if not token:
        raise PaymentDeclined("Authorize.net did not return a payment page")
    return token
