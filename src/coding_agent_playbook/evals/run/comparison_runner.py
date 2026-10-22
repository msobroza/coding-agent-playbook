"""Run the same eval tasks on two sides, a git ref and a prompt set each (D37, D76; prU F-01).

``playbook eval --compare <base-ref>`` is opt-in and paid: every run drives a real
agent. Each side is checked out as a detached ``git worktree`` of its ref, and each
task runs there ``samples`` times through that checkout's own engine (``python -m
coding_agent_playbook.cli eval <id> --run --format json``, with the checkout's
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
from coding_agent_playbook.evals.comparison import SampleOutcome, TaskComparison, compare_task
from coding_agent_playbook.evals.run.git_env import without_repo_location

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from contextlib import AbstractContextManager
    from pathlib import Path

#: Bound on one ``git worktree`` call (it touches only the local repository).
_GIT_TIMEOUT_S: Final = 120.0
#: Bound on one paid eval run; a run past it counts as an unscorable sample.
DEFAULT_TASK_TIMEOUT_S: Final = 3600.0
#: The side names used for the checkout and report directories.
_SIDES: Final = ("base", "head")


class ComparisonError(RuntimeError):
    """A side could not be prepared (its ref does not check out)."""


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


class TaskRunner(Protocol):
    """Runs one task once in a checkout with a prompt set (``PlaybookEvalTask`` in production)."""

    def __call__(self, checkout: Path, task_id: str, prompt_set: PromptSet) -> EvalRunOutput: ...


@dataclass(frozen=True)
class PlaybookEvalTask:
    """Run a task through the checkout's own engine as a child process.

    ``flags`` are passed through (``--runner``, ``--judge``, ``--full-scoring``);
    ``--prompt-set`` is passed only for a set other than v1, so a base ref older
    than prompt sets still runs. A run past ``timeout_s`` is unscorable.

    Example::

        >>> PlaybookEvalTask(("--runner", "fake")).flags
        ('--runner', 'fake')
    """

    flags: tuple[str, ...] = ()
    timeout_s: float = DEFAULT_TASK_TIMEOUT_S

    def __call__(self, checkout: Path, task_id: str, prompt_set: PromptSet) -> EvalRunOutput:
        argv = [sys.executable, "-m", "coding_agent_playbook.cli", "eval", task_id, "--run"]
        argv += ["--format", "json", "--repo-root", str(checkout), *self.flags]
        if prompt_set != DEFAULT_PROMPT_SET:
            argv += ["--prompt-set", prompt_set]
        try:
            done = subprocess.run(
                argv,
                cwd=checkout,
                env=_checkout_env(checkout),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return EvalRunOutput(2, "", f"timed out after {self.timeout_s:g}s")
        return EvalRunOutput(done.returncode, done.stdout, done.stderr)


def _checkout_env(checkout: Path) -> dict[str, str]:
    """The child's environment: the checkout's ``src/`` first on ``PYTHONPATH``."""
    env = without_repo_location(os.environ)
    src = checkout / "src"
    if (src / "coding_agent_playbook").is_dir():
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(src), env.get("PYTHONPATH")) if p)
    return env


def git_worktree_checkout(
    repo_root: Path,
) -> Callable[[str, Path], AbstractContextManager[Path]]:
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
    task_ids: Sequence[str],
    base: ComparisonSide,
    head: ComparisonSide,
    *,
    samples: int,
    run_task: TaskRunner,
    checkout_ref: Callable[[str, Path], AbstractContextManager[Path]],
    work_dir: Path,
) -> list[TaskComparison]:
    """Run every task ``samples`` times on each side and compare them, one row per task.

    Example::

        >>> rows = run_comparison(  # doctest: +SKIP
        ...     ["refactor-extract-helper"], ComparisonSide("origin/main"), ComparisonSide("HEAD"),
        ...     samples=3, run_task=PlaybookEvalTask(), checkout_ref=git_worktree_checkout(repo),
        ...     work_dir=work,
        ... )
    """
    outcomes = [
        _run_side(side, name, task_ids, samples, run_task, checkout_ref, work_dir)
        for side, name in zip((base, head), _SIDES, strict=True)
    ]
    return [compare_task(task, outcomes[0][task], outcomes[1][task]) for task in task_ids]


def _run_side(
    side: ComparisonSide,
    name: str,
    task_ids: Sequence[str],
    samples: int,
    run_task: TaskRunner,
    checkout_ref: Callable[[str, Path], AbstractContextManager[Path]],
    work_dir: Path,
) -> dict[str, list[SampleOutcome]]:
    """Check out ``side.ref`` once, run each task ``samples`` times there, keep each report."""
    reports = work_dir / "reports" / name
    reports.mkdir(parents=True, exist_ok=True)
    outcomes: dict[str, list[SampleOutcome]] = {}
    with checkout_ref(side.ref, work_dir / "checkouts" / name) as checkout:
        for task_id in task_ids:
            runs = [run_task(checkout, task_id, side.prompt_set) for _ in range(samples)]
            for number, run in enumerate(runs, start=1):
                _keep_report(reports, f"{task_id}-{number}", run)
            outcomes[task_id] = [SampleOutcome.from_run(r.exit_code, r.stdout) for r in runs]
    return outcomes


def _keep_report(reports: Path, stem: str, run: EvalRunOutput) -> None:
    (reports / f"{stem}.json").write_text(run.stdout, encoding="utf-8")
    if run.stderr:
        (reports / f"{stem}.stderr.txt").write_text(run.stderr, encoding="utf-8")
