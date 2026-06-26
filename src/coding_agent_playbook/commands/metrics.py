"""``playbook metrics`` — standalone static code-quality gate (PR-M Track M3).

Measures the static evaluators (cyclomatic complexity, maintainability index,
WMC, LCOM4, DIT, CBO≈) over a set of Python files, optionally diffing against a
baseline (a git ref or a directory), grades the result with
:func:`~coding_agent_playbook.evaluators.grade.grade`, and exits non-zero on a
breach — mirroring ``playbook check``'s convention.

Usage::

    playbook metrics [PATHS…] [--baseline git:REF|DIR] [--mode regression|absolute|both]
                     [--strict] [--format text|json] [--repo-root DIR]

* **Default PATHS** — when none are given, the repo's ``src/`` directory if it
  exists, else the repo root (``--repo-root`` or cwd). Directories recurse for
  ``*.py``, skipping dotdirs and common ignores (``__pycache__``, ``.venv``,
  ``venv``, ``node_modules``, ``build``, ``dist``, ``.git``).
* **Baseline** — ``--baseline git:<ref>`` reads each candidate's prior source via
  ``git show <ref>:<relpath>`` (a file missing in the ref is all-new); ``--baseline
  <dir>`` reads the matching relative file under ``<dir>``. With no baseline (or
  ``regression``/``both`` requested without one) the gate falls back to absolute
  mode and notes it.
* **Config** — a ``[metrics]`` table in ``.coding-agent-playbook.toml`` (parsed by
  :func:`coding_agent_playbook.config.parse_metrics_config`) seeds the
  :class:`~coding_agent_playbook.evaluators.types.MetricConfig`; CLI flags
  override it.

Exit codes: ``0`` pass; ``1`` when ``report.passed`` is ``False`` and
``fail_on_breach``; ``2`` on usage errors (bad path, bad baseline ref/dir).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.config import parse_metrics_config
from coding_agent_playbook.evaluators import (
    EvalContext,
    Measurement,
    MetricConfig,
    grade,
    parse_module,
    static_evaluators,
)

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.evaluators import EvaluationReport, Evaluator, Finding


_CONFIG_FILENAME = ".coding-agent-playbook.toml"

#: Directory names never recursed into during ``*.py`` discovery.
_IGNORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

_VALID_MODES = ("regression", "absolute", "both")
_VALID_FORMATS = ("text", "json")


class _UsageError(Exception):
    """Raised for a bad path / baseline — translated to exit code 2."""


# --------------------------------------------------------------------------- #
# Target discovery
# --------------------------------------------------------------------------- #


def _discover_targets(paths: list[str], repo_root: Path) -> list[Path]:
    """Resolve PATHS into a sorted, de-duplicated list of ``*.py`` files.

    Each entry may be a ``.py`` file or a directory (recursed, skipping dotdirs
    and :data:`_IGNORED_DIRS`). With no PATHS, defaults to ``<repo_root>/src`` if
    it exists, else ``<repo_root>``. Raises :class:`_UsageError` for a path that
    does not exist.
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
            raise _UsageError(f"path not found: {root}")
    return sorted(found)


def _iter_py_files(directory: Path) -> list[Path]:
    """Recurse ``directory`` for ``*.py`` files, skipping ignored/dot dirs."""
    out: list[Path] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_dir():
            if entry.name.startswith(".") or entry.name in _IGNORED_DIRS:
                continue
            out.extend(_iter_py_files(entry))
        elif entry.is_file() and entry.suffix == ".py":
            out.append(entry.resolve())
    return out


