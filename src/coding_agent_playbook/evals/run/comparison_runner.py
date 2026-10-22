"""Run the same eval samples on two sides, a git ref and a prompt set each (D37, D76; prU F-01).

``playbook eval --compare <base-ref>`` is opt-in and paid: every run drives a real
agent. Each side is checked out as a detached ``git worktree`` of its ref, and each
eval sample runs there ``runs`` times through that checkout's own engine (``python
-m coding_agent_playbook.cli eval <id> --run --format json``, with the checkout's
``src/`` first on ``PYTHONPATH``), so the base side grades the base ref's prompts and
rule bodies. Every run's JSON report is kept under ``<work_dir>/reports/<side>/``;
:mod:`coding_agent_playbook.evals.comparison` turns the outcomes into the table.
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.catalog.prompt_sets import DEFAULT_PROMPT_SET, PromptSet
from coding_agent_playbook.evals.comparison import RunOutcome, SampleComparison, compare_sample
from coding_agent_playbook.evals.run.git_env import without_repo_location
from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from contextlib import AbstractContextManager
    from pathlib import Path

#: Bound on one ``git worktree`` call (it touches only the local repository).
_GIT_TIMEOUT_S: Final = 120.0
#: Bound on one paid eval run; a run past it counts as an unscorable run.
DEFAULT_RUN_TIMEOUT_S: Final = 3600.0


class ComparisonError(ExitTwoError):
    """A side could not be prepared (its ref does not check out); the CLI exits 2."""


@dataclass(frozen=True)
class ComparisonSide:
    """One side of a comparison: the git ref to check out and the prompt set to grade.

    Example::

        >>> ComparisonSide("origin/main").label
        'origin/main (v1)'
    """

    ref: str
    prompt_set: PromptSet = DEFAULT_PROMPT_SET

    @property
    def label(self) -> str:
        """``<ref> (<prompt set>)``, the side's name in the table."""
        return f"{self.ref} ({self.prompt_set})"


@dataclass(frozen=True)
class EvalRunOutput:
    """What one ``playbook eval <id> --run --format json`` run printed, and its exit code."""

    exit_code: int
    stdout: str
    stderr: str = ""


class SampleRunner(Protocol):
    """Runs one eval sample once in a checkout with a prompt set (``PlaybookEvalRun`` in prod)."""

    def __call__(self, checkout: Path, sample_id: str, prompt_set: PromptSet) -> EvalRunOutput: ...


class CheckoutFactory(Protocol):
    """Checks ``ref`` out at ``dest`` for a ``with`` block (``git_worktree_checkout`` in prod)."""

    def __call__(self, ref: str, dest: Path) -> AbstractContextManager[Path]: ...


@dataclass(frozen=True)
class ComparisonPlan:
    """What both sides run: the eval samples, the runs of each, how to run and check out.

    Example::

        >>> plan = ComparisonPlan(["refactor-extract-helper"], 3, PlaybookEvalRun(),  # doctest: +SKIP
        ...                       git_worktree_checkout(repo), work_dir)
    """

    sample_ids: Sequence[str]
    runs: int
    run_sample: SampleRunner
    checkout_ref: CheckoutFactory
    work_dir: Path


@dataclass(frozen=True)
class PlaybookEvalRun:
    """Run an eval sample through the checkout's own engine as a child process.

    ``flags`` are passed through (``--runner``, ``--judge``, ``--full-scoring``);
    ``--prompt-set`` is passed only for a set other than v1, so a base ref older
    than prompt sets still runs. A run past ``timeout_s`` is unscorable (exit 2).

    Example::

        >>> PlaybookEvalRun(("--runner", "fake")).flags
        ('--runner', 'fake')
    """

    flags: tuple[str, ...] = ()
    timeout_s: float = DEFAULT_RUN_TIMEOUT_S

    def __call__(self, checkout: Path, sample_id: str, prompt_set: PromptSet) -> EvalRunOutput:
        argv = [sys.executable, "-m", "coding_agent_playbook.cli", "eval", sample_id, "--run"]
        argv += ["--format", "json", "--repo-root", str(checkout), *self.flags]
        if prompt_set != DEFAULT_PROMPT_SET:
            argv += ["--prompt-set", prompt_set]
        try:
            done = subprocess.run(
                argv,
                cwd=checkout,
                env=checkout_env(checkout, os.environ),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return EvalRunOutput(2, "", f"timed out after {self.timeout_s:g}s")
        return EvalRunOutput(done.returncode, done.stdout, done.stderr)


def checkout_env(checkout: Path, parent: Mapping[str, str]) -> dict[str, str]:
    """The child's environment: ``parent`` with the checkout's ``src/`` first on ``PYTHONPATH``.

    A checkout without ``src/coding_agent_playbook`` keeps ``parent``'s ``PYTHONPATH``.

    Example::

        >>> checkout_env(Path("/nowhere"), {"PYTHONPATH": "/x"})["PYTHONPATH"]  # doctest: +SKIP
        '/x'
    """
    env = without_repo_location(parent)
    src = checkout / "src"
    if (src / "coding_agent_playbook").is_dir():
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(src), env.get("PYTHONPATH")) if p)
    return env


def git_worktree_checkout(repo_root: Path) -> CheckoutFactory:
    """A checkout factory adding a detached ``git worktree`` of ``repo_root`` per ref.

    The worktree is removed when the ``with`` block ends, even on an error.

    Example::

        >>> with git_worktree_checkout(repo)("origin/main", dest) as path:  # doctest: +SKIP
        ...     (path / "README.md").exists()
        True
    """

    @contextmanager
    def checkout(ref: str, dest: Path) -> Iterator[Path]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(repo_root, "worktree", "add", "--detach", str(dest), ref)
        try:
            yield dest
        finally:
            _git(repo_root, "worktree", "remove", "--force", str(dest))

    return checkout


def _git(repo_root: Path, *args: str) -> None:
    try:
        subprocess.run(
            ["git", "-C", str(repo_root), *args],
            env=without_repo_location(os.environ),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise ComparisonError(f"git {' '.join(args)} failed in {repo_root}: {detail}") from exc


def run_comparison(
    plan: ComparisonPlan, base: ComparisonSide, head: ComparisonSide
) -> list[SampleComparison]:
    """Run every eval sample ``plan.runs`` times on each side and compare, one row each.

    Example::

        >>> rows = run_comparison(plan, ComparisonSide("origin/main"), ComparisonSide("HEAD"))  # doctest: +SKIP
    """
    base_outcomes = _run_side(plan, base, "base")
    head_outcomes = _run_side(plan, head, "head")
    return [
        compare_sample(sample_id, base_outcomes[sample_id], head_outcomes[sample_id])
        for sample_id in plan.sample_ids
    ]


def _run_side(plan: ComparisonPlan, side: ComparisonSide, name: str) -> dict[str, list[RunOutcome]]:
    """Check out ``side.ref`` once, run each eval sample there, keep each run's report."""
    reports = plan.work_dir / "reports" / name
    reports.mkdir(parents=True, exist_ok=True)
    outcomes: dict[str, list[RunOutcome]] = {}
    with plan.checkout_ref(side.ref, plan.work_dir / "checkouts" / name) as checkout:
        for sample_id in plan.sample_ids:
            runs = [plan.run_sample(checkout, sample_id, side.prompt_set) for _ in range(plan.runs)]
            for number, run in enumerate(runs, start=1):
                _keep_report(reports, f"{sample_id}-{number}", run)
            outcomes[sample_id] = [RunOutcome.from_run(r.exit_code, r.stdout) for r in runs]
    return outcomes


def _keep_report(reports: Path, stem: str, run: EvalRunOutput) -> None:
    (reports / f"{stem}.json").write_text(run.stdout, encoding="utf-8")
    if run.stderr:
        (reports / f"{stem}.stderr.txt").write_text(run.stderr, encoding="utf-8")
