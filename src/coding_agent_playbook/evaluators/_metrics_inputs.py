"""What the metrics gate measures: targets, candidate and baseline sources, suite runs.

These are the helpers behind
:func:`~coding_agent_playbook.evaluators.metrics_gate.run_metrics_gate`
(prK §F.0.3 item 1), moved out of ``commands/metrics.py``. Import the public
names from ``metrics_gate``. Every input the gate cannot use raises
:class:`MetricsGateUsageError`, whose message ``playbook metrics`` prints
verbatim before exiting 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from coding_agent_playbook.evaluators.baseline_git import BaselineGitError, GitTimeoutError
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.types import EvalContext

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evaluators.baseline_git import BaselineGit
    from coding_agent_playbook.evaluators.execution.project import ProjectHandle
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.types import Measurement

#: Directory names never recursed into during ``*.py`` discovery.
IGNORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

#: MODULE label the execution metrics key their suite-wide measurements on.
SUITE_LABEL = "suite"

_GIT_PREFIX = "git:"


class MetricsGateUsageError(Exception):
    """An input the metrics gate cannot use: a bad path, baseline, config or command.

    The message is the CLI's ``error:`` text verbatim (``playbook metrics`` exits
    2 on it), so a hook that reports it says exactly what the CLI would.

    Example::

        >>> str(MetricsGateUsageError("path not found: src/missing.py"))
        'path not found: src/missing.py'
    """


class ProjectFactory(Protocol):
    """Builds the :class:`ProjectHandle` a suite run measures (``ProjectHandle.create``)."""

    def __call__(
        self, root: Path, report_dir: Path, test_cmd: list[str] | None = None
    ) -> ProjectHandle: ...


# --------------------------------------------------------------------------- #
# Target discovery
# --------------------------------------------------------------------------- #


def discover_targets(paths: Sequence[str], repo_root: Path) -> list[Path]:
    """Resolve PATHS into a sorted, de-duplicated list of ``*.py`` files.

    Each entry may be a ``.py`` file or a directory (recursed, skipping dotdirs
    and :data:`IGNORED_DIRS`). With no PATHS, defaults to ``<repo_root>/src`` if
    it exists, else ``<repo_root>``. Raises :class:`MetricsGateUsageError` for a
    path that does not exist.

    Example::

        >>> discover_targets(["src/app.py"], Path("."))  # doctest: +SKIP
        [PosixPath('/repo/src/app.py')]
    """
    if not paths:
        default = repo_root / "src"
        roots = [default if default.is_dir() else repo_root]
    else:
        roots = [Path(p) for p in paths]

    found: set[Path] = set()
    for root in roots:
        if root.is_file():
            if root.suffix == ".py":
                found.add(root.resolve())
        elif root.is_dir():
            found.update(_iter_py_files(root))
        else:
            raise MetricsGateUsageError(f"path not found: {root}")
    return sorted(found)


def _iter_py_files(directory: Path) -> list[Path]:
    """Recurse ``directory`` for ``*.py`` files, skipping ignored/dot dirs."""
    out: list[Path] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_dir():
            if entry.name.startswith(".") or entry.name in IGNORED_DIRS:
                continue
            out.extend(_iter_py_files(entry))
        elif entry.is_file() and entry.suffix == ".py":
            out.append(entry.resolve())
    return out


def rel_label(path: Path, repo_root: Path) -> str:
    """Repo-relative POSIX label for ``path`` (falls back to the name)."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _repo_rel_path(path: Path, repo_root: Path) -> str | None:
    """Repo-relative POSIX path for ``path``, or ``None`` if it is outside.

    Unlike :func:`rel_label` this does *not* fall back to the basename, so a
    ``git:`` baseline never resolves an out-of-repo target against a coincidental
    same-named file at the repo root (it is treated as all-new instead).
    """
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Static measurement
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SourceMeter:
    """Measures one Python source with the gate's static metrics."""

    metrics: Sequence[Metric]
    tool_paths: Mapping[str, str]

    def measure(self, source: str, label: str) -> list[Measurement]:
        """Parse ``source`` and run every available metric over it.

        Raises :exc:`SyntaxError` when the source does not parse (the caller
        decides whether to skip the file).
        """
        module = parse_module(source, label)
        ctx = EvalContext(module=module, source=source, label=label, tool_paths=self.tool_paths)
        measurements: list[Measurement] = []
        for metric in self.metrics:
            if metric.available(ctx):
                measurements.extend(metric.measure(ctx))
        return measurements

    def measure_or_drop(self, source: str, label: str) -> list[Measurement]:
        """Measure a baseline source; one that does not parse yields nothing (all-new)."""
        try:
            return self.measure(source, label)
        except SyntaxError:
            return []


@dataclass
class CandidateMeasurements:
    """The candidate side: its measurements, the files skipped and why, and the measured count."""

    measurements: list[Measurement] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    measured_count: int = 0


def measure_candidates(
    targets: Sequence[Path], repo_root: Path, meter: SourceMeter
) -> CandidateMeasurements:
    """Measure every target; a file that cannot be read or parsed is skipped with a reason."""
    out = CandidateMeasurements()
    for target in targets:
        label = rel_label(target, repo_root)
        try:
            source = target.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file is rare
            out.skipped.append((label, f"unreadable ({exc})"))
            continue
        try:
            out.measurements.extend(meter.measure(source, label))
            out.measured_count += 1
        except SyntaxError as exc:
            out.skipped.append((label, f"unparseable ({exc.msg})"))
    return out


# --------------------------------------------------------------------------- #
# Static baseline
# --------------------------------------------------------------------------- #


