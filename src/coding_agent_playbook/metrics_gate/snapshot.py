"""Raw-measurement snapshots: what ``--emit-measurements`` writes and ``--baseline json:`` reads.

A snapshot is ``{"schema": 1, "tree": "<git tree id or null>", "measurements":
[{"evaluator", "scope_key", "value"}]}`` (prK §F.0.3 item 4); the keys match
:class:`~coding_agent_playbook.evaluators.types.Measurement` and the
``playbook metrics --format json`` findings. Comparing against a cached
snapshot replaces a second suite run on a baseline worktree: main's CI job
emits one, pull-request jobs and the coverage Stop stage read it.

``tree`` names the commit tree the measurements belong to, ``null`` when the
worktree was not clean, so a reader can tell whether a snapshot is a baseline
for its ``HEAD``.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook._atomic_io import atomic_write_bytes
from coding_agent_playbook.evaluators.types import Measurement

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = [
    "SNAPSHOT_SCHEMA",
    "SnapshotError",
    "read_snapshot",
    "snapshot_document",
    "write_snapshot",
]

#: The only snapshot layout this engine writes and reads.
SNAPSHOT_SCHEMA: Final = 1


class SnapshotError(ValueError):
    """A snapshot that cannot be read or does not have the schema-1 layout.

    Example::

        >>> str(SnapshotError("bad measurement snapshot cov.json: not JSON"))
        'bad measurement snapshot cov.json: not JSON'
    """


def write_snapshot(path: Path, measurements: Sequence[Measurement], *, tree: str | None) -> None:
    """Write ``measurements`` to ``path`` atomically, as a schema-1 snapshot of ``tree``.

    Raises ``OSError`` when ``path`` cannot be written.

    Example::

        >>> write_snapshot(Path("cov.json"), [Measurement("coverage", "a.py", 90.0)], tree=None)
    """
    text = json.dumps(snapshot_document(measurements, tree=tree), indent=2, sort_keys=True)
    atomic_write_bytes(path, (text + "\n").encode("utf-8"))


def snapshot_document(measurements: Sequence[Measurement], *, tree: str | None) -> dict[str, Any]:
    """The schema-1 snapshot of ``measurements`` for ``tree``, as a JSON-ready dict.

    The coverage Stop stage writes it through the hook state store instead of a path.

    Example::

        >>> snapshot_document([], tree="ab12")
        {'schema': 1, 'tree': 'ab12', 'measurements': []}
    """
    return {
        "schema": SNAPSHOT_SCHEMA,
        "tree": tree,
        "measurements": [
            {"evaluator": m.evaluator, "scope_key": m.scope_key, "value": m.value}
            for m in measurements
        ],
    }


def read_snapshot(path: Path) -> list[Measurement]:
    """The measurements of the snapshot at ``path``, in file order.

    Raises :class:`SnapshotError` naming ``path`` when the file is unreadable,
    not JSON, of another schema, or holds a malformed measurement.

    Example::

        >>> read_snapshot(Path("cov.json"))  # doctest: +SKIP
        [Measurement(evaluator='coverage', scope_key='a.py', value=90.0)]
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SnapshotError(f"cannot read measurement snapshot {path}: {exc}") from exc
    try:
        return _measurements(json.loads(text))
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        problem = "not JSON" if isinstance(exc, json.JSONDecodeError) else str(exc)
        raise SnapshotError(f"bad measurement snapshot {path}: {problem}") from exc


def _measurements(document: Any) -> list[Measurement]:
    """Validate a decoded snapshot; raises ``ValueError`` describing the first problem."""
    if not isinstance(document, dict):
        raise ValueError(f"expected a JSON object, got {type(document).__name__}")
    schema = document.get("schema")
    if schema != SNAPSHOT_SCHEMA:
        raise ValueError(f"schema {schema!r} is not supported (expected {SNAPSHOT_SCHEMA})")
    if not isinstance(document.get("tree"), str | None):
        raise ValueError(f"'tree' must be a string or null, got {document['tree']!r}")
    rows = document.get("measurements")
    if not isinstance(rows, list):
        raise ValueError(f"'measurements' must be a list, got {rows!r}")
    return [_measurement(index, row) for index, row in enumerate(rows)]


def _measurement(index: int, row: Any) -> Measurement:
    """One ``{"evaluator", "scope_key", "value"}`` row; the value is a finite number."""
    if isinstance(row, dict):
        evaluator, scope_key, value = row.get("evaluator"), row.get("scope_key"), row.get("value")
        if (
            isinstance(evaluator, str)
            and isinstance(scope_key, str)
            and isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(value)
        ):
            return Measurement(evaluator, scope_key, float(value))
    raise ValueError(
        f"measurement {index} must be {{evaluator: str, scope_key: str, value: number}}, "
        f"got {row!r}"
    )
