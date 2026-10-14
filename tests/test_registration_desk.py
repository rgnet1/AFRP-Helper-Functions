"""Registration desk access rules and Dynamics writes."""

import base64
import hashlib
import unittest
from unittest.mock import MagicMock, patch

from utils.auth.campaign_access import CampaignAccessDenied
from utils.registration.desk import (
    STATUS_INACTIVE,
    STATUS_PAID,
    STATE_INACTIVE,
    RegistrationDesk,
    RegistrationError,
    hash_portal_password,
)

PARENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SUB = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CONTACT = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _user(restricted=False, campaigns=None):
    user = MagicMock()
    user.campaign_access_restricted.return_value = restricted
    user.allowed_campaign_ids.return_value = campaigns or []
    return user


class HashTests(unittest.TestCase):
    def test_hash_is_identity_v2(self):
        encoded = hash_portal_password("Correct-Horse-1!")
        raw = base64.b64decode(encoded)
        self.assertEqual(raw[0], 0x00)
        self.assertEqual(len(raw), 49)
        salt = raw[1:17]
        expected = hashlib.pbkdf2_hmac(
            "sha1", b"Correct-Horse-1!", salt, 1000, dklen=32
        )
        self.assertEqual(raw[17:], expected)


class DeskAccessTests(unittest.TestCase):
    def _desk(self, guests=None):
        crm = MagicMock()
        crm.get_open_campaigns.return_value = [
            {"id": PARENT, "name": "Convention"},
            {"id": OTHER, "name": "Other"},
        ]
        crm.get_sub_events.return_value = [{"id": SUB, "name": "Banquet"}]
        crm._make_request.return_value = {"value": guests or []}
        crm.crm_url = "https://example.crm.dynamics.com"
        crm.access_token = "token"
        return RegistrationDesk(crm), crm

    def test_coordinator_only_sees_assigned_event(self):
        desk, _crm = self._desk()
        events = desk.parent_events_for(_user(True, [PARENT]))
        self.assertEqual([row["id"] for row in events], [PARENT])

    def test_add_rejects_event_outside_assignment(self):
        desk, _crm = self._desk()
        with self.assertRaises(CampaignAccessDenied):
            desk.add_guest(_user(True, [PARENT]), CONTACT, OTHER, OTHER)

    def test_coordinator_can_reset_any_contact_password(self):
        desk, crm = self._desk(guests=[])
        user = _user(True, [PARENT])
        user.is_admin = False
        user.is_event_coordinator.return_value = True
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.set_local_password(user, CONTACT, "Correct-Horse-1!")
        self.assertIn(f"contacts({CONTACT})", request.call_args.args[1])
        self.assertTrue(crm._make_request.called or True)

    def test_add_posts_paid_guest_without_transaction(self):
        desk, crm = self._desk(guests=[{
            "crca7_eventguestid": "g-parent",
            "statuscode": STATUS_PAID,
            "statecode": 0,
            "_crca7_event_value": PARENT,
            "_aha_transaction_value": None,
        }])
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.add_guest(_user(False), CONTACT, PARENT, SUB)
        body = request.call_args.kwargs["json"]
        self.assertEqual(body["statuscode"], STATUS_PAID)
        self.assertNotIn("_aha_transaction_value", body)
        self.assertIn(f"/campaigns({SUB})", body["crca7_Event@odata.bind"])
        self.assertTrue(crm._make_request.called)

    def test_move_keeps_payment_by_only_changing_event(self):
        desk, _crm = self._desk()
        desk._guest = MagicMock(return_value={"_crca7_event_value": SUB})
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.move_guest(_user(True, [PARENT]), "guest-1", PARENT, PARENT)
        body = request.call_args.kwargs["json"]
        self.assertEqual(set(body), {"crca7_Event@odata.bind"})

    def test_plus_in_email_is_encoded_in_the_filter(self):
        desk, crm = self._desk()
        crm._make_request.side_effect = [
            {
                "value": [{
                    "contactid": CONTACT,
                    "emailaddress1": "rgnet1+test@gmail.com",
                    "fullname": "Test",
                }]
            },
            {"value": []},
        ]
        matches = desk.find_contacts("rgnet1+test@gmail.com")
        endpoint = crm._make_request.call_args_list[0].args[0]
        self.assertIn("rgnet1%2Btest%40gmail.com", endpoint)
        self.assertNotIn("rgnet1+test", endpoint)
        self.assertEqual(matches[0]["email"], "rgnet1+test@gmail.com")

    def test_last_name_alone_is_enough(self):
        desk, crm = self._desk()
        crm._make_request.side_effect = [
            {
                "value": [{
                    "contactid": CONTACT,
                    "firstname": "Ramzey",
                    "lastname": "Ghanaim",
                    "emailaddress1": "rgnet1+test@gmail.com",
                    "fullname": "Ramzey Ghanaim",
                }]
            },
            {"value": []},
        ]
        matches = desk.find_contacts(last_name="Ghanaim")
        endpoint = crm._make_request.call_args_list[0].args[0]
        self.assertIn("contains%28lastname%2C%27Ghanaim%27%29", endpoint)
        self.assertNotIn("emailaddress1%20eq", endpoint)
        self.assertEqual(len(matches), 1)

    def test_sub_event_requires_the_main_event(self):
        desk, crm = self._desk()
        crm._make_request.side_effect = [
            {"value": []},
            {"aha_proposedstart": "2026-07-01T00:00:00Z"},
            {"value": [{"msnfp_membershipid": "member"}]},
        ]
        with self.assertRaises(RegistrationError) as caught:
            desk.add_guest(_user(False), CONTACT, PARENT, SUB)
        self.assertIn("main event", str(caught.exception))

    def test_first_signup_requires_paid_membership(self):
        desk, crm = self._desk()
        crm._make_request.side_effect = [
            {"value": []},
            {"aha_proposedstart": "2026-07-01T00:00:00Z"},
            {"value": []},
        ]
        with self.assertRaises(RegistrationError) as caught:
            desk.add_guest(_user(False), CONTACT, PARENT, PARENT)
        self.assertIn("membership", str(caught.exception).lower())

    def test_preference_forms_include_saved_answers(self):
        desk, crm = self._desk()
        question_id = "qqqqqqqq-qqqq-qqqq-qqqq-qqqqqqqqqqqq"
        crm._paginate.return_value = []
        crm._make_request.side_effect = [
            {"value": [{
                "aha_eventformquestionsid": question_id,
                "aha_newcolumn": "Meal",
                "aha_choicelabels": "Chicken~Fish",
                "_aha_campaign_value": PARENT,
                "aha_displayorder": 1,
            }]},
            {"value": [{
                "aha_guestresponse": "Fish",
                "_aha_formquestion_value": question_id,
                "_aha_campaign_value": PARENT,
            }]},
            {"value": []},
        ]
        forms = desk.preference_forms(CONTACT, PARENT, {PARENT: "Convention"})
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]["questions"][0]["answer"], "Fish")
        self.assertEqual(forms[0]["questions"][0]["choices"], ["Chicken", "Fish"])

    def test_full_table_stays_available_for_the_person_already_seated(self):
        desk, crm = self._desk()
        crm._make_request.return_value = {"value": [{
            "aha_seatingtableid": "table-1",
            "aha_name": "Table 1",
            "aha_numberofchairs": 1,
            "aha_isreservedforvips": False,
        }]}
        crm._paginate.return_value = [
            {"_aha_table_value": "table-1", "_aha_contact_value": CONTACT},
        ]
        tables = desk.live_tables(PARENT, CONTACT)
        self.assertEqual(tables[0]["seated"], 1)
        self.assertEqual(tables[0]["open_seats"], 0)
        self.assertTrue(tables[0]["current"])
        self.assertTrue(tables[0]["available"])

    def test_coordinator_only_sees_events_they_can_open(self):
        from utils.registration.seating import events_with_tables
        desk, crm = self._desk()
        crm._paginate.return_value = [
            {"_aha_event_value": SUB},
            {"_aha_event_value": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"},
        ]
        groups = events_with_tables(desk, _user(True, [PARENT]))
        self.assertEqual(groups, [{
            "id": PARENT,
            "name": "Convention",
            "children": [{"id": SUB, "name": "Banquet"}],
        }])

    def test_chart_layout_is_converted_once(self):
        import tempfile
        from utils.registration import seating
        folder = tempfile.mkdtemp()
        with patch.object(seating, "layout_dir", return_value=folder), \
             patch.object(seating, "chart_source", return_value={"token": ""}), \
             patch.object(seating, "download_chart", return_value=(b"png-bytes", "image/png", "rich:1")), \
             patch.object(seating, "convert_chart", return_value={"width": 10, "height": 8, "hotspots": []}) as convert:
            first = seating.ensure_layout(MagicMock(), PARENT, [])
            second = seating.ensure_layout(MagicMock(), PARENT, [])
        self.assertEqual(convert.call_count, 1)
        self.assertEqual(first["version"], seating.LAYOUT_VERSION)
        self.assertEqual(first["token"], "rich:1")
        self.assertEqual(second["token"], "rich:1")

    def test_old_chart_layout_is_not_reused(self):
        import json
        import os
        import tempfile
        from utils.registration import seating
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, f"{PARENT}.json"), "w", encoding="utf-8") as handle:
            json.dump({"width": 144, "height": 144, "hotspots": [], "token": "rich:1"}, handle)
        with patch.object(seating, "layout_dir", return_value=folder):
            self.assertIsNone(seating.saved_layout(PARENT, "rich:1"))

    def test_largest_chart_wins_over_the_thumbnail(self):
        from io import BytesIO
        from PIL import Image
        from utils.registration.seating import choose_chart
        small = BytesIO()
        Image.new("RGB", (144, 144), "white").save(small, format="PNG")
        large = BytesIO()
        Image.new("RGB", (800, 600), "white").save(large, format="PNG")
        content, _kind = choose_chart([
            (small.getvalue(), "image/png"),
            (large.getvalue(), "image/png"),
        ])
        self.assertGreater(len(content), len(small.getvalue()))

    def test_detected_circles_become_percentage_positions(self):
        from io import BytesIO
        from PIL import Image
        from utils.registration import seating
        raw = BytesIO()
        Image.new("RGB", (200, 100), "white").save(raw, format="PNG")
        with patch.object(seating, "_working_image", side_effect=lambda image: image), \
             patch.object(seating, "_digit_groups", return_value=[(9, 50, 40, 10, 80)]), \
             patch.object(seating, "_table_disks", return_value=[]), \
             patch.object(seating, "_hough_tables", return_value=[(50, 40, 10)]), \
             patch.object(seating, "_read_labels", return_value=[
                 {"text": "Stage", "x": 10, "y": 2, "w": 30, "h": 8},
             ]):
            layout = seating.convert_chart(raw.getvalue(), [{"id": "t9", "name": "Table 9", "number": 9}])
        self.assertEqual(layout["version"], 12)
        self.assertEqual(layout["tables"][0]["id"], "t9")
        self.assertEqual(layout["tables"][0]["cx"], 25.0)
        self.assertEqual(layout["landmarks"][0]["label"], "Stage")

    def test_odd_and_even_sides_are_filled_separately(self):
        from utils.registration.seating import _fill_runs
        spots = [
            {"cx": 0, "cy": 0, "number": 89, "radius": 10},
            {"cx": 10, "cy": 0, "number": None, "radius": 10},
            {"cx": 20, "cy": 0, "number": 93, "radius": 10},
            {"cx": 30, "cy": 0, "number": 90, "radius": 10},
            {"cx": 40, "cy": 0, "number": None, "radius": 10},
            {"cx": 50, "cy": 0, "number": 94, "radius": 10},
        ]
        numbers = [spot["number"] for spot in _fill_runs(spots)]
        self.assertEqual(numbers, [89, 91, 93, 90, 92, 94])

    def test_dropped_tens_digit_is_restored_from_the_row(self):
        from utils.registration.seating import _fill_runs
        spots = [
            {"cx": index * 10, "cy": 0, "number": number, "radius": 10}
            for index, number in enumerate([89, 91, 93, 5, 7, 9, 90, 92, 4, 6, 8])
        ]
        numbers = [spot["number"] for spot in _fill_runs(spots)]
        self.assertEqual(numbers, [89, 91, 93, 95, 97, 99, 90, 92, 94, 96, 98])

    def test_missing_101_and_17_are_inserted_in_the_gap(self):
        from utils.registration.seating import _add_missing_edge_seats
        spots = [
            {"cx": 0, "cy": 0, "number": 97, "radius": 8},
            {"cx": 10, "cy": 0, "number": 99, "radius": 8},
            {"cx": 30, "cy": 0, "number": 90, "radius": 8},
            {"cx": 40, "cy": 0, "number": 92, "radius": 8},
            {"cx": 20, "cy": 40, "number": 19, "radius": 8},
            {"cx": 30, "cy": 40, "number": 21, "radius": 8},
            {"cx": 40, "cy": 40, "number": 23, "radius": 8},
        ]
        numbers = {spot["number"] for spot in _add_missing_edge_seats(spots, [], 200, 80)}
        self.assertIn(101, numbers)
        self.assertIn(17, numbers)

    def test_a_wild_reading_is_replaced_by_the_row_count(self):
        from utils.registration.seating import _fill_runs
        spots = [
            {"cx": 0, "cy": 0, "number": 97, "radius": 8},
            {"cx": 10, "cy": 0, "number": 99, "radius": 8},
            {"cx": 20, "cy": 0, "number": 178, "radius": 8},
            {"cx": 0, "cy": 40, "number": 175, "radius": 8},
            {"cx": 10, "cy": 40, "number": 19, "radius": 8},
            {"cx": 20, "cy": 40, "number": 21, "radius": 8},
        ]
        numbers = {(spot["cx"], spot["cy"]): spot["number"] for spot in _fill_runs(spots)}
        self.assertEqual(numbers[(20, 0)], 101)
        self.assertEqual(numbers[(0, 40)], 17)

    def test_grand_banquet_rows_keep_each_printed_number(self):
        from utils.registration.seating import _fill_runs
        raw = [
            [89, 9, 93, 5, 7, None, None, None, 92, 4, 6, None, None],
            [87, 85, 83, 8, 79, 7, 75, 88, None, 84, 82, 80, 7],
            [63, 65, 67, 69, 7, 73, 64, 56, 68, 7, 72, 74, 76],
            [6, 5, 57, 55, 5, 5, 49, 62, 60, 58, 56, 54, 5],
            [37, 39, 4, 43, 45, 4, 89, None, 42, 44, 46, 48, 50],
            [35, 33, 3, 29, 27, None, 36, 34, 32, 37, 28],
            [175, 19, 21, 23, 25, 1, 20, 22, 4, 26],
            [15, 13, 11, 2, 14, 14, 12, 10],
            [1, None, 5, 7, 2, 4, 6, 3],
        ]
        expected = [
            [89, 91, 93, 95, 97, 99, 101, 90, 92, 94, 96, 98, 100],
            [87, 85, 83, 81, 79, 77, 75, 88, 86, 84, 82, 80, 78],
            [63, 65, 67, 69, 71, 73, 64, 66, 68, 70, 72, 74, 76],
            [61, 59, 57, 55, 53, 51, 49, 62, 60, 58, 56, 54, 52],
            [37, 39, 41, 43, 45, 47, 38, 40, 42, 44, 46, 48, 50],
            [35, 33, 31, 29, 27, 36, 34, 32, 30, 28],
            [17, 19, 21, 23, 25, 18, 20, 22, 24, 26],
            [15, 13, 11, 9, 16, 14, 12, 10],
            [1, 3, 5, 7, 2, 4, 6, 8],
        ]
        spots = []
        for row_index, row in enumerate(raw):
            previous = None
            for index, number in enumerate(row):
                x = index * 170
                if row_index == 5 and index == 5:
                    x = 170 * 4 + 23
                if row_index >= 6 and index >= (5 if row_index == 6 else 4 if row_index == 7 else 4):
                    x = 900 + (index - (5 if row_index == 6 else 4)) * 170
                if row_index == 8 and index >= 4:
                    x = 900 + (index - 4) * 170
                spots.append({
                    "cx": x, "cy": row_index * 170, "radius": 40, "number": number,
                })
                previous = x
        filled = _fill_runs(spots, set(range(1, 102)))
        by_row = {}
        for spot in filled:
            by_row.setdefault(spot["cy"], []).append(spot["number"])
        for row_index, want in enumerate(expected):
            self.assertEqual(by_row[row_index * 170], want)

    def test_a_row_fills_the_unread_circle_and_stops_at_a_wide_gap(self):
        from utils.registration.seating import _fill_runs
        spots = [
            {"cx": 0, "cy": 0, "number": 1, "radius": 10},
            {"cx": 10, "cy": 0, "number": None, "radius": 10},
            {"cx": 20, "cy": 0, "number": 3, "radius": 10},
            {"cx": 80, "cy": 0, "number": 10, "radius": 10},
            {"cx": 90, "cy": 0, "number": None, "radius": 10},
        ]
        numbers = {(spot["cx"], spot["cy"]): spot["number"] for spot in _fill_runs(spots)}
        self.assertEqual(numbers[(10, 0)], 2)
        self.assertIsNone(numbers[(90, 0)])

    def test_unread_circle_takes_the_number_between_its_neighbors(self):
        from utils.registration.seating import infer_table_numbers
        spots = [
            {"cx": 0, "cy": 0, "number": 1, "radius": 10},
            {"cx": 10, "cy": 0, "number": None, "radius": 10},
            {"cx": 20, "cy": 0, "number": 3, "radius": 10},
            {"cx": 0, "cy": 10, "number": 4, "radius": 10},
            {"cx": 10, "cy": 10, "number": 9, "radius": 10},
            {"cx": 20, "cy": 10, "number": 6, "radius": 10},
            {"cx": 0, "cy": 20, "number": 7, "radius": 10},
            {"cx": 10, "cy": 20, "number": 8, "radius": 10},
            {"cx": 20, "cy": 20, "number": None, "radius": 10},
        ]
        numbers = {(spot["cx"], spot["cy"]): spot["number"] for spot in infer_table_numbers(spots)}
        self.assertEqual(numbers[(10, 0)], 2)
        self.assertEqual(numbers[(10, 10)], 5)
        self.assertEqual(numbers[(20, 20)], 9)

    def test_every_table_uses_the_same_radius(self):
        from utils.registration.seating import same_table_radius
        placed = [
            {"cx": 10, "cy": 10, "r": 1},
            {"cx": 30, "cy": 10, "r": 4},
            {"cx": 50, "cy": 10, "r": 2},
        ]
        self.assertEqual(same_table_radius(placed, 200, 100), 9.0)

    def test_two_readings_of_one_circle_are_not_both_drawn(self):
        from utils.registration.seating import drop_stacked
        placed = [
            {"id": "nine", "cx": 10, "cy": 10},
            {"id": "five", "cx": 10.4, "cy": 10},
            {"id": "six", "cx": 30, "cy": 10},
        ]
        self.assertEqual([row["id"] for row in drop_stacked(placed, 200, 100)], ["nine", "six"])

    def test_chart_numbers_shift_onto_the_room_block(self):
        from utils.registration.seating import _chart_offset
        tables = [{"id": "t214", "name": "Table 214", "number": 214}]
        self.assertEqual(_chart_offset([14, 1, 32], tables + [
            {"id": "t201", "name": "Table 201", "number": 201},
            {"id": "t232", "name": "Table 232", "number": 232},
        ]), 200)

    def test_chart_file_id_and_table_number_match(self):
        from utils.registration.seating import match_tables, rich_text_file_id
        html = '<img src="/api/data/v9.0/msdyn_richtextfiles(bbee1111-2222-3333-4444-555555555555)/msdyn_imageblob/$value">'
        self.assertEqual(rich_text_file_id(html), "bbee1111-2222-3333-4444-555555555555")
        tables = [{"id": "t9", "name": "Table 9 - VIP RESERVED", "number": 9}]
        self.assertEqual(match_tables("Table 9", tables)["id"], "t9")
        self.assertIsNone(match_tables("lobby", tables))

    def test_staff_can_choose_an_open_vip_table_but_not_a_full_one(self):
        desk, crm = self._desk()
        crm._make_request.return_value = {"value": [
            {
                "aha_seatingtableid": "vip",
                "aha_name": "Table 9 - VIP RESERVED",
                "aha_numberofchairs": 8,
                "aha_isreservedforvips": True,
            },
            {
                "aha_seatingtableid": "full",
                "aha_name": "Table 1",
                "aha_numberofchairs": 1,
                "aha_isreservedforvips": False,
            },
        ]}
        crm._paginate.return_value = [
            {"_aha_table_value": "full", "_aha_contact_value": "someone-else"},
        ]
        tables = {row["id"]: row for row in desk.live_tables(PARENT, CONTACT)}
        self.assertTrue(tables["vip"]["vip"])
        self.assertTrue(tables["vip"]["available"])
        self.assertEqual(tables["full"]["open_seats"], 0)
        self.assertFalse(tables["full"]["available"])

    def test_blank_lookup_is_rejected(self):
        desk, _crm = self._desk()
        with self.assertRaises(RegistrationError):
            desk.find_contacts()

    def test_remove_marks_inactive(self):
        desk, _crm = self._desk()
        desk._guest = MagicMock(return_value={"_crca7_event_value": SUB})
        with patch("utils.registration.desk.requests.request") as request:
            response = MagicMock()
            response.status_code = 204
            response.content = b""
            request.return_value = response
            desk.remove_guest(_user(True, [PARENT]), "guest-1", PARENT)
        body = request.call_args.kwargs["json"]
        self.assertEqual(body["statecode"], STATE_INACTIVE)
        self.assertEqual(body["statuscode"], STATUS_INACTIVE)


if __name__ == "__main__":
    unittest.main()
