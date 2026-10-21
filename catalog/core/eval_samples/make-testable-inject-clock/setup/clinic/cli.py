"""Entry point: send the reminders due for the appointments in a JSON file.

Run it as ``python -m clinic.cli appointments.json``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from clinic.reminders import Appointment, send_due_reminders


def load_appointments(path: Path) -> list[Appointment]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        Appointment(
            patient=row["patient"],
            phone=row["phone"],
            starts_at=datetime.fromisoformat(row["starts_at"]),
            reminded=row.get("reminded", False),
        )
        for row in rows
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m clinic.cli APPOINTMENTS_JSON", file=sys.stderr)
        return 2
    reminded = send_due_reminders(load_appointments(Path(args[0])))
    print(f"sent {len(reminded)} reminder(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
