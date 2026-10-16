"""Tests for the reminder job, pinning the clock through the module global."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from clinic import reminders
from clinic.reminders import Appointment, format_reminder, send_due_reminders
from tests.fakes import FakeSmsSender

if TYPE_CHECKING:
    import pytest

NOW = datetime(2030, 3, 4, 8, 0)


def test_send_due_reminders_texts_only_due_patients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reminders, "_now", lambda: NOW)
    sms = FakeSmsSender()
    ada = Appointment("Ada", "+15550100", NOW + timedelta(hours=2))
    bob = Appointment("Bob", "+15550101", NOW + timedelta(days=3))

    assert send_due_reminders([ada, bob], sms=sms) == ["Ada"]
    assert sms.sent == [(ada.phone, format_reminder(ada))]
