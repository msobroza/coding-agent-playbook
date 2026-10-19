"""Per-guard counts over guard-decision-log lines (specs/prK-hook-pack.md §E.5, principle 17).

``playbook-hook doctor`` summarizes the local decision log per guard: deny and
ask counts, how often a user approved an ask (the override rate) and degraded
events. That is the evidence required before flipping an ``ask`` to ``deny``
or promoting an opt-in hook. Lines carry ids and flags only (§D.6.2), so the
summary can never show content. Canary lines (self-tests) are not counted.
Stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = ["GuardSummary", "read_decisions", "summarize_decisions"]

#: ``decisions-YYYY-MM[.n].jsonl``: a month file, rotated copies included.
_DECISION_FILE: Final = re.compile(
    r"decisions-(?P<month>[0-9]{4}-(?:0[1-9]|1[0-2]))(?:\.[0-9]+)?\.jsonl"
)
#: Reads stop after this many bytes per file: a summary, not a forensic tool.
_MAX_FILE_BYTES: Final = 8 * 1024 * 1024
_ASKS: Final = frozenset({"ask", "ask→deny"})
_DEGRADED: Final = frozenset({"degraded", "contract_violation"})


@dataclass(frozen=True, slots=True)
class GuardSummary:
    """One guard's counts over the summarized window.

    Example::

        >>> GuardSummary("g", deny=1, ask=4, override=1, degraded=0).override_rate
        0.25
    """

    hook_id: str
    deny: int = 0
    ask: int = 0
    override: int = 0
    degraded: int = 0

    @property
    def override_rate(self) -> float | None:
        """Overrides per ask (the user approved what the guard asked), ``None`` without asks."""
        return None if self.ask == 0 else self.override / self.ask

    def line(self) -> str:
        """``deny 1, ask 4, override 1 (25%), degraded 0``: the doctor detail text."""
        rate = self.override_rate
        shown = "n/a" if rate is None else f"{round(rate * 100)}%"
        return (
            f"deny {self.deny}, ask {self.ask}, override {self.override} ({shown}), "
            f"degraded {self.degraded}"
        )


def read_decisions(state_dir: Path, *, since_ts: str) -> list[dict[str, Any]]:
    """Every decision line under ``state_dir`` stamped at or after ``since_ts``, oldest file first.

    ``since_ts`` is ISO-8601 UTC (the lines' own format, so strings compare in
    time order); month files wholly before it are not opened. Unparsable lines
    are skipped: the log is never trusted to be well formed.

    Example::

        >>> read_decisions(state_dir, since_ts="2026-09-14T00:00:00.000Z")  # doctest: +SKIP
        [{'decision': 'deny', 'hook_id': 'destructive-command-guard', ...}]
    """
    try:
        names = sorted(os.listdir(state_dir))
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for name in names:
        match = _DECISION_FILE.fullmatch(name)
        if match is None or match["month"] < since_ts[:7]:
            continue
        records.extend(r for r in _lines(state_dir / name) if str(r.get("ts", "")) >= since_ts)
    return records


def summarize_decisions(records: Iterable[dict[str, Any]]) -> list[GuardSummary]:
    """Per-guard deny/ask/override/degraded counts, sorted by hook id; canary lines skipped.

    ``ask→deny`` (an ask nobody could answer) counts as an ask; a
    ``contract_violation`` counts as degraded.

    Example::

        >>> summarize_decisions([{"hook_id": "g", "decision": "deny", "canary": False}])
        [GuardSummary(hook_id='g', deny=1, ask=0, override=0, degraded=0)]
    """
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        hook_id, decision = record.get("hook_id"), record.get("decision")
        if record.get("canary") is True or not isinstance(hook_id, str):
            continue
        bucket = _bucket(decision)
        if bucket is not None:
            tally = counts.setdefault(hook_id, {})
            tally[bucket] = tally.get(bucket, 0) + 1
    return [GuardSummary(hook_id, **tally) for hook_id, tally in sorted(counts.items())]


def _bucket(decision: object) -> str | None:
    if decision == "deny" or decision == "override":
        return str(decision)
    if decision in _ASKS:
        return "ask"
    return "degraded" if decision in _DEGRADED else None


def _lines(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as handle:
            data = handle.read(_MAX_FILE_BYTES)
    except OSError:
        return []
    parsed: list[dict[str, Any]] = []
    for raw in data.splitlines():
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed
