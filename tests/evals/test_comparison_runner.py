"""The comparison runner runs every eval sample on both prepared sides (D37, D76; F-01; #281 ticket 14).

``run_comparison`` is tested with a named fake sample runner, a fake checkout, a
fake edition builder (the fixture edition of ``tests.edition_fixtures``) and a
fake render check; ``git_worktree_checkout`` against a real throwaway git repo.
"""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.comparison import RunOutcome
from coding_agent_playbook.evals.run.comparison_runner import (
    ComparisonPlan,
    EvalRunOutput,
    PlaybookEvalRun,
    SideRenderCheck,
    checkout_env,
    run_comparison,
)
from coding_agent_playbook.evals.run.comparison_sides import (
    EDITION_DIR_FLAG,
    ComparisonError,
    ComparisonSide,
    PreparedSide,
    SideSources,
    git_worktree_checkout,
    takes_edition_head,
)
from coding_agent_playbook.evals.task_registry import load_task_sample
from coding_agent_playbook.exit_two import ExitTwoError
from coding_agent_playbook.release.edition import load_edition
from coding_agent_playbook.release.edition_digests import edition_dir
from tests._process_tree import (
    TIMEOUT_S,
    is_alive,
    reaped_grandchild,
    recorded_pid,
    spawning_program,
)
from tests.edition_fixtures import (
    ENGINE,
    SAMPLE_ID,
    TAG,
    write_digests,
    write_edition_files,
    write_fixture_catalog,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager
    from pathlib import Path

    from coding_agent_playbook.evals.comparison import SampleComparison

_SAMPLES = ("sample-a", "sample-b")
_EDITION_HEAD = ("--edition", "head")


def _side_key(checkout: Path, flags: tuple[str, ...]) -> str:
    """``edition`` or ``head`` for a side in place, else the ref its checkout holds."""
    if EDITION_DIR_FLAG in flags:
        return "edition"
    if (checkout / "REF").is_file():
        return (checkout / "REF").read_text(encoding="utf-8")
    return "head"


@dataclass
class FakeSampleRunner:
    """Scores an eval sample by its side; records every call."""

    score_by_side: dict[str, float]
    calls: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)

    def __call__(
        self, checkout: Path, sample_id: str, side_flags: tuple[str, ...]
    ) -> EvalRunOutput:
        key = _side_key(checkout, side_flags)
        self.calls.append((key, sample_id, side_flags))
        score = self.score_by_side.get(key)
        if score is None:
            return EvalRunOutput(exit_code=2, stdout="", stderr="could not be scored")
        report = {"passed": score >= 0.5, "aggregate_score": score}
        return EvalRunOutput(exit_code=0 if score >= 0.5 else 1, stdout=json.dumps(report))


@dataclass
class FakeRenderCheck:
    """Fails the ``(side key, sample)`` pairs it is given; records every check."""

    failing: set[tuple[str, str]] = field(default_factory=set)
    checked: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, side: PreparedSide, sample_id: str) -> str | None:
        key = _side_key(side.checkout, side.flags)
        self.checked.append((key, sample_id))
        return "the prompt does not render" if (key, sample_id) in self.failing else None


@contextmanager
def fake_checkout(ref: str, dest: Path) -> Iterator[Path]:
    dest.mkdir(parents=True)
    (dest / "REF").write_text(ref, encoding="utf-8")
    yield dest


def fake_edition_builder(tag: str, dest: Path) -> Path:
    """Build the fixture edition ``tag`` under ``dest`` (no git, no real tag)."""
    root = write_edition_files(dest, tag)
    write_digests(root, tag)
    return root


def _plan(
    tmp_path: Path, runner: FakeSampleRunner, check: FakeRenderCheck | None = None
) -> ComparisonPlan:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    sources = SideSources(repo, fake_checkout, fake_edition_builder)
    return ComparisonPlan(
        _SAMPLES, 3, runner, sources, tmp_path / "work", check or FakeRenderCheck()
    )


def _compare(
    tmp_path: Path,
    runner: FakeSampleRunner,
    base: ComparisonSide,
    head: ComparisonSide,
    check: FakeRenderCheck | None = None,
) -> list[SampleComparison]:
    return run_comparison(_plan(tmp_path, runner, check), base, head)


def test_each_sample_runs_the_run_count_on_each_side(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"main": 0.9, "HEAD": 0.9})
    _compare(tmp_path, runner, ComparisonSide("main"), ComparisonSide("HEAD"))
    assert sorted(runner.calls) == sorted(
        [(ref, s, _EDITION_HEAD) for ref in ("main", "HEAD") for s in _SAMPLES] * 3
    )


def test_a_git_ref_side_never_passes_a_prompt_set(tmp_path: Path) -> None:
    """Regression (#300): a ref side once passed ``--prompt-set``, which the engine now refuses."""
    runner = FakeSampleRunner({"HEAD": 0.9})
    _compare(tmp_path, runner, ComparisonSide("HEAD"), ComparisonSide("HEAD"))
    assert {call[2] for call in runner.calls} == {_EDITION_HEAD}
    assert len(runner.calls) == 12


