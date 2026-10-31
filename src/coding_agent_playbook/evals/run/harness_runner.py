"""``HarnessRunner`` — execute one eval sample end-to-end and score it (PR R1).

This is the v1.1 activation of the former v2 placeholder (SPEC §15.3). A
:class:`HarnessRunner` runs a single :class:`~coding_agent_playbook.evals.sample.EvalSample`
against an agent and grades the result through the
:class:`~coding_agent_playbook.grading.metric.Metric` /
:class:`~coding_agent_playbook.grading.check.Check` /
:class:`~coding_agent_playbook.grading.rubric.Rubric` model, so the
*deterministic* scoring layers (``[expected]`` file checks + ``[metrics]``
static/execution metrics, including non-regression vs the ``setup/`` baseline)
are live. **Judged/rubric scoring is deferred to R2**: the runner sets no
``Judge`` on the :class:`EvalContext`, so judged checks report ``available() is
False`` and are skipped.

The class is a **template method**: :meth:`HarnessRunner.run_sample` owns the fixed
pipeline (materialize → render prompt → invoke agent → capture → score → assemble
a :class:`SampleResult`) and the only per-assistant step is the abstract
:meth:`_invoke_agent` hook. The hermetic default + unit-test driver is
:class:`~coding_agent_playbook.evals.run.fake_runner.FakeRunner`; the thin
``ClaudeCodeRunner`` ships in R1c. Discovery is via the
``coding_agent_playbook.runners`` entry-point group — never instantiate runners
directly.

The result model is **Option B** (SPEC §15.3, revised by the R1 brainstorm):
:class:`SampleResult` carries one :class:`EvaluationReport` rather than the inert
``programmatic_checks``/``rubric_scores`` placeholder fields, which had no
consumers. The old per-check placeholder is retired — a programmatic check is now
a BOOL :class:`~coding_agent_playbook.grading.types.ScopeDetail` row.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.run.git_env import without_repo_location
from coding_agent_playbook.evals.run.scoring import score
from coding_agent_playbook.evals.run.scoring_suite import require_suite_toolchain
from coding_agent_playbook.evals.run.setup_baseline import (
    prepare_setup_baseline,
    take_setup_snapshot,
)
from coding_agent_playbook.evals.token_usage import TokenUsage, sum_usage

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.evals.graded_source import GradedRecord
    from coding_agent_playbook.evals.run.setup_baseline import SetupBaseline, SetupSnapshot
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.grading.check import Check
    from coding_agent_playbook.grading.types import (
        CheckResult,
        EvaluationReport,
        JudgeLike,
        TrialResult,
    )
    from coding_agent_playbook.release.edition import Edition


# --------------------------------------------------------------------------- #
# Result types (Option B)
# --------------------------------------------------------------------------- #


@dataclass
class AgentRun:
    """The raw outcome of one agent invocation inside the scratch repo.

    ``returncode`` is ``0`` when the agent loop completed; ``transcript`` is the
    captured conversation/log (the judge's ``artifact`` in R2). ``reported_model``
    is the model id the harness says it ran, when its output reports one, and
    ``usage`` its token counts (``None`` when the harness reports none).
    """

    transcript: str
    returncode: int
    reported_model: str | None = None
    usage: TokenUsage | None = None


#: The return code a run stopped at its timeout records, as ``timeout(1)`` exits.
TIMED_OUT_RETURNCODE: Final = 124


def timed_out_run(exc: subprocess.TimeoutExpired, redact: Callable[[str], str]) -> AgentRun:
    """The :class:`AgentRun` of an agent stopped at its timeout: its partial output and a note.

    The partial output goes through ``redact`` (the runner's endpoint secrets), as
    a finished run's transcript does.

    Example::

        >>> exc = subprocess.TimeoutExpired(["agent"], 600, output=b"half an answer")
        >>> run = timed_out_run(exc, str)
        >>> run.returncode, run.transcript
        (124, 'half an answer\\n[the agent was stopped at its 600 s timeout]')
    """
    partial = with_stderr(_decoded(exc.stdout), _decoded(exc.stderr))
    note = f"[the agent was stopped at its {exc.timeout:g} s timeout]"
    transcript = f"{partial}\n{note}" if partial else note
    return AgentRun(transcript=redact(transcript), returncode=TIMED_OUT_RETURNCODE)


def with_stderr(answer: str, stderr: str) -> str:
    """``answer`` then the CLI's ``stderr`` on a line of its own, when there is any.

    Why the line break: the answer's last line is often a verdict that a sample's
    ``answer_matches`` regex anchors with ``$``. Claude Code prints a warning to
    stderr on every run with a non-Anthropic model
    (``[claude-code:unrecognized_model] {...}``), and glued onto ``approve`` it
    failed every review sample's gate on the Qwen record of 2026-10-29.

    Example::

        >>> with_stderr("approve", "[warning]\\n")
        'approve\\n[warning]\\n'
        >>> with_stderr("", "boom"), with_stderr("done\\n", "boom")
        ('boom', 'done\\nboom')
    """
    if not stderr:
        return answer
    if not answer:
        return stderr
    return answer + stderr if answer.endswith("\n") else f"{answer}\n{stderr}"


def _decoded(stream: bytes | str | None) -> str:
    """A partial stream as text: ``TimeoutExpired`` carries bytes even in text mode."""
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode("utf-8", errors="replace")


@dataclass
class _Trial:
    """One trial's graded :class:`TrialResult` + its raw transcript (internal).

    The runner collects these per trial; only the first trial's ``transcript``
    surfaces on the assembled :class:`SampleResult` (a representative log).
    """

    result: TrialResult
    transcript: str
    reported_model: str | None = None
    usage: TokenUsage | None = None


@dataclass
class SampleResult:
    """Per-sample outcome: the unified evaluation report + convenience aggregates.

    ``report`` is a **representative** :class:`EvaluationReport` (the first trial's)
    covering the ``[gate]`` / ``[rubric]`` layers. ``passed`` is the **sample**
    verdict: the single trial's verdict for a non-aggregate sample (``N=1``), or the
    ``[aggregate]`` layer's pass/fail when the sample aggregates across trials —
    unless that layer is skipped (its ``over`` axis never ran, e.g. ``over =
    "rubric"`` with no judge), when it passes only if every trial passed.
    ``aggregate_score`` mirrors ``report.composite`` for a single-trial sample, the
    aggregate check's ``0-1`` reliability score when aggregating, and the trial
    pass rate when the aggregate is skipped.

    ``trials`` carries every per-trial
    :class:`~coding_agent_playbook.grading.types.TrialResult` (one for ``N=1``);
    ``aggregate`` is the graded ``[aggregate]`` :class:`CheckResult` (``None`` when
    the sample has no ``[aggregate]`` block).

    ``target`` is the Eval target's name (``playbook eval`` sets it; ``None`` when
    a runner is driven directly), ``requested_model`` the model the runner sent
    to its harness (``None``: the harness default) and ``reported_model`` the
    model id the harness reported for the first trial, when it reports one.
    ``endpoint`` and ``endpoint_fingerprint`` name the target's endpoint and a
    digest of its URL (never the URL); ``None`` when the run used the harness's
    personal settings.
    ``usage`` is the token usage summed over every trial (``None`` when any
    trial's harness reported none).
    ``graded`` records what the run graded (an edition or the current text, with
    digests; ``playbook eval`` sets it, #281 ticket 09).
    """

    sample_id: str
    harness: str
    report: EvaluationReport
    passed: bool
    aggregate_score: float
    duration_seconds: float
    transcript: str
    trials: list[TrialResult] = field(default_factory=list)
    aggregate: CheckResult | None = None
    target: str | None = None
    requested_model: str | None = None
    reported_model: str | None = None
    endpoint: str | None = None
    endpoint_fingerprint: str | None = None
    usage: TokenUsage | None = None
    graded: GradedRecord | None = None


@dataclass
class EvalReport:
    """Aggregate over several :class:`SampleResult`\\ s for one harness.

    ``aggregate_pass_rate`` is the mean of ``result.passed`` across ``sample_results``
    (``0.0`` for an empty run).
    """

    engine_version: str
    harness: str
    sample_results: list[SampleResult]
    aggregate_pass_rate: float
    timestamp: str

    @staticmethod
    def pass_rate(sample_results: list[SampleResult]) -> float:
        """Mean of ``result.passed`` over ``sample_results`` (``0.0`` when empty)."""
        if not sample_results:
            return 0.0
        return sum(1 for result in sample_results if result.passed) / len(sample_results)


# --------------------------------------------------------------------------- #
# Orchestration handles
# --------------------------------------------------------------------------- #


@dataclass
class Baseline:
    """The materialized ``setup/`` state — the non-regression reference.

    ``repo_root`` is the git-init'd scratch repo (the agent edits this in place);
    ``commit`` is the baseline commit ref. Scoring never compares against this
    repo: its reference is the sample's ``setup/`` as the engine read it into
    memory before any agent ran
    (:class:`~coding_agent_playbook.evals.run.setup_baseline.SetupBaseline`). Why: a
    copy beside the agent's cwd was writable by the agent, so editing it too
    passed ``file_unchanged`` and a planted ``conftest.py`` broke the baseline suite.
    """

    repo_root: Path
    commit: str


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


#: ``git diff`` of the staged tree, one unquoted NUL-terminated path per change,
#: a rename listed as its deletion and its addition (see :func:`_changed_paths`).
_CHANGED_PATHS_ARGS = (
    "-c",
    "core.quotepath=false",
    "diff",
    "--cached",
    "--name-only",
    "--no-renames",
    "-z",
)


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``git`` in ``repo_root`` with a pinned hermetic identity.

    The inherited ``GIT_DIR``/``GIT_INDEX_FILE`` and the other repo-location
    variables are dropped: inside a hook in a linked worktree git exports them,
    and the scratch repo would otherwise be the caller's gitdir and index.
    """
    return subprocess.run(
        ["git", *_GIT_ENV_ARGS, *args],
        cwd=repo_root,
        env=without_repo_location(os.environ),
        capture_output=True,
        text=True,
        check=True,
    )


# --------------------------------------------------------------------------- #
# Orchestration helpers
# --------------------------------------------------------------------------- #


def materialize(
    sample: EvalSample, scratch_dir: Path, *, snapshot: SetupSnapshot | None = None
) -> Baseline:
    """Write the sample's ``setup/`` into ``scratch_dir``, install deps, commit baseline.

    The ``setup/`` files come from ``snapshot``, the runner's per-sample
    :class:`~coding_agent_playbook.evals.run.setup_baseline.SetupSnapshot` read
    before any agent ran (default: one read now from the catalog), so every trial
    starts from the same bytes even if the catalog changed meanwhile. They are
    written into ``scratch_dir`` (which becomes the agent's working tree). When
    that tree carries a ``pyproject.toml`` :func:`_uv_sync_scratch` shells out to ``uv
    sync`` (``--frozen`` if a ``uv.lock`` is present) so the agent and the
    execution evaluators see a real installed environment — the canonical Python
    project metadata lives in ``setup/pyproject.toml``, not in ``sample.toml``.
    The scratch repo is then ``git init``'d and the initial state committed so
    :func:`capture` can ``git diff`` against it. No second copy of ``setup/`` is
    made here: scoring grades against the snapshot, never against a tree the agent
    can edit.

    A sample whose ``setup/`` directory is missing yields an empty baseline repo —
    the runner still works, the static/execution layers simply have nothing to
    measure. A ``setup/`` with no ``pyproject.toml`` (a deps-less fixture) skips
    the ``uv sync`` step entirely; ``uv`` is only required when a pyproject is
    present.
    """
    scratch_dir = Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    snapshot = take_setup_snapshot(sample.setup_dir) if snapshot is None else snapshot
    snapshot.write_tree(scratch_dir)

    _uv_sync_scratch(scratch_dir)

    _git(scratch_dir, "init", "-q")
    _git(scratch_dir, "add", "-A")
    _git(scratch_dir, "commit", "-q", "--allow-empty", "-m", "setup baseline")
    commit = _git(scratch_dir, "rev-parse", "HEAD").stdout.strip()

    return Baseline(repo_root=scratch_dir, commit=commit)


def _uv_sync_scratch(scratch_dir: Path) -> None:
    """Install the scratch tree's ``pyproject.toml`` deps via ``uv sync``.

    No-op when the tree has no ``pyproject.toml`` (a deps-less fixture; the
    ``uv`` binary is not required in that case). When a pyproject exists,
    ``uv`` must be on ``PATH`` — raises a clear :exc:`RuntimeError` otherwise.
    Uses ``uv sync --frozen`` if a ``uv.lock`` is present; falls back to
    ``uv sync`` to resolve and lock on the fly when it is not (the default for
    fixtures that ship without a lockfile).

    Stdlib only (``subprocess`` / ``shutil``) — ``uv`` stays a shell-out, the
    same shape as the existing ``claude`` / ``opencode`` CLI runners. The
    caller decides where to invoke this (the scratch repo and the baseline
    snapshot both need it; see :func:`materialize`).
    """
    pyproject = scratch_dir / "pyproject.toml"
    if not pyproject.is_file():
        return
    if shutil.which("uv") is None:
        raise RuntimeError(
            "uv binary required to materialize setup/pyproject.toml; install uv on PATH"
        )
    args = ["uv", "sync", "--frozen"] if (scratch_dir / "uv.lock").is_file() else ["uv", "sync"]
    result = subprocess.run(args, cwd=scratch_dir, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"uv sync failed in {scratch_dir}: {result.stderr}")


def capture(
    scratch_dir: Path,
    baseline: Baseline,
    transcript: str,
    *,
    redact: Callable[[str], str] | None = None,
) -> Candidate:
    """Capture the post-agent tree + ``git diff`` vs baseline + the transcript.

    ``git diff <baseline.commit>`` is taken over the scratch repo (after staging
    untracked files so newly-created files appear in the diff and in
    ``changed_files``). The diff string + transcript are retained for R2's judge;
    R1 scoring reads the tree (and ``changed_files``) directly. ``redact`` (the
    runner's endpoint redaction) is applied to the diff, so a token an agent wrote
    into a file never reaches the judge's argv.
    """
    scratch_dir = Path(scratch_dir)
    # Stage everything so new/untracked files participate in the diff.
    _git(scratch_dir, "add", "-A")
    diff = _git(scratch_dir, "diff", "--cached", baseline.commit).stdout
    return Candidate(
        tree=scratch_dir,
        diff=diff if redact is None else redact(diff),
        transcript=transcript,
        changed_files=_changed_paths(scratch_dir, baseline.commit),
    )


def _changed_paths(scratch_dir: Path, commit: str) -> list[str]:
    """Every path the staged tree changed against ``commit``, both sides of a rename included.

    Why ``--no-renames``: git pairs a move or a delete-plus-similar-file as a rename
    and lists only the new path, so the old setup/ test file read as untouched and
    suite integrity rule 1 failed an honest move. Why ``-z`` and UTF-8: git quotes
    and octal-escapes a non-ASCII path otherwise, so it never matched the session
    record's path. ``surrogateescape`` keeps an undecodable name a usable path.
    """
    raw = subprocess.run(
        ["git", *_GIT_ENV_ARGS, *_CHANGED_PATHS_ARGS, commit],
        cwd=scratch_dir,
        env=without_repo_location(os.environ),
        capture_output=True,
        check=True,
    ).stdout
    return [path for path in raw.decode("utf-8", "surrogateescape").split("\0") if path]


def _grade_aggregate(
    aggregate: Check, trials: list[TrialResult]
) -> tuple[CheckResult, bool, float]:
    """Grade the ``[aggregate]`` layer: ``(result, sample verdict, sample score)``.

    The compiled check grades over an :class:`EvalContext` carrying the trials,
    and its ``passed``/``score`` become the sample verdict / score. When the axis it
    reduces never ran in any trial (``over = "rubric"`` with no judge) the layer
    is skipped — neutral — so the sample falls back to the trials' own verdicts:
    it passes only if every trial passed, scored by the trial pass rate.
    """
    from coding_agent_playbook.grading.check import MeasurementSet
    from coding_agent_playbook.grading.scheduler import skipped_result
    from coding_agent_playbook.grading.types import EvalContext

    agg_ctx = EvalContext(module=None, source="", label="aggregate", trials=trials)
    if not aggregate.available(agg_ctx):
        verdicts = [t.verdict for t in trials]
        return skipped_result(aggregate), all(verdicts), sum(verdicts) / len(verdicts)
    result = aggregate.grade(agg_ctx, MeasurementSet([], None))
    score = result.score if result.score is not None else float(result.passed)
    return result, result.passed, score


# --------------------------------------------------------------------------- #
# The runner ABC (template method)
# --------------------------------------------------------------------------- #


class HarnessRunner(ABC):
    """Invoke an agent for one sample and grade the result (template method).

    Subclasses set the class attribute :attr:`name` (the
    ``coding_agent_playbook.runners`` entry-point key) and implement the single
    abstract hook :meth:`_invoke_agent`. :meth:`run_sample` is concrete and fixed.

    :attr:`requires_resolved_prompt` controls prompt strictness in
    :func:`render_prompt`: the hermetic
    :class:`~coding_agent_playbook.evals.run.fake_runner.FakeRunner` leaves it ``False``
    (it tolerates the placeholder a synthetic test sample yields), while a real
    runner like ``ClaudeCodeRunner`` sets it ``True`` so an unresolvable prompt
    raises :class:`PromptResolutionError` rather than driving a live agent with a
    placeholder.
    """

    name: str
    #: The executable a real runner drives (its ``--version`` names the harness
    #: version in release metrics); ``None`` for a runner with no CLI.
    cli: str | None = None
    #: Whether the constructor takes ``model=`` (an Eval target's model). The
    #: CLI runners do; a runner that does not is refused for a target with a model.
    accepts_model: bool = False
    #: Whether the constructor takes ``route=`` (an Eval target's endpoint wiring).
    #: A runner that does not is refused for a target with an endpoint.
    accepts_endpoint: bool = False
    #: The model sent to the harness; ``None`` leaves it on its own default.
    model: str | None = None
    #: When True, ``run_sample`` resolves the prompt strictly (raises on an
    #: unresolvable ``prompt_id``). Real runners set this; the FakeRunner does not.
    requires_resolved_prompt: bool = False

    def run_sample(
        self,
        sample: EvalSample,
        scratch_dir: Path,
        *,
        judge: JudgeLike | None = None,
        judge_samples: int = 1,
        fail_fast: bool = True,
        edition: Edition | None = None,
    ) -> SampleResult:
        """Run ``sample`` over ``N`` trials in ``scratch_dir`` and grade a :class:`SampleResult`.

        ``N`` is :attr:`~coding_agent_playbook.evals.compile.compiler.CompiledSample.trials_needed`
        — **1** for a sample with no ``[aggregate]`` block (the single-trial default;
        this path is one ``materialize → render → invoke → capture → score``), and
        ``max(k)`` over the aggregate handles otherwise.

        Each trial runs the fixed per-trial pipeline in its **own** scratch subdir
        (a fresh ``setup/`` materialization, so the agent never inherits a prior
        trial's edits): :func:`materialize` → :meth:`_invoke_agent` (the only
        per-assistant step) → :func:`capture` →
        :func:`~coding_agent_playbook.evals.run.scoring.score`. Each yields a
        :class:`~coding_agent_playbook.grading.types.TrialResult` (the per-trial
        report + its derived verdict). The prompt is resolved **once** up front
        (identical across trials) via :func:`render_prompt` — so a real runner's
        strict resolution still raises :class:`PromptResolutionError` before any
        trial runs. It renders the current text by default; ``edition`` renders a pinned sample's frozen edition instead (#281 ticket 09).

        With an ``[aggregate]`` layer the sample verdict is that layer's pass/fail —
        the :class:`~coding_agent_playbook.evals.checks.aggregate.AggregateCheck`\\ s
        reduce the trials' selected ``over`` axis (``gate`` / ``rubric`` /
        ``verdict``) into a ``pass@k`` / ``pass^k`` reliability score; if that layer
        is skipped, the sample verdict falls back to every trial passing, scored by
        the trial pass rate (see :func:`_grade_aggregate`). Without one the sample
        verdict is the single trial's verdict.

        ``judge``/``judge_samples`` are keyword-only with R1-compatible defaults: with no
        ``judge`` each trial's report is deterministic-only (judged evaluators are
        skipped). ``fail_fast`` defaults to ``True`` — the per-trial scheduler's
        cost-saving short-circuit; ``--full-scoring`` flips it off, and
        :func:`~coding_agent_playbook.evals.run.scoring.score` ignores it for a sample
        whose result it could change
        (:attr:`~coding_agent_playbook.evals.compile.compiler.CompiledSample.short_circuit_safe`).
        """
        from coding_agent_playbook.evals.sample import compile_eval_sample

        scratch_dir = Path(scratch_dir)
        started = monotonic()
        # Resolve the prompt first (identical across trials) so a real runner's
        # strict resolution raises before any trial.
        prompt = render_prompt(sample, strict=self.requires_resolved_prompt, edition=edition)
        compiled = compile_eval_sample(sample)
        # Before any agent runs: a scoring interpreter without pytest-cov would
        # otherwise surface only after a paid agent run, at the first trial's score.
        require_suite_toolchain(compiled.per_trial)
        # Once, before any agent runs: setup/ read into memory and measured here is
        # what every trial starts from and is graded against (see setup_baseline).
        setup_baseline = prepare_setup_baseline(sample)
        n = compiled.trials_needed

        trials: list[TrialResult] = []
        usages: list[TokenUsage | None] = []
        first: _Trial | None = None
        for i in range(n):
            # Each trial gets its own scratch subdir so a fresh setup/ is
            # materialized per trial (the N=1 case reuses ``scratch_dir`` exactly,
            # so the single-trial on-disk layout is unchanged).
            trial_dir = scratch_dir if n == 1 else scratch_dir / f"trial-{i}"
            trial = self._run_trial(
                sample,
                prompt,
                trial_dir,
                setup_baseline,
                judge=judge,
                judge_samples=judge_samples,
                fail_fast=fail_fast,
            )
            trials.append(trial.result)
            usages.append(trial.usage)
            if first is None:
                first = trial

        assert first is not None  # trials_needed is always >= 1
        result = self._assemble(sample, compiled.aggregate, trials, first, started)
        result.usage = sum_usage(usages)
        return result

    def _run_trial(
        self,
        sample: EvalSample,
        prompt: str,
        trial_dir: Path,
        setup_baseline: SetupBaseline,
        *,
        judge: JudgeLike | None,
        judge_samples: int,
        fail_fast: bool,
    ) -> _Trial:
        """Run one trial's fixed pipeline and grade it into a :class:`_Trial`.

        :func:`materialize` the ``setup/`` snapshot of ``setup_baseline`` →
        :meth:`_invoke_agent` (with the pre-resolved ``prompt``) → :func:`capture` →
        :func:`score` against ``setup_baseline``, then derive
        the per-trial :class:`~coding_agent_playbook.grading.types.TrialResult`
        (``verdict = report.passed``, the skipped-neutral gate/rubric verdict the
        scorer already wrote).
        """
        from coding_agent_playbook.grading.types import TrialResult

        baseline = materialize(sample, trial_dir, snapshot=setup_baseline.snapshot)
        run = self._invoke_bounded(prompt, trial_dir)
        candidate = capture(trial_dir, baseline, run.transcript, redact=self._redact)
        report = score(
            sample,
            setup_baseline,
            candidate,
            judge=judge,
            judge_samples=judge_samples,
            fail_fast=fail_fast,
        )
        return _Trial(
            result=TrialResult(report=report, verdict=report.passed),
            transcript=run.transcript,
            reported_model=run.reported_model,
            usage=run.usage,
        )

    def _invoke_bounded(self, prompt: str, trial_dir: Path) -> AgentRun:
        """:meth:`_invoke_agent`, with a run stopped at its timeout kept as a scored trial.

        Why: a CLI runner's ``subprocess.run(..., timeout=...)`` raises
        ``TimeoutExpired``, and one stuck agent then aborted a whole
        ``eval --run --all --record`` with no metrics written (the first v0.4.0
        release eval). The trial is graded on the tree and partial transcript the
        agent left, like any other.
        """
        try:
            return self._invoke_agent(prompt, trial_dir)
        except subprocess.TimeoutExpired as exc:
            return timed_out_run(exc, self._redact)

    def _assemble(
        self,
        sample: EvalSample,
        aggregate: Check | None,
        trials: list[TrialResult],
        first: _Trial,
        started: float,
    ) -> SampleResult:
        """Fold the trials (+ optional aggregate) into one :class:`SampleResult`.

        With ``aggregate is None`` (the single-trial default) the sample verdict
        is ``trials[0].verdict`` and the score is the representative report's
        composite (falling back to ``0.0``/``1.0``). With an ``[aggregate]`` layer
        see :func:`_grade_aggregate`.
        """
        report = trials[0].report
        agg_result: CheckResult | None = None
        if aggregate is None:
            passed = trials[0].verdict
            aggregate_score = report.composite if report.composite is not None else float(passed)
        else:
            agg_result, passed, aggregate_score = _grade_aggregate(aggregate, trials)

        return SampleResult(
            sample_id=sample.id,
            harness=self.name,
            report=report,
            passed=passed,
            aggregate_score=aggregate_score,
            duration_seconds=monotonic() - started,
            transcript=first.transcript,
            trials=trials,
            aggregate=agg_result,
            requested_model=self.model,
            reported_model=first.reported_model,
        )

    def probe(self, prompt: str, scratch_dir: Path) -> AgentRun:
        """One agent turn on ``prompt`` in ``scratch_dir``, ungraded (``eval --targets --check``).

        Example::

            >>> FakeRunner().probe("Reply OK.", Path("/tmp/x")).returncode  # doctest: +SKIP
            0
        """
        return self._invoke_agent(prompt, scratch_dir)

    def _redact(self, text: str) -> str:
        """``text`` with the endpoint's secrets replaced; unchanged here (no endpoint).

        A runner with an endpoint route overrides it; the graded diff goes through it.
        """
        return text

    @abstractmethod
    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        """Drive the agent against ``scratch_dir`` and return its raw outcome.

        The only per-assistant step. Implementations mutate ``scratch_dir`` in
        place (the agent's working tree) and return an :class:`AgentRun` with the
        transcript and a return code.
        """
