"""How ``playbook ci`` reports its steps (specs/prK-hook-pack.md §F.5).

Text mode prints one ``PASS``/``FAIL``/``TIMEOUT``/``SKIP`` line per step and a
count line; JSON mode prints ``{"steps": [...], "exit": n}`` on stdout. Either
way each child's command line and output are logged as the step finishes
(stderr in JSON mode), so a CI log reads in order.
"""

from __future__ import annotations

import json
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from coding_agent_playbook.commands.ci import StepRecord

__all__ = ["json_report", "log_step", "summary_text"]


def log_step(record: StepRecord, stream: TextIO | None) -> None:
    """Log ``record``'s command line and output to ``stream`` (nothing for ``None``).

    Example: ``log_step(record, sys.stdout)`` prints ``--- validate: python -m ...``.
    """
    if stream is None:
        return
    print(f"--- {record.step}: {shlex.join(record.argv)}", file=stream)
    if record.output.strip():
        print(record.output.rstrip("\n"), file=stream)
    stream.flush()


def summary_text(records: Sequence[StepRecord]) -> str:
    """One status line per step, then ``playbook ci: N passed, N failed, N skipped``.

    Example: ``summary_text([]) == "playbook ci: 0 passed, 0 failed, 0 skipped"``.
    """
    lines = [_status_line(record) for record in records]
    counts = {status: sum(r.status == status for r in records) for status in ("passed", "skipped")}
    failed = len(records) - counts["passed"] - counts["skipped"]
    lines.append(
        f"playbook ci: {counts['passed']} passed, {failed} failed, {counts['skipped']} skipped"
    )
    return "\n".join(lines)


def json_report(records: Sequence[StepRecord], code: int) -> str:
    """``{"steps": [...], "exit": code}``, indented.

    Example: ``json.loads(json_report([], 0)) == {"steps": [], "exit": 0}``.
    """
    document = {"steps": [record.to_json() for record in records], "exit": code}
    return json.dumps(document, indent=2)


def _status_line(record: StepRecord) -> str:
    if record.status == "skipped":
        return f"SKIP {record.step}: {record.note}"
    if record.status == "timeout":
        return f"TIMEOUT {record.step} (after {record.duration_s:.2f}s)"
    word = "PASS" if record.status == "passed" else "FAIL"
    return f"{word} {record.step} (exit {record.exit}, {record.duration_s:.2f}s)"