@contextmanager
def pinned_checkout(ref: str, dest: Path, *, engine_takes_edition_head: bool) -> Iterator[Path]:
    """A ref holding the pinned fixture sample and an engine with or without ``--edition head``."""
    with fake_checkout(ref, dest) as checkout:
        write_fixture_catalog(checkout, edition=TAG)
        evals = checkout / "src" / "coding_agent_playbook" / "evals"
        evals.mkdir(parents=True)
        if engine_takes_edition_head:
            (evals / "graded_source.py").write_text("", encoding="utf-8")
        yield checkout


def _pinned_ref_plan(
    tmp_path: Path, runner: FakeSampleRunner, *, takes_flag: bool
) -> ComparisonPlan:
    def checkout(ref: str, dest: Path) -> AbstractContextManager[Path]:
        return pinned_checkout(ref, dest, engine_takes_edition_head=takes_flag)

    plan = _plan(tmp_path, runner)
    return replace(
        plan, sample_ids=(SAMPLE_ID,), sources=replace(plan.sources, checkout_ref=checkout)
    )


def test_a_pinned_sample_on_a_git_ref_grades_the_refs_text(tmp_path: Path) -> None:
    # #320 review: without --edition head the ref's engine graded the frozen edition.
    runner = FakeSampleRunner({"origin/main": 0.9, "head": 0.9})
    plan = _pinned_ref_plan(tmp_path, runner, takes_flag=True)
    run_comparison(plan, ComparisonSide("origin/main"), ComparisonSide("head"))
    assert {call[2] for call in runner.calls if call[0] == "origin/main"} == {_EDITION_HEAD}


def test_a_ref_whose_engine_predates_editions_runs_without_edition_head(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"v0": 0.9, "head": 0.9})
    plan = _pinned_ref_plan(tmp_path, runner, takes_flag=False)
    run_comparison(plan, ComparisonSide("v0"), ComparisonSide("head"))
    assert {call[2] for call in runner.calls if call[0] == "v0"} == {()}


def test_an_engine_takes_edition_head_when_it_ships_graded_source(tmp_path: Path) -> None:
    assert takes_edition_head(tmp_path)  # no engine in the checkout: this engine grades it
    for takes_flag in (True, False):
        with pinned_checkout(
            "r", tmp_path / str(takes_flag), engine_takes_edition_head=takes_flag
        ) as c:
            assert takes_edition_head(c) is takes_flag


def test_an_edition_side_is_built_in_the_work_dir_and_graded_in_place(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"edition": 0.9, "head": 0.9})
    _compare(tmp_path, runner, ComparisonSide("edition:v9.9.9"), ComparisonSide("head"))
    root = edition_dir(tmp_path / "work" / "edition-base", TAG)
    assert load_edition(root).tag == TAG
    assert {call[2] for call in runner.calls if call[0] == "edition"} == {
        (EDITION_DIR_FLAG, str(root))
    }
    assert {call[2] for call in runner.calls if call[0] == "head"} == {("--edition", "head")}
    assert not (tmp_path / "repo" / "catalog").exists()  # nothing written into the repository


def test_every_sample_renders_on_both_sides_before_the_first_run(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"edition": 0.9, "head": 0.9})
    check = FakeRenderCheck(failing={("edition", "sample-b")})
    with pytest.raises(ComparisonError) as raised:
        _compare(tmp_path, runner, ComparisonSide("edition:v9.9.9"), ComparisonSide("head"), check)
    assert runner.calls == []  # no paid run
    assert sorted(check.checked) == sorted((k, s) for k in ("edition", "head") for s in _SAMPLES)
    assert "sample-b on edition v9.9.9: the prompt does not render" in str(raised.value)
    assert isinstance(raised.value, ExitTwoError)  # the CLI exits 2


def test_a_side_with_no_scorable_run_is_unscorable_not_ok(tmp_path: Path) -> None:
    runner = FakeSampleRunner({"head": 0.9})
    rows = _compare(tmp_path, runner, ComparisonSide("edition:v9.9.9"), ComparisonSide("head"))
    assert [(row.unscorable_sides, row.regressed) for row in rows] == [(("base",), False)] * 2


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
        f"{s}-{n}.json" for s in _SAMPLES for n in (1, 2, 3)
    ]
    kept = json.loads((reports / "base" / "sample-a-1.json").read_text(encoding="utf-8"))
    assert kept["aggregate_score"] == 0.9


def test_a_side_label_names_its_ref_or_its_edition() -> None:
    assert ComparisonSide("origin/main").label == "origin/main"
    assert ComparisonSide("head").label == "head"
    assert ComparisonSide.parse("edition:v0.1.0").label == "edition v0.1.0"


