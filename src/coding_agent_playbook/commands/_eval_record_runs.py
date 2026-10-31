"""Run a ``--record``'s samples, ``--jobs`` at a time, checkpointing each one as it ends.

Each unit is one sample (or one pinned sample's edition control) with all its
runs. A unit the checkpoint already holds for the same inputs is reused
(``--resume``, ``evals.record_checkpoint``); the others run on a thread pool of
``--jobs`` workers. Almost all of a unit's time is spent waiting on the harness
and judge subprocesses, so threads are enough, and each run already works in its
own scratch and config directories. A unit that fails stops new units from
starting; units already running finish and are checkpointed before the first
failure is raised, so a rerun with ``--resume`` loses nothing that ended. An
interrupt (Ctrl-C) instead cancels the queue and ends the running units at once:
their agent and judge CLIs get SIGTERM, then SIGKILL, and start no next one.
"""

from __future__ import annotations

import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.record_checkpoint import (
    RecordCheckpoint,
    default_checkpoint_path,
)
from coding_agent_playbook.evals.release_metrics import GRADED_HEAD
from coding_agent_playbook.grading import bounded_subprocess

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.evals.record_checkpoint import CheckpointKey, UnitKind
    from coding_agent_playbook.evals.release_metrics import RecordedTarget, SampleRecord
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.release.edition import Edition


@dataclass(frozen=True)
class RecordUnit:
    """One sample to run ``runs`` times: on the current text, or on its edition as a control.

    ``index`` is the sample's position in the sorted selection, for progress lines.

    Example::

        >>> RecordUnit("sample", sample, 0, "ab12").graded  # doctest: +SKIP
        'head'
    """

    kind: UnitKind
    sample: EvalSample
    index: int
    inputs_digest: str
    edition: Edition | None = None

    @property
    def key(self) -> CheckpointKey:
        return (self.kind, self.sample.id)

    @property
    def graded(self) -> str:
        """The graded source the unit's entry records: ``head`` or the edition tag."""
        return GRADED_HEAD if self.edition is None else self.edition.tag


def open_checkpoint(
    args: argparse.Namespace, out_path: Path, recorded: RecordedTarget
) -> RecordCheckpoint:
    """The run's checkpoint (``--checkpoint``, else beside ``out_path``); with ``--resume``,
    say how many samples it may reuse.

    Example::

        >>> open_checkpoint(args, Path("m/opus.json"), recorded).path.name  # doctest: +SKIP
        'opus.json.partial.jsonl'
    """
    flag = getattr(args, "checkpoint", None)
    path = Path(flag) if flag is not None else default_checkpoint_path(out_path)
    assert recorded.setup is not None  # a record always computes its setup parts
    resume = getattr(args, "resume", False)
    checkpoint = RecordCheckpoint.open(path, setup_digest=recorded.setup.digest, resume=resume)
    if resume:
        print(f"checkpoint: {checkpoint.resumable} finished sample(s) to reuse from {path}")
    return checkpoint


def record_units(
    units: Sequence[RecordUnit],
    *,
    jobs: int,
    run: Callable[[RecordUnit], SampleRecord],
    checkpoint: RecordCheckpoint,
) -> dict[CheckpointKey, SampleRecord]:
    """Every unit's record: reused from ``checkpoint`` when it matches, else run and saved.

    Example::

        >>> record_units(units, jobs=4, run=run_unit, checkpoint=checkpoint)  # doctest: +SKIP
    """
    records: dict[CheckpointKey, SampleRecord] = {}
    pending: list[RecordUnit] = []
    for unit in units:
        kept = checkpoint.resumed(
            unit.kind, unit.sample.id, inputs_digest=unit.inputs_digest, graded=unit.graded
        )
        if kept is None:
            pending.append(unit)
        else:
            records[unit.key] = kept

    def finish(unit: RecordUnit, record: SampleRecord) -> None:
        checkpoint.append(unit.kind, record)
        records[unit.key] = record

    if jobs == 1:
        for unit in pending:
            finish(unit, run(unit))
    else:
        _run_parallel(pending, jobs, run, finish)
    return records


def _run_parallel(
    units: Sequence[RecordUnit],
    jobs: int,
    run: Callable[[RecordUnit], SampleRecord],
    finish: Callable[[RecordUnit, SampleRecord], None],
) -> None:
    """Run ``units`` on ``jobs`` threads; on a failure, cancel the queue and raise it last.

    On an interrupt, or an error of its own, cancel the queue, end the running
    units' bounded children and refuse their next ones, then re-raise.
    """
    halt = threading.Event()
    pool = ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="playbook-record")
    try:
        halting_run = bounded_subprocess.halted_by(halt, run)
        futures = {pool.submit(halting_run, unit): unit for unit in units}
        first_error = _finish_as_completed(futures, finish)
    except BaseException:
        # Why not the pool's own exit: shutdown(wait=True) lets each worker run
        # its unit to the end and then start every queued one, each an agent and
        # a judge run billed after the user asked to stop.
        pool.shutdown(wait=False, cancel_futures=True)
        bounded_subprocess.halt_bounded_runs(halt)
        raise
    pool.shutdown(wait=True)
    if first_error is not None:
        raise first_error


def _finish_as_completed(
    futures: dict[Future[SampleRecord], RecordUnit],
    finish: Callable[[RecordUnit, SampleRecord], None],
) -> Exception | None:
    """Finish each unit as it ends; on the first failure cancel the queue and return it."""
    first_error: Exception | None = None
    for future in as_completed(futures):
        try:
            record = future.result()
        except CancelledError:
            continue
        # Kept, not raised: the units still running finish and are saved first.
        except Exception as exc:
            if first_error is None:
                first_error = exc
                for other in futures:
                    other.cancel()
            continue
        finish(futures[future], record)
    return first_error
