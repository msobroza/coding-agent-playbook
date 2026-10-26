"""Text and JSON views of an eval sample result (``playbook eval --run``, SPEC §15).

The report is iterated as Metric, Check and Rubric rows: ``report.checks`` and
their per-scope ``subresults``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.grading.scope import Determinism
from coding_agent_playbook.grading.types import CheckResult, ScopeDetail

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.evals.run.harness_runner import SampleResult
    from coding_agent_playbook.grading.types import TrialResult

#: Printed under a report whose scores include an LLM judge's (SPEC §19 Q12).
_UNCALIBRATED_NOTE = (
    "  note: judged scores come from an uncalibrated LLM judge (SPEC §19 Q12); "
    "treat them as advisory"
)


def sample_result_to_dict(result: SampleResult) -> dict[str, object]:
    """Stable JSON view of a :class:`SampleResult` (sample envelope + the report).

    The report is rendered as the list of :class:`CheckResult` rows the
    :class:`~coding_agent_playbook.grading.rubric.Rubric` produced, each with
    its flattened per-scope :class:`ScopeDetail` ``subresults``. The flat
    ``findings`` list is kept too (transitional) so existing JSON consumers that
    read ``report.findings`` keep working. ``target`` records the Eval target:
    its name, harness, the requested model and the model the harness reported
    (``None`` for the harness default, or when the harness reports none).
    """
    report = result.report
    out: dict[str, object] = {
        "sample_id": result.sample_id,
        "harness": result.harness,
        "target": _target_to_dict(result),
        "passed": result.passed,
        "aggregate_score": result.aggregate_score,
        "duration_seconds": result.duration_seconds,
        "report": {
            "passed": report.passed,
            "warn_count": report.warn_count,
            "fail_count": report.fail_count,
            "composite": report.composite,
            "checks": [_check_to_dict(c) for c in report.checks],
            "findings": [_finding_to_dict(f) for f in report.findings],
        },
    }
    # Across-trial aggregate: present only when the sample authored an
    # [aggregate] block. ``trials`` is the per-trial pass/fail sequence.
    out["uncalibrated_judge"] = _any_trial_judge_scored(result)
    if result.aggregate is not None:
        out["trials"] = len(result.trials)
        out["aggregate"] = _check_to_dict(result.aggregate)
        out["trial_verdicts"] = [t.verdict for t in result.trials]
    return out


def _target_to_dict(result: SampleResult) -> dict[str, object]:
    """The Eval target a result was run with (spec #281: target, harness, both models)."""
    return {
        "name": result.target,
        "harness": result.harness,
        "model": result.requested_model,
        "reported_model": result.reported_model,
    }


def _target_line(result: SampleResult) -> str:
    """The text-report line naming the target, its harness and the models.

    Example::

        target: claude-opus (claude_code, model claude-opus-5-5, reported claude-opus-5-5)
    """
    name = result.target if result.target is not None else result.harness
    model = result.requested_model or "harness default"
    reported = f", reported {result.reported_model}" if result.reported_model else ""
    return f"  target: {name} ({result.harness}, model {model}{reported})"


def _check_to_dict(check: CheckResult) -> dict[str, object]:
    """Stable JSON view of one :class:`CheckResult` + its leaf ``subresults``."""
    return {
        "check_id": check.check_id,
        "passed": check.passed,
        "score": check.score,
        "weight": check.weight,
        "required": check.required,
        "status": check.status,
        "subresults": [
            _finding_to_dict(sub) for sub in check.subresults if isinstance(sub, ScopeDetail)
        ],
    }


def _finding_to_dict(finding: ScopeDetail) -> dict[str, object]:
    """Stable JSON view of one per-scope :class:`ScopeDetail` leaf."""
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


def format_sample_result_text(result: SampleResult) -> str:
    """Human view: per-check blocks (each with its scope leaves) + a footer."""
    report = result.report
    lines: list[str] = ["=== Eval scoring ==="]

    run_checks = [c for c in report.checks if c.status == "run"]
    if not run_checks:
        lines.append("  (no checks ran)")
    for check in run_checks:
        verdict = "PASS" if check.passed else "FAIL"
        score = "n/a" if check.score is None else f"{check.score:.3f}"
        lines.append(f"  [{verdict}] {check.check_id} (score={score})")
        for sub in check.subresults:
            if not isinstance(sub, ScopeDetail) or sub.level == "ok":
                continue
            detail = _scope_detail(sub)
            lines.append(
                f"      [{sub.level}] {sub.evaluator} @ {sub.scope_key} "
                f"= {sub.value:g} ({sub.kind}{detail})"
            )

    skipped = [c for c in report.checks if c.status == "skipped"]
    for check in skipped:
        lines.append(f"  [skip] {check.check_id}")

    composite = "n/a" if report.composite is None else f"{report.composite:.3f}"
    verdict = "PASS" if result.passed else "FAIL"
    lines.append(
        f"  summary: {verdict} — {report.fail_count} fail, {report.warn_count} warn, "
        f"composite={composite}"
    )

    # Across-trial aggregate: pass@k / pass^k over N trials, when present.
    if result.aggregate is not None:
        lines.append(_aggregate_line(result.aggregate, result.trials))

    if _any_trial_judge_scored(result):
        lines.append(_UNCALIBRATED_NOTE)
    lines.append(_target_line(result))

    footer = (
        f"  sample: {result.sample_id} via {result.harness} — {verdict} "
        f"(score={result.aggregate_score:.3f}, {result.duration_seconds:.2f}s)"
    )
    return "\n".join([*lines, footer])


def _aggregate_line(agg: CheckResult, trials: list[TrialResult]) -> str:
    """The text-report line for the ``[aggregate]`` layer's result.

    A skipped aggregate (its ``over`` axis never ran, e.g. ``over = "rubric"``
    with no judge) has no verdict of its own: the sample verdict fell back to the
    trials' verdicts, so say that rather than print a misleading ``FAIL``.
    """
    n_pass = sum(1 for t in trials if t.verdict)
    n = len(trials)
    if agg.status != "run":
        return (
            f"  aggregate: {agg.check_id} skipped (its over-axis never ran); "
            f"verdict from all {n} trials ({n_pass}/{n} passed)"
        )
    agg_verdict = "PASS" if agg.passed else "FAIL"
    score = "n/a" if agg.score is None else f"{agg.score:.3f}"
    return (
        f"  aggregate: {agg.check_id} = {score} ({agg_verdict}), {n} trials ({n_pass}/{n} passed)"
    )


def _any_trial_judge_scored(result: SampleResult) -> bool:
    """Whether a judge scored anything in *any* trial (not just the reported one)."""
    reports = [t.report for t in result.trials] or [result.report]
    return any(_judge_scored(report.checks) for report in reports)


def _judge_scored(checks: Iterable[CheckResult]) -> bool:
    """Whether any *leaf* check that ran was judged (its score came from a judge).

    Composers inherit ``JUDGED`` from any judged child even when only their
    deterministic children ran, so only leaves count.
    """
    return any(_judge_scored_leaf(check) for check in checks)


def _judge_scored_leaf(check: CheckResult) -> bool:
    if check.status != "run":
        return False
    nested = [sub for sub in check.subresults if isinstance(sub, CheckResult)]
    if nested:
        return _judge_scored(nested)
    return check.determinism is Determinism.JUDGED


def _scope_detail(sub: ScopeDetail) -> str:
    """A short suffix describing the comparison that decided a scope leaf."""
    if sub.kind == "regression" and sub.baseline is not None:
        return f"; baseline={sub.baseline:g}"
    if sub.bound is not None:
        return f"; bound={sub.bound:g}"
    return ""
