"""``playbook eval`` — Tier 0 enumeration + the R1 live runner (SPEC §12.8, §15).

``playbook eval`` is both a read-only enumeration of the prompt-to-task graph and
— with ``--run`` (PR R1d) — the entry point that *executes* one task end-to-end
through a :class:`~coding_agent_playbook.evals.runner.HarnessRunner` and grades it
via the unified PR-M :class:`EvaluationReport`.

Sub-modes:

- ``playbook eval --list`` (also the default when no arg is given): tree-shape
  coverage report across every prompt, with per-task summary lines.
- ``playbook eval --show <id>``: detailed dump for one task — sections from
  SPEC §12.8 (Task / Source / Prompt under test / Description / Setup /
  Invocation / Expected / Rubric).
- ``playbook eval <id>`` (no ``--run``): runner-deferral message. Exits 0 if the
  task is known, exits 1 if it isn't (so typos still surface — the deferral only
  applies to tasks that genuinely exist).
- ``playbook eval <id> --run [--runner NAME] [--format text|json]``: load the
  task, select ``NAME`` from the ``coding_agent_playbook.runners`` entry-point
  group (default ``claude_code``), run it in a throwaway scratch dir, and render
  ``result.report`` (reusing ``commands/metrics.py``'s text/json renderer). Exits
  ``0`` on a passing report, ``1`` on a failing one, ``2`` on usage errors
  (unknown task, unknown/unavailable runner, bad ``--format``).

  Unlike ``playbook metrics``, there is **no ``--run-tests`` flag**: whether the
  execution evaluators (``coverage``/``test_pass_rate``) run is declared by the
  task's own ``[metrics]`` block (``run_tests``), so the eval task — not a CLI
  flag — carries that intent.
"""

from __future__ import annotations

import json
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.orchestrator import SyncContext

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.evals.runner import HarnessRunner, TaskResult
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.types import Prompt


#: Entry-point group runners self-register under (mirrors adapters/sources).
_RUNNERS_GROUP = "coding_agent_playbook.runners"

#: Default runner when ``--runner`` is omitted (the one thin real runner).
_DEFAULT_RUNNER = "claude_code"

_VALID_FORMATS = ("text", "json")


_RUNNER_DEFERRAL_TEMPLATE = (
    "Eval runner not yet implemented (v1 ships task schema only).\n"
    "The task is well-formed and ready to run when the v2 runner lands. For now:\n"
    "  - Use `playbook eval --show {task_id}` to inspect the task.\n"
    "  - Use `playbook eval --list` to see all task coverage.\n"
    "  - To run manually: copy setup/ to a scratch repo, invoke /{slash}\n"
    "    with the documented args, and grade against the expected/rubric.\n"
    "See SPEC.md Section 15 for the v2 runner API."
)


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
        return _print_runner_deferral(bare_id, tasks, ctx.prompts_resolved)
    # No flag — default to --list (matches the "helpful empty invocation" rule).
    return _print_list(ctx.prompts_resolved, tasks)


# --------------------------------------------------------------------------- #
# --run — execute one task through a HarnessRunner and grade it (PR R1d)
# --------------------------------------------------------------------------- #


