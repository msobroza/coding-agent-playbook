"""``HarnessRunner`` — execute one eval task end-to-end and score it (PR R1).

This is the v1.1 activation of the former v2 placeholder (SPEC §15.3). A
:class:`HarnessRunner` runs a single :class:`~coding_agent_playbook.evals.task.EvalTask`
against an agent and grades the result through the
:class:`~coding_agent_playbook.evaluators.metric.Metric` /
:class:`~coding_agent_playbook.evaluators.check.Check` /
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` model, so the
*deterministic* scoring layers (``[expected]`` file checks + ``[metrics]``
static/execution metrics, including non-regression vs the ``setup/`` baseline)
are live. **Judged/rubric scoring is deferred to R2**: the runner sets no
``Judge`` on the :class:`EvalContext`, so judged checks report ``available() is
False`` and are skipped.

The class is a **template method**: :meth:`HarnessRunner.run_task` owns the fixed
pipeline (materialize → render prompt → invoke agent → capture → score → assemble
a :class:`TaskResult`) and the only per-assistant step is the abstract
:meth:`_invoke_agent` hook. The hermetic default + unit-test driver is
:class:`~coding_agent_playbook.evals.fake_runner.FakeRunner`; the thin
``ClaudeCodeRunner`` ships in R1c. Discovery is via the
``coding_agent_playbook.runners`` entry-point group — never instantiate runners
directly.

The result model is **Option B** (SPEC §15.3, revised by the R1 brainstorm):
:class:`TaskResult` carries one :class:`EvaluationReport` rather than the inert
``programmatic_checks``/``rubric_scores`` placeholder fields, which had no
consumers. The old per-check placeholder is retired — a programmatic check is now
a BOOL :class:`~coding_agent_playbook.evaluators.types.ScopeDetail` row.
"""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.scoring import score

if TYPE_CHECKING:
    from coding_agent_playbook.evals.task import EvalTask
    from coding_agent_playbook.evaluators import EvaluationReport, JudgeLike


class PromptResolutionError(RuntimeError):
    """A runner that ``requires_resolved_prompt`` could not resolve its prompt.

    Raised by :func:`render_prompt` when ``strict=True`` and the task's
    ``prompt_id`` resolves to no shipped :class:`Prompt`. A *real* agent must never
    be driven with the descriptive placeholder the hermetic
    :class:`~coding_agent_playbook.evals.fake_runner.FakeRunner` tolerates, so the
    strict path fails loudly instead.
    """


# --------------------------------------------------------------------------- #
# Result types (Option B)
# --------------------------------------------------------------------------- #


@dataclass
class AgentRun:
    """The raw outcome of one agent invocation inside the scratch repo.

    ``returncode`` is ``0`` when the agent loop completed; ``transcript`` is the
    captured conversation/log (the judge's ``artifact`` in R2).
    """

    transcript: str
    returncode: int


@dataclass
class TaskResult:
    """Per-task outcome: the unified evaluation report + convenience aggregates.

    ``report`` is the single :class:`EvaluationReport` covering both the
    ``[expected]`` BOOL findings and the ``[metrics]`` static/execution findings.
    ``passed`` mirrors ``report.passed`` and ``aggregate_score`` mirrors
    ``report.composite`` (falling back to ``1.0``/``0.0`` from ``passed`` when no
    weighted evaluator contributed a composite).
    """

    task_id: str
    harness: str
    report: EvaluationReport
    passed: bool
    aggregate_score: float
    duration_seconds: float
    transcript: str


@dataclass
class EvalReport:
    """Aggregate over several :class:`TaskResult`\\ s for one harness.

    ``aggregate_pass_rate`` is the mean of ``tr.passed`` across ``task_results``
    (``0.0`` for an empty run).
    """

    engine_version: str
    harness: str
    task_results: list[TaskResult]
    aggregate_pass_rate: float
    timestamp: str

    @staticmethod
    def pass_rate(task_results: list[TaskResult]) -> float:
        """Mean of ``tr.passed`` over ``task_results`` (``0.0`` when empty)."""
        if not task_results:
            return 0.0
        return sum(1 for tr in task_results if tr.passed) / len(task_results)


