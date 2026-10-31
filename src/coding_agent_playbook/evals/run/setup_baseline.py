"""The sample's ``setup/`` baseline, read into engine memory once per sample before any agent runs.

Scoring compares an agent's work with the sample's catalog ``setup/``
(:attr:`~coding_agent_playbook.evals.sample.EvalSample.setup_dir`): ``file_unchanged``
compares bytes with it, the static and suite rows of the non-regression checks are
measured over it, and the suite integrity rules compare the candidate's session
with its suite's. That directory is not out of the agent's reach: with an
editable install it is the user's checkout, and the agent and the scoring suite
run as the same user. So the engine reads it once, before any agent code runs:

* :func:`take_setup_snapshot` reads every regular file of ``setup/`` into a
  :class:`SetupSnapshot` (path to bytes, and a digest of them);
* :func:`prepare_setup_baseline` measures that snapshot once per sample, from a
  temporary tree written from it: the static rows and, when the rubric runs the
  suite, the baseline suite's rows and session record. Every trial grades against
  this one :class:`SetupBaseline`, which also saves one suite run per trial;
* the runner materializes each trial's scratch repo from the snapshot, so every
  trial starts from the same bytes, and scoring writes the ``file_unchanged``
  baseline tree from it only after the trial's suite exited;
* :func:`require_catalog_unchanged` compares the live catalog ``setup/`` with the
  snapshot after the candidate's suite, and stops the sample
  (:class:`CatalogSetupChangedError`, exit 2) when the agent or its code wrote
  there: the grade is still made from the snapshot, but the checkout must be restored.

What this cannot stop: a process the agent or its tests start that leaves its
session (a ``setsid`` daemon) keeps running as the same user after the suite.
It cannot reach this sample's baseline, measured before any agent ran, but it
can rewrite a later sample's temporary trees (its baseline tree among them);
only a sandbox or another user keeps it out.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.scoring_suite import (
    UnscorableSuiteError,
    check_suite_toolchain,
    open_suite_handle,
    static_metrics_of,
    suite_metrics_of,
    suite_rows,
    tree_static_rows,
)
from coding_agent_playbook.grading.types import MeasureSetup

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle
    from coding_agent_playbook.grading.execution_metrics.suite_record import SuiteRecord
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.types import Measurement


class BaselineSuiteError(UnscorableSuiteError):
    """The ``setup/`` baseline's own suite gave no result: the sample author's to fix."""


class CatalogSetupChangedError(UnscorableSuiteError):
    """The catalog ``setup/`` changed while the sample ran: the checkout must be restored."""


class UnexpectedSetupEntryError(ValueError):
    """A ``setup/`` entry that is neither a regular file nor a directory (a symlink, a device).

    ``rel_path`` is its POSIX path relative to ``setup/``.
    """

    def __init__(self, message: str, *, rel_path: str) -> None:
        super().__init__(message)
        self.rel_path = rel_path


@dataclass(frozen=True)
class SetupSnapshot:
    """Every regular file of a ``setup/`` tree, read into memory: relative POSIX path to bytes.

    ``digest`` is a sha256 over the sorted paths and their bytes, so two
    snapshots with the same files have the same digest.

    Example::

        >>> take_setup_snapshot(sample.setup_dir).files["mod.py"][:3]  # doctest: +SKIP
        b'def'
    """

    files: Mapping[str, bytes]
    digest: str

    def write_tree(self, dest: Path) -> Path:
        """Write every file of the snapshot under ``dest`` (created if missing); return ``dest``.

        Example::

            >>> snapshot.write_tree(Path(tmp) / "setup")  # doctest: +SKIP
            PosixPath('/tmp/.../setup')
        """
        dest.mkdir(parents=True, exist_ok=True)
        for rel, data in self.files.items():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return dest


def take_setup_snapshot(setup_dir: Path) -> SetupSnapshot:
    """Read every regular file under ``setup_dir`` into a :class:`SetupSnapshot`.

    A missing ``setup_dir`` gives an empty snapshot (a sample with no fixture). An
    entry that is neither a regular file nor a directory raises
    :class:`UnexpectedSetupEntryError` (a :exc:`ValueError`) naming it: a symlink
    would let the tree's bytes change after the snapshot without changing it.

    Example::

        >>> sorted(take_setup_snapshot(sample.setup_dir).files)  # doctest: +SKIP
        ['mod.py', 'test_mod.py']
    """
    files = _setup_files(setup_dir) if setup_dir.is_dir() else {}
    return SetupSnapshot(MappingProxyType(files), _digest(files))


def _setup_files(setup_dir: Path) -> dict[str, bytes]:
    """``{relative POSIX path: bytes}`` for every regular file under ``setup_dir``, sorted."""
    files: dict[str, bytes] = {}
    for root, dirnames, filenames in os.walk(setup_dir):
        for name in sorted((*dirnames, *filenames)):
            _read_entry(Path(root) / name, setup_dir, files)
    return dict(sorted(files.items()))


def _read_entry(path: Path, setup_dir: Path, files: dict[str, bytes]) -> None:
    """Add ``path``'s bytes to ``files`` when it is a regular file; skip a directory; else raise."""
    mode = path.lstat().st_mode
    rel = path.relative_to(setup_dir).as_posix()
    if stat.S_ISDIR(mode):
        return
    if not stat.S_ISREG(mode):
        raise UnexpectedSetupEntryError(
            f"{path} in setup/ is neither a regular file nor a directory (a symlink or a "
            "device); a sample's setup/ must hold only regular files and directories",
            rel_path=rel,
        )
    files[rel] = path.read_bytes()