def _run_task_cli(args: argparse.Namespace, repo_root: Path) -> int:
    """Load + run one task, render its report, map ``passed`` to the exit code.

    Exit codes: ``0`` pass, ``1`` failing report, ``2`` usage errors (no task id,
    unknown task, unknown/unavailable runner, bad ``--format``).
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
    runner_cls = _load_runner_class(runner_name)
    if runner_cls is None:
        available = ", ".join(_available_runner_names()) or "(none registered)"
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

    runner = runner_cls()
    with tempfile.TemporaryDirectory(prefix="playbook-eval-") as tmp:
        result = runner.run_task(task, Path(tmp) / "scratch")

    if fmt == "json":
        print(json.dumps(_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(_format_result_text(result))

    return 0 if result.report.passed else 1


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


def _load_runner_class(name: str) -> type[HarnessRunner] | None:
    """Load the runner class registered under ``name`` in the runners group.

    Never instantiates the runner here (the caller does, after the availability
    guard). Returns ``None`` when no entry point matches ``name``.
    """
    for ep in metadata.entry_points(group=_RUNNERS_GROUP):
        if ep.name == name:
            return ep.load()  # type: ignore[no-any-return]
    return None


def _available_runner_names() -> list[str]:
    """Sorted names of every runner registered in the entry-point group."""
    return sorted(ep.name for ep in metadata.entry_points(group=_RUNNERS_GROUP))


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


# --------------------------------------------------------------------------- #
# Report rendering (reuses commands/metrics.py's EvaluationReport renderer)
# --------------------------------------------------------------------------- #


def _result_to_dict(result: TaskResult) -> dict[str, object]:
    """Stable JSON view of a :class:`TaskResult` (task envelope + the report)."""
    from coding_agent_playbook.commands.metrics import _report_to_dict

    return {
        "task_id": result.task_id,
        "harness": result.harness,
        "passed": result.passed,
        "aggregate_score": result.aggregate_score,
        "duration_seconds": result.duration_seconds,
        "report": _report_to_dict(result.report),
    }


def _format_result_text(result: TaskResult) -> str:
    """Human view: the metrics-style findings block + a per-task footer."""
    from coding_agent_playbook.commands.metrics import _format_text

    body = _format_text(result.report, skipped=[], note=None, measured_count=0)
    verdict = "PASS" if result.passed else "FAIL"
    footer = (
        f"  task: {result.task_id} via {result.harness} — {verdict} "
        f"(score={result.aggregate_score:.3f}, {result.duration_seconds:.2f}s)"
    )
    return f"{body}\n{footer}"


def _print_list(prompts: list[Prompt], tasks: list[EvalTask]) -> int:
    """Tree-shape coverage report per SPEC §12.8.

    Layout (one prompt per block):

        === Eval tasks ===
        <prompt-id> (<source>)
          ├── <task-id>        ✓ task defined
          │   └── N rubric criteria, M programmatic checks
          └── ...

        Total: P prompts, T eval tasks, U prompts without tasks
    """
    tasks_by_id: dict[str, EvalTask] = {t.id: t for t in tasks}
    tasks_by_prompt: dict[str, list[EvalTask]] = {}
    for task in tasks:
        tasks_by_prompt.setdefault(task.prompt_id, []).append(task)

    lines: list[str] = ["=== Eval tasks ==="]
    rendered_any_prompt = False
    prompts_without_tasks = 0
    for prompt in prompts:
        rendered_any_prompt = True
        prompt_id = prompt.frontmatter.id
        # Order tasks by the prompt's eval_tasks: frontmatter (the
        # authoring-order users expect). Tasks present on-disk but missing
        # from the frontmatter still get rendered, in alphabetical order,
        # so authoring drift is visible.
        declared_order = prompt.frontmatter.eval_tasks or []
        ordered: list[EvalTask] = []
        seen: set[str] = set()
        for declared_id in declared_order:
            candidate = tasks_by_id.get(declared_id)
            if candidate is not None and candidate.prompt_id == prompt_id:
                ordered.append(candidate)
                seen.add(declared_id)
        for leftover in sorted(tasks_by_prompt.get(prompt_id, []), key=lambda t: t.id):
            if leftover.id not in seen:
                ordered.append(leftover)
        prompt_tasks = ordered
        source = _short_source(prompt.source_package)
        lines.append(f"{prompt_id} ({source})")
        if not prompt_tasks:
            lines.append("  └── (no eval tasks declared)         ⚠ consider adding tasks")
            prompts_without_tasks += 1
            continue
        for index, task in enumerate(prompt_tasks):
            is_last = index == len(prompt_tasks) - 1
            connector = "└──" if is_last else "├──"
            sub_connector = "    " if is_last else "│   "
            id_padded = f"{task.id:<36}"
            lines.append(f"  {connector} {id_padded}✓ task defined")
            criteria_count = len(task.rubric.criteria) if task.rubric else 0
            checks_count = _count_programmatic_checks(task)
            lines.append(
                f"  {sub_connector}└── "
                f"{criteria_count} rubric criteria, {checks_count} programmatic checks"
            )

    # Blank separator between the per-prompt blocks and the Total: line
    # is part of the SPEC §12.8 layout. On an empty repo (zero prompts
    # rendered), omit it so the header is immediately followed by the
    # Total without a stray blank line — keeps ``playbook eval --list`` clean
    # on a fresh project that hasn't authored prompts yet.
    if rendered_any_prompt:
        lines.append("")
    # Pluralize each count so single-item totals don't read "1 prompts"
    # (SPEC §12.8 example covers both singular and plural shapes). The
    # "prompts without tasks" suffix has to be spelled out because the
    # head noun ("prompt") is not at the tail — naively appending "s" to
    # "prompt without tasks" would emit "prompt without taskss".
    pwt_label = "prompt without tasks" if prompts_without_tasks == 1 else "prompts without tasks"
    lines.append(
        f"Total: {_plural(len(prompts), 'prompt')}, "
        f"{_plural(len(tasks), 'eval task')}, "
        f"{prompts_without_tasks} {pwt_label}"
    )
    print("\n".join(lines))
    return 0


def _plural(n: int, word: str) -> str:
    """Render ``n word`` with the English ``+s`` suffix when ``n != 1``.

    Used by ``playbook eval --list`` so the ``Total:`` line reads ``1 prompt``
    instead of ``1 prompts``. Only works for words whose plural is formed
    by appending ``s`` to the supplied lemma — compound subjects whose head
    noun is not at the tail (e.g. ``"prompt without tasks"``) must be
    handled at the call site.
    """
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _print_show(task_id: str, tasks: list[EvalTask], prompts: list[Prompt]) -> int:
    """Detailed task dump per SPEC §12.8."""
    task = next((t for t in tasks if t.id == task_id), None)
    if task is None:
        print(f"error: no eval task with id {task_id!r}", file=sys.stderr)
        return 1

    lines: list[str] = []
    lines.append(f"Task: {task.id}")
    lines.append(f"Source: {_display_source_path(task)}")
    lines.append(f"Prompt under test: {task.prompt_id}")
    lines.append(f"Description: {task.description}")
    lines.append("Setup:")
    facts = (
        f"python_version={task.setup.python_version}, "
        f"frameworks=[{', '.join(task.setup.frameworks)}]"
    )
    lines.append(f"  Mock facts: {facts}")
    files_list = ", ".join(str(p) for p in task.setup.files) or "(none)"
    lines.append(f"  Files ({len(task.setup.files)}): {files_list}")
    lines.append("Invocation:")
    # The slash name is the prompt's own slash (which the schema allows to
    # differ from the prompt id — e.g. id="generate-tests" + slash="gen-tests").
    # Falling back to the prompt_id when the prompt is missing keeps --show
    # useful in mid-authoring states where the prompt hasn't been written yet,
    # but for any resolved prompt we honour its declared slash.
    prompt = next((p for p in prompts if p.frontmatter.id == task.prompt_id), None)
    slash = prompt.frontmatter.slash if prompt is not None else task.prompt_id
    lines.append(f"  Prompt: /{slash}")
    lines.append(f'  Args: "{task.invocation.prompt_args}"')
    if task.invocation.input_variables:
        bindings = ", ".join(f"{k}={v}" for k, v in task.invocation.input_variables.items())
        lines.append(f"  Variables: {bindings}")

    if task.expected is None:
        lines.append("Expected: (none)")
    else:
        checks_count = _count_programmatic_checks(task)
        lines.append(f"Expected (programmatic, {checks_count} checks):")
        for created in task.expected.files_created:
            lines.append(f"  - File created: {created}")
        for entry in task.expected.files_must_contain:
            lines.append(f"  - {entry['path']} contains: {entry['pattern']}")
        for unchanged in task.expected.files_unchanged:
            lines.append(f"  - File unchanged: {unchanged}")
        for forbidden in task.expected.files_forbidden:
            lines.append(f"  - File forbidden: {forbidden}")

    if task.rubric is None:
        lines.append("Rubric: (none)")
    else:
        if task.rubric.weights is not None:
            total = sum(task.rubric.weights)
            header = (
                f"Rubric (manual / LLM-judge, {len(task.rubric.criteria)} criteria, "
                f"weights sum={total:.1f}):"
            )
            lines.append(header)
            for weight, criterion in zip(task.rubric.weights, task.rubric.criteria, strict=True):
                lines.append(f"  - {weight}: {criterion}")
        else:
            lines.append(
                f"Rubric (manual / LLM-judge, {len(task.rubric.criteria)} criteria, "
                "weights=uniform):"
            )
            for criterion in task.rubric.criteria:
                lines.append(f"  - {criterion}")

    print("\n".join(lines))
    return 0


def _print_runner_deferral(task_id: str, tasks: list[EvalTask], prompts: list[Prompt]) -> int:
    """Bare ``playbook eval <id>`` — verify task exists, then print deferral. Exit 0.

    Unknown task ids exit 1 so typos surface (the deferral promise applies
    only to tasks that genuinely exist).
    """
    task = next((t for t in tasks if t.id == task_id), None)
    if task is None:
        print(f"error: no eval task with id {task_id!r}", file=sys.stderr)
        return 1
    # If the prompt is loadable, use its slash; otherwise fall back to the
    # prompt id so the message is still useful in mid-authoring states.
    slash = task.prompt_id
    for prompt in prompts:
        if prompt.frontmatter.id == task.prompt_id:
            slash = prompt.frontmatter.slash
            break
    print(f"playbook eval {task_id}:")
    print(_RUNNER_DEFERRAL_TEMPLATE.format(task_id=task_id, slash=slash))
    return 0


def _short_source(source_package: str) -> str:
    """Render the prompt's source package as ``"engine"``/``"overlay X"``/etc.

    Matches the SPEC §12.8 example where the engine is annotated ``engine`` and
    overlay packages get ``overlay <name>``.
    """
    if source_package == "coding_agent_playbook":
        return "engine"
    if source_package == "<repo-local>":
        return "repo-local"
    return f"overlay {source_package}"


def _display_source_path(task: EvalTask) -> str:
    """Format ``task.source_path`` for human reading on the ``Source:`` line.

    SPEC §12.8 shows the path as package-relative for engine/overlay tasks
    (``coding_agent_playbook/resources/eval_tasks/<id>/``) and repo-relative
    for repo-local tasks (``playbook/eval_tasks/<id>/``). Absolute
    filesystem paths would leak the local workspace layout into the output,
    which is both noisy and unhelpful — package-relative paths are the
    canonical reference users grep for when jumping to the task source.

    Strategy:

    - For engine/overlay sources (any ``source_package`` other than
      ``"<repo-local>"``), find the ``resources/`` segment in the path and
      prefix the parts from there with the package name.
    - For repo-local sources, find the ``playbook/`` segment and emit the
      path starting from there.
    - If the expected segment is missing (e.g. unusual layout, or the source
      was constructed by a non-filesystem implementation), fall back to the
      task directory's basename prefixed with the package name so the output
      is still attributable. Never raise — ``playbook eval --show`` should never
      crash on a path-formatting issue.

    The trailing ``/`` is appended so the output always reads as a directory
    (matching the SPEC example).
    """
    parts = task.source_path.parent.parts
    if task.source_package == "<repo-local>":
        if "playbook" in parts:
            idx = parts.index("playbook")
            return str(Path(*parts[idx:])) + "/"
        return task.source_path.parent.name + "/"
    # Engine or overlay package.
    if "resources" in parts:
        idx = parts.index("resources")
        return f"{task.source_package}/" + str(Path(*parts[idx:])) + "/"
    return f"{task.source_package}/{task.source_path.parent.name}/"


def _count_programmatic_checks(task: EvalTask) -> int:
    """Sum every entry across the four ``ExpectedOutcome`` lists."""
    if task.expected is None:
        return 0
    return (
        len(task.expected.files_created)
        + len(task.expected.files_must_contain)
        + len(task.expected.files_unchanged)
        + len(task.expected.files_forbidden)
    )
