"""``playbook eval`` — Tier 0 enumeration + the R1 live runner (SPEC §12.8, §15).

``playbook eval`` is both a read-only enumeration of the prompt-to-task graph and
— with ``--run`` (PR R1d) — the entry point that *executes* one task end-to-end
through a :class:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner` and grades it
via the unified PR-M :class:`EvaluationReport`.

Sub-modes:

- ``playbook eval --list`` (also the default when no arg is given): tree-shape
  coverage report across every prompt, with per-task summary lines.
- ``playbook eval --show <id>``: detailed dump for one task — sections from
  SPEC §12.8 (Task / Source / Prompt under test / Description / Setup /
  Invocation / Expected / Rubric).
- ``playbook eval <id>`` (no ``--run``): prints how to run the task. Exits 0 if
  the task is known, exits 1 if it isn't (so typos still surface).
- ``playbook eval <id> --run [--runner NAME] [--judge NAME] [--samples N]
  [--format text|json]``: load the task, select the runner ``NAME`` from the
  ``coding_agent_playbook.runners`` entry-point group (default ``claude_code``),
  run it in a throwaway scratch dir, and render ``result.report`` (reusing
  ``commands/metrics.py``'s text/json renderer). Exits ``0`` on a passing report,
  ``1`` on a failing one, ``2`` on usage errors (unknown task,
  unknown/unavailable runner, unknown/unavailable judge, bad ``--format``) and
  when the task cannot be scored at all (its prompt fails to render, or the judge
  gives no score) — that is neither a pass nor a fail.

  ``--judge`` (R2) selects a Tier-2 judge from the
  ``coding_agent_playbook.judges`` group (``llm`` ships, opt-in/CLI-gated) so the
  task's ``[rubric]`` criteria are scored too; omitted ⇒ deterministic-only (no
  judge). ``--samples N`` (default 1) is the per-criterion sample count the judge
  averages.

  Unlike ``playbook metrics``, there is **no ``--run-tests`` flag**: whether the
  execution evaluators (``coverage``/``test_pass_rate``) run is declared by the
  task's own ``[metrics]`` block (``run_tests``), so the eval task — not a CLI
  flag — carries that intent.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.commands._eval_enumerate import (
    _DEFAULT_RUNNER,
    _print_list,
    _print_run_hint,
    _print_show,
)
from coding_agent_playbook.evals import registry
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.prompting import PromptResolutionError
from coding_agent_playbook.evals.report_format import format_task_result_text, task_result_to_dict
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner
    from coding_agent_playbook.evals.task import EvalTask


_VALID_FORMATS = ("text", "json")


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())

    # ``--run`` is the only path that *executes* a task; it has its own loading
    # (one task by id) so it never pays for the full list+resolve unless the task
    # is missing (then it falls through to the SyncContext for a helpful error).
    if getattr(args, "run", False):
        return _run_task_cli(args, repo_root)

    ctx = SyncContext.from_repo(repo_root)
    tasks = ctx.artifact_source.list_eval_tasks()

    if getattr(args, "list", False):
        return _print_list(ctx.prompts_resolved, tasks)
    show_id = getattr(args, "show", None)
    if show_id:
        return _print_show(show_id, tasks, ctx.prompts_resolved)
    bare_id = getattr(args, "id", None)
    if bare_id:
        return _print_run_hint(bare_id, tasks, ctx.prompts_resolved)
    # No flag — default to --list (matches the "helpful empty invocation" rule).
    return _print_list(ctx.prompts_resolved, tasks)


# --------------------------------------------------------------------------- #
# --run — execute one task through a HarnessRunner and grade it (PR R1d)
# --------------------------------------------------------------------------- #


def _run_task_cli(args: argparse.Namespace, repo_root: Path) -> int:
    """Load + run one task, render its report, map ``passed`` to the exit code.

    Exit codes: ``0`` pass, ``1`` failing report, ``2`` usage errors (no task id,
    unknown task, unknown/unavailable runner, bad ``--format``) or an unscorable
    task (prompt render failure, judge error).
    """
    fmt = getattr(args, "format", None) or "text"
    if fmt not in _VALID_FORMATS:
        print(f"error: unknown --format {fmt!r}", file=sys.stderr)
        return 2

    task_id = getattr(args, "id", None)
    if not task_id:
        print("error: `playbook eval --run` requires a task id", file=sys.stderr)
        return 2

    task = _load_task(task_id, repo_root)
    if task is None:
        print(f"error: no eval task with id {task_id!r}", file=sys.stderr)
        return 2

    runner_name = getattr(args, "runner", None) or _DEFAULT_RUNNER
    runner_cls = registry.load_runner_class(runner_name)
    if runner_cls is None:
        available = ", ".join(registry.available_runner_names()) or "(none registered)"
        print(
            f"error: unknown --runner {runner_name!r}; registered runners: {available}",
            file=sys.stderr,
        )
        return 2
    if not _runner_available(runner_cls):
        print(
            f"error: runner {runner_name!r} is unavailable in this environment "
            "(its CLI/SDK is not installed). Try `--runner fake` for a hermetic "
            "no-op run, or install the agent CLI.",
            file=sys.stderr,
        )
        return 2

    # --judge selects a Tier-2 judge from the judges entry-point group. Omitted =>
    # deterministic-only (no judge); judged [rubric] criteria are skipped.
    judge_name = getattr(args, "judge", None)
    judge: Judge | None = None
    if judge_name is not None:
        judge_cls = registry.load_judge_class(judge_name)
        if judge_cls is None:
            available = ", ".join(registry.available_judge_names()) or "(none registered)"
            print(
                f"error: unknown --judge {judge_name!r}; registered judges: {available}",
                file=sys.stderr,
            )
            return 2
        if not judge_cls.available():
            print(
                f"error: judge {judge_name!r} is unavailable in this environment "
                "(its CLI/SDK is not installed). Omit `--judge` for a "
                "deterministic-only run, or install the judge's CLI.",
                file=sys.stderr,
            )
            return 2
        judge = judge_cls()

    samples = getattr(args, "samples", None) or 1
    # Fail-fast is ON by default (a lost deterministic gate skips the costlier
    # judge tier); --full-scoring grades every check unconditionally.
    fail_fast = not bool(getattr(args, "full_scoring", False))

    runner = runner_cls()
    try:
        with tempfile.TemporaryDirectory(prefix="playbook-eval-") as tmp:
            result = runner.run_task(
                task,
                Path(tmp) / "scratch",
                judge=judge,
                samples=samples,
                fail_fast=fail_fast,
            )
    except (PromptResolutionError, JudgeError) as exc:
        # Neither a pass nor a fail: no verdict exists, so never exit 0/1 here.
        print(f"error: task {task_id!r} could not be scored: {exc}", file=sys.stderr)
        return 2

    if fmt == "json":
        print(json.dumps(task_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(format_task_result_text(result))

    # The task verdict is ``result.passed`` — the single trial's verdict for a
    # non-aggregate task (== report.passed), or the [aggregate] layer's pass/fail
    # when the task aggregates across trials (every trial's verdict if that layer
    # was skipped). ``report.passed`` alone would be only the *first* trial's
    # verdict, so map the exit code off ``result.passed``.
    return 0 if result.passed else 1


def _load_task(task_id: str, repo_root: Path) -> EvalTask | None:
    """Resolve ``task_id`` to its :class:`EvalTask`, or ``None`` if absent.

    Loads via the same :class:`SyncContext` enumeration the read-only modes use
    (engine + overlay + repo-local tasks), so ``--run`` sees exactly the task set
    ``--list`` does.
    """
    ctx = SyncContext.from_repo(repo_root)
    for task in ctx.artifact_source.list_eval_tasks():
        if task.id == task_id:
            return task
    return None


def _runner_available(runner_cls: type[HarnessRunner]) -> bool:
    """Whether ``runner_cls`` can run here.

    Runners may expose an ``available()`` classmethod (the real
    ``ClaudeCodeRunner`` does, guarding on its CLI being on ``PATH``). A runner
    without one — the hermetic ``FakeRunner`` — is always available.
    """
    guard = getattr(runner_cls, "available", None)
    if guard is None:
        return True
    return bool(guard())
