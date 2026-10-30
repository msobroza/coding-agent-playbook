"""Load the review benchmark's results: built-in reviewers and the playbook's prompt.

Two sources, one shape. The built-in reviewers (``/code-review``, ``/review``)
were run by ``run_agents.py`` and scored by ``score_runs.py`` without fail-fast,
so every run has a gate, a judge score and one score per rubric criterion. The
playbook's ``review`` prompt was run by the v0.4.0 release eval (``playbook eval
--record``), whose record keeps per-sample totals only and, being fail-fast,
never judges a run whose gate failed.

Needs only the standard library, so the notebook and ``report.py`` load it
outside the project venv.
"""

from __future__ import annotations

import json
import statistics
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bench

RUN_DIR: Final = _bench.RESULTS_ROOT / "review-qwen3.8-27b"
SAMPLES_DIR: Final = _bench.REPO_ROOT / "catalog" / "core" / "eval_samples" / "review"
#: Gate checks about the verdict line or the ``Findings:`` count line, a format
#: only the playbook's prompt asks for. "Pass ignoring the verdict line" drops them.
VERDICT_CHECKS: Final = frozenset({"approves", "blocks", "counts_important"})
#: A rubric criterion counts as met in a run when the judge's mean score reaches this.
CRITERION_MET: Final = 0.5
#: The six original samples first, then the eight CRBugBench paraphrases.
ORIGINAL_SAMPLES: Final = (
    "spot-the-bug",
    "change-drops-part-of-request",
    "rereview-earlier-findings",
    "diff-old-bug-on-untouched-line",
    "clean-multi-file-change",
    "style-only-no-changes-needed",
)


@dataclass(frozen=True)
class Reviewer:
    """One reviewer setup; ``record`` names a playbook release record under ``playbook/``."""

    key: str
    label: str
    harness: str
    builtin: bool
    record: str | None = None


REVIEWERS: Final = (
    Reviewer(
        "claude-playbook", "Claude Code + playbook", "Claude Code", False, "claude-code-qwen.json"
    ),
    Reviewer("claude-code-review", "Claude Code /code-review", "Claude Code", True),
    Reviewer("opencode-playbook", "OpenCode + playbook", "OpenCode", False, "opencode-qwen.json"),
    Reviewer("opencode-review", "OpenCode /review", "OpenCode", True),
)


@dataclass(frozen=True)
class BuiltinRun:
    """One scored run of a built-in reviewer on one sample."""

    reviewer: str
    sample: str
    passed: bool
    rubric_passed: bool
    content_ok: bool  # every gate check but the verdict-line ones holds
    edited: bool
    judge_score: float
    seconds: float
    timed_out: bool
    criteria: tuple[tuple[str, float, float], ...]  # (criterion, weight, judge score)


@dataclass(frozen=True)
class TaskResult:
    """One reviewer on one sample, over its runs.

    ``judged`` is how many runs the judge graded: all of them for a built-in
    reviewer, only the gate-passing ones for the playbook (fail-fast). A field
    the record cannot tell for the unjudged runs is ``None``.
    """

    reviewer: str
    sample: str
    runs: int
    passes: int
    judged: int
    judge_passes: int
    fair_passes: int | None
    judge_score: float | None
    edited: int | None
    seconds: float


@dataclass(frozen=True)
class Summary:
    """One reviewer's totals over every sample (the README's results table)."""

    reviewer: Reviewer
    runs: int
    passes: int
    judged: int
    judge_passes: int
    fair_passes: int  # a lower bound when judged < runs
    judge_score: float  # mean over the judged runs
    edited: int  # over the judged runs
    median_seconds: float


def short_name(sample_id: str) -> str:
    """``review/spot-the-bug`` -> ``spot-the-bug``; ``review-spot-the-bug`` too."""
    return sample_id.split("/", 1)[-1].removeprefix("review-")


def load_builtin_runs(run_dir: Path = RUN_DIR) -> list[BuiltinRun]:
    """Every scored built-in run under ``run_dir/run-*/<reviewer>/<sample>/score.json``."""
    paths = sorted(run_dir.glob("run-*/*/*/score.json"))
    if not paths:
        raise FileNotFoundError(f"no score.json under {run_dir}/run-*; run score_runs.py first")
    return [_builtin_run(json.loads(p.read_text(encoding="utf-8"))) for p in paths]


def _builtin_run(score: dict[str, Any]) -> BuiltinRun:
    rubric = next(c for c in score["report"]["checks"] if c["check_id"] == "rubric")
    gate = score["gate_detail"]
    return BuiltinRun(
        reviewer=score["experiment"],
        sample=short_name(score["sample_id"]),
        passed=bool(score["passed"]),
        rubric_passed=bool(rubric["passed"]),
        content_ok=all(ok for name, ok in gate.items() if name not in VERDICT_CHECKS),
        edited=bool(score["changed_files"]),
        judge_score=float(score["rubric_weighted_score"]),
        seconds=float(score["agent"]["duration_seconds"]),
        timed_out=bool(score["agent"]["timed_out"]),
        criteria=tuple((c["criterion"], c["weight"], c["score"]) for c in score["judge_calls"]),
    )


def builtin_tasks(runs: list[BuiltinRun]) -> list[TaskResult]:
    """Per reviewer x sample totals of the built-in runs."""
    groups: dict[tuple[str, str], list[BuiltinRun]] = defaultdict(list)
    for run in runs:
        groups[run.reviewer, run.sample].append(run)
    return [
        TaskResult(
            reviewer=reviewer,
            sample=sample,
            runs=len(rs),
            passes=sum(r.passed for r in rs),
            judged=len(rs),
            judge_passes=sum(r.rubric_passed for r in rs),
            fair_passes=sum(r.rubric_passed and r.content_ok and not r.edited for r in rs),
            judge_score=statistics.mean(r.judge_score for r in rs),
            edited=sum(r.edited for r in rs),
            seconds=statistics.mean(r.seconds for r in rs),
        )
        for (reviewer, sample), rs in groups.items()
    ]


