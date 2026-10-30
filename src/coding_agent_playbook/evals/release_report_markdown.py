"""The release report as Markdown, for the release PR body and its assets (spec D4).

Per target, in order: a headline (pass rate and mean score with their deltas,
the rerun, carried and re-judged counts, the setup line, the regressions with
any accepted reason, and the regression check's notes), the per-task table,
the samples that changed (carried and unchanged samples are counted, not
listed), the edition controls, the judge change when there is one, and a trend
table. Each of these is a *section*: :func:`render_markdown` cuts the document
at a section boundary when it is over the limit, and points at the full file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.evals.release_metrics import entries_summary
from coding_agent_playbook.evals.release_metrics_schema import (
    CONTROLS_KEY,
    JUDGE_CHANGE_KEY,
    MEASURED_IN_KEY,
    rejudged_here,
)
from coding_agent_playbook.evals.release_report_rows import old_judges

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.evals.release_regression import SampleVerdict
    from coding_agent_playbook.evals.release_report import ReleaseReport, TargetReport, TaskDelta

#: The default Markdown limit in characters (spec D4).
MARKDOWN_LIMIT: Final = 120_000
#: What a truncated report ends with.
TRUNCATION_POINTER: Final = "\n…truncated; the full report is report.md in the release assets.\n"
#: The per-task table's header, which the release PR body's test pins.
TASK_TABLE_HEADER: Final = (
    "| task | previous pass rate | pass rate | Δ pass rate | previous mean | mean | Δ mean "
    "| regressions | improvements | carried | rejudged | new |"
)
_LISTED: Final = frozenset({"improvement", "regression", "not_comparable", "new", "rejudged"})
_NONE: Final = "—"


def render_markdown(report: ReleaseReport, limit: int = MARKDOWN_LIMIT) -> str:
    """``report`` as Markdown; over ``limit`` characters, whole sections only, then a pointer.

    Example::

        >>> render_markdown(report, limit=200).endswith(TRUNCATION_POINTER)  # doctest: +SKIP
        True
    """
    sections = [_title(report)]
    for section in report.targets:
        sections += _target_sections(report, section)
    return _fit(sections, limit)


def _fit(sections: Sequence[str], limit: int) -> str:
    """``sections`` joined; when over ``limit``, the longest prefix that fits with the pointer."""
    full = "\n".join(sections)
    if len(full) <= limit:
        return full
    kept = 0
    while kept < len(sections) and _length(sections[: kept + 1]) <= limit:
        kept += 1
    return "\n".join(sections[:kept]) + TRUNCATION_POINTER


def _length(sections: Sequence[str]) -> int:
    return len("\n".join(sections)) + len(TRUNCATION_POINTER)


def _title(report: ReleaseReport) -> str:
    targets = ", ".join(f"{s.target} (vs {s.previous or 'no baseline'})" for s in report.targets)
    return f"# Release metrics: {report.version}\n\nTargets: {targets}.\n"


def _target_sections(report: ReleaseReport, section: TargetReport) -> list[str]:
    parts = [_headline(section), _task_table(report, section), _changed(section)]
    parts += [_controls(section), _judge_change(section), _trend(report, section)]
    return [part for part in parts if part]


def _headline(section: TargetReport) -> str:
    lines = [f"## {section.target}", "", _scores(section), _counts(section.data)]
    lines += [_setup(section.data), "", *_regressions(section), *_notes(section)]
    return "\n".join(lines) + "\n"


def _scores(section: TargetReport) -> str:
    rate, mean = _summary(section.data)
    if section.baseline is None:
        return (
            f"Pass rate {_num(rate)}, mean score {_num(mean)}. {section.target}: no baseline; "
            "the gate recorded no previous release for this target, so nothing is compared."
        )
    old_rate, old_mean = _summary(section.baseline)
    return (
        f"Pass rate {_num(rate)} ({_delta(rate, old_rate)} vs {section.previous}), "
        f"mean score {_num(mean)} ({_delta(mean, old_mean)})."
    )


def _summary(data: Mapping[str, Any]) -> tuple[float, float | None]:
    """The file's pooled pass rate and mean score (``evals.release_metrics.entries_summary``)."""
    summary = entries_summary(data["samples"])
    rate, mean = summary["pass_rate"], summary["mean_score"]
    assert isinstance(rate, float | int)  # entries_summary's contract
    return float(rate), float(mean) if isinstance(mean, float | int) else None


def _counts(data: Mapping[str, Any]) -> str:
    entries = list(data["samples"].values())
    rejudged = sum(1 for entry in entries if rejudged_here(entry))
    carried = sum(1 for e in entries if MEASURED_IN_KEY in e and not rejudged_here(e))
    return f"Rerun {len(entries) - carried - rejudged} / carried {carried} / rejudged {rejudged}."


def _setup(data: Mapping[str, Any]) -> str:
    target = data["target"]
    harness = f"{target['harness']} {target.get('harness_version') or '(unknown version)'}"
    digest = data.get("setup_digest") or "not recorded"
    return (
        f"Setup: {harness}, model {target['model']}, judge {target.get('judge_model') or 'none'}, "
        f"setup digest {digest}."
    )


def _regressions(section: TargetReport) -> list[str]:
    if section.check is None:
        return []
    found = [v for v in section.check.samples if v.status == "regression"]
    if not found:
        return ["No regressions."]
    return ["Regressions:", "", *(_regression_line(v) for v in found)]


