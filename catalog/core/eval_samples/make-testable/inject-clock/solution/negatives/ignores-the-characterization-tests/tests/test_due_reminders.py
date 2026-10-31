"""Unit tests for the reminder core and its shell, driven by a fixed clock and a fake."""

from __future__ import annotations

from datetime import datetime, timedelta

from clinic.reminders import (
    REMINDER_WINDOW,
    Appointment,
    due_appointments,
    format_reminder,
    send_due_reminders,
)
from tests.fakes import FakeSmsSender

NOW = datetime(2030, 3, 4, 8, 0)


def _booked(patient: str, starts_in: timedelta, *, reminded: bool = False) -> Appointment:
    return Appointment(patient, f"+1555{patient}", NOW + starts_in, reminded)


def test_window_bounds_are_inclusive() -> None:
    at_now = _booked("Ada", timedelta(0))
    at_edge = _booked("Bob", REMINDER_WINDOW)

    assert due_appointments([at_now, at_edge], NOW) == [at_now, at_edge]


def test_past_later_and_already_reminded_appointments_are_not_due() -> None:
    past = _booked("Ada", -timedelta(minutes=1))
    later = _booked("Bob", REMINDER_WINDOW + timedelta(minutes=1))
    reminded = _booked("Cy", timedelta(hours=1), reminded=True)

    assert due_appointments([past, later, reminded], NOW) == []


def test_send_due_reminders_texts_only_due_patients_in_order() -> None:
    sms = FakeSmsSender()
    ada = _booked("Ada", timedelta(hours=2))
    bob = _booked("Bob", timedelta(days=3))
    cy = _booked("Cy", timedelta(hours=5))

    reminded = send_due_reminders([ada, bob, cy], clock=lambda: NOW, sms=sms)

    assert reminded == ["Ada", "Cy"]
    assert sms.sent == [(ada.phone, format_reminder(ada)), (cy.phone, format_reminder(cy))]


def test_send_due_reminders_sends_nothing_for_an_empty_book() -> None:
    sms = FakeSmsSender()

    assert send_due_reminders([], clock=lambda: NOW, sms=sms) == []
    assert sms.sent == []
