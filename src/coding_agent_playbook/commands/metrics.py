"""``playbook metrics`` — standalone code-quality gate (PR-M Tracks M3 + M4).

Measures the static metrics (cyclomatic complexity, maintainability index, WMC,
LCOM4, DIT, CBO≈) over a set of Python files, optionally diffing against a
baseline (a git ref or a directory), grades the result through the
:class:`~coding_agent_playbook.grading.metric.Metric` /
:class:`~coding_agent_playbook.grading.check.Check` /
:class:`~coding_agent_playbook.grading.rubric.Rubric` stack, and exits non-zero
on a breach — mirroring ``playbook check``'s convention. With ``--run-tests`` it
also runs the **execution** metrics (``test_pass_rate``, ``coverage``), which
shell out to the target's ``pytest``; execution is opt-in (side effects/cost) and
is **not** in the default pre-commit hook.

This module is the thin CLI: it maps argv onto a
:class:`~coding_agent_playbook.metrics_gate.run.MetricsGateRequest`,
renders the result as text or JSON, and picks the exit code. Measuring and
grading live in :mod:`coding_agent_playbook.metrics_gate.run`, which the
Stop stages call in-process (prK §F.0.3 item 1).

Usage::

    playbook metrics [PATHS…] [--baseline git:REF|json:PATH|DIR] [--changed]
                     [--select M,…] [--extend-select M,…] [--ignore M,…]
                     [--mode regression|absolute|both] [--strict]
                     [--run-tests|--no-run-tests] [--test-cmd "…"]
                     [--emit-measurements PATH]
                     [--format text|json] [--repo-root DIR]

* **Default PATHS** — when none are given, the repo's ``src/`` directory if it
  exists, else the repo root (``--repo-root`` or cwd). Directories recurse for
  ``*.py``, skipping dotdirs and common ignores (``__pycache__``, ``.venv``,
  ``venv``, ``node_modules``, ``build``, ``dist``, ``.git``). Files matching
  ``[metrics] exclude`` (default: the eval ``setup/`` fixtures) are never
  measured, even when named explicitly. ``--changed`` keeps only the files
  changed against the ``git:`` baseline (plus untracked ones).
* **Selection** — ``--select`` / ``--extend-select`` / ``--ignore`` take
  comma-separated metric or family names (``quality``, ``docstrings``,
  ``testing``) and each replaces its ``[metrics]`` key. Opt-in metrics are
  enabled only by name.
* **Baseline** — ``--baseline git:<ref>`` reads each candidate's prior source at
  ``<ref>`` (a file missing in the ref is all-new); ``--baseline <dir>`` reads
  the matching relative file under ``<dir>``; ``--baseline json:<path>`` reads an
  ``--emit-measurements`` snapshot, so no baseline suite runs. With no baseline
  (or ``regression``/``both`` requested without one) the gate falls back to
  absolute mode and notes it.
* **Execution (`--run-tests`)** — builds a ``ProjectHandle`` rooted at
  ``--repo-root`` (or cwd), runs the suite once, and merges the
  ``test_pass_rate``/``coverage`` measurements alongside the static ones.
  ``--test-cmd "…"`` overrides the default ``python -m pytest`` command
  (shlex-split). With a baseline, the suite is also run against the baseline: a
  ``git:<ref>`` baseline is materialised via a temporary ``git worktree`` (heavier
  than the static read) and a ``<dir>`` baseline runs in that directory.
  ``--no-run-tests`` overrides ``[metrics] run_tests = true``. ``diff_coverage``
  scores only the lines changed since a ``git:`` baseline (test files and
  ``[metrics] exclude`` left out); it needs no baseline run, so ``--select
  diff_coverage`` runs the suite once. ``[metrics] test_timeout_s`` bounds
  each run.
* **Snapshot** — ``--emit-measurements PATH`` writes the raw candidate
  measurements as JSON, tagged with ``HEAD^{tree}`` when the worktree is clean.
* **Config** — a ``[metrics]`` table in ``.coding-agent-playbook.toml`` (parsed by
  :func:`coding_agent_playbook.metrics_gate.config.parse_metrics_config`) seeds the
  :class:`~coding_agent_playbook.metrics_gate.config.MetricConfig`; CLI flags
  override it. ``[metrics] run_tests`` and ``test_cmd`` are resolved here, in
  the CLI, never by the gate.

Exit codes: ``0`` pass; ``1`` when ``report.passed`` is ``False`` and
``fail_on_breach``; ``2`` on usage errors (bad path, bad baseline ref/dir/snapshot,
a git call past ``[metrics] git_timeout_s``, malformed/invalid ``[metrics]``
config, an unknown selection name, an execution metric selected without
``--run-tests``, ``--changed`` without a ``git:`` baseline).

Finding levels by format: ``--format json`` includes every finding (``ok`` level
too) for a machine audience; ``--format text`` shows only ``warn``/``fail`` for a
human audience.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from coding_agent_playbook.grading.baseline_git import BaselineGitError, clean_head_tree
from coding_agent_playbook.grading.types import ScopeDetail
from coding_agent_playbook.metrics_gate.run import (
    MetricsGateDeps,
    MetricsGateRequest,
    MetricsGateUsageError,
    cli_tool_paths,
    load_metrics_config,
    run_metrics_gate,
)
from coding_agent_playbook.metrics_gate.targets import fix_note

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.grading.types import EvaluationReport, Mode
    from coding_agent_playbook.metrics_gate.config import MetricConfig
    from coding_agent_playbook.metrics_gate.run import MetricsGateResult

NAME: Final = "metrics"
HELP: Final = "static code-quality gate (cyclomatic complexity, MI, ...) (PR-M)"

_VALID_MODES = ("regression", "absolute", "both")
_VALID_FORMATS = ("text", "json")


# --------------------------------------------------------------------------- #
# argv → request
# --------------------------------------------------------------------------- #


def _resolve_test_cmd(args: argparse.Namespace, config: MetricConfig) -> tuple[str, ...] | None:
    """Effective test command: ``--test-cmd`` (shlex-split) over config ``test_cmd``.

    ``None`` means "use :meth:`ProjectHandle.create`'s isolated default". Raises
    :class:`MetricsGateUsageError` for an empty/unparseable ``--test-cmd``.
    """
    raw = getattr(args, "test_cmd", None)
    if raw:
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            raise MetricsGateUsageError(f"bad --test-cmd: {exc}") from exc
        if not parts:
            raise MetricsGateUsageError("--test-cmd is empty")
        return tuple(parts)
    return None if config.test_cmd is None else tuple(config.test_cmd)


def _build_request(
    args: argparse.Namespace, repo_root: Path, deps: MetricsGateDeps
) -> MetricsGateRequest:
    """Load ``[metrics]`` and fold the flags in.

    ``--run-tests`` / ``--no-run-tests`` override ``[metrics] run_tests``; each
    selection flag replaces its ``[metrics]`` key. The metrics' tools come from
    ``PATH`` (``deps.which``): ``ruff`` for the opt-in ``ruff_violations``,
    ``complexipy`` for the opt-in ``cognitive_complexity``.
    """
    config = load_metrics_config(repo_root)
    run_tests = getattr(args, "run_tests", None)
    emit = getattr(args, "emit_measurements", None)
    return MetricsGateRequest(
        repo_root=repo_root,
        config=config,
        paths=tuple(getattr(args, "paths", None) or []),
        baseline=getattr(args, "baseline", None),
        mode=cast("Mode | None", getattr(args, "mode", None)),
        strict=bool(getattr(args, "strict", False)),
        run_tests=config.run_tests if run_tests is None else bool(run_tests),
        test_cmd=_resolve_test_cmd(args, config),
        tool_paths=cli_tool_paths(deps.which),
        select=_comma_names(getattr(args, "select", None)),
        extend_select=_comma_names(getattr(args, "extend_select", None)),
        ignore=_comma_names(getattr(args, "ignore", None)),
        changed_only=bool(getattr(args, "changed", False)),
        emit_measurements=None if emit is None else Path(emit),
        snapshot_tree=None if emit is None else _snapshot_tree(repo_root, config, deps),
    )


def _comma_names(raw: str | None) -> tuple[str, ...] | None:
    """A comma-separated flag as names; ``None`` (flag absent) keeps the ``[metrics]`` key."""
    if raw is None:
        return None
    return tuple(name.strip() for name in raw.split(",") if name.strip())


def _snapshot_tree(repo_root: Path, config: MetricConfig, deps: MetricsGateDeps) -> str | None:
    """``HEAD^{tree}`` for a clean worktree, so the snapshot is a reusable baseline; else ``None``.

    Not knowing the tree only makes the snapshot anonymous, so a git failure is
    not an error here.
    """
    try:
        return clean_head_tree(deps.git_runner_factory(repo_root, config.git_timeout_s))
    except BaselineGitError:
        return None


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
    skipped: Sequence[tuple[str, str]],
    note: str | None,
    measured_count: int,
    missing_tools: Sequence[tuple[str, str]] = (),
    config: MetricConfig | None = None,
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
    for metric, tool in missing_tools:
        lines.append(f"  note: {metric} not measured: {tool} not found on PATH")

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
                detail = _finding_detail(finding, config)
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


def _finding_detail(finding: ScopeDetail, config: MetricConfig | None) -> str:
    """A short suffix: the comparison that decided the finding, then its fix note.

    The fix note (``metrics_gate.targets.fix_note``) is the raw value the scope
    passes at and how to get there; it needs the effective ``config``.
    """
    if finding.kind == "regression" and finding.baseline is not None:
        compared = f"; baseline={finding.baseline:g}"
    elif finding.bound is not None:
        compared = f"; bound={finding.bound:g}"
    else:
        compared = ""
    note = "" if config is None else fix_note(finding, config)
    return f"{compared}; {note}" if note else compared


def _render(result: MetricsGateResult, fmt: str) -> str:
    """The ``--format`` view of a gate result."""
    if fmt == "json":
        return json.dumps(_report_to_dict(result.report), indent=2, sort_keys=True)
    return _format_text(
        result.report,
        skipped=result.skipped,
        note=result.note,
        measured_count=result.measured_count,
        missing_tools=result.missing_tools,
        config=result.config,
    )


# --------------------------------------------------------------------------- #
# Flags
# --------------------------------------------------------------------------- #


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook metrics [PATHS] [--baseline B] [--changed] ...`` (SPEC §12.12).

    Example::

        >>> configure(argparse.ArgumentParser(prog="playbook metrics"))  # doctest: +SKIP
    """
    parser.add_argument(
        "paths",
        nargs="*",
        help="Python files or directories to measure (default: the repo's src/ dir)",
    )
    parser.add_argument(
        "--baseline",
        help="non-regression baseline: 'git:<ref>', 'json:<path>' (an --emit-measurements "
        "snapshot) or a directory path",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="only the .py files changed against the git: baseline, plus untracked ones",
    )
    _add_selection_flags(parser)
    _add_mode_and_output_flags(parser)