def test_a_side_parses_as_a_ref_head_or_an_edition() -> None:
    assert [ComparisonSide.parse(t).kind for t in ("HEAD", "head", "edition:v1.2.3")] == [
        "ref",
        "head",
        "edition",
    ]


def test_an_edition_side_needs_a_release_tag() -> None:
    with pytest.raises(ComparisonError, match="edition:<release tag>"):
        ComparisonSide.parse("edition:main")


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
    output = PlaybookEvalRun(timeout_s=0.001)(tmp_path, "refactor/extract-helper", ())
    assert (output.exit_code, output.stdout) == (2, "")
    assert "timed out" in output.stderr
    assert RunOutcome.from_run(output.exit_code, output.stdout).score is None


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_timed_out_run_takes_its_child_processes_with_it(tmp_path: Path) -> None:
    """Regression: the timeout killed the side's engine only; its agent CLI kept running.

    The checkout's ``src/`` comes first on the child's ``PYTHONPATH``, so its
    ``coding_agent_playbook.cli`` is the fake that starts a grandchild.
    """
    engine = tmp_path / "src" / "coding_agent_playbook"
    engine.mkdir(parents=True)
    (engine / "__init__.py").write_text("", encoding="utf-8")
    with reaped_grandchild(tmp_path / "grandchild.pid") as pid_file:
        (engine / "cli.py").write_text(spawning_program(pid_file), encoding="utf-8")
        output = PlaybookEvalRun(timeout_s=TIMEOUT_S)(tmp_path, "refactor/extract-helper", ())
        assert output.exit_code == 2
        assert not is_alive(recorded_pid(pid_file))


def test_a_checkout_with_an_engine_puts_its_src_first_on_pythonpath(tmp_path: Path) -> None:
    (tmp_path / "src" / "coding_agent_playbook").mkdir(parents=True)
    env = checkout_env(tmp_path, {"PYTHONPATH": "/other", "GIT_DIR": "/repo/.git"})
    assert env["PYTHONPATH"].split(os.pathsep) == [str(tmp_path / "src"), "/other"]
    assert "GIT_DIR" not in env


def test_a_checkout_without_an_engine_keeps_the_parent_pythonpath(tmp_path: Path) -> None:
    assert checkout_env(tmp_path, {"PYTHONPATH": "/other"})["PYTHONPATH"] == "/other"
    assert "PYTHONPATH" not in checkout_env(tmp_path, {})


# --------------------------------------------------------------------------- #
# SideRenderCheck: in place in this process, a git ref through its own engine
# --------------------------------------------------------------------------- #


@dataclass
class FakeChildRun:
    """A ``--runner fake`` child that exits with ``exit_code``; records its calls."""

    exit_code: int
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def __call__(
        self, checkout: Path, sample_id: str, side_flags: tuple[str, ...]
    ) -> EvalRunOutput:
        self.calls.append((sample_id, side_flags))
        return EvalRunOutput(self.exit_code, "", "error: no eval sample 'review/pinned'")


def _fixture_side(tmp_path: Path, side: ComparisonSide) -> tuple[PreparedSide, SideRenderCheck]:
    catalog = write_fixture_catalog(tmp_path)
    sample = load_task_sample(catalog / "core/eval_samples/review/pinned", source_package=ENGINE)
    edition = None
    if side.kind == "edition":
        edition = load_edition(fake_edition_builder(side.tag, tmp_path / "built"))
    prepared = PreparedSide("base", side, tmp_path, (), edition)
    return prepared, SideRenderCheck({sample.id: sample}, FakeChildRun(0))


def test_a_sample_renders_on_head_and_on_its_edition_in_place(tmp_path: Path) -> None:
    head, check = _fixture_side(tmp_path / "h", ComparisonSide("head"))
    edition, edition_check = _fixture_side(tmp_path / "e", ComparisonSide.parse("edition:v9.9.9"))
    assert check(head, "review/pinned") is None
    assert edition_check(edition, "review/pinned") is None


def test_a_sample_whose_prompt_the_edition_lacks_does_not_render(tmp_path: Path) -> None:
    side = ComparisonSide.parse("edition:v9.9.9")
    prepared, check = _fixture_side(tmp_path, side)
    assert prepared.edition is not None
    empty = replace(prepared, edition=replace(prepared.edition, prompts={}))
    why = check(empty, "review/pinned")
    assert why is not None
    assert "no prompt 'review'" in why


def test_a_git_ref_side_renders_through_a_fake_run_of_its_own_engine(tmp_path: Path) -> None:
    child = FakeChildRun(2)
    check = SideRenderCheck({}, child)
    side = PreparedSide("base", ComparisonSide("origin/main"), tmp_path, ("--flag", "x"))
    assert check(side, "review/pinned") == "error: no eval sample 'review/pinned'"
    assert child.calls == [("review/pinned", ("--flag", "x"))]
    assert SideRenderCheck({}, FakeChildRun(1))(side, "review/pinned") is None  # a verdict renders
