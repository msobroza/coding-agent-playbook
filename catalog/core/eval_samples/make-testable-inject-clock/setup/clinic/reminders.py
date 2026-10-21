"""Appointment reminders: decide who is due a text message and send it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from clinic.sms import SmsGateway

REMINDER_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Appointment:
    patient: str
    phone: str
    starts_at: datetime
    reminded: bool = False


def format_reminder(appointment: Appointment) -> str:
    when = appointment.starts_at.strftime("%H:%M on %d %b")
    return f"Hi {appointment.patient}, this is a reminder of your appointment at {when}."


def send_due_reminders(appointments: list[Appointment]) -> list[str]:
    """Text every patient whose appointment starts within the next 24 hours."""
    now = datetime.now()
    gateway = SmsGateway()
    reminded: list[str] = []
    for appointment in appointments:
        if appointment.reminded:
            continue
        if now <= appointment.starts_at <= now + REMINDER_WINDOW:
            gateway.send(appointment.phone, format_reminder(appointment))
            reminded.append(appointment.patient)
    return reminded
