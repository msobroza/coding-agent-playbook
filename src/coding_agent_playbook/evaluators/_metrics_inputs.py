"""What the metrics gate measures statically: targets, candidate and baseline sources.

These are the helpers behind
:func:`~coding_agent_playbook.evaluators.metrics_gate.run_metrics_gate`
(prK §F.0.3 items 1 and 7), moved out of ``commands/metrics.py``; the suite runs
live in ``_metrics_suite``. Import the public names from ``metrics_gate``. Every
input the gate cannot use raises :class:`MetricsGateUsageError`, whose message
``playbook metrics`` prints verbatim before exiting 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.baseline_git import BaselineGitError, GitTimeoutError
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.types import EvalContext

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evaluators.baseline_git import BaselineGit
    from coding_agent_playbook.evaluators.metric import Metric
    from coding_agent_playbook.evaluators.types import Measurement

#: Directory names never recursed into during ``*.py`` discovery.
IGNORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

#: The ``--baseline`` prefix that names a git ref instead of a directory.
GIT_PREFIX = "git:"

#: Default ``MetricsGateRequest.max_file_bytes``: a larger candidate or baseline
#: file is never parsed. A module that size is generated or vendored, and parsing
#: it would blow the Stop stage budget.
MAX_FILE_BYTES = 1_000_000

#: What a hostile or broken source can raise while it is parsed and measured
#: (prK §F.0.3 item 7). CPython reports a parser stack overflow on a deeply
#: nested source as MemoryError ("too complex to parse"), not RecursionError.
#: UnicodeDecodeError is a ValueError.
_BAD_SOURCE_ERRORS = (SyntaxError, RecursionError, MemoryError, ValueError)


class MetricsGateUsageError(Exception):
    """An input the metrics gate cannot use: a bad path, baseline, config or command.

    The message is the CLI's ``error:`` text verbatim (``playbook metrics`` exits
    2 on it), so a hook that reports it says exactly what the CLI would.

    Example::

        >>> str(MetricsGateUsageError("path not found: src/missing.py"))
        'path not found: src/missing.py'
    """


class _SkippedSource(Exception):
    """Why one source file is not measured: the text after ``skipped <label>: ``."""


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
    """Reads and measures Python sources with the gate's static metrics.

    A file over ``max_file_bytes`` is never read into the parser.
    """

    metrics: Sequence[Metric]
    tool_paths: Mapping[str, str]
    max_file_bytes: int = MAX_FILE_BYTES

    def measure(self, source: str, label: str) -> list[Measurement]:
        """Parse ``source`` and run every available metric over it.

        Raises what a broken source makes the parser or a metric raise
        (:data:`_BAD_SOURCE_ERRORS`); the caller skips or drops the file.
        """
        module = parse_module(source, label)
        ctx = EvalContext(module=module, source=source, label=label, tool_paths=self.tool_paths)
        measurements: list[Measurement] = []
        for metric in self.metrics:
            if metric.available(ctx):
                measurements.extend(metric.measure(ctx))
        return measurements

    def measure_or_drop(self, source: str, label: str) -> list[Measurement]:
        """Measure a baseline source; one that breaks the parser or a metric yields nothing (all-new)."""
        try:
            return self.measure(source, label)
        except _BAD_SOURCE_ERRORS:
            return []

    def read(self, path: Path) -> str:
        """``path`` as UTF-8 text; raises :class:`_SkippedSource` when unreadable or too large."""
        try:
            size = path.stat().st_size
            source = None if size > self.max_file_bytes else path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _SkippedSource(f"unreadable ({exc})") from exc
        if source is None:
            raise _SkippedSource(
                f"too large ({size} bytes, over the {self.max_file_bytes}-byte cap)"
            )
        return source

    def decode_blob(self, raw: bytes) -> str | None:
        """A git baseline blob as text, like ``git show`` under ``text=True``: UTF-8, universal newlines.

        ``None`` (the file counts as all-new, like one that does not parse) when
        the blob is over the cap or not UTF-8.
        """
        if len(raw) > self.max_file_bytes:
            return None
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class CandidateMeasurements:
    """The candidate side: its measurements, the files skipped and why, and the measured count."""

    measurements: list[Measurement] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    measured_count: int = 0


def measure_candidates(
    targets: Sequence[Path], repo_root: Path, meter: SourceMeter
) -> CandidateMeasurements:
    """Measure every target; one that cannot be read, parsed or measured is skipped with a reason.

    A hostile file costs a note, never a traceback: the gate runs inside hooks.
    """
    out = CandidateMeasurements()
    for target in targets:
        label = rel_label(target, repo_root)
        reason = _measure_candidate(target, label, meter, out.measurements)
        if reason is None:
            out.measured_count += 1
        else:
            out.skipped.append((label, reason))
    return out


def _measure_candidate(
    target: Path, label: str, meter: SourceMeter, into: list[Measurement]
) -> str | None:
    """Measure one candidate into ``into``; the skip reason, or ``None`` once measured."""
    try:
        into.extend(meter.measure(meter.read(target), label))
    except _SkippedSource as exc:
        return str(exc)
    except _BAD_SOURCE_ERRORS as exc:
        return _skip_reason(exc)
    return None


def _skip_reason(exc: Exception) -> str:
    """The note for a source that broke the parser or a metric."""
    if isinstance(exc, SyntaxError):
        return f"unparseable ({exc.msg})"
    if isinstance(exc, MemoryError):
        return "unparseable (too complex to parse)"
    if isinstance(exc, RecursionError):
        return "too deeply nested to measure"
    return f"unmeasurable ({exc})"


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
    if baseline.startswith(GIT_PREFIX):
        return _git_baseline(baseline[len(GIT_PREFIX) :], targets, repo_root, meter, git)
    base_dir = Path(baseline)
    if not base_dir.is_dir():
        raise MetricsGateUsageError(f"baseline directory not found: {base_dir}")
    measurements: list[Measurement] = []
    for target in targets:
        label = rel_label(target, repo_root)
        base_file = base_dir / label
        if base_file.is_file():
            measurements.extend(_measure_baseline_file(base_file, label, meter))
    return measurements


def _measure_baseline_file(path: Path, label: str, meter: SourceMeter) -> list[Measurement]:
    """A baseline file that cannot be read or is too large counts as all-new."""
    try:
        source = meter.read(path)
    except _SkippedSource:
        return []
    return meter.measure_or_drop(source, label)


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
        raise git_usage_error(exc, f"bad --baseline git ref {ref!r}") from exc
    measurements: list[Measurement] = []
    for rel in rels:
        source = meter.decode_blob(blobs[rel]) if rel in blobs else None
        if source is not None:
            measurements.extend(meter.measure_or_drop(source, rel))
    return measurements


def verify_git_ref(git: BaselineGit, repo_root: Path, ref: str) -> None:
    """Fail fast (exit 2) when ``ref`` is not a resolvable git revision."""
    try:
        is_commit = git.is_commit(repo_root, ref)
    except BaselineGitError as exc:
        raise git_usage_error(exc, f"bad --baseline git ref {ref!r}") from exc
    if not is_commit:
        raise MetricsGateUsageError(f"bad --baseline git ref {ref!r} (not a valid revision)")


def git_usage_error(exc: BaselineGitError, context: str) -> MetricsGateUsageError:
    """A git failure as the CLI's exit-2 error; a timeout keeps its own message."""
    if isinstance(exc, GitTimeoutError):
        return MetricsGateUsageError(str(exc))
    return MetricsGateUsageError(f"{context}: {exc}")
