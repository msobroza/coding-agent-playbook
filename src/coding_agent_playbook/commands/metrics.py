"""``playbook metrics`` — standalone code-quality gate (PR-M Tracks M3 + M4).

Measures the static metrics (cyclomatic complexity, maintainability index, WMC,
LCOM4, DIT, CBO≈) over a set of Python files, optionally diffing against a
baseline (a git ref or a directory), grades the result through the
:class:`~coding_agent_playbook.evaluators.metric.Metric` /
:class:`~coding_agent_playbook.evaluators.check.Check` /
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` stack, and exits non-zero
on a breach — mirroring ``playbook check``'s convention. With ``--run-tests`` it
also runs the **execution** metrics (``test_pass_rate``, ``coverage``), which
shell out to the target's ``pytest``; execution is opt-in (side effects/cost) and
is **not** in the default pre-commit hook.

The gate is one :class:`Rubric` of metric-backed checks (one per metric in the
gated set), built through the shared
:func:`coding_agent_playbook.evaluators.policy.metric_check` factory the eval-task
compiler also uses — so the standalone gate and an eval task's ``[metrics]`` block
grade with identical per-metric policy. The gated set is the full
:func:`~coding_agent_playbook.evaluators.metric.static_metrics` set (plus
:func:`~coding_agent_playbook.evaluators.metric.execution_metrics` under
``--run-tests``), each check carrying ``config``'s per-metric threshold /
regression / weight override when present, else the metric's ported default — the
faithful successor to the retired ``grade()`` over the full measured set.

Usage::

    playbook metrics [PATHS…] [--baseline git:REF|DIR] [--mode regression|absolute|both]
                     [--strict] [--run-tests] [--test-cmd "…"]
                     [--format text|json] [--repo-root DIR]

* **Default PATHS** — when none are given, the repo's ``src/`` directory if it
  exists, else the repo root (``--repo-root`` or cwd). Directories recurse for
  ``*.py``, skipping dotdirs and common ignores (``__pycache__``, ``.venv``,
  ``venv``, ``node_modules``, ``build``, ``dist``, ``.git``).
* **Baseline** — ``--baseline git:<ref>`` reads each candidate's prior source via
  ``git show <ref>:<relpath>`` (a file missing in the ref is all-new); ``--baseline
  <dir>`` reads the matching relative file under ``<dir>``. With no baseline (or
  ``regression``/``both`` requested without one) the gate falls back to absolute
  mode and notes it.
* **Execution (`--run-tests`)** — builds a ``ProjectHandle`` rooted at
  ``--repo-root`` (or cwd), runs the suite once, and merges the
  ``test_pass_rate``/``coverage`` measurements alongside the static ones.
  ``--test-cmd "…"`` overrides the default ``python -m pytest`` command
  (shlex-split). With a baseline, the suite is also run against the baseline: a
  ``git:<ref>`` baseline is materialised via a temporary ``git worktree`` (heavier
  than the static ``git show``) and a ``<dir>`` baseline runs in that directory.
* **Config** — a ``[metrics]`` table in ``.coding-agent-playbook.toml`` (parsed by
  :func:`coding_agent_playbook.config.parse_metrics_config`) seeds the
  :class:`~coding_agent_playbook.evaluators.types.MetricConfig`; CLI flags
  override it.

Exit codes: ``0`` pass; ``1`` when ``report.passed`` is ``False`` and
``fail_on_breach``; ``2`` on usage errors (bad path, bad baseline ref/dir,
malformed/invalid ``[metrics]`` config).

Finding levels by format: ``--format json`` includes every finding (``ok`` level
too) for a machine audience; ``--format text`` shows only ``warn``/``fail`` for a
human audience.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
import tomllib
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.config import parse_metrics_config
from coding_agent_playbook.evaluators import (
    EvalContext,
    Measurement,
    MetricConfig,
    parse_module,
)
from coding_agent_playbook.evaluators.check import MeasurementSet
from coding_agent_playbook.evaluators.execution.project import ProjectHandle
from coding_agent_playbook.evaluators.metric import execution_metrics, static_metrics
from coding_agent_playbook.evaluators.policy import metric_check
from coding_agent_playbook.evaluators.rubric import Rubric
from coding_agent_playbook.evaluators.types import ScopeDetail

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.evaluators import EvaluationReport
    from coding_agent_playbook.evaluators.check import Check
    from coding_agent_playbook.evaluators.metric import Metric


_CONFIG_FILENAME = ".coding-agent-playbook.toml"

#: Directory names never recursed into during ``*.py`` discovery.
_IGNORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

_VALID_MODES = ("regression", "absolute", "both")
_VALID_FORMATS = ("text", "json")

#: The name the Rubric carries (stable per-run; metrics has one rubric).
_RUBRIC_NAME = "metrics"


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


def _repo_rel_path(path: Path, repo_root: Path) -> str | None:
    """Repo-relative POSIX path for ``path``, or ``None`` if it is outside.

    Unlike :func:`_rel_label` this does *not* fall back to the basename, so a
    ``git:`` baseline never resolves an out-of-repo target against a coincidental
    same-named file at the repo root (it is treated as all-new instead).
    """
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #


def _measure_source(source: str, label: str, metrics: list[Metric]) -> list[Measurement]:
    """Parse ``source`` and run every available static metric over it.

    Raises :exc:`SyntaxError` when the source does not parse (the caller decides
    whether to skip the file).
    """
    module = parse_module(source, label)
    ctx = EvalContext(module=module, source=source, label=label)
    measurements: list[Measurement] = []
    for metric in metrics:
        if metric.available(ctx):
            measurements.extend(metric.measure(ctx))
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
    metrics: list[Metric],
) -> list[Measurement]:
    """Measure the baseline variant of each target file.

    ``baseline`` is ``git:<ref>`` (read via ``git show``) or a directory path
    (read the matching relative file). A file absent from the baseline yields no
    measurements, so the regression check treats it as all-new.
    """
    measurements: list[Measurement] = []
    if baseline.startswith("git:"):
        ref = baseline[len("git:") :]
        _validate_git_ref(repo_root, ref)
        for target in targets:
            rel = _repo_rel_path(target, repo_root)
            # A target outside repo_root has no git-tracked counterpart; treat it
            # as all-new rather than guessing a coincidental same-named repo file.
            if rel is None:
                continue
            source = _git_show(repo_root, ref, rel)
            if source is None:
                continue
            measurements.extend(_safe_measure(source, rel, metrics))
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
        measurements.extend(_safe_measure(source, label, metrics))
    return measurements


def _safe_measure(source: str, label: str, metrics: list[Metric]) -> list[Measurement]:
    """Measure a baseline source, swallowing parse errors (drop that file)."""
    try:
        return _measure_source(source, label, metrics)
    except SyntaxError:
        return []


# --------------------------------------------------------------------------- #
# Execution metrics (--run-tests)
# --------------------------------------------------------------------------- #

#: MODULE label the execution metrics key their suite-wide measurements on.
_SUITE_LABEL = "suite"


def _resolve_test_cmd(args: argparse.Namespace, config: MetricConfig) -> list[str] | None:
    """Effective test command: ``--test-cmd`` (shlex-split) over config ``test_cmd``.

    ``None`` means "use :meth:`ProjectHandle.create`'s isolated default". Raises
    :class:`_UsageError` for an empty/unparseable ``--test-cmd``.
    """
    raw = getattr(args, "test_cmd", None)
    if raw:
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            raise _UsageError(f"bad --test-cmd: {exc}") from exc
        if not parts:
            raise _UsageError("--test-cmd is empty")
        return parts
    return config.test_cmd


def _run_execution(
    root: Path,
    report_dir: Path,
    metrics: list[Metric],
    test_cmd: list[str] | None,
) -> list[Measurement]:
    """Build a handle, run the suite once, and collect execution measurements.

    Both execution metrics read the same :class:`ProjectHandle`, so the suite
    runs exactly once. Raises :class:`_UsageError` when the suite cannot be run.
    """
    handle = ProjectHandle.create(root, report_dir, test_cmd=test_cmd)
    ctx = EvalContext(module=None, source="", label=_SUITE_LABEL, project=handle)
    measurements: list[Measurement] = []
    try:
        for metric in metrics:
            if metric.available(ctx):
                measurements.extend(metric.measure(ctx))
    except RuntimeError as exc:
        raise _UsageError(str(exc)) from exc
    return measurements


def _execution_baseline(
    baseline: str,
    repo_root: Path,
    metrics: list[Metric],
    test_cmd: list[str] | None,
    work_dir: Path,
) -> list[Measurement]:
    """Run the execution metrics on the baseline (a git ref or a directory).

    ``git:<ref>`` materialises the ref via a temporary ``git worktree add`` under
    ``work_dir`` (cleaned up afterwards via ``git worktree remove``); ``<dir>``
    runs the suite directly in that directory. Raises :class:`_UsageError` on a
    bad ref / non-git dir / missing directory or an unrunnable suite.
    """
    if baseline.startswith("git:"):
        ref = baseline[len("git:") :]
        _validate_git_ref(repo_root, ref)
        return _execution_git_worktree(ref, repo_root, metrics, test_cmd, work_dir)

    base_dir = Path(baseline)
    if not base_dir.is_dir():
        raise _UsageError(f"baseline directory not found: {base_dir}")
    return _run_execution(base_dir, work_dir / "baseline-reports", metrics, test_cmd)


def _execution_git_worktree(
    ref: str,
    repo_root: Path,
    metrics: list[Metric],
    test_cmd: list[str] | None,
    work_dir: Path,
) -> list[Measurement]:
    """Materialise ``ref`` in a temp git worktree, run the suite, then clean up."""
    worktree = work_dir / "baseline-worktree"
    add = subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree), ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        raise _UsageError(f"could not create baseline worktree for {ref!r}: {add.stderr.strip()}")
    try:
        return _run_execution(worktree, work_dir / "baseline-reports", metrics, test_cmd)
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )


# --------------------------------------------------------------------------- #
# Rubric assembly
# --------------------------------------------------------------------------- #


def _build_rubric(metrics: list[Metric], config: MetricConfig) -> Rubric:
    """Assemble one metric-backed :class:`Check` per metric into a :class:`Rubric`.

    Each check is built through the shared
    :func:`~coding_agent_playbook.evaluators.policy.metric_check` factory (the
    eval-task compiler uses the same one), so the standalone gate honours
    ``config``'s per-metric threshold / regression / weight override when present
    and the metric's ported default otherwise — reproducing the retired
    ``grade()``'s ``resolve_policy`` over the full measured set. The metrics are
    already deterministic-ordered (``static_metrics()`` then
    ``execution_metrics()``), so the rubric's checks run in a stable order.
    """
    checks: list[Check] = []
    for metric in metrics:
        check = metric_check(metric.name, config)
        if check is not None:
            checks.append(check)
    return Rubric(checks, name=_RUBRIC_NAME)


# --------------------------------------------------------------------------- #
# Config + flag merge
# --------------------------------------------------------------------------- #


def _load_config(repo_root: Path) -> MetricConfig:
    """Parse ``[metrics]`` from ``.coding-agent-playbook.toml`` if present.

    Malformed TOML (:class:`tomllib.TOMLDecodeError`) or an invalid ``[metrics]``
    value (:class:`ValueError` from :func:`parse_metrics_config`, e.g. a bad
    ``mode``) is re-raised as :class:`_UsageError` so the caller maps it to exit
    code 2 instead of crashing with a traceback.
    """
    config_path = repo_root / _CONFIG_FILENAME
    if not config_path.is_file():
        return MetricConfig()
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
        return parse_metrics_config(data.get("metrics", {}))
    except tomllib.TOMLDecodeError as exc:
        raise _UsageError(f"malformed {_CONFIG_FILENAME}: {exc}") from exc
    except ValueError as exc:
        raise _UsageError(f"invalid [metrics] config in {_CONFIG_FILENAME}: {exc}") from exc


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
# Reporting (Metric/Check/Rubric: iterate report.checks → subresults)
# --------------------------------------------------------------------------- #


def _report_to_dict(report: EvaluationReport) -> dict[str, object]:
    """Stable JSON-serialisable view of an :class:`EvaluationReport`.

    The flat ``findings`` list carries the per-scope :class:`ScopeDetail` leaves
    the rubric's run checks produced (every level, ``ok`` too), keeping the JSON
    contract — ``{evaluator, scope_key, value, baseline, bound, score, level,
    kind}`` per finding — byte-compatible with the pre-cutover ``grade()`` output
    that machine consumers read.
    """
    return {
        "passed": report.passed,
        "warn_count": report.warn_count,
        "fail_count": report.fail_count,
        "composite": report.composite,
        "findings": [_finding_to_dict(f) for f in report.findings],
    }


def _finding_to_dict(finding: ScopeDetail) -> dict[str, object]:
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
    """Human-readable findings grouped by file then scope, plus a summary.

    Iterates the rubric's run checks and flattens their per-scope
    :class:`ScopeDetail` leaves, then groups by file (the ``scope_key`` prefix
    before ``::``) — same shape the pre-cutover ``grade()`` text output had, so a
    ``[fail] cyclomatic_complexity @ … (regression; baseline=…)`` line still reads
    identically.
    """
    lines: list[str] = ["=== Metrics ==="]
    if note:
        lines.append(f"  note: {note}")

    by_file: dict[str, list[ScopeDetail]] = {}
    for finding in _leaf_findings(report):
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


def _leaf_findings(report: EvaluationReport) -> list[ScopeDetail]:
    """The per-scope :class:`ScopeDetail` leaves of every run check.

    The rubric already flattens these onto ``report.findings``; this narrows that
    list to the concrete leaf type so the text renderer can read
    ``.scope_key``/``.level``/... without a type ignore.
    """
    return [f for f in report.findings if isinstance(f, ScopeDetail)]


def _finding_detail(finding: ScopeDetail) -> str:
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
    static = static_metrics()

    try:
        config = _load_config(repo_root)
        run_tests = bool(getattr(args, "run_tests", False)) or config.run_tests
        test_cmd = _resolve_test_cmd(args, config)
        targets = _discover_targets(paths, repo_root)
        baseline_measurements: list[Measurement] | None = (
            _baseline_measurements(baseline, targets, repo_root, static)
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
            candidate.extend(_measure_source(source, label, static))
            measured_count += 1
        except SyntaxError as exc:
            skipped.append((label, f"unparseable ({exc.msg})"))

    # The gated set: the full static metrics, plus the execution metrics when
    # --run-tests opted in. One metric-backed check per metric.
    gated: list[Metric] = list(static)
    execution = execution_metrics() if run_tests else []
    gated.extend(execution)

    # Execution metrics (opt-in): run the target's suite once and, when a
    # baseline is given, the baseline's suite too (temp git worktree / dir).
    if run_tests:
        try:
            with tempfile.TemporaryDirectory(prefix="playbook-metrics-") as tmp:
                tmp_path = Path(tmp)
                candidate.extend(
                    _run_execution(repo_root, tmp_path / "candidate-reports", execution, test_cmd)
                )
                if baseline is not None:
                    exec_baseline = _execution_baseline(
                        baseline, repo_root, execution, test_cmd, tmp_path
                    )
                    baseline_measurements = (baseline_measurements or []) + exec_baseline
        except _UsageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    effective, note = _merge_flags(config, args, baseline=baseline)

    # Build the rubric (one check per gated metric) and grade the pre-built
    # measurements. fail_fast=False: metrics is deterministic-only and wants the
    # COMPLETE report (every breach surfaced), not a gate short-circuit. The ctx
    # only needs the measurement set; availability stand-ins (a parsed empty
    # module for static checks, a lazy project handle for execution checks) flip
    # the metric-backed checks' availability on so the pre-built scores grade —
    # nothing is ever re-measured here.
    rubric = _build_rubric(gated, effective)
    ms = MeasurementSet(candidate, baseline_measurements)
    with ExitStack() as stack:
        ctx = _grading_ctx(static, execution, repo_root, candidate, baseline_measurements, stack)
        report = rubric.evaluate(ctx, ms, strict=effective.strict, fail_fast=False)

    if fmt == "json":
        print(json.dumps(_report_to_dict(report), indent=2, sort_keys=True))
    else:
        print(_format_text(report, skipped=skipped, note=note, measured_count=measured_count))

    if not report.passed and effective.fail_on_breach:
        return 1
    return 0


def _grading_ctx(
    static: list[Metric],
    execution: list[Metric],
    repo_root: Path,
    candidate: list[Measurement],
    baseline_measurements: list[Measurement] | None,
    stack: ExitStack,
) -> EvalContext:
    """An :class:`EvalContext` whose slots satisfy the metric checks' availability.

    The metric-backed checks gate availability on the same ctx slot the
    underlying metric does (``ctx.module`` for static, ``ctx.project`` for
    execution). The measurements are already computed, so the checks only grade
    the pre-built :class:`MeasurementSet`; this ctx flips their availability on
    without anything being re-measured:

    - a parsed empty ``module`` satisfies the static checks (when any static
      metric is gated);
    - a lazy candidate :class:`ProjectHandle` over ``repo_root`` satisfies the
      execution checks (when ``--run-tests`` gated execution metrics). The handle
      only shells out to ``pytest`` when :meth:`ProjectHandle.run` is called,
      which the *checks* never do (they grade the pre-built measurements), so the
      suite is never re-run; its throwaway report dir is cleaned when ``stack``
      exits.

    ``ctx.candidate_measurements`` / ``ctx.baseline_measurements`` are carried so
    the rubric (also a Metric) could self-measure if ever nested.
    """
    module = parse_module("", _RUBRIC_NAME) if static else None
    project = None
    if execution:
        report_dir = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="playbook-metrics-avail-"))
        )
        project = ProjectHandle.create(repo_root, report_dir)
    return EvalContext(
        module=module,
        source="",
        label=_RUBRIC_NAME,
        project=project,
        candidate_measurements=candidate,
        baseline_measurements=baseline_measurements,
    )