def _add_selection_flags(parser: argparse.ArgumentParser) -> None:
    """``--select``, ``--extend-select``, ``--ignore`` and ``--emit-measurements``."""
    # Ruff-shaped selection (prK §F.0.3 item 2): each flag replaces its [metrics] key.
    parser.add_argument(
        "--select",
        metavar="NAMES",
        help="comma-separated metrics or families (quality, docstrings, testing) to "
        "measure instead of the default set",
    )
    parser.add_argument(
        "--extend-select",
        dest="extend_select",
        metavar="NAMES",
        help="comma-separated metrics or families to add; opt-in metrics only by name",
    )
    parser.add_argument(
        "--ignore",
        metavar="NAMES",
        help="comma-separated metrics or families to leave out",
    )
    parser.add_argument(
        "--emit-measurements",
        dest="emit_measurements",
        metavar="PATH",
        help="write the raw candidate measurements as a JSON snapshot (for --baseline json:PATH)",
    )


def _add_mode_and_output_flags(parser: argparse.ArgumentParser) -> None:
    """``--mode``, ``--strict``, ``--run-tests``, ``--test-cmd``, ``--format``, ``--repo-root``."""
    parser.add_argument(
        "--mode",
        choices=_VALID_MODES,
        help="comparison mode (default: from [metrics] config, else 'regression')",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="promote warnings to gate failures (non-zero exit)",
    )
    # Tri-state: None defers to [metrics] run_tests; --no-run-tests keeps the
    # pre-commit twins static even when the config enables tests (§F.0.3 item 6).
    parser.add_argument(
        "--run-tests",
        dest="run_tests",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="also run the execution evaluators (test_pass_rate, coverage): "
        "shells out to the target's pytest (opt-in, has side effects); "
        "--no-run-tests overrides [metrics] run_tests = true",
    )
    parser.add_argument(
        "--test-cmd",
        dest="test_cmd",
        help="override the test command used by --run-tests (a shell-style "
        "string, split with shlex; default: python -m pytest with junit+cov XML)",
    )
    parser.add_argument(
        "--format",
        choices=_VALID_FORMATS,
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument("--repo-root", help="repo to measure against (defaults to cwd)")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def run(args: argparse.Namespace, *, deps: MetricsGateDeps | None = None) -> int:
    """Execute ``playbook metrics``; see the module docstring for the contract.

    ``deps`` replaces the gate's collaborators (git, suite runs) in tests.
    """
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    fmt = getattr(args, "format", None) or "text"
    if fmt not in _VALID_FORMATS:
        print(f"error: unknown --format {fmt!r}", file=sys.stderr)
        return 2
    mode = getattr(args, "mode", None)
    if mode is not None and mode not in _VALID_MODES:
        print(f"error: unknown --mode {mode!r}", file=sys.stderr)
        return 2

    gate_deps = deps if deps is not None else MetricsGateDeps()
    try:
        result = run_metrics_gate(_build_request(args, repo_root, gate_deps), deps=gate_deps)
    except MetricsGateUsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(_render(result, fmt))
    if result.breached and result.config.fail_on_breach:
        return 1
    return 0
