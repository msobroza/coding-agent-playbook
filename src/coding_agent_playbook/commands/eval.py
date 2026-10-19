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
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.roots import is_bundled_layer
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.prompting import PromptResolutionError
from coding_agent_playbook.evaluators.scope import Determinism
from coding_agent_playbook.evaluators.types import CheckResult, ScopeDetail
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.runner import HarnessRunner, TaskResult
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.evaluators.types import TrialResult


#: Entry-point group runners self-register under (mirrors adapters/sources).
_RUNNERS_GROUP = "coding_agent_playbook.runners"

#: Entry-point group judges register under (``llm`` ships; default: no judge).
_JUDGES_GROUP = "coding_agent_playbook.judges"

#: Default runner when ``--runner`` is omitted (the one thin real runner).
_DEFAULT_RUNNER = "claude_code"

_VALID_FORMATS = ("text", "json")


_RUN_HINT_TEMPLATE = (
    "Add --run to execute this task against an agent and grade it:\n"
    "  playbook eval {task_id} --run --runner fake    # hermetic no-op agent, no CLI\n"
    "  playbook eval {task_id} --run                  # default runner: {default_runner}\n"
    "  playbook eval {task_id} --run --judge llm      # also score the [rubric] layer\n"
    "Inspect it with `playbook eval --show {task_id}`; coverage: `playbook eval --list`.\n"
    "To run it by hand, copy setup/ to a scratch repo and invoke /{slash}."
)

