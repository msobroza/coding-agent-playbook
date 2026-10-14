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

This module is the thin CLI: it maps argv onto a
:class:`~coding_agent_playbook.evaluators.metrics_gate.MetricsGateRequest`,
renders the result as text or JSON, and picks the exit code. Measuring and
grading live in :mod:`coding_agent_playbook.evaluators.metrics_gate`, which the
Stop stages call in-process (prK §F.0.3 item 1).

Usage::

    playbook metrics [PATHS…] [--baseline git:REF|DIR] [--mode regression|absolute|both]
                     [--strict] [--run-tests] [--test-cmd "…"]
                     [--format text|json] [--repo-root DIR]

* **Default PATHS** — when none are given, the repo's ``src/`` directory if it
  exists, else the repo root (``--repo-root`` or cwd). Directories recurse for
  ``*.py``, skipping dotdirs and common ignores (``__pycache__``, ``.venv``,
  ``venv``, ``node_modules``, ``build``, ``dist``, ``.git``).
* **Baseline** — ``--baseline git:<ref>`` reads each candidate's prior source at
  ``<ref>`` (a file missing in the ref is all-new); ``--baseline <dir>`` reads
  the matching relative file under ``<dir>``. With no baseline (or
  ``regression``/``both`` requested without one) the gate falls back to absolute
  mode and notes it.
* **Execution (`--run-tests`)** — builds a ``ProjectHandle`` rooted at
  ``--repo-root`` (or cwd), runs the suite once, and merges the
  ``test_pass_rate``/``coverage`` measurements alongside the static ones.
  ``--test-cmd "…"`` overrides the default ``python -m pytest`` command
  (shlex-split). With a baseline, the suite is also run against the baseline: a
  ``git:<ref>`` baseline is materialised via a temporary ``git worktree`` (heavier
  than the static read) and a ``<dir>`` baseline runs in that directory.
* **Config** — a ``[metrics]`` table in ``.coding-agent-playbook.toml`` (parsed by
  :func:`coding_agent_playbook.config.parse_metrics_config`) seeds the
  :class:`~coding_agent_playbook.evaluators.types.MetricConfig`; CLI flags
  override it. ``[metrics] run_tests`` and ``test_cmd`` are resolved here, in
  the CLI, never by the gate.

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
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from coding_agent_playbook.evaluators.metrics_gate import (
    MetricsGateRequest,
    MetricsGateUsageError,
    load_metrics_config,
    run_metrics_gate,
)
from coding_agent_playbook.evaluators.types import ScopeDetail

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence

    from coding_agent_playbook.evaluators import EvaluationReport, MetricConfig
    from coding_agent_playbook.evaluators.metrics_gate import MetricsGateResult
    from coding_agent_playbook.evaluators.types import Mode


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


def _build_request(args: argparse.Namespace, repo_root: Path) -> MetricsGateRequest:
    """Load ``[metrics]`` and fold the flags in; ``--run-tests`` OR ``[metrics] run_tests``."""
    config = load_metrics_config(repo_root)
    return MetricsGateRequest(
        repo_root=repo_root,
        config=config,
        paths=tuple(getattr(args, "paths", None) or []),
        baseline=getattr(args, "baseline", None),
        mode=cast("Mode | None", getattr(args, "mode", None)),
        strict=bool(getattr(args, "strict", False)),
        run_tests=bool(getattr(args, "run_tests", False)) or config.run_tests,
        test_cmd=_resolve_test_cmd(args, config),
    )


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


def _render(result: MetricsGateResult, fmt: str) -> str:
    """The ``--format`` view of a gate result."""
    if fmt == "json":
        return json.dumps(_report_to_dict(result.report), indent=2, sort_keys=True)
    return _format_text(
        result.report,
        skipped=result.skipped,
        note=result.note,
        measured_count=result.measured_count,
    )


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

    try:
        result = run_metrics_gate(_build_request(args, repo_root))
    except MetricsGateUsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(_render(result, fmt))
    if result.breached and result.config.fail_on_breach:
        return 1
    return 0
