"""The comparison runner runs every task on each side's checkout and prompt set (D37, D76; F-01).

``run_comparison`` is tested with a named fake task runner and a fake checkout;
``git_worktree_checkout`` against a real throwaway git repo.
"""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.comparison_runner import (
    ComparisonSide,
    EvalRunOutput,
    git_worktree_checkout,
    run_comparison,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from coding_agent_playbook.catalog.prompt_sets import PromptSet
    from coding_agent_playbook.evals.comparison import TaskComparison


@dataclass
class FakeTaskRunner:
    """Scores a task by the ref its checkout holds; records every call."""

    score_by_ref: dict[str, float]
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def __call__(self, checkout: Path, task_id: str, prompt_set: PromptSet) -> EvalRunOutput:
        ref = (checkout / "REF").read_text(encoding="utf-8")
        self.calls.append((ref, task_id, prompt_set))
        score = self.score_by_ref[ref]
        report = {"passed": score >= 0.5, "aggregate_score": score}
        return EvalRunOutput(exit_code=0 if score >= 0.5 else 1, stdout=json.dumps(report))


@contextmanager
def fake_checkout(ref: str, dest: Path) -> Iterator[Path]:
    dest.mkdir(parents=True)
    (dest / "REF").write_text(ref, encoding="utf-8")
    yield dest


def _compare(
    tmp_path: Path, runner: FakeTaskRunner, base: ComparisonSide, head: ComparisonSide
) -> list[TaskComparison]:
    return run_comparison(
        ["task-a", "task-b"],
        base,
        head,
        samples=3,
        run_task=runner,
        checkout_ref=fake_checkout,
        work_dir=tmp_path / "work",
    )


def test_each_task_runs_the_sample_count_on_each_side(tmp_path: Path) -> None:
    runner = FakeTaskRunner({"main": 0.9, "HEAD": 0.9})
    _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    assert sorted(runner.calls) == sorted(
        [(ref, task, "v1") for ref in ("main", "HEAD") for task in ("task-a", "task-b")] * 3
    )


def test_each_side_runs_its_own_prompt_set(tmp_path: Path) -> None:
    runner = FakeTaskRunner({"HEAD": 0.9})
    _compare(tmp_path, runner, ComparisonSide("HEAD", "v1"), ComparisonSide("HEAD", "v2"))
    assert sorted({call[2] for call in runner.calls}) == ["v1", "v2"]
    assert len(runner.calls) == 12


def test_a_lower_scoring_head_is_flagged(tmp_path: Path) -> None:
    runner = FakeTaskRunner({"main": 0.9, "HEAD": 0.6})
    rows = _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    assert [(row.task_id, row.regressed) for row in rows] == [("task-a", True), ("task-b", True)]


def test_every_run_report_is_kept_per_side(tmp_path: Path) -> None:
    runner = FakeTaskRunner({"main": 0.9, "HEAD": 0.6})
    _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    reports = tmp_path / "work" / "reports"
    assert sorted(p.name for p in (reports / "head").iterdir()) == [
        f"{task}-{n}.json" for task in ("task-a", "task-b") for n in (1, 2, 3)
    ]
    kept = json.loads((reports / "base" / "task-a-1.json").read_text(encoding="utf-8"))
    assert kept["aggregate_score"] == 0.9


def test_a_side_label_names_its_ref_and_prompt_set() -> None:
    assert ComparisonSide("origin/main", "v2").label == "origin/main (v2)"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, timeout=60
    )
    return done.stdout.strip()


def _repo_with_two_commits(repo: Path) -> str:
    repo.mkdir()
    _git(repo, "init", "-q")
    for text in ("old", "new"):
        (repo / "f.txt").write_text(text, encoding="utf-8")
        _git(repo, "add", "f.txt")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", text)
    return _git(repo, "rev-parse", "HEAD~1")


def test_a_git_checkout_holds_the_ref_and_is_removed_afterwards(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    old = _repo_with_two_commits(repo)
    dest = tmp_path / "checkouts" / "base"
    with git_worktree_checkout(repo)(old, dest) as checkout:
        assert (checkout / "f.txt").read_text(encoding="utf-8") == "old"
    assert not dest.exists()
    assert (repo / "f.txt").read_text(encoding="utf-8") == "new"
    assert str(dest) not in _git(repo, "worktree", "list")
