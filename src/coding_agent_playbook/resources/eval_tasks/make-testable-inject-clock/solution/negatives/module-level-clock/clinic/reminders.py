"""Appointment reminders: decide who is due a text message and send it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

REMINDER_WINDOW = timedelta(hours=24)

Clock = Callable[[], datetime]

_now: Clock = datetime.now


class SmsSender(Protocol):
    """What reminders need from an SMS provider."""

    def send(self, phone: str, body: str) -> None: ...


@dataclass(frozen=True)
class Appointment:
    patient: str
    phone: str
    starts_at: datetime
    reminded: bool = False


def format_reminder(appointment: Appointment) -> str:
    when = appointment.starts_at.strftime("%H:%M on %d %b")
    return f"Hi {appointment.patient}, this is a reminder of your appointment at {when}."


def due_appointments(appointments: list[Appointment], now: datetime) -> list[Appointment]:
    """Appointments not yet reminded that start within the window after ``now``."""
    return [
        appointment
        for appointment in appointments
        if not appointment.reminded and now <= appointment.starts_at <= now + REMINDER_WINDOW
    ]


def send_due_reminders(appointments: list[Appointment], *, sms: SmsSender) -> list[str]:
    """Text every patient whose appointment starts within the next 24 hours."""
    due = due_appointments(appointments, _now())
    for appointment in due:
        sms.send(appointment.phone, format_reminder(appointment))
    return [appointment.patient for appointment in due]