def _rel_label(path: Path, repo_root: Path) -> str:
    """Repo-relative POSIX label for ``path`` (falls back to the name)."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #


def _measure_source(source: str, label: str, evaluators: list[Evaluator]) -> list[Measurement]:
    """Parse ``source`` and run every available static evaluator over it.

    Raises :exc:`SyntaxError` when the source does not parse (the caller decides
    whether to skip the file).
    """
    module = parse_module(source, label)
    ctx = EvalContext(module=module, source=source, label=label)
    measurements: list[Measurement] = []
    for evaluator in evaluators:
        if evaluator.available(ctx):
            measurements.extend(evaluator.evaluate(ctx))
    return measurements


# --------------------------------------------------------------------------- #
# Baseline resolution
# --------------------------------------------------------------------------- #


def _git_show(repo_root: Path, ref: str, rel_path: str) -> str | None:
    """Return the source of ``rel_path`` at ``ref`` via ``git show``.

    ``None`` when the file does not exist in that ref (all-new file). Raises
    :class:`_UsageError` when the ref itself is invalid or the dir is not a git
    repo.
    """
    spec = f"{ref}:{rel_path}"
    proc = subprocess.run(
        ["git", "show", spec],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return proc.stdout
    stderr = proc.stderr.lower()
    # "does not exist" / "exists on disk, but not in" => file absent at ref.
    if "does not exist" in stderr or "exists on disk" in stderr:
        return None
    # An invalid ref or a non-git dir is a usage error.
    raise _UsageError(f"bad --baseline git ref {ref!r}: {proc.stderr.strip()}")


def _validate_git_ref(repo_root: Path, ref: str) -> None:
    """Fail fast (exit 2) when ``ref`` is not a resolvable git revision."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise _UsageError(f"bad --baseline git ref {ref!r} (not a valid revision)")


def _baseline_measurements(
    baseline: str,
    targets: list[Path],
    repo_root: Path,
    evaluators: list[Evaluator],
) -> list[Measurement]:
    """Measure the baseline variant of each target file.

    ``baseline`` is ``git:<ref>`` (read via ``git show``) or a directory path
    (read the matching relative file). A file absent from the baseline yields no
    measurements, so :func:`grade` treats it as all-new.
    """
    measurements: list[Measurement] = []
    if baseline.startswith("git:"):
        ref = baseline[len("git:") :]
        _validate_git_ref(repo_root, ref)
        for target in targets:
            label = _rel_label(target, repo_root)
            source = _git_show(repo_root, ref, label)
            if source is None:
                continue
            measurements.extend(_safe_measure(source, label, evaluators))
        return measurements

    base_dir = Path(baseline)
    if not base_dir.is_dir():
        raise _UsageError(f"baseline directory not found: {base_dir}")
    for target in targets:
        label = _rel_label(target, repo_root)
        base_file = base_dir / label
        if not base_file.is_file():
            continue
        source = base_file.read_text(encoding="utf-8")
        measurements.extend(_safe_measure(source, label, evaluators))
    return measurements


def _safe_measure(source: str, label: str, evaluators: list[Evaluator]) -> list[Measurement]:
    """Measure a baseline source, swallowing parse errors (drop that file)."""
    try:
        return _measure_source(source, label, evaluators)
    except SyntaxError:
        return []


# --------------------------------------------------------------------------- #
# Config + flag merge
# --------------------------------------------------------------------------- #


def _load_config(repo_root: Path) -> MetricConfig:
    """Parse ``[metrics]`` from ``.coding-agent-playbook.toml`` if present."""
    config_path = repo_root / _CONFIG_FILENAME
    if not config_path.is_file():
        return MetricConfig()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    return parse_metrics_config(data.get("metrics", {}))


def _merge_flags(
    config: MetricConfig, args: argparse.Namespace, *, baseline: str | None
) -> tuple[MetricConfig, str | None]:
    """CLI flags override config; resolve the effective mode + a note.

    ``regression``/``both`` without a baseline degrade to ``absolute`` (returned
    note explains the fallback).
    """
    mode = getattr(args, "mode", None) or config.mode
    strict = config.strict or bool(getattr(args, "strict", False))

    note: str | None = None
    if baseline is None and mode in ("regression", "both"):
        note = f"no --baseline given; '{mode}' mode falls back to 'absolute'."
        mode = "absolute"

    return replace(config, mode=mode, strict=strict), note


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def _report_to_dict(report: EvaluationReport) -> dict[str, object]:
    """Stable JSON-serialisable view of an :class:`EvaluationReport`."""
    return {
        "passed": report.passed,
        "warn_count": report.warn_count,
        "fail_count": report.fail_count,
        "composite": report.composite,
        "findings": [_finding_to_dict(f) for f in report.findings],
    }