def _digest(files: Mapping[str, bytes]) -> str:
    """A sha256 over ``files``' sorted paths and their bytes, each length-prefixed."""
    sha = hashlib.sha256()
    for rel in sorted(files):
        data = files[rel]
        sha.update(f"{rel}\0{len(data)}\0".encode())
        sha.update(data)
    return sha.hexdigest()


@dataclass(frozen=True)
class SetupBaseline:
    """One sample's ``setup/`` baseline, measured once from its snapshot before any agent ran.

    ``static_rows`` are the static metrics over the snapshot's ``*.py`` files;
    ``suite_rows`` and ``record`` the baseline suite's rows and session record,
    empty and ``None`` when the sample's rubric runs no suite. ``setup_dir`` is the
    catalog directory the snapshot was read from, for messages and
    :func:`require_catalog_unchanged`.

    Example::

        >>> prepare_setup_baseline(sample).snapshot.digest  # doctest: +SKIP
        '3f2a...'
    """

    sample_id: str
    setup_dir: Path
    snapshot: SetupSnapshot
    static_rows: tuple[Measurement, ...] = ()
    suite_rows: tuple[Measurement, ...] = ()
    record: SuiteRecord | None = None


def prepare_setup_baseline(
    sample: EvalSample, *, snapshot: SetupSnapshot | None = None
) -> SetupBaseline:
    """Measure ``sample``'s ``setup/`` once, from ``snapshot`` (default: one taken now).

    The runner calls it once per sample, before any agent runs, and every trial
    grades against the result. Why before: a process an agent's suite started
    could otherwise rewrite the baseline's temporary tree before its suite ran;
    and why once: the baseline does not depend on the agent, so a per-trial run
    only cost one more suite run per trial. The temporary tree is removed before
    this returns. Raises :class:`BaselineSuiteError` when the baseline suite gives
    no result, and :class:`~coding_agent_playbook.evals.run.scoring_suite.SuiteToolchainError`
    when this interpreter cannot run it.

    Example::

        >>> baseline = prepare_setup_baseline(sample)  # doctest: +SKIP
        >>> score(sample, baseline, candidate).passed  # doctest: +SKIP
        True
    """
    from coding_agent_playbook.evals.sample import compile_eval_sample

    snapshot = take_setup_snapshot(sample.setup_dir) if snapshot is None else snapshot
    rubric = compile_eval_sample(sample).per_trial
    setup = MeasureSetup()
    with ExitStack() as stack:
        work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-eval-setup-")))
        tree = snapshot.write_tree(work / "setup")
        static = tuple(tree_static_rows(tree, static_metrics_of(rubric), setup))
        execution = suite_metrics_of(rubric)
        if not execution:
            return SetupBaseline(sample.id, sample.setup_dir, snapshot, static_rows=static)
        check_suite_toolchain()
        handle = open_suite_handle(tree, stack)
        rows = _baseline_suite_rows(sample, handle, execution, setup)
        return SetupBaseline(
            sample.id,
            sample.setup_dir,
            snapshot,
            static_rows=static,
            suite_rows=tuple(rows),
            record=handle.run().record,
        )


def _baseline_suite_rows(
    sample: EvalSample, handle: ProjectHandle, metrics: list[Metric], setup: MeasureSetup
) -> list[Measurement]:
    """``sample``'s ``setup/`` suite measurements; :class:`BaselineSuiteError` when it gave none.

    Why raise: ``setup/`` is the sample author's, so its failure is not the agent's
    to carry, and a regression check with no baseline row grades a "new" scope
    against unset bounds and passes. The message names the catalog ``setup/``,
    the tree the author edits, not the temporary tree the suite ran in.
    """
    rows = suite_rows(handle, metrics, setup)
    if handle.no_result is not None:
        raise BaselineSuiteError(
            f"the setup/ baseline suite of {sample.id} ({sample.setup_dir}) gave no result "
            f"({handle.no_result.reason}); a sample's setup/ suite must finish and write its reports"
        )
    return rows


def require_catalog_unchanged(baseline: SetupBaseline) -> None:
    """Raise :class:`CatalogSetupChangedError` when the catalog ``setup/`` left its snapshot.

    Scoring calls it after the candidate's suite. Grading never reads the live
    catalog, so the trial's grade would be right; but the checkout is the user's,
    and every later sample and run would read the edited files.

    Example::

        >>> require_catalog_unchanged(prepare_setup_baseline(sample))  # doctest: +SKIP
    """
    changed = first_setup_change(baseline.snapshot, baseline.setup_dir)
    if changed is None:
        return
    raise CatalogSetupChangedError(
        f"the catalog setup/ of {baseline.sample_id} ({baseline.setup_dir}) changed while the "
        f"sample ran, first at {changed}: the agent or its code wrote there, so the sample "
        f"cannot be scored; restore it (for example with git checkout -- {baseline.setup_dir}) "
        "and run the sample again"
    )


def first_setup_change(snapshot: SetupSnapshot, setup_dir: Path) -> str | None:
    """The first path (sorted) at which ``setup_dir`` differs from ``snapshot``; ``None`` if none.

    A file added, removed or rewritten counts, and so does an entry a snapshot
    refuses (a symlink, a device) or one that cannot be read.

    Example::

        >>> first_setup_change(snapshot, sample.setup_dir) is None  # doctest: +SKIP
        True
    """
    try:
        live = take_setup_snapshot(setup_dir)
    except UnexpectedSetupEntryError as exc:
        return exc.rel_path
    except OSError as exc:
        return str(exc.filename or setup_dir)
    if live.digest == snapshot.digest:
        return None
    old, new = snapshot.files, live.files
    changed = (old.keys() ^ new.keys()) | {
        rel for rel in old.keys() & new.keys() if old[rel] != new[rel]
    }
    return min(changed) if changed else None