def static_baseline(
    baseline: str, targets: Sequence[Path], repo_root: Path, meter: SourceMeter, git: BaselineGit
) -> list[Measurement]:
    """Measure the baseline variant of each target file.

    ``baseline`` is ``git:<ref>`` (one batched read through ``git``) or a
    directory path (read the matching relative file). A file absent from the
    baseline yields no measurements, so the regression check treats it as all-new.
    """
    if baseline.startswith(_GIT_PREFIX):
        return _git_baseline(baseline[len(_GIT_PREFIX) :], targets, repo_root, meter, git)
    base_dir = Path(baseline)
    if not base_dir.is_dir():
        raise MetricsGateUsageError(f"baseline directory not found: {base_dir}")
    measurements: list[Measurement] = []
    for target in targets:
        label = rel_label(target, repo_root)
        base_file = base_dir / label
        if base_file.is_file():
            source = base_file.read_text(encoding="utf-8")
            measurements.extend(meter.measure_or_drop(source, label))
    return measurements


def _git_baseline(
    ref: str, targets: Sequence[Path], repo_root: Path, meter: SourceMeter, git: BaselineGit
) -> list[Measurement]:
    verify_git_ref(git, repo_root, ref)
    # A target outside repo_root has no git-tracked counterpart; treat it as
    # all-new rather than guessing a coincidental same-named repo file.
    rels = [rel for rel in (_repo_rel_path(t, repo_root) for t in targets) if rel is not None]
    try:
        blobs = git.read_sources(repo_root, ref, rels)
    except BaselineGitError as exc:
        raise _usage_error(exc, f"bad --baseline git ref {ref!r}") from exc
    measurements: list[Measurement] = []
    for rel in rels:
        source = _decode_blob(blobs[rel]) if rel in blobs else None
        if source is not None:
            measurements.extend(meter.measure_or_drop(source, rel))
    return measurements


def _decode_blob(raw: bytes) -> str | None:
    """Decode a baseline blob as ``git show`` under ``text=True`` did: UTF-8, universal newlines.

    A blob that is not UTF-8 is dropped (all-new), like one that does not parse.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def verify_git_ref(git: BaselineGit, repo_root: Path, ref: str) -> None:
    """Fail fast (exit 2) when ``ref`` is not a resolvable git revision."""
    try:
        is_commit = git.is_commit(repo_root, ref)
    except BaselineGitError as exc:
        raise _usage_error(exc, f"bad --baseline git ref {ref!r}") from exc
    if not is_commit:
        raise MetricsGateUsageError(f"bad --baseline git ref {ref!r} (not a valid revision)")


def _usage_error(exc: BaselineGitError, context: str) -> MetricsGateUsageError:
    """A git failure as the CLI's exit-2 error; a timeout keeps its own message."""
    if isinstance(exc, GitTimeoutError):
        return MetricsGateUsageError(str(exc))
    return MetricsGateUsageError(f"{context}: {exc}")


# --------------------------------------------------------------------------- #
# Execution metrics (run_tests)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SuiteRun:
    """Runs the execution metrics over one project root: one suite run per root.

    ``test_cmd`` is exactly what runs (``None`` = the handle's isolated pytest
    default); it is never read from ``[metrics] test_cmd``.
    """

    metrics: Sequence[Metric]
    test_cmd: list[str] | None
    project_factory: ProjectFactory
    tool_paths: Mapping[str, str]

    def measure(self, root: Path, report_dir: Path) -> list[Measurement]:
        """Build a handle, run the suite once, and collect execution measurements.

        Every execution metric reads the same handle, so the suite runs exactly
        once. Raises :class:`MetricsGateUsageError` when the suite cannot be run.
        """
        handle = self.project_factory(root, report_dir, test_cmd=self.test_cmd)
        ctx = EvalContext(
            module=None, source="", label=SUITE_LABEL, project=handle, tool_paths=self.tool_paths
        )
        measurements: list[Measurement] = []
        try:
            for metric in self.metrics:
                if metric.available(ctx):
                    measurements.extend(metric.measure(ctx))
        except RuntimeError as exc:
            raise MetricsGateUsageError(str(exc)) from exc
        return measurements


def suite_baseline(
    baseline: str, repo_root: Path, suite: SuiteRun, work_dir: Path, git: BaselineGit
) -> list[Measurement]:
    """Run the execution metrics on the baseline (a git ref or a directory).

    ``git:<ref>`` materialises the ref via a temporary worktree under
    ``work_dir`` (removed afterwards); ``<dir>`` runs the suite directly in that
    directory. Raises :class:`MetricsGateUsageError` on a bad ref, a non-git dir,
    a missing directory, a git timeout or an unrunnable suite.
    """
    if baseline.startswith(_GIT_PREFIX):
        ref = baseline[len(_GIT_PREFIX) :]
        verify_git_ref(git, repo_root, ref)
        return _suite_in_worktree(ref, repo_root, suite, work_dir, git)
    base_dir = Path(baseline)
    if not base_dir.is_dir():
        raise MetricsGateUsageError(f"baseline directory not found: {base_dir}")
    return suite.measure(base_dir, work_dir / "baseline-reports")


def _suite_in_worktree(
    ref: str, repo_root: Path, suite: SuiteRun, work_dir: Path, git: BaselineGit
) -> list[Measurement]:
    """Materialise ``ref`` in a temp git worktree, run the suite, then clean up."""
    worktree = work_dir / "baseline-worktree"
    try:
        git.add_worktree(repo_root, worktree, ref)
    except BaselineGitError as exc:
        raise _usage_error(exc, f"could not create baseline worktree for {ref!r}") from exc
    try:
        return suite.measure(worktree, work_dir / "baseline-reports")
    finally:
        git.remove_worktree(repo_root, worktree)