def _finding_to_dict(finding: Finding) -> dict[str, object]:
    return {
        "evaluator": finding.evaluator,
        "scope_key": finding.scope_key,
        "value": finding.value,
        "baseline": finding.baseline,
        "bound": finding.bound,
        "score": finding.score,
        "level": finding.level,
        "kind": finding.kind,
    }


def _format_text(
    report: EvaluationReport,
    *,
    skipped: list[tuple[str, str]],
    note: str | None,
    measured_count: int,
) -> str:
    """Human-readable findings grouped by file then scope, plus a summary."""
    lines: list[str] = ["=== Metrics ==="]
    if note:
        lines.append(f"  note: {note}")

    by_file: dict[str, list[Finding]] = {}
    for finding in report.findings:
        if finding.level == "ok":
            continue
        file_key = finding.scope_key.split("::", 1)[0]
        by_file.setdefault(file_key, []).append(finding)

    if not by_file:
        lines.append(f"  OK — {measured_count} file(s) measured, no warnings or failures.")
    else:
        for file_key in sorted(by_file):
            lines.append(f"  {file_key}:")
            for finding in by_file[file_key]:
                scope = (
                    finding.scope_key.split("::", 1)[1] if "::" in finding.scope_key else "(file)"
                )
                detail = _finding_detail(finding)
                lines.append(
                    f"    [{finding.level}] {finding.evaluator} @ {scope} "
                    f"= {finding.value:g} ({finding.kind}{detail})"
                )

    for label, reason in skipped:
        lines.append(f"  skipped {label}: {reason}")

    composite = "n/a" if report.composite is None else f"{report.composite:.3f}"
    verdict = "PASS" if report.passed else "FAIL"
    lines.append(
        f"  summary: {verdict} — {report.fail_count} fail, {report.warn_count} warn, "
        f"composite={composite}"
    )
    return "\n".join(lines)


def _finding_detail(finding: Finding) -> str:
    """A short suffix describing the comparison that decided the finding."""
    if finding.kind == "regression" and finding.baseline is not None:
        return f"; baseline={finding.baseline:g}"
    if finding.bound is not None:
        return f"; bound={finding.bound:g}"
    return ""


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def run(args: argparse.Namespace) -> int:
    """Execute ``playbook metrics``; see the module docstring for the contract."""
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    fmt = getattr(args, "format", None) or "text"
    if fmt not in _VALID_FORMATS:
        print(f"error: unknown --format {fmt!r}", file=sys.stderr)
        return 2
    mode = getattr(args, "mode", None)
    if mode is not None and mode not in _VALID_MODES:
        print(f"error: unknown --mode {mode!r}", file=sys.stderr)
        return 2

    paths = list(getattr(args, "paths", None) or [])
    baseline = getattr(args, "baseline", None)
    evaluators = static_evaluators()

    try:
        targets = _discover_targets(paths, repo_root)
        baseline_measurements = (
            _baseline_measurements(baseline, targets, repo_root, evaluators)
            if baseline is not None
            else None
        )
    except _UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    candidate: list[Measurement] = []
    skipped: list[tuple[str, str]] = []
    measured_count = 0
    for target in targets:
        label = _rel_label(target, repo_root)
        try:
            source = target.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unreadable file is rare
            skipped.append((label, f"unreadable ({exc})"))
            continue
        try:
            candidate.extend(_measure_source(source, label, evaluators))
            measured_count += 1
        except SyntaxError as exc:
            skipped.append((label, f"unparseable ({exc.msg})"))

    config = _load_config(repo_root)
    effective, note = _merge_flags(config, args, baseline=baseline)
    report = grade(candidate, baseline_measurements, effective)

    if fmt == "json":
        print(json.dumps(_report_to_dict(report), indent=2, sort_keys=True))
    else:
        print(_format_text(report, skipped=skipped, note=note, measured_count=measured_count))

    if not report.passed and effective.fail_on_breach:
        return 1
    return 0
