"""Coordinator portal-password date window."""

import unittest
from datetime import date

from utils.auth.password_window import password_window_status


class PasswordWindowTests(unittest.TestCase):
    def test_default_window_is_the_event_dates(self):
        allowed, _message = password_window_status(
            date(2026, 7, 2),
            0,
            [{"name": "Convention", "start": date(2026, 7, 1), "end": date(2026, 7, 4)}],
        )
        self.assertTrue(allowed)

    def test_zero_days_before_stays_closed_until_the_start(self):
        allowed, message = password_window_status(
            date(2026, 6, 30),
            0,
            [{"name": "Convention", "start": date(2026, 7, 1), "end": date(2026, 7, 4)}],
        )
        self.assertFalse(allowed)
        self.assertIn("Jul 01, 2026", message)

    def test_days_before_opens_early(self):
        allowed, _message = password_window_status(
            date(2026, 6, 28),
            3,
            [{"name": "Convention", "start": date(2026, 7, 1), "end": date(2026, 7, 4)}],
        )
        self.assertTrue(allowed)

    def test_missing_start_denies(self):
        allowed, message = password_window_status(
            date(2026, 7, 2),
            5,
            [{"name": "Convention", "start": None, "end": None}],
        )
        self.assertFalse(allowed)
        self.assertIn("no start date", message)