# --------------------------------------------------------------------------- #
# Orchestration handles
# --------------------------------------------------------------------------- #


@dataclass
class Baseline:
    """The materialized ``setup/`` state — the non-regression reference.

    ``repo_root`` is the git-init'd scratch repo (the agent edits this in place);
    ``commit`` is the baseline commit ref; ``setup_snapshot`` is a *separate*,
    untouched copy of the ``setup/`` tree that the execution evaluators run their
    baseline suite against (so a candidate that breaks tests is compared against a
    pristine baseline rather than the post-agent tree).
    """

    repo_root: Path
    commit: str
    setup_snapshot: Path


@dataclass
class Candidate:
    """The post-agent state captured for scoring.

    ``tree`` is the scratch repo root after the agent ran (the static + execution
    evaluators read it); ``diff`` is the ``git diff`` against the baseline commit
    and ``transcript`` is the agent log — both reserved for R2's judge.
    """

    tree: Path
    diff: str
    transcript: str
    changed_files: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# git helpers (stdlib subprocess; no third-party dep)
# --------------------------------------------------------------------------- #

#: Inline identity so ``git commit`` works in a hermetic scratch repo without
#: relying on (or mutating) the caller's global git config.
_GIT_ENV_ARGS = [
    "-c",
    "user.name=playbook-eval",
    "-c",
    "user.email=eval@coding-agent-playbook.invalid",
    "-c",
    "commit.gpgsign=false",
]


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git`` in ``repo_root`` with a pinned hermetic identity."""
    return subprocess.run(
        ["git", *_GIT_ENV_ARGS, *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )


# --------------------------------------------------------------------------- #
# Orchestration helpers
# --------------------------------------------------------------------------- #


def materialize(task: EvalTask, scratch_dir: Path) -> Baseline:
    """Copy the task's ``setup/`` into ``scratch_dir`` and commit it as baseline.

    The ``setup/`` tree (sibling of the task's ``task.toml``) is byte-copied into
    ``scratch_dir`` (which becomes the agent's working tree). The scratch repo is
    ``git init``'d and the initial state committed so :func:`capture` can ``git
    diff`` against it and the ``[expected]`` ``files_unchanged`` check has a
    reference. A *second*, pristine copy of ``setup/`` is kept alongside the
    scratch repo as the execution-evaluator baseline (run on the untouched setup,
    never on the post-agent tree).

    A task whose ``setup/`` directory is missing yields an empty baseline repo —
    the runner still works, the static/execution layers simply have nothing to
    measure.
    """
    scratch_dir = Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    setup_dir = task.source_path.parent / "setup"
    if setup_dir.is_dir():
        shutil.copytree(setup_dir, scratch_dir, dirs_exist_ok=True)

    _git(scratch_dir, "init", "-q")
    _git(scratch_dir, "add", "-A")
    _git(scratch_dir, "commit", "-q", "--allow-empty", "-m", "setup baseline")
    commit = _git(scratch_dir, "rev-parse", "HEAD").stdout.strip()

    # Pristine snapshot of setup/ for the execution baseline. Kept *outside* the
    # scratch repo (sibling dir) so the agent cannot touch it.
    snapshot = scratch_dir.parent / f"{scratch_dir.name}__setup_baseline"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    if setup_dir.is_dir():
        shutil.copytree(setup_dir, snapshot)
    else:
        snapshot.mkdir(parents=True, exist_ok=True)

    return Baseline(repo_root=scratch_dir, commit=commit, setup_snapshot=snapshot)


def render_prompt(task: EvalTask, *, strict: bool = False) -> str:
    """Resolve ``task.prompt_id`` to its :class:`Prompt` and render its body.

    Resolution scans the ``resources/prompts/`` directory alongside the task's
    ``eval_tasks/`` tree (see :func:`_resolve_prompt`), finds the prompt whose
    ``id`` matches ``task.prompt_id``, and renders its template body through the
    renderer with ``task.invocation.input_variables`` under ``StrictUndefined``
    (so a typo'd variable fails loudly). ``prompt_args`` is appended to the
    rendered body.

    Pragmatic fallbacks (documented): the ``includes_rules:`` appendix is *not*
    expanded here — rendering the bare prompt body is enough to drive an agent and
    keeps prompt resolution free of the full sync/rule-registry machinery; a
    prompt that uses ``{{ rule(...) }}`` in its *body* would need that registry, but
    none of the shipped prompts do (rules are appended, not inlined).

    When the prompt cannot be resolved at all (e.g. an out-of-tree test task) the
    behaviour depends on ``strict``: the hermetic
    :class:`~coding_agent_playbook.evals.fake_runner.FakeRunner` never reads the
    rendered text for the deterministic scoring layers, so it tolerates a stable
    placeholder (``strict=False``, the default). A *real* runner must never feed a
    placeholder to a live agent, so it passes ``strict=True`` and an unresolvable
    prompt raises :class:`PromptResolutionError` instead. ``run_task`` selects the
    mode via :attr:`HarnessRunner.requires_resolved_prompt`.
    """
    from coding_agent_playbook.renderer import build_environment, render_string

    prompt = _resolve_prompt(task)
    invocation = task.invocation.input_variables
    if prompt is None:
        if strict:
            raise PromptResolutionError(
                f"prompt_id {task.prompt_id!r} for task {task.id!r} resolved to no "
                "shipped prompt; a real runner cannot be driven with a placeholder. "
                "Check the task's prompt_id and that resources/prompts/ is reachable."
            )
        # No resolvable prompt: the deterministic scoring layers do not read the
        # rendered text, so emit a stable placeholder rather than failing.
        args = task.invocation.prompt_args
        return f"[prompt:{task.prompt_id}] {args}".strip()

    env = build_environment([], is_prompt_context=False)
    body = render_string(prompt.template_body, dict(invocation), env=env)
    args = task.invocation.prompt_args
    return f"{body}\n\n{args}".rstrip() if args else body


def _resolve_prompt(task: EvalTask):  # type: ignore[no-untyped-def]
    """Best-effort lookup of the :class:`Prompt` for ``task.prompt_id``.

    Scans the ``resources/prompts/`` directory that sits alongside the task's
    ``resources/eval_tasks/`` tree (engine or overlay) and returns the
    :class:`~coding_agent_playbook.types.Prompt` whose ``id`` matches
    ``task.prompt_id``. This deliberately reads the prompt markdown directly
    rather than through :class:`SyncContext` — resolution must work for the
    engine's own resources, which carry no ``.coding-agent-playbook.toml`` (that
    config only exists in a consumer repo). Returns ``None`` when the prompts
    directory cannot be located or no prompt matches (the caller falls back to a
    placeholder).
    """
    from coding_agent_playbook.types import Prompt

    prompts_dir = _infer_prompts_dir(task.source_path)
    if prompts_dir is None or not prompts_dir.is_dir():
        return None
    for entry in sorted(prompts_dir.iterdir()):
        name = entry.name
        if not entry.is_file() or not (name.endswith(".md") or name.endswith(".md.j2")):
            continue
        try:
            prompt = Prompt.from_markdown(entry, source_package=task.source_package)
        except (OSError, ValueError, KeyError):
            continue
        if prompt.frontmatter.id == task.prompt_id:
            return prompt
    return None


def _infer_prompts_dir(task_toml: Path) -> Path | None:
    """Locate the ``resources/prompts/`` dir sibling to the task's ``eval_tasks/``.

    A task lives at ``<…>/resources/eval_tasks/<id>/task.toml``; the prompts live
    at ``<…>/resources/prompts/``. Returns ``None`` when the path has no
    ``resources`` component (e.g. a synthetic test task).
    """
    parts = task_toml.resolve().parts
    if "resources" not in parts:
        return None
    idx = parts.index("resources")
    return Path(*parts[: idx + 1]) / "prompts"


def capture(scratch_dir: Path, baseline: Baseline, transcript: str) -> Candidate:
    """Capture the post-agent tree + ``git diff`` vs baseline + the transcript.

    ``git diff <baseline.commit>`` is taken over the scratch repo (after staging
    untracked files so newly-created files appear in the diff and in
    ``changed_files``). The diff string + transcript are retained for R2's judge;
    R1 scoring reads the tree (and ``changed_files``) directly.
    """
    scratch_dir = Path(scratch_dir)
    # Stage everything so new/untracked files participate in the diff.
    _git(scratch_dir, "add", "-A")
    diff = _git(scratch_dir, "diff", "--cached", baseline.commit).stdout
    name_only = _git(scratch_dir, "diff", "--cached", "--name-only", baseline.commit).stdout
    changed = [line for line in name_only.splitlines() if line.strip()]
    return Candidate(
        tree=scratch_dir,
        diff=diff,
        transcript=transcript,
        changed_files=changed,
    )


# --------------------------------------------------------------------------- #
# The runner ABC (template method)
# --------------------------------------------------------------------------- #


class HarnessRunner(ABC):
    """Invoke an agent for one task and grade the result (template method).

    Subclasses set the class attribute :attr:`name` (the
    ``coding_agent_playbook.runners`` entry-point key) and implement the single
    abstract hook :meth:`_invoke_agent`. :meth:`run_task` is concrete and fixed.

    :attr:`requires_resolved_prompt` controls prompt strictness in
    :func:`render_prompt`: the hermetic
    :class:`~coding_agent_playbook.evals.fake_runner.FakeRunner` leaves it ``False``
    (it tolerates the placeholder a synthetic test task yields), while a real
    runner like ``ClaudeCodeRunner`` sets it ``True`` so an unresolvable prompt
    raises :class:`PromptResolutionError` rather than driving a live agent with a
    placeholder.
    """

    name: str
    #: When True, ``run_task`` resolves the prompt strictly (raises on an
    #: unresolvable ``prompt_id``). Real runners set this; the FakeRunner does not.
    requires_resolved_prompt: bool = False

    def run_task(
        self,
        task: EvalTask,
        scratch_dir: Path,
        *,
        judge: JudgeLike | None = None,
        samples: int = 1,
        fail_fast: bool = True,
    ) -> TaskResult:
        """Run ``task`` in ``scratch_dir`` and return a graded :class:`TaskResult`.

        Pipeline: :func:`materialize` the ``setup/`` baseline → :func:`render_prompt`
        → :meth:`_invoke_agent` (the only per-assistant step) → :func:`capture`
        the candidate → :func:`~coding_agent_playbook.evals.scoring.score`.

        ``judge``/``samples`` are keyword-only with R1-compatible defaults: with no
        ``judge`` the report is deterministic-only (judged evaluators are skipped),
        exactly as R1. With a ``judge`` set, the task's ``[rubric]`` criteria are
        scored over the captured diff (averaged over ``samples``) and folded into
        the same report.

        ``fail_fast`` defaults to ``True`` — the cost-saving short-circuit: a lost
        deterministic gate skips the remaining costlier tiers (so a failing
        ``[expected]``/metric check spares the LLM judge). ``playbook eval``'s
        ``--full-scoring`` flag flips it off to grade every check unconditionally.
        """
        baseline = materialize(task, scratch_dir)
        prompt = render_prompt(task, strict=self.requires_resolved_prompt)
        started = monotonic()
        run = self._invoke_agent(prompt, scratch_dir)
        candidate = capture(scratch_dir, baseline, run.transcript)
        report = score(task, baseline, candidate, judge=judge, samples=samples, fail_fast=fail_fast)
        return TaskResult(
            task_id=task.id,
            harness=self.name,
            report=report,
            passed=report.passed,
            aggregate_score=(
                report.composite if report.composite is not None else float(report.passed)
            ),
            duration_seconds=monotonic() - started,
            transcript=run.transcript,
        )

    @abstractmethod
    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        """Drive the agent against ``scratch_dir`` and return its raw outcome.

        The only per-assistant step. Implementations mutate ``scratch_dir`` in
        place (the agent's working tree) and return an :class:`AgentRun` with the
        transcript and a return code.
        """