def _regression_line(verdict: SampleVerdict) -> str:
    accepted = f" (accepted: {verdict.accepted})" if verdict.accepted else " (not accepted)"
    return f"- `{verdict.sample_id}`: {'; '.join(verdict.reasons)}{accepted}"


def _notes(section: TargetReport) -> list[str]:
    if section.check is None or not section.check.notes:
        return []
    return ["", "Notes:", "", *(f"- {note}" for note in section.check.notes)]


def _task_table(report: ReleaseReport, section: TargetReport) -> str:
    rows = [_task_row(t) for t in report.tasks if t.target == section.target]
    divider = "|" + "---|" * 12
    return "\n".join([f"### Tasks: {section.target}", "", TASK_TABLE_HEADER, divider, *rows]) + "\n"


def _task_row(task: TaskDelta) -> str:
    counts = task.counts
    cells = [
        task.task,
        _num(task.previous_pass_rate),
        _num(task.pass_rate),
        _delta(task.pass_rate, task.previous_pass_rate),
        _num(task.previous_mean),
        _num(task.mean),
        _delta(task.mean, task.previous_mean),
        *(str(counts[k]) for k in ("regression", "improvement", "carried", "rejudged", "new")),
    ]
    return _row(cells)


def _changed(section: TargetReport) -> str:
    if section.check is None:
        return ""
    listed = [v for v in section.check.samples if v.status in _LISTED]
    tasks = {sample_id: e["prompt_id"] for sample_id, e in section.data["samples"].items()}
    header = "| sample | task | status | previous mean | mean | Δ mean | reasons |"
    rows = [_changed_row(v, str(tasks[v.sample_id])) for v in listed]
    body = [header, "|" + "---|" * 7, *rows] if rows else ["No sample changed."]
    carried = section.check.count("carried")
    footer = ["", f"Carried samples (counted, not listed): {carried}."] if carried else []
    return "\n".join([f"### Changed samples: {section.target}", "", *body, *footer]) + "\n"


def _changed_row(verdict: SampleVerdict, task: str) -> str:
    reasons = "; ".join(verdict.reasons) or _NONE
    cells = [verdict.sample_id, task, verdict.status, _num(verdict.previous_mean)]
    return _row([*cells, _num(verdict.mean), _signed(verdict.delta), reasons])


def _controls(section: TargetReport) -> str:
    controls = section.data.get(CONTROLS_KEY) or {}
    old = (section.baseline or {}).get(CONTROLS_KEY) or {}
    header = "| control | edition | passes | runs | previous mean | mean | Δ mean |"
    rows = [_control_row(i, e, old.get(i)) for i, e in sorted(controls.items())]
    body = [header, "|" + "---|" * 7, *rows] if rows else ["No edition controls."]
    return "\n".join([f"### Controls: {section.target}", "", *body]) + "\n"


def _control_row(sample_id: str, entry: Mapping[str, Any], old: Mapping[str, Any] | None) -> str:
    same_edition = old is not None and old["graded"] == entry["graded"]
    previous = float(old["mean_score"]) if same_edition and old is not None else None
    mean = float(entry["mean_score"])
    cells = [sample_id, str(entry["graded"]), str(entry["passes"]), str(entry["runs"])]
    return _row([*cells, _num(previous), _num(mean), _delta(mean, previous)])


def _judge_change(section: TargetReport) -> str:
    change = section.data.get(JUDGE_CHANGE_KEY)
    if not isinstance(change, dict):
        return ""
    summary = (
        f"Judge changed from {old_judges(change)} to {change['to'].get('judge_model')}: "
        f"{change['runs']} runs, pass agreement {_percent(change['pass_agreement'])}, "
        f"mean |Δ score| {_num(change['mean_abs_score_diff'])}."
    )
    header = "| task | runs | pass agreement | mean abs score diff |"
    rows = [_agreement_row(task, a) for task, a in sorted(change["tasks"].items())]
    lines = [f"### Judge change: {section.target}", "", summary, "", header, "|---|---|---|---|"]
    return "\n".join([*lines, *rows]) + "\n"


def _agreement_row(task: str, agreement: Mapping[str, Any]) -> str:
    cells = [task, str(agreement["runs"]), _percent(agreement["pass_agreement"])]
    return _row([*cells, _num(agreement["mean_abs_score_diff"])])


def _trend(report: ReleaseReport, section: TargetReport) -> str:
    points = [p for p in report.trend if p.target == section.target]
    header = "| release | task | pass rate | mean | judge changed |"
    rows = [
        _row([p.release, p.task, _num(p.pass_rate), _num(p.mean), "yes" if p.judge_changed else ""])
        for p in points
    ]
    lines = [f"### Trend: {section.target}", "", header, "|---|---|---|---|---|", *rows]
    return "\n".join(lines) + "\n"


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _num(value: float | None) -> str:
    return _NONE if value is None else f"{value:.3f}"


def _signed(value: float | None) -> str:
    return _NONE if value is None else f"{value:+.3f}"


def _delta(now: float | None, before: float | None) -> str:
    return _NONE if now is None or before is None else _signed(now - before)


def _percent(value: float) -> str:
    return f"{value:.0%}"
