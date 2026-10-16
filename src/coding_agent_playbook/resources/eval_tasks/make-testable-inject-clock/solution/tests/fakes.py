"""Named fakes for the reminder job's dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeSmsSender:
    """Records each ``(phone, body)`` it is asked to send; nothing leaves the process."""

    sent: list[tuple[str, str]] = field(default_factory=list)

    def send(self, phone: str, body: str) -> None:
        self.sent.append((phone, body))
