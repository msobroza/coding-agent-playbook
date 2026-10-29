"""The checkpoint of a ``--record`` run: each finished sample, saved as it ends.

A release recording runs every sample several times on a paid harness, for
hours, and writes its metrics file only at the end, so a crash, a timeout or a
sleeping laptop used to lose every finished sample. ``--record`` now appends
each finished sample (or edition control) to a JSON Lines checkpoint
(``--checkpoint``, default ``<record>.partial.jsonl``) and removes it once the
metrics file is written.

The first line is a header naming the run's setup digest
(``evals.setup_digest``); every other line is one :class:`SampleRecord`, as
``build_release_metrics_from_records`` folds it. ``--resume`` reuses a line only
when the header's setup digest is this run's and the entry's inputs digest and
graded source are this run's too, so a reused sample is exactly what a fresh run
would measure; anything else reruns. Without ``--resume`` the file starts over.

The checkpoint doubles as live progress: ``tail -f`` it to see each sample's
passes, runs and mean score as it lands.
"""

from __future__ import annotations

import json
import os
import threading
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.evals.release_metrics import SampleRecord
from coding_agent_playbook.evals.release_metrics_schema import INPUTS_DIGEST_KEY

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: The checkpoint format; a header of another version starts the file over.
CHECKPOINT_VERSION: Final = 1
#: Appended to the record path's name for the default checkpoint path.
CHECKPOINT_SUFFIX: Final = ".partial.jsonl"

#: A line's kind: a sample graded on the current text, or a pinned sample's edition control.
UnitKind = Literal["sample", "control"]
#: A checkpoint line's identity: its kind and its sample id.
CheckpointKey = tuple[UnitKind, str]


def default_checkpoint_path(record: Path) -> Path:
    """The checkpoint beside the metrics file ``record``.

    Example::

        >>> default_checkpoint_path(Path("metrics/opus.json")).name
        'opus.json.partial.jsonl'
    """
    return record.with_name(record.name + CHECKPOINT_SUFFIX)


class RecordCheckpoint:
    """The checkpoint file of one record run; :meth:`append` is safe from worker threads.

    Example::

        >>> checkpoint = RecordCheckpoint.open(path, setup_digest="ab12", resume=False)  # doctest: +SKIP
        >>> checkpoint.append("sample", record)  # doctest: +SKIP
    """

    def __init__(self, path: Path, resumed: Mapping[CheckpointKey, SampleRecord]) -> None:
        self.path = path
        self._resumed = dict(resumed)
        self._lock = threading.Lock()

    @classmethod
    def open(cls, path: Path, *, setup_digest: str, resume: bool) -> RecordCheckpoint:
        """The checkpoint at ``path``, keeping its lines of this setup when ``resume`` is set.

        The file is rewritten with the header and the kept lines only, which
        drops a line cut short by a crash.
        """
        kept = _read_lines(path, setup_digest) if resume else {}
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            _header(setup_digest),
            *(_line(kind, record) for (kind, _), record in kept.items()),
        ]
        partial = path.with_name(path.name + ".tmp")
        partial.write_text("".join(lines), encoding="utf-8")
        partial.replace(path)
        return cls(path, kept)

    @property
    def resumable(self) -> int:
        """How many lines this run may reuse."""
        return len(self._resumed)

    def resumed(
        self, kind: UnitKind, sample_id: str, *, inputs_digest: str, graded: str
    ) -> SampleRecord | None:
        """The kept record of ``sample_id`` when it measured these inputs and graded source."""
        record = self._resumed.get((kind, sample_id))
        if record is None:
            return None
        entry = record.entry
        if entry.get(INPUTS_DIGEST_KEY) != inputs_digest or entry.get("graded") != graded:
            return None
        return record

    def append(self, kind: UnitKind, record: SampleRecord) -> None:
        """Save one finished sample, flushed to disk before returning."""
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(_line(kind, record))
            handle.flush()
            os.fsync(handle.fileno())

    def remove(self) -> None:
        """Delete the checkpoint once the metrics file is written."""
        self.path.unlink(missing_ok=True)


def _header(setup_digest: str) -> str:
    return json.dumps({"checkpoint": CHECKPOINT_VERSION, "setup_digest": setup_digest}) + "\n"


def _line(kind: UnitKind, record: SampleRecord) -> str:
    data = {
        "kind": kind,
        "sample_id": record.sample_id,
        "entry": record.entry,
        "run_tokens": list(record.run_tokens),
        "run_costs": list(record.run_costs),
        "reported_models": list(record.reported_models),
        "answers": list(record.answers),
    }
    return json.dumps(data, sort_keys=True) + "\n"


def _read_lines(path: Path, setup_digest: str) -> dict[CheckpointKey, SampleRecord]:
    """The records of ``path`` measured on ``setup_digest``; none for another setup or no file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    rows = [row for row in (_parse(line) for line in text.splitlines()) if row is not None]
    if not rows or rows[0] != json.loads(_header(setup_digest)):
        return {}
    kept: dict[CheckpointKey, SampleRecord] = {}
    for row in rows[1:]:
        parsed = _record(row)
        if parsed is not None:
            kept[parsed[0]] = parsed[1]
    return kept


def _parse(line: str) -> dict[str, Any] | None:
    """One JSON object line, or ``None`` for a line a crash cut short."""
    try:
        data = json.loads(line)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _record(row: Mapping[str, Any]) -> tuple[CheckpointKey, SampleRecord] | None:
    """The key and record of one line, or ``None`` when it lacks a field."""
    kind = row.get("kind")
    if kind not in ("sample", "control"):
        return None
    try:
        record = SampleRecord(
            sample_id=str(row["sample_id"]),
            entry=dict(row["entry"]),
            run_tokens=tuple(row["run_tokens"]),
            run_costs=tuple(row["run_costs"]),
            reported_models=tuple(row["reported_models"]),
            # A line written before answers were kept (spec D8) has none.
            answers=tuple(dict(answer) for answer in row.get("answers", ())),
        )
    except (KeyError, TypeError, ValueError):
        return None
    return (kind, record.sample_id), record
