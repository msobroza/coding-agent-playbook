"""What the metrics gate measures statically: targets, candidate and baseline sources.

These are the helpers behind
:func:`~coding_agent_playbook.metrics_gate.run.run_metrics_gate`
(prK §F.0.3 items 1 and 7), moved out of ``commands/metrics.py``; the suite runs
live in :mod:`~coding_agent_playbook.metrics_gate.suite`. Both measure through the
grading kernel's one measuring pass (:mod:`coding_agent_playbook.grading.measuring`),
the one eval scoring uses too. Every input the gate cannot use raises
:class:`MetricsGateUsageError`, whose message ``playbook metrics`` prints verbatim
before exiting 2.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.baseline_git import BaselineGitError, GitTimeoutError
from coding_agent_playbook.grading.measuring import measure_files, python_files
from coding_agent_playbook.grading.paths import matches_any_glob

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.grading.baseline_git import BaselineGit
    from coding_agent_playbook.grading.measuring import SourceMeter, TreeMeasurements
    from coding_agent_playbook.grading.types import Measurement

#: The ``--baseline`` prefix that names a git ref instead of a directory.
GIT_PREFIX = "git:"

#: The ``--baseline`` prefix that names an ``--emit-measurements`` snapshot file.
JSON_PREFIX = "json:"


class MetricsGateUsageError(Exception):
    """An input the metrics gate cannot use: a bad path, baseline, config or command.

    The message is the CLI's ``error:`` text verbatim (``playbook metrics`` exits
    2 on it), so a hook that reports it says exactly what the CLI would.

    Example::

        >>> str(MetricsGateUsageError("path not found: src/missing.py"))
        'path not found: src/missing.py'
    """


# --------------------------------------------------------------------------- #
# Target discovery
# --------------------------------------------------------------------------- #


def discover_targets(paths: Sequence[str], repo_root: Path) -> list[Path]:
    """Resolve PATHS into a sorted, de-duplicated list of ``*.py`` files.

    Each entry may be a ``.py`` file or a directory (recursed by
    :func:`~coding_agent_playbook.grading.measuring.python_files`, skipping dotdirs
    and ``IGNORED_DIRS``). With no PATHS, defaults to ``<repo_root>/src`` if
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
            found.update(path.resolve() for path in python_files(root))
        else:
            raise MetricsGateUsageError(f"path not found: {root}")
    return sorted(found)


def filter_targets(
    targets: Sequence[Path],
    repo_root: Path,
    *,
    exclude: Sequence[str],
    changed: frozenset[str] | None = None,
) -> list[Path]:
    """Drop the targets an ``exclude`` glob matches; with ``changed``, also every one not in it.

    Globs and ``changed`` hold paths relative to ``repo_root``. A target outside
    ``repo_root`` matches no glob, and is never "changed": git cannot report it.

    Example::

        >>> filter_targets(targets, root, exclude=("gen/**",), changed=frozenset({"a.py"}))
        [PosixPath('/repo/a.py')]
    """
    kept: list[Path] = []
    for target in targets:
        rel = _repo_rel_path(target, repo_root)
        if rel is not None and matches_any_glob(rel, exclude):
            continue
        if changed is None or rel in changed:
            kept.append(target)
    return kept


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


def measure_candidates(
    targets: Sequence[Path], repo_root: Path, meter: SourceMeter
) -> TreeMeasurements:
    """Measure every target, labelled repo-relative (:func:`rel_label`).

    A file that cannot be read, parsed or measured is skipped with a reason: a
    hostile file costs a note, never a traceback, because the gate runs inside hooks.
    """
    return measure_files([(target, rel_label(target, repo_root)) for target in targets], meter)


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
            measurements.extend(meter.measure_file_or_drop(base_file, label))
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