#: Printed under a report whose scores include an LLM judge's (SPEC §19 Q12).
_UNCALIBRATED_NOTE = (
    "  note: judged scores come from an uncalibrated LLM judge (SPEC §19 Q12); "
    "treat them as advisory"
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

    # --judge selects a Tier-2 judge from the judges entry-point group. Omitted =>
    # deterministic-only (no judge); judged [rubric] criteria are skipped.
    judge_name = getattr(args, "judge", None)
    judge: Judge | None = None
    if judge_name is not None:
        judge_cls = _load_judge_class(judge_name)
        if judge_cls is None:
            available = ", ".join(_available_judge_names()) or "(none registered)"
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
        print(json.dumps(_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(_format_result_text(result))

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


def _load_judge_class(name: str) -> type[Judge] | None:
    """Load the judge class registered under ``name`` in the judges group.

    Never instantiates the judge here (the caller does, after the availability
    guard). Returns ``None`` when no entry point matches ``name``.
    """
    for ep in metadata.entry_points(group=_JUDGES_GROUP):
        if ep.name == name:
            return ep.load()  # type: ignore[no-any-return]
    return None


def _available_judge_names() -> list[str]:
    """Sorted names of every judge registered in the entry-point group."""
    return sorted(ep.name for ep in metadata.entry_points(group=_JUDGES_GROUP))


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
# Report rendering (Metric/Check/Rubric: iterate report.checks → subresults)
# --------------------------------------------------------------------------- #


def _result_to_dict(result: TaskResult) -> dict[str, object]:
    """Stable JSON view of a :class:`TaskResult` (task envelope + the report).

    The report is rendered as the list of :class:`CheckResult` rows the
    :class:`~coding_agent_playbook.evaluators.rubric.Rubric` produced, each with
    its flattened per-scope :class:`ScopeDetail` ``subresults``. The flat
    ``findings`` list is kept too (transitional) so existing JSON consumers that
    read ``report.findings`` keep working.
    """
    report = result.report
    out: dict[str, object] = {
        "task_id": result.task_id,
        "harness": result.harness,
        "passed": result.passed,
        "aggregate_score": result.aggregate_score,
        "duration_seconds": result.duration_seconds,
        "report": {
            "passed": report.passed,
            "warn_count": report.warn_count,
            "fail_count": report.fail_count,
            "composite": report.composite,
            "checks": [_check_to_dict(c) for c in report.checks],
            "findings": [_finding_to_dict(f) for f in report.findings],
        },
    }
    # Across-trial aggregate: present only when the task authored an
    # [aggregate] block. ``trials`` is the per-trial pass/fail sequence.
    out["uncalibrated_judge"] = _any_trial_judge_scored(result)
    if result.aggregate is not None:
        out["trials"] = len(result.trials)
        out["aggregate"] = _check_to_dict(result.aggregate)
        out["trial_verdicts"] = [t.verdict for t in result.trials]
    return out


def _check_to_dict(check: CheckResult) -> dict[str, object]:
    """Stable JSON view of one :class:`CheckResult` + its leaf ``subresults``."""
    return {
        "check_id": check.check_id,
        "passed": check.passed,
        "score": check.score,
        "weight": check.weight,
        "required": check.required,
        "status": check.status,
        "subresults": [
            _finding_to_dict(sub) for sub in check.subresults if isinstance(sub, ScopeDetail)
        ],
    }


def _finding_to_dict(finding: ScopeDetail) -> dict[str, object]:
    """Stable JSON view of one per-scope :class:`ScopeDetail` leaf."""
    return {
        "evaluator": finding.evaluator,
        "scope_key": finding.scope_key,
        "value": finding.value,
        "baseline": finding.baseline,
        "bound": finding.bound,
        "score": finding.score,
        "level": finding.level,
        "kind": finding.kind,
    }


def _format_result_text(result: TaskResult) -> str:
    """Human view: per-check blocks (each with its scope leaves) + a footer."""
    report = result.report
    lines: list[str] = ["=== Eval scoring ==="]

    run_checks = [c for c in report.checks if c.status == "run"]
    if not run_checks:
        lines.append("  (no checks ran)")
    for check in run_checks:
        verdict = "PASS" if check.passed else "FAIL"
        score = "n/a" if check.score is None else f"{check.score:.3f}"
        lines.append(f"  [{verdict}] {check.check_id} (score={score})")
        for sub in check.subresults:
            if not isinstance(sub, ScopeDetail) or sub.level == "ok":
                continue
            detail = _scope_detail(sub)
            lines.append(
                f"      [{sub.level}] {sub.evaluator} @ {sub.scope_key} "
                f"= {sub.value:g} ({sub.kind}{detail})"
            )

    skipped = [c for c in report.checks if c.status == "skipped"]
    for check in skipped:
        lines.append(f"  [skip] {check.check_id}")

    composite = "n/a" if report.composite is None else f"{report.composite:.3f}"
    verdict = "PASS" if result.passed else "FAIL"
    lines.append(
        f"  summary: {verdict} — {report.fail_count} fail, {report.warn_count} warn, "
        f"composite={composite}"
    )

    # Across-trial aggregate: pass@k / pass^k over N trials, when present.
    if result.aggregate is not None:
        lines.append(_aggregate_line(result.aggregate, result.trials))

    if _any_trial_judge_scored(result):
        lines.append(_UNCALIBRATED_NOTE)

    footer = (
        f"  task: {result.task_id} via {result.harness} — {verdict} "
        f"(score={result.aggregate_score:.3f}, {result.duration_seconds:.2f}s)"
    )
    return "\n".join([*lines, footer])


def _aggregate_line(agg: CheckResult, trials: list[TrialResult]) -> str:
    """The text-report line for the ``[aggregate]`` layer's result.

    A skipped aggregate (its ``over`` axis never ran, e.g. ``over = "rubric"``
    with no judge) has no verdict of its own: the task verdict fell back to the
    trials' verdicts, so say that rather than print a misleading ``FAIL``.
    """
    n_pass = sum(1 for t in trials if t.verdict)
    n = len(trials)
    if agg.status != "run":
        return (
            f"  aggregate: {agg.check_id} skipped (its over-axis never ran); "
            f"verdict from all {n} trials ({n_pass}/{n} passed)"
        )
    agg_verdict = "PASS" if agg.passed else "FAIL"
    score = "n/a" if agg.score is None else f"{agg.score:.3f}"
    return (
        f"  aggregate: {agg.check_id} = {score} ({agg_verdict}), {n} trials ({n_pass}/{n} passed)"
    )


def _any_trial_judge_scored(result: TaskResult) -> bool:
    """Whether a judge scored anything in *any* trial (not just the reported one)."""
    reports = [t.report for t in result.trials] or [result.report]
    return any(_judge_scored(report.checks) for report in reports)


def _judge_scored(checks: Iterable[CheckResult]) -> bool:
    """Whether any *leaf* check that ran was judged (its score came from a judge).

    Composers inherit ``JUDGED`` from any judged child even when only their
    deterministic children ran, so only leaves count.
    """
    return any(_judge_scored_leaf(check) for check in checks)


def _judge_scored_leaf(check: CheckResult) -> bool:
    if check.status != "run":
        return False
    nested = [sub for sub in check.subresults if isinstance(sub, CheckResult)]
    if nested:
        return _judge_scored(nested)
    return check.determinism is Determinism.JUDGED


def _scope_detail(sub: ScopeDetail) -> str:
    """A short suffix describing the comparison that decided a scope leaf."""
    if sub.kind == "regression" and sub.baseline is not None:
        return f"; baseline={sub.baseline:g}"
    if sub.bound is not None:
        return f"; bound={sub.bound:g}"
    return ""


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
            criteria_count = _count_rubric_criteria(task)
            checks_count = _count_gate_checks(task)
            lines.append(
                f"  {sub_connector}└── {criteria_count} rubric criteria, {checks_count} gate checks"
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
    # ``project_kind`` is the lone mock-detector fact carried by [setup] (the
    # other facts — python version, deps — live in setup/pyproject.toml since
    # C11). Any extras (e.g. ``ml_stack``) print alongside it.
    fact_bits = [f"project_kind={task.setup.project_kind}"]
    for key, value in sorted(task.setup.extra_facts.items()):
        fact_bits.append(f"{key}={value!r}")
    lines.append(f"  Mock facts: {', '.join(fact_bits)}")
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

    if task.gate is None:
        lines.append("Gate: (none)")
    else:
        gate_checks = _gate_check_descriptions(task)
        expr = task.gate.expr or " and ".join(task.gate.bind) or "(empty)"
        lines.append(f"Gate (deterministic, {len(gate_checks)} checks, expr: {expr}):")
        for desc in gate_checks:
            lines.append(f"  - {desc}")

    if task.rubric is None:
        lines.append("Rubric: (none)")
    else:
        criteria = _rubric_criteria_with_weights(task)
        lines.append(f"Rubric (manual / LLM-judge, {len(criteria)} criteria):")
        for weight, criterion in criteria:
            prefix = "" if weight is None else f"{weight}: "
            lines.append(f"  - {prefix}{criterion}")

    lines.append(f"Verdict: {task.verdict}")

    print("\n".join(lines))
    return 0


def _print_run_hint(task_id: str, tasks: list[EvalTask], prompts: list[Prompt]) -> int:
    """Bare ``playbook eval <id>`` — verify the task exists, then print how to run it.

    Exit 0. Unknown task ids exit 1 so typos surface.
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
    print(_RUN_HINT_TEMPLATE.format(task_id=task_id, slash=slash, default_runner=_DEFAULT_RUNNER))
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
    """Label the task's directory for the ``Source:`` line, by its layer.

    SPEC §12.8 shows a layer-relative path, never the absolute filesystem path,
    which would leak the local workspace layout into the output. The label is
    built from the layer kind and ``<dir>``, the task directory's name
    (``task.source_path.parent.name``, never ``task.id``, which nothing ties to
    the directory). No path segment is searched for, so an unusual layout can
    neither crash ``playbook eval --show`` nor change the label:

    - bundled layers (engine, bundled plugins): ``<source_package>/eval_tasks/<dir>/``;
    - third-party overlays: ``<source_package>/resources/eval_tasks/<dir>/``,
      still a real package-relative path;
    - repo-local tasks: ``playbook/eval_tasks/<dir>/``.

    The trailing ``/`` makes the label read as a directory (the SPEC example).
    """
    task_dir = task.source_path.parent.name
    if task.source_package == "<repo-local>":
        return f"playbook/eval_tasks/{task_dir}/"
    if is_bundled_layer(task.source_package):
        return f"{task.source_package}/eval_tasks/{task_dir}/"
    return f"{task.source_package}/resources/eval_tasks/{task_dir}/"


def _count_gate_checks(task: EvalTask) -> int:
    """Number of top-level ``[gate.bind]`` handles (the deterministic gate checks).

    A composed handle (an ``all_of``/``any_of`` group) counts as one — the summary
    line is a coarse handle count, not a deep leaf count.
    """
    if task.gate is None:
        return 0
    return len(task.gate.bind)


def _count_rubric_criteria(task: EvalTask) -> int:
    """Number of judged criteria the ``[rubric.bind]`` rubric groups declare."""
    return len(_rubric_criteria_with_weights(task))


def _gate_check_descriptions(task: EvalTask) -> list[str]:
    """A one-line description of each ``[gate.bind]`` handle for ``--show``.

    Renders the handle name + a short shape summary (the ``check`` kind +
    path/pattern for a standalone file/threshold check, or the boolean-group /
    ref shape). Reads the raw binding tables — no compilation — so ``--show`` works
    even on a task that would fail to compile.
    """
    if task.gate is None:
        return []
    out: list[str] = []
    for name, binding in task.gate.bind.items():
        out.append(f"{name}: {_describe_binding(binding)}")
    return out


def _describe_binding(binding: dict[str, object]) -> str:
    """Short human description of one handle binding (its shape + key fields)."""
    if "check" in binding:
        kind = binding["check"]
        path = binding.get("path")
        pattern = binding.get("pattern")
        detail = f" {path}" if path else ""
        detail += f" ~/{pattern}/" if pattern else ""
        return f"check {kind}{detail}"
    if "ref" in binding:
        return f"ref {binding['ref']}"
    if "rubric" in binding:
        criteria = binding["rubric"]
        n = len(criteria) if isinstance(criteria, list) else 0
        return f"rubric ({n} criteria)"
    for group in ("all_of", "any_of", "not"):
        if group in binding:
            return f"{group} group"
    return "(unknown)"


def _rubric_criteria_with_weights(task: EvalTask) -> list[tuple[float | None, str]]:
    """The ``(weight, criterion)`` pairs across every ``[rubric.bind]`` rubric group.

    Reads the raw binding tables (no compilation): each ``rubric`` group's entries
    are ``{judge=…, weight=…}``, flattened across all rubric-group handles. A
    non-``rubric`` handle (a ref or composed boolean) contributes nothing here.
    """
    if task.rubric is None:
        return []
    out: list[tuple[float | None, str]] = []
    for binding in task.rubric.bind.values():
        criteria = binding.get("rubric")
        if not isinstance(criteria, list):
            continue
        for entry in criteria:
            if not isinstance(entry, dict):
                continue
            judge = entry.get("judge")
            weight = entry.get("weight")
            if isinstance(judge, str):
                w = float(weight) if isinstance(weight, (int, float)) else None
                out.append((w, judge))
    return out
