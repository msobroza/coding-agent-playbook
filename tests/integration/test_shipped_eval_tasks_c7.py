"""Integration test: the shipped eval tasks under the C7 schema.

Loads every ``catalog/core/eval_tasks/<id>/task.toml`` the engine ships, asserts the
whole set validates clean (compile-based rules), and runs each task end-to-end
through :func:`~coding_agent_playbook.evals.scoring.score` — once deterministic-only
(no judge ⇒ the judged rubric layer skips, so the verdict reduces to the gate) and
once with a :class:`~coding_agent_playbook.evals.judge.StubJudge` (the rubric layer
contributes and a high stub score keeps it passing).

This is the destructive-cutover guard: if a migrated ``task.toml`` regresses (an
unknown check, a malformed binding, a bad expr, a weight-sum drift), the validate
step fails here.

Since C11 the shipped fixtures carry a ``setup/pyproject.toml`` (so the runner
``uv sync``'s their deps); the integration suite must stay hermetic, so the
fixtures that exercise :func:`~coding_agent_playbook.evals.runner.materialize`
monkeypatch ``subprocess.run`` to treat ``uv`` invocations as no-ops (returning
a success ``CompletedProcess``) — git calls pass through unchanged.

The captured transcript is
:data:`~tests.integration.ccv_answers.ALL_CLASSES_ANSWER` rather than a
placeholder: the ``find-injected-vuln-*`` fixtures gate deterministically on the
agent's *answer* (an ``answer_matches`` CWE-class handle), so a placeholder would
lose their gate and quietly reduce these runs to asserting a failure. The
per-fixture behaviour of that gate is covered in
``test_crosscommitvuln_fixtures.py``.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.evals.fake_runner import write_files
from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evals.loader import (
    discover_eval_task_dirs,
    load_eval_task_from_dir,
)
from coding_agent_playbook.evals.runner import capture, materialize
from coding_agent_playbook.evals.scoring import score
from coding_agent_playbook.evals.task import Verdict
from coding_agent_playbook.evals.validator import validate_tasks
from tests._catalog import CORE_ROOT
from tests.integration.ccv_answers import ALL_CLASSES_ANSWER

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.task import EvalTask

pytestmark = pytest.mark.catalog


@pytest.fixture
def stub_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic ``uv sync`` stub: never actually shells out, treats every call as OK.

    C11 wires ``materialize`` to ``uv sync`` the scratch tree when it contains a
    ``pyproject.toml`` (the shipped fixtures do). The integration suite must
    stay air-gapped, so this fixture monkeypatches ``subprocess.run`` to
    short-circuit ``uv`` invocations to a success result and pretends ``uv`` is
    on PATH; git calls pass through unchanged.
    """
    real_run = subprocess.run

    def _stub_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr("coding_agent_playbook.evals.runner.subprocess.run", _stub_run)
    monkeypatch.setattr(
        "coding_agent_playbook.evals.runner.shutil.which", lambda _binary: "/fake/uv"
    )


_TASKS_ROOT = CORE_ROOT / "eval_tasks"
_PROMPTS_ROOT = CORE_ROOT / "prompts"


def _shipped_tasks() -> list[EvalTask]:
    return [
        load_eval_task_from_dir(d, source_package="coding_agent_playbook")
        for d in discover_eval_task_dirs(_TASKS_ROOT)
    ]


def _shipped_prompts() -> list[Prompt]:
    prompts: list[Prompt] = []
    for entry in sorted(_PROMPTS_ROOT.iterdir()):
        if entry.is_file() and (entry.name.endswith(".md") or entry.name.endswith(".md.j2")):
            prompts.append(Prompt.from_markdown(entry, source_package="coding_agent_playbook"))
    return prompts


def test_ships_twenty_three_tasks() -> None:
    tasks = _shipped_tasks()
    # 10 original fixtures + 10 find-injected-vuln-* crosscommitvuln fixtures (C1-C3)
    # + 3 for the review-architecture / make-testable / characterize prompts.
    assert len(tasks) == 23


def test_every_shipped_task_compiles_to_gate_and_rubric_layers() -> None:
    for task in _shipped_tasks():
        compiled = task.compiled()
        # Every shipped task migrated to a gate + rubric pair, verdict gate and rubric.
        assert compiled.layers == frozenset({"gate", "rubric"})
        assert [c.id for c in compiled.per_trial.checks] == ["gate", "rubric"]
        assert task.verdict == Verdict(mode="boolean", trial="gate and rubric")


def test_shipped_tasks_validate_clean() -> None:
    tasks = _shipped_tasks()
    prompts = _shipped_prompts()
    errors = validate_tasks(tasks, prompts)
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)


@pytest.mark.parametrize("task", _shipped_tasks(), ids=lambda t: t.id)
def test_shipped_task_runs_deterministic_only(
    task: EvalTask, tmp_path: Path, stub_uv_sync: None
) -> None:
    """No judge ⇒ the rubric layer's judged content skips; the verdict = gate."""
    scratch = tmp_path / "scratch"
    baseline = materialize(task, scratch)
    candidate = capture(baseline.repo_root, baseline, ALL_CLASSES_ANSWER)

    report = score(task, baseline, candidate)  # no judge
    # No judged scope leaves were produced (deterministic-only).
    assert not any(d.evaluator.startswith("judge:") for d in report.findings)
    # The verdict equals the gate layer's pass/fail (rubric skipped-neutral).
    gate = next(c for c in report.checks if c.check_id == "gate")
    assert report.passed == gate.passed


@pytest.mark.parametrize("task", _shipped_tasks(), ids=lambda t: t.id)
def test_shipped_task_runs_with_a_judge(task: EvalTask, tmp_path: Path, stub_uv_sync: None) -> None:
    """With a high StubJudge the rubric layer contributes and runs (not skipped)."""
    scratch = tmp_path / "scratch"
    baseline = materialize(task, scratch)
    candidate = capture(baseline.repo_root, baseline, ALL_CLASSES_ANSWER)

    # A high default keeps every judged criterion above its 0.5 floor.
    report = score(task, baseline, candidate, judge=StubJudge(default=0.9))
    rubric = next(c for c in report.checks if c.check_id == "rubric")
    assert rubric.status == "run"
    assert rubric.passed is True  # composite 0.9 >= 0.5 floor


def test_judge_verdict_can_diverge_from_gate(tmp_path: Path, stub_uv_sync: None) -> None:
    """A low judge fails the rubric layer, so a passing-gate task's verdict flips.

    Picks a task whose deterministic gate the no-op agent satisfies (a
    file-unchanged review task), then shows a low judge sinks the verdict via the
    rubric layer — proving the judged layer actually folds into the verdict.
    """
    task_dir = _TASKS_ROOT / "review-spot-the-bug"
    task = load_eval_task_from_dir(task_dir, source_package="coding_agent_playbook")

    scratch = tmp_path / "scratch"
    baseline = materialize(task, scratch)
    # No-op agent: the reviewed file stays unchanged => the gate passes.
    write_files({})(baseline.repo_root)
    candidate = capture(baseline.repo_root, baseline, ALL_CLASSES_ANSWER)

    high = score(task, baseline, candidate, judge=StubJudge(default=0.9))
    low = score(task, baseline, candidate, judge=StubJudge(default=0.1))

    gate_high = next(c for c in high.checks if c.check_id == "gate")
    assert gate_high.passed is True
    assert high.passed is True  # gate ok + rubric high => verdict passes
    assert low.passed is False  # gate ok + rubric low => verdict fails
