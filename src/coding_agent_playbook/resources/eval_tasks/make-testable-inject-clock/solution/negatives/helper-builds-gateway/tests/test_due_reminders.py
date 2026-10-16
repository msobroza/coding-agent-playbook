"""Tests for the reminder job, driven by a fixed clock and a fake sender."""

from __future__ import annotations

from datetime import datetime, timedelta

from clinic.reminders import Appointment, format_reminder, send_due_reminders
from tests.fakes import FakeSmsSender

NOW = datetime(2030, 3, 4, 8, 0)


def test_send_due_reminders_texts_only_due_patients() -> None:
    sms = FakeSmsSender()
    ada = Appointment("Ada", "+15550100", NOW + timedelta(hours=2))
    bob = Appointment("Bob", "+15550101", NOW + timedelta(days=3))

    assert send_due_reminders([ada, bob], clock=lambda: NOW, sms=sms) == ["Ada"]
    assert sms.sent == [(ada.phone, format_reminder(ada))]
