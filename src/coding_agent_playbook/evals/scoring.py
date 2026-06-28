"""Scoring bridge — grade an agent's output through the PR-M model (PR R1 §2).

:func:`score` turns a materialized :class:`~coding_agent_playbook.evals.runner.Baseline`
and the captured :class:`~coding_agent_playbook.evals.runner.Candidate` into one
:class:`~coding_agent_playbook.evaluators.types.EvaluationReport`, covering two
deterministic families in a single report:

* **``[metrics]``** — the static + execution evaluators selected by
  :func:`~coding_agent_playbook.evals.task.evaluators_for_task` for the task's
  ``[metrics]`` policy. Static evaluators run per candidate source file; execution
  evaluators run a :class:`~coding_agent_playbook.evaluators.execution.project.ProjectHandle`
  over the candidate tree, with the **baseline suite run on the pristine
  ``setup/`` snapshot** so non-regression compares against the untouched setup.
  The measurements are graded by :func:`~coding_agent_playbook.evaluators.grade.grade`.

* **``[rubric]``** — one
  :class:`~coding_agent_playbook.evaluators.judged.JudgedCriterion` per criterion,
  included **only when a judge is configured** (the ``judge`` argument is not
  ``None``). Each scores the candidate's captured diff/transcript into a ``0-1``
  SCORE measurement (averaged over ``samples``) and is graded through the same
  :func:`grade` call — the un-registered criterion instances are passed as
  ``extra_evaluators`` so they feed the weighted composite and gate on an
  optional min-score ``fail``. With no judge (the default) judged evaluators are
  skipped entirely: deterministic-only, the R1 behaviour preserved.

* **``[expected]``** — the :class:`~coding_agent_playbook.evals.task.ExpectedOutcome`
  file checks compiled **directly into BOOL findings** (one per
  ``files_created`` / ``files_must_contain`` / ``files_unchanged`` /
  ``files_forbidden`` entry). These are *not* routed through
  :func:`grade` — there is no registered evaluator for them in R1 — but are
  emitted as :class:`~coding_agent_playbook.evaluators.types.Finding`\\ s
  (``kind="absolute"``, ``level="ok"|"fail"``, ``score=1.0|0.0``, weight 0) so the
  single report shape stays coherent. The full registered-evaluator ``[expected]``
  compile inside ``evaluators_for_task`` is R3.

The two finding sets are merged into one report: ``warn_count``/``fail_count`` are
recomputed, ``composite`` comes from the metrics report (the BOOL findings carry
no weight), and ``passed`` is ``metrics_report.passed and`` every expected finding
passing.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators import (
    EvalContext,
    EvaluationReport,
    Finding,
    Measurement,
    MetricConfig,
    grade,
    parse_module,
)
from coding_agent_playbook.evaluators.execution.project import ProjectHandle

if TYPE_CHECKING:
    from coding_agent_playbook.evals.runner import Baseline, Candidate
    from coding_agent_playbook.evals.task import EvalTask, ExpectedOutcome
    from coding_agent_playbook.evaluators import Evaluator, JudgeLike

#: Directory names skipped when discovering candidate ``*.py`` source files.
_IGNORED_DIRS = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

#: MODULE label the execution evaluators key their suite-wide measurements on.
_SUITE_LABEL = "suite"

#: Label the judged criteria key their per-artifact measurements on (R2).
_RUBRIC_LABEL = "rubric"


def score(
    task: EvalTask,
    baseline: Baseline,
    candidate: Candidate,
    *,
    judge: JudgeLike | None = None,
    samples: int = 1,
) -> EvaluationReport:
    """Grade ``candidate`` for ``task`` into one report (R1 deterministic + R2 judged).

    With ``judge`` set, the task's ``[rubric]`` criteria are scored too (one
    SCORE measurement each, averaged over ``samples``) and folded into the same
    :func:`grade` call as the ``[metrics]`` measurements. With ``judge=None``
    (the default) only the deterministic ``[metrics]`` + ``[expected]`` layers
    run — the R1 behaviour, unchanged.
    """
    policy = task.metrics or MetricConfig()
    evaluators = _evaluators_for_task(task, policy)

    static_evals = [ev for ev in evaluators if not ev.needs_project and _is_static(ev)]
    exec_evals = [ev for ev in evaluators if ev.needs_project]

    candidate_measurements: list[Measurement] = []
    baseline_measurements: list[Measurement] = []

    if static_evals:
        candidate_measurements += _static_measurements(candidate.tree, static_evals)
        baseline_measurements += _static_measurements(baseline.setup_snapshot, static_evals)

    if exec_evals and policy.run_tests:
        candidate_measurements += _execution_measurements(candidate.tree, exec_evals)
        baseline_measurements += _execution_measurements(baseline.setup_snapshot, exec_evals)

    extra_evaluators: dict[str, Evaluator] = {}
    if judge is not None:
        judged_evals = _judged_evaluators_for_task(task)
        if judged_evals:
            judged_measurements, extra_evaluators = _judged_measurements(
                judged_evals, candidate, judge, samples
            )
            candidate_measurements += judged_measurements

    metrics_report = grade(
        candidate_measurements,
        baseline_measurements or None,
        policy,
        extra_evaluators=extra_evaluators,
    )

    expected_findings = _expected_findings(task.expected, candidate, baseline)

    return _merge(metrics_report, expected_findings)


# --------------------------------------------------------------------------- #
# [metrics] evaluator selection
# --------------------------------------------------------------------------- #


def _evaluators_for_task(task: EvalTask, policy: MetricConfig) -> list[Evaluator]:
    """The evaluators selected by the task's ``[metrics]`` config (deterministic).

    Wraps :func:`~coding_agent_playbook.evals.task.evaluators_for_task` so the
    judged ``[rubric]`` criteria it also returns are filtered out here — R1 scores
    only the deterministic families.
    """
    from coding_agent_playbook.evals.task import evaluators_for_task

    return [ev for ev in evaluators_for_task(task, policy) if _is_deterministic(ev)]


def _is_deterministic(evaluator: Evaluator) -> bool:
    from coding_agent_playbook.evaluators import Determinism

    return evaluator.determinism is Determinism.DETERMINISTIC


def _is_static(evaluator: Evaluator) -> bool:
    """Static evaluators read ``ctx.module``; they are deterministic + not project."""
    return not evaluator.needs_project


# --------------------------------------------------------------------------- #
# [rubric] -> judged measurements (R2; only when a judge is configured)
# --------------------------------------------------------------------------- #


def _judged_evaluators_for_task(task: EvalTask) -> list[Evaluator]:
    """The task's ``[rubric]`` :class:`JudgedCriterion` instances (judged family).

    Filters :func:`~coding_agent_playbook.evals.task.evaluators_for_task` down to
    the JUDGED determinism — the complement of :func:`_evaluators_for_task`'s
    deterministic selection.
    """
    from coding_agent_playbook.evals.task import evaluators_for_task
    from coding_agent_playbook.evaluators import Determinism

    return [
        ev for ev in evaluators_for_task(task, task.metrics) if ev.determinism is Determinism.JUDGED
    ]


def _judged_measurements(
    evaluators: list[Evaluator],
    candidate: Candidate,
    judge: JudgeLike,
    samples: int,
) -> tuple[list[Measurement], dict[str, Evaluator]]:
    """Score each judged criterion over the candidate diff into SCORE measurements.

    Returns the measurements plus a ``name -> evaluator`` map (the un-registered
    ``judged:<slug>`` instances) so :func:`grade` can resolve each measurement's
    policy without a registry lookup. The judged artifact is the candidate's
    captured ``git diff`` (the agent's change), keyed on a stable ``rubric`` label.
    """
    ctx = EvalContext(
        module=None,
        source="",
        label=_RUBRIC_LABEL,
        judge=judge,
        artifact=candidate.diff,
        samples=samples,
    )
    measurements: list[Measurement] = []
    by_name: dict[str, Evaluator] = {}
    for evaluator in evaluators:
        if evaluator.available(ctx):
            measurements.extend(evaluator.evaluate(ctx))
            by_name[evaluator.name] = evaluator
    return measurements, by_name


# --------------------------------------------------------------------------- #
# Static measurements (per source file)
# --------------------------------------------------------------------------- #


def _static_measurements(tree: Path, evaluators: list[Evaluator]) -> list[Measurement]:
    """Run static evaluators over every ``*.py`` file under ``tree``.

    The label is the tree-relative POSIX path so a candidate file matches its
    ``setup/`` baseline counterpart in :func:`grade` (same scope keys).
    Unparseable files are skipped.
    """
    measurements: list[Measurement] = []
    for path in _iter_py_files(tree):
        label = path.relative_to(tree).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable file is rare
            continue
        try:
            module = parse_module(source, label)
        except SyntaxError:
            continue
        ctx = EvalContext(module=module, source=source, label=label)
        for evaluator in evaluators:
            if evaluator.available(ctx):
                measurements.extend(evaluator.evaluate(ctx))
    return measurements


def _iter_py_files(root: Path) -> list[Path]:
    """Recurse ``root`` for ``*.py`` files, skipping dot/ignored dirs (sorted)."""
    out: list[Path] = []
    if not root.is_dir():
        return out
    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            if entry.name.startswith(".") or entry.name in _IGNORED_DIRS:
                continue
            out.extend(_iter_py_files(entry))
        elif entry.is_file() and entry.suffix == ".py":
            out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# Execution measurements (ProjectHandle over the tree)
# --------------------------------------------------------------------------- #


def _execution_measurements(tree: Path, evaluators: list[Evaluator]) -> list[Measurement]:
    """Run the suite once under ``tree`` and collect execution measurements.

    Both execution evaluators read the same :class:`ProjectHandle`, so the suite
    runs exactly once. The report dir is a throwaway temp dir. A suite that cannot
    be launched (no pytest in the target env) yields no measurements rather than
    failing the whole score — the deterministic ``[expected]`` layer still grades.
    """
    measurements: list[Measurement] = []
    with tempfile.TemporaryDirectory(prefix="playbook-eval-reports-") as report_dir:
        handle = ProjectHandle.create(tree, Path(report_dir))
        ctx = EvalContext(module=None, source="", label=_SUITE_LABEL, project=handle)
        try:
            for evaluator in evaluators:
                if evaluator.available(ctx):
                    measurements.extend(evaluator.evaluate(ctx))
        except RuntimeError:
            return []
    return measurements


# --------------------------------------------------------------------------- #
# [expected] -> BOOL findings (interim; R3 moves this into evaluators_for_task)
# --------------------------------------------------------------------------- #


def _expected_findings(
    expected: ExpectedOutcome | None,
    candidate: Candidate,
    baseline: Baseline,
) -> list[Finding]:
    """Compile ``[expected]`` file checks into BOOL findings over the candidate.

    One finding per entry; ``score`` is ``1.0`` when the check holds and ``0.0``
    otherwise, ``level`` is ``ok``/``fail`` and ``kind`` is ``absolute`` (weight 0
    — these gate but never feed the composite). ``files_unchanged`` compares the
    candidate file's bytes against the baseline ``setup/`` snapshot.
    """
    if expected is None:
        return []
    tree = candidate.tree
    findings: list[Finding] = []

    for rel in expected.files_created:
        ok = (tree / rel).is_file()
        findings.append(_bool_finding("files_created", rel, ok))

    for entry in expected.files_must_contain:
        rel = entry["path"]
        pattern = entry["pattern"]
        ok = _file_matches(tree / rel, pattern)
        findings.append(_bool_finding("files_must_contain", f"{rel}~/{pattern}/", ok))

    for rel in expected.files_unchanged:
        ok = _files_equal(tree / rel, baseline.setup_snapshot / rel)
        findings.append(_bool_finding("files_unchanged", rel, ok))

    for rel in expected.files_forbidden:
        ok = not (tree / rel).exists()
        findings.append(_bool_finding("files_forbidden", rel, ok))

    return findings


def _bool_finding(evaluator: str, scope_key: str, ok: bool) -> Finding:
    """One BOOL :class:`Finding`: ``ok`` -> level ``ok`` score ``1.0``, else fail."""
    return Finding(
        evaluator=evaluator,
        scope_key=scope_key,
        value=1.0 if ok else 0.0,
        baseline=None,
        bound=None,
        score=1.0 if ok else 0.0,
        level="ok" if ok else "fail",
        kind="absolute",
    )


def _file_matches(path: Path, pattern: str) -> bool:
    """True when ``path`` exists and its text matches the regex ``pattern``."""
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - unreadable file is rare
        return False
    return re.search(pattern, text) is not None


def _files_equal(a: Path, b: Path) -> bool:
    """True when both files exist and have byte-identical contents."""
    if not a.is_file() or not b.is_file():
        return False
    return a.read_bytes() == b.read_bytes()


# --------------------------------------------------------------------------- #
# Merge
# --------------------------------------------------------------------------- #


def _merge(metrics_report: EvaluationReport, expected_findings: list[Finding]) -> EvaluationReport:
    """Merge the metrics report + the ``[expected]`` BOOL findings into one report."""
    findings = list(metrics_report.findings) + expected_findings
    warn_count = sum(1 for f in findings if f.level == "warn")
    fail_count = sum(1 for f in findings if f.level == "fail")
    expected_passed = all(f.level != "fail" for f in expected_findings)
    return EvaluationReport(
        findings=findings,
        warn_count=warn_count,
        fail_count=fail_count,
        composite=metrics_report.composite,
        passed=metrics_report.passed and expected_passed,
    )
