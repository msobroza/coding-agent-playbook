"""Characterization tests for the reminder job, written before it could be faked.

``send_due_reminders`` reads the wall clock and builds a live SMS gateway
itself, so these tests only drive paths where nothing is due and no message
leaves the process. They pin today's behavior and must keep passing unchanged.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from clinic.cli import load_appointments, main
from clinic.reminders import Appointment, format_reminder

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_format_reminder_names_the_patient_and_the_time() -> None:
    appointment = Appointment("Ada", "+15550100", datetime(2030, 3, 4, 9, 30))

    text = format_reminder(appointment)

    assert text == "Hi Ada, this is a reminder of your appointment at 09:30 on 04 Mar."


def test_load_appointments_reads_iso_timestamps(tmp_path: Path) -> None:
    book = tmp_path / "book.json"
    rows = [{"patient": "Ada", "phone": "+15550100", "starts_at": "2030-03-04T09:30:00"}]
    book.write_text(json.dumps(rows), encoding="utf-8")

    appointments = load_appointments(book)

    assert appointments == [Appointment("Ada", "+15550100", datetime(2030, 3, 4, 9, 30))]


def test_main_sends_nothing_when_no_appointment_is_due(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    soon = (datetime.now() + timedelta(hours=1)).isoformat()
    rows = [
        {"patient": "Ada", "phone": "+15550100", "starts_at": "2001-01-01T09:00:00"},
        {"patient": "Bob", "phone": "+15550101", "starts_at": "2999-01-01T09:00:00"},
        {"patient": "Cy", "phone": "+15550102", "starts_at": soon, "reminded": True},
    ]
    book = tmp_path / "book.json"
    book.write_text(json.dumps(rows), encoding="utf-8")

    assert main([str(book)]) == 0
    assert capsys.readouterr().out == "sent 0 reminder(s)\n"


def test_main_rejects_a_missing_argument(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage" in capsys.readouterr().err
