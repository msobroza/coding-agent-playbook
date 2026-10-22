"""The comparison runner runs every eval sample on each side's checkout and prompt set (D37, D76; F-01).

``run_comparison`` is tested with a named fake sample runner and a fake checkout;
``git_worktree_checkout`` against a real throwaway git repo.
"""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.comparison import RunOutcome
from coding_agent_playbook.evals.run.comparison_runner import (
    ComparisonPlan,
    ComparisonSide,
    EvalRunOutput,
    PlaybookEvalRun,
    checkout_env,
    git_worktree_checkout,
    run_comparison,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from coding_agent_playbook.catalog.prompt_sets import PromptSet
    from coding_agent_playbook.evals.comparison import SampleComparison


@dataclass
class FakeSampleRunner:
    """Scores an eval sample by the ref its checkout holds; records every call."""

    score_by_ref: dict[str, float]
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def __call__(self, checkout: Path, sample_id: str, prompt_set: PromptSet) -> EvalRunOutput:
        ref = (checkout / "REF").read_text(encoding="utf-8")
        self.calls.append((ref, sample_id, prompt_set))
        score = self.score_by_ref[ref]
        report = {"passed": score >= 0.5, "aggregate_score": score}
        return EvalRunOutput(exit_code=0 if score >= 0.5 else 1, stdout=json.dumps(report))


@contextmanager
def fake_checkout(ref: str, dest: Path) -> Iterator[Path]:
    dest.mkdir(parents=True)
    (dest / "REF").write_text(ref, encoding="utf-8")
    yield dest


def _compare(
    tmp_path: Path, runner: FakeSampleRunner, base: ComparisonSide, head: ComparisonSide
) -> list[SampleComparison]:
    plan = ComparisonPlan(["sample-a", "sample-b"], 3, runner, fake_checkout, tmp_path / "work")
    return run_comparison(plan, base, head)


def test_each_sample_runs_the_run_count_on_each_side(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"main": 0.9, "HEAD": 0.9})
    _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    assert sorted(runner.calls) == sorted(
        [(ref, s, "v1") for ref in ("main", "HEAD") for s in ("sample-a", "sample-b")] * 3
    )


def test_each_side_runs_its_own_prompt_set(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"HEAD": 0.9})
    _compare(tmp_path, runner, ComparisonSide("HEAD", "v1"), ComparisonSide("HEAD", "v2"))
    assert sorted({call[2] for call in runner.calls}) == ["v1", "v2"]
    assert len(runner.calls) == 12


def test_a_lower_scoring_head_is_flagged(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"main": 0.9, "HEAD": 0.6})
    rows = _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    assert [(row.sample_id, row.regressed) for row in rows] == [
        ("sample-a", True),
        ("sample-b", True),
    ]


def test_every_run_report_is_kept_per_side(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"main": 0.9, "HEAD": 0.6})
    _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    reports = tmp_path / "work" / "reports"
    assert sorted(p.name for p in (reports / "head").iterdir()) == [
        f"{s}-{n}.json" for s in ("sample-a", "sample-b") for n in (1, 2, 3)
    ]
    kept = json.loads((reports / "base" / "sample-a-1.json").read_text(encoding="utf-8"))
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


def test_rows_name_base_and_head_by_side_not_by_position(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"main": 0.9, "HEAD": 0.6})
    rows = _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    assert (rows[0].base.mean, rows[0].head.mean) == (0.9, 0.6)


def test_a_run_past_its_timeout_is_unscorable(tmp_path: Path) -> None:
    output = PlaybookEvalRun(timeout_s=0.001)(tmp_path, "refactor-extract-helper", "v1")
    assert (output.exit_code, output.stdout) == (2, "")
    assert "timed out" in output.stderr
    assert RunOutcome.from_run(output.exit_code, output.stdout).score is None


def test_a_checkout_with_an_engine_puts_its_src_first_on_pythonpath(tmp_path: Path) -> None:
    (tmp_path / "src" / "coding_agent_playbook").mkdir(parents=True)
    env = checkout_env(tmp_path, {"PYTHONPATH": "/other", "GIT_DIR": "/repo/.git"})
    assert env["PYTHONPATH"].split(os.pathsep) == [str(tmp_path / "src"), "/other"]
    assert "GIT_DIR" not in env


def test_a_checkout_without_an_engine_keeps_the_parent_pythonpath(tmp_path: Path) -> None:
    assert checkout_env(tmp_path, {"PYTHONPATH": "/other"})["PYTHONPATH"] == "/other"
    assert "PYTHONPATH" not in checkout_env(tmp_path, {})