def playbook_tasks(reviewer: Reviewer, run_dir: Path = RUN_DIR) -> list[TaskResult]:
    """Per-sample totals of the playbook's ``review/*`` samples, from its release record."""
    if reviewer.record is None:
        raise ValueError(f"{reviewer.key} has no release record; expected a playbook reviewer")
    record = json.loads((run_dir / "playbook" / reviewer.record).read_text(encoding="utf-8"))
    return [
        _playbook_task(reviewer.key, sample_id, entry)
        for sample_id, entry in record["samples"].items()
        if sample_id.startswith("review/")
    ]


def _playbook_task(reviewer: str, sample_id: str, entry: dict[str, Any]) -> TaskResult:
    # A record's check values are means over the runs that reached the check: the
    # gate over all runs, the rubric only over the gate-passing (judged) ones.
    runs, checks = int(entry["runs"]), entry["checks"]
    judged = round(checks["gate"] * runs)
    judge_passes = round(checks.get("rubric", 0.0) * judged)
    complete = judged == runs  # every run judged, so nothing is unknown
    return TaskResult(
        reviewer=reviewer,
        sample=short_name(sample_id),
        runs=runs,
        passes=int(entry["passes"]),
        judged=judged,
        judge_passes=judge_passes,
        fair_passes=judge_passes if complete else None,
        judge_score=checks.get("threshold:quality"),
        edited=0 if complete else None,
        seconds=float(entry["duration_seconds_mean"]),
    )


def all_tasks(run_dir: Path = RUN_DIR) -> list[TaskResult]:
    """Every reviewer's per-sample totals, built-in and playbook alike."""
    tasks = builtin_tasks(load_builtin_runs(run_dir))
    for reviewer in REVIEWERS:
        if not reviewer.builtin:
            tasks.extend(playbook_tasks(reviewer, run_dir))
    return tasks


def summarize(tasks: list[TaskResult], runs: list[BuiltinRun]) -> list[Summary]:
    """One :class:`Summary` per reviewer, in :data:`REVIEWERS` order."""
    out = []
    for reviewer in REVIEWERS:
        mine = [t for t in tasks if t.reviewer == reviewer.key]
        scored = [(t.judge_score, t.judged) for t in mine if t.judge_score is not None]
        times = (
            [r.seconds for r in runs if r.reviewer == reviewer.key]
            if reviewer.builtin
            else [t.seconds for t in mine]
        )
        out.append(
            Summary(
                reviewer=reviewer,
                runs=sum(t.runs for t in mine),
                passes=sum(t.passes for t in mine),
                judged=sum(t.judged for t in mine),
                judge_passes=sum(t.judge_passes for t in mine),
                fair_passes=sum(
                    t.fair_passes if t.fair_passes is not None else t.passes for t in mine
                ),
                judge_score=sum(s * n for s, n in scored) / sum(n for _, n in scored),
                edited=sum(t.edited or 0 for t in mine),
                median_seconds=statistics.median(times),
            )
        )
    return out


@dataclass(frozen=True)
class CriterionResult:
    """How often one built-in reviewer met one rubric criterion."""

    reviewer: str
    sample: str
    criterion: str
    weight: float
    met: int
    runs: int


def criterion_results(runs: list[BuiltinRun]) -> list[CriterionResult]:
    """Per reviewer x criterion: runs whose judge score reached :data:`CRITERION_MET`."""
    groups: dict[tuple[str, str, str, float], list[float]] = defaultdict(list)
    for run in runs:
        for criterion, weight, score in run.criteria:
            groups[run.reviewer, run.sample, criterion, weight].append(score)
    return [
        CriterionResult(
            rev, sample, crit, weight, sum(s >= CRITERION_MET for s in scores), len(scores)
        )
        for (rev, sample, crit, weight), scores in groups.items()
    ]


@dataclass(frozen=True)
class MissedCriterion:
    """A rubric criterion that at least one built-in reviewer never met; ``met`` is per reviewer."""

    number: int
    sample: str
    criterion: str
    met: dict[str, int]


def never_met(criteria: list[CriterionResult]) -> list[MissedCriterion]:
    """The criteria some built-in reviewer met in none of its runs, numbered in sample order.

    The rubric map labels its points with these numbers, the README's table lists them.
    """
    met: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for c in criteria:
        met[c.sample, c.criterion][c.reviewer] = c.met
    order = sample_order({sample for sample, _ in met})
    missed = sorted(
        (key for key, by in met.items() if 0 in by.values()),
        key=lambda k: (order.index(k[0]), k[1]),
    )
    return [MissedCriterion(n, s, c, met[s, c]) for n, (s, c) in enumerate(missed, start=1)]


def sample_order(samples: set[str]) -> list[str]:
    """The originals in :data:`ORIGINAL_SAMPLES` order, then the CRBugBench ones sorted."""
    return [s for s in ORIGINAL_SAMPLES if s in samples] + sorted(samples - set(ORIGINAL_SAMPLES))


def sample_spec(sample: str) -> dict[str, Any]:
    """The parsed ``sample.toml`` of ``review/<sample>``."""
    return tomllib.loads((SAMPLES_DIR / sample / "sample.toml").read_text(encoding="utf-8"))


def expected_verdict(sample: str) -> str:
    """The verdict the sample's gate asks for: ``approve``, ``request changes`` or ``any``."""
    expr = sample_spec(sample)["gate"]["expr"]
    if "not approves" in expr:
        return "request changes"
    if "approves" in expr:
        return "approve"
    return "any"
