"""Event price differences and Authorize.net charge rules."""

import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock

from utils.registration.payments import (
    EventPrice,
    MissingMerchant,
    PaymentDeclined,
    charge_saved_card,
    hosted_payment_token,
    inherit_merchant,
    quote_add,
    quote_move,
)


def _event(event_id, cost, profile, name="Event"):
    return EventPrice(
        id=event_id,
        name=name,
        cost=Decimal(cost),
        profile_id=profile,
        profile_name=profile or "",
    )


class QuoteTests(unittest.TestCase):
    def test_same_account_charges_only_the_increase(self):
        quote = quote_move(
            _event("a", "20.00", "acct"),
            _event("b", "50.00", "acct", "Banquet"),
        )
        self.assertEqual(quote.amount, Decimal("30.00"))
        self.assertFalse(quote.accounts_differ)
        self.assertEqual(quote.profile_id, "acct")

    def test_same_price_is_not_charged(self):
        quote = quote_move(_event("a", "20.00", "acct"), _event("b", "20.00", "acct"))
        self.assertEqual(quote.amount, Decimal("0.00"))
        self.assertFalse(quote.charges)

    def test_decrease_is_never_negative(self):
        quote = quote_move(_event("a", "50.00", "acct"), _event("b", "20.00", "acct"))
        self.assertEqual(quote.amount, Decimal("0.00"))

    def test_different_accounts_charge_the_full_new_price(self):
        quote = quote_move(
            _event("a", "20.00", "afrp", "Bingo"),
            _event("b", "50.00", "education", "Banquet"),
        )
        self.assertTrue(quote.accounts_differ)
        self.assertEqual(quote.amount, Decimal("50.00"))
        self.assertEqual(quote.profile_id, "education")

    def test_sub_event_uses_the_main_event_account(self):
        parent = _event("parent", "250.00", "afrp", "Convention")
        child = _event("banquet", "50.00", None, "Secondary Banquet Room")
        child.profile_name = ""
        inherit_merchant(child, parent)
        quote = quote_add([child])
        self.assertEqual(quote.profile_id, "afrp")
        self.assertEqual(quote.amount, Decimal("50.00"))

    def test_priced_event_without_an_account_is_refused(self):
        with self.assertRaises(MissingMerchant):
            quote_move(_event("a", "0.00", None), _event("b", "25.00", None))

    def test_add_sums_people_on_one_account(self):
        event = _event("bingo", "20.00", "acct", "Bingo")
        quote = quote_add([event, event])
        self.assertEqual(quote.amount, Decimal("40.00"))

    def test_remove_style_empty_add_is_free(self):
        quote = quote_add([])
        self.assertFalse(quote.charges)


class ChargeTests(unittest.TestCase):
    def test_expired_card_is_skipped(self):
        from utils.registration.payments import _card_expired
        self.assertTrue(_card_expired("2026-09"))
        self.assertFalse(_card_expired("2029-08"))

    def test_decline_raises_and_returns_no_transaction(self):
        def poster(body):
            if "getCustomerProfileRequest" in body:
                return {
                    "messages": {"message": [{"code": "I00001"}]},
                    "profile": {"paymentProfiles": [{"customerPaymentProfileId": "pay"}]},
                }
            return {
                "messages": {"message": [{"code": "I00001"}]},
                "transactionResponse": {
                    "responseCode": "2",
                    "errors": [{"errorText": "Declined"}],
                },
            }

        with self.assertRaises(PaymentDeclined):
            charge_saved_card(
                {"login": "login", "key": "key"},
                "customer",
                Decimal("30.00"),
                poster,
            )

    def test_approved_charge_returns_transaction_id(self):
        def poster(body):
            if "getCustomerProfileRequest" in body:
                return {
                    "messages": {"message": [{"code": "I00001"}]},
                    "profile": {"paymentProfiles": [{"customerPaymentProfileId": "pay"}]},
                }
            request = body["createTransactionRequest"]["transactionRequest"]
            self.assertEqual(request["amount"], "30.00")
            self.assertEqual(
                request["profile"]["customerProfileId"],
                "customer",
            )
            return {
                "messages": {"message": [{"code": "I00001"}]},
                "transactionResponse": {"responseCode": "1", "transId": "txn-9"},
            }

        trans_id = charge_saved_card(
            {"login": "login", "key": "secret"},
            "customer",
            Decimal("30.00"),
            poster,
        )
        self.assertEqual(trans_id, "txn-9")
        self.assertNotIn("secret", trans_id)


class HostedFormTests(unittest.TestCase):
    def test_return_urls_do_not_contain_raw_ampersands(self):
        captured = {}

        def poster(body):
            captured["body"] = body
            return {"token": "token", "messages": {"message": [{"code": "I00001"}]}}

        token = hosted_payment_token(
            {"login": "login", "key": "key"},
            Decimal("12.00"),
            "https://example.com/registration/payment-done",
            "https://example.com/registration?campaign_id=1&email=a@b.com",
            "https://example.com/registration/communicator",
            poster=poster,
        )
        settings = captured["body"]["getHostedPaymentPageRequest"]["hostedPaymentSettings"]["setting"]
        by_name = {row["settingName"]: row["settingValue"] for row in settings}
        raw = by_name["hostedPaymentReturnOptions"]
        self.assertNotIn("&", raw)
        parsed = json.loads(raw)
        self.assertEqual(parsed["cancelUrl"], "https://example.com/registration")
        self.assertEqual(token, "token")


if __name__ == "__main__":
    unittest.main()
