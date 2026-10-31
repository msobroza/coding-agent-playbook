"""``playbook eval --run --all --runs N --record <path>``: write one release metrics file (ticket 07).

Every eval sample (or the one ``<id>`` names) runs ``N`` times on one Eval
target (``--runs``, else the target's ``runs``, else 1), and the results are
written as a release metrics file, schema version 1
(``evals.release_metrics_schema``). Before any paid run, ``--record`` refuses a
target without an explicit model, a moving model alias and, with ``--judge``,
an unpinned ``[evals.judge] model`` (``evals.model_pins``), ``--format``, and
a sample whose prompt cannot be resolved. ``--full-scoring`` grades every check,
as for ``--run``. A sample that cannot
be scored stops the recording, so a file never silently lacks a sample. Every
sample grades the current text (``samples``); a pinned sample also runs on its
edition as a control (``controls``, #281 ticket 15), whose edition is loaded and
rendered before any paid run too. Each entry records the inputs digest of that
pre-run render (#329 ticket 03). The
harness and the judge run isolated from the user's personal settings, so a
missing credential is refused before any paid run too, and the target block
records ``isolated`` (#329 ticket 02, ``evals.record_isolation``). The file
records its setup digest and parts (#329 ticket 04, ``evals.setup_digest``),
with the judge CLI's version probed once like the harness's.
``--carry-from PREVIOUS`` (with ``--all`` only, #329 ticket 05,
``evals.release_carry``) loads that baseline before any run, refusing one of
another target, or indexes the releases directory PREVIOUS
(``commands._eval_record_carry``), prints the plan (each rerun with its reason,
the carried count) before the first paid run, runs only new samples, samples whose inputs digest
changed and every edition control (every sample when the setup differs or the
baseline lacks the digests), and carries the other entries. A sample that only a
file of another judge holds is re-graded from its stored answers instead of
rerun (spec D9, ``commands._eval_record_rejudge``), and the new judge's agreement
with the old one is recorded (spec D10, ``commands._eval_record_agreement``). The
file is written whatever the scores are: exit ``0`` once it is written, ``2`` on
a refusal or an unscorable sample. Each finished sample is saved to a
checkpoint as it ends (``--checkpoint``, ``evals.record_checkpoint``), which
``--resume`` reuses; ``--jobs N`` runs N samples at a time
(``commands._eval_record_runs``). Each fresh run's answers are written beside the
file or to ``--answers`` (spec D8, ``commands._eval_record_answers``).
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import coding_agent_playbook
from coding_agent_playbook.commands._eval_options import (
    build_judge,
    build_target_runner,
    judge_sample_count,
    select_target,
)
from coding_agent_playbook.commands._eval_record_agreement import with_judge_change
from coding_agent_playbook.commands._eval_record_answers import (
    answers_out_path,
    capturing,
    stored_run,
    write_record_answers,
)
from coding_agent_playbook.commands._eval_record_carry import (
    load_carry_baseline,
    print_carry_plan,
)
from coding_agent_playbook.commands._eval_record_flags import (
    carry_from_path,
    job_count,
    record_path,
    refuse_format,
    run_count,
    selected_samples,
)

# Bound as ``_head_commit``: tests stub the commit stamp on this module.
from coding_agent_playbook.commands._eval_record_output import head_commit as _head_commit
from coding_agent_playbook.commands._eval_record_output import write_metrics
from coding_agent_playbook.commands._eval_record_rejudge import rejudge_units, rejudger
from coding_agent_playbook.commands._eval_record_runs import (
    RecordUnit,
    open_checkpoint,
    record_units,
)
from coding_agent_playbook.evals import registry
from coding_agent_playbook.evals.answers_store import judge_parts
from coding_agent_playbook.evals.graded_source import graded_source
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.model_pins import RecordRefusedError, check_recordable
from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.record_isolation import check_record_credentials
from coding_agent_playbook.evals.release_carry import CarryPlan, merge_carried
from coding_agent_playbook.evals.release_metrics import (
    GRADED_HEAD,
    RecordedTarget,
    SampleRecord,
    SampleRuns,
    build_release_metrics_from_records,
    sample_record,
)
from coding_agent_playbook.evals.release_metrics_schema import validate_release_metrics
from coding_agent_playbook.evals.run.harness_version import harness_cli_version
from coding_agent_playbook.evals.run.scoring_suite import UnscorableSuiteError
from coding_agent_playbook.evals.sample_digest import inputs_digest, prompt_digest, sample_digest
from coding_agent_playbook.evals.setup_digest import UNKNOWN_VERSION, SetupParts, scoring_digest
from coding_agent_playbook.release.edition import EditionError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.evals.answers_store import CapturingJudge
    from coding_agent_playbook.evals.endpoints import Endpoint
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.record_checkpoint import (
        RecordCheckpoint,
    )
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner, SampleResult
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.evals.targets import EvalSettings, EvalTarget
    from coding_agent_playbook.release.edition import Edition


def run_record(args: argparse.Namespace, repo_root: Path, settings: EvalSettings) -> int:
    """Run the samples on the target and write the release metrics file; see the module doc.

    Example::

        >>> run_record(args, Path("."), load_eval_settings(Path(".")))  # doctest: +SKIP
        0
    """
    out_path = record_path(args)
    refuse_format(args)
    carry_from = carry_from_path(args)
    target = select_target(args, settings)
    baseline = load_carry_baseline(carry_from, target_name=target.name, out_path=out_path)
    runs = run_count(getattr(args, "runs", None), target.runs)
    jobs = job_count(getattr(args, "jobs", None))
    uses_judge = getattr(args, "judge", None) is not None
    check_recordable(target, judge_model=settings.judge.model, uses_judge=uses_judge)
    isolated = _check_credentials(target, settings, getattr(args, "judge", None))
    samples = selected_samples(args, repo_root)
    plan = _build_plan(args, settings, target, runs)
    if plan is None:
        return 2
    inputs = plan.check_prompts(samples)
    controls = plan.control_editions(samples)
    judge_model = settings.judge.model if uses_judge else None
    recorded = plan.recorded_target(target, judge_model=judge_model, isolated=isolated)
    carry = print_carry_plan(baseline, recorded, inputs, controls, samples)
    checkpoint = open_checkpoint(args, out_path, recorded)
    work = _RecordWork(plan, recorded, jobs, checkpoint, answers_out_path(args, out_path))
    metrics = _record_metrics(work, samples, inputs, controls, carry, repo_root)
    validate_release_metrics(metrics)
    write_metrics(out_path, metrics)
    checkpoint.remove()
    extra = f" (+{len(controls)} edition controls)" if controls else ""
    jobs_note = f" on {jobs} jobs" if jobs > 1 else ""
    rejudged = f", {len(carry.rejudge)} rejudged" if carry is not None and carry.rejudge else ""
    counts = "" if carry is None else f"{len(carry.rerun)} rerun, {len(carry.carried)} carried"
    carried = f" ({counts}{rejudged})" if counts else ""
    print(
        f"recorded {len(samples)} samples{carried}{extra} x {runs} runs on target "
        f"{target.name!r}{jobs_note} to {out_path}"
    )
    return 0


@dataclass(frozen=True)
class _RecordWork:
    """What runs each unit: the plan, the target block, ``--jobs``, the checkpoint, the answers."""

    plan: _RecordPlan
    recorded: RecordedTarget
    jobs: int
    checkpoint: RecordCheckpoint
    answers: Path


def _record_metrics(
    work: _RecordWork,
    samples: list[EvalSample],
    inputs: Mapping[str, str],
    controls: Mapping[str, _Control],
    carry: CarryPlan | None,
    repo_root: Path,
) -> dict[str, object]:
    """Run what reruns (every sample without ``carry``) and build the file; carry the rest."""
    units = [
        RecordUnit("sample", sample, index, inputs[sample.id])
        for index, sample in enumerate(samples)
        if carry is None or carry.reruns(sample.id)
    ]
    units += [
        RecordUnit("control", sample, index, control.inputs_digest, control.edition)
        for index, sample in enumerate(samples)
        if (control := controls.get(sample.id)) is not None
    ]
    units += rejudge_units(samples, inputs, carry)
    run = _unit_runner(work, len(samples), carry)
    records = record_units(units, jobs=work.jobs, run=run, checkpoint=work.checkpoint)
    fresh = [records[unit.key] for unit in units if unit.kind == "sample"]
    rejudged = [records[unit.key] for unit in units if unit.kind == "rejudge"]
    write_record_answers(work.answers, [*fresh, *rejudged])
    metrics = build_release_metrics_from_records(
        release=coding_agent_playbook.__version__,
        commit=_head_commit(repo_root),
        recorded=work.recorded,
        samples=fresh,
        controls=[records[unit.key] for unit in units if unit.kind == "control"],
    )
    if carry is None:
        return metrics
    merged = merge_carried(metrics, carry, {record.sample_id: record.entry for record in rejudged})
    return with_judge_change(merged, carry, rejudged, samples, judge_parts(work.recorded.setup))


def _unit_runner(
    work: _RecordWork, total: int, carry: CarryPlan | None
) -> Callable[[RecordUnit], SampleRecord]:
    """Run one unit's ``runs`` and fold them into its record; re-grade a ``rejudge`` unit."""
    price = work.recorded.target.price
    parts = judge_parts(work.recorded.setup)
    plan = work.plan
    regrade = rejudger(plan.judge, judge_samples=plan.judge_samples, parts=parts, carry=carry)

    def run(unit: RecordUnit) -> SampleRecord:
        if regrade is not None and unit.kind == "rejudge":
            return regrade(unit)
        runs = work.plan.run(
            unit.sample, unit.index, total, unit.inputs_digest, edition=unit.edition, parts=parts
        )
        return sample_record(runs, price)

    return run


def _build_plan(
    args: argparse.Namespace, settings: EvalSettings, target: EvalTarget, runs: int
) -> _RecordPlan | None:
    """The runner, judge and judge sample count of the run; ``None`` after an error line.

    Both are built isolated from the user's personal settings (#329 ticket 02).
    """
    runner = build_target_runner(target, isolated=True)
    judge_name = getattr(args, "judge", None)
    judge = (
        build_judge(judge_name, settings.judge, isolated=True) if judge_name is not None else None
    )
    judge_samples = judge_sample_count(args, default=settings.judge.samples or 1)
    if runner is None or (judge_name is not None and judge is None) or judge_samples is None:
        return None
    fail_fast = not getattr(args, "full_scoring", False)
    judged = judge is not None
    judge_endpoint = settings.judge.endpoint if judged else None
    effort = settings.judge.reasoning_effort if judged else None
    return _RecordPlan(runner, judge, judge_samples, runs, fail_fast, judge_endpoint, effort)


def _check_credentials(target: EvalTarget, settings: EvalSettings, judge_name: str | None) -> bool:
    """Refuse before any paid call when an isolated harness or judge has no credential.

    A runner or judge that takes an endpoint route is a CLI that runs isolated
    under ``--record``; the fake runner, or no judge, needs no credential.
    Returns whether the whole run is isolated (:func:`_ran_isolated`), from the
    same classes, so the recorded flag and the check stay in step.
    """
    runner_cls = registry.load_runner_class(target.harness)
    judge_cls = registry.load_judge_class(judge_name) if judge_name is not None else None
    check_record_credentials(
        target_endpoint=target.endpoint,
        judge_endpoint=settings.judge.endpoint,
        harness_isolated=runner_cls is not None and runner_cls.accepts_endpoint,
        judge_isolated=judge_cls is not None and judge_cls.accepts_endpoint,
        env=os.environ,
    )
    return _ran_isolated(runner_cls, judge_cls)


def _ran_isolated(runner_cls: type[HarnessRunner] | None, judge_cls: type[Judge] | None) -> bool:
    """Whether a record run with these classes ran isolated from personal settings.

    A runner without a CLI (the fake) has nothing to isolate; a CLI runner or a
    judge is isolated only when it takes a route (``accepts_endpoint``).

    Example::

        >>> _ran_isolated(None, None)
        True
    """
    runner_ok = runner_cls is None or runner_cls.cli is None or runner_cls.accepts_endpoint
    return runner_ok and (judge_cls is None or judge_cls.accepts_endpoint)


@dataclass(frozen=True)
class _Control:
    """A pinned sample's control: its edition and the inputs digest of the edition's render."""

    edition: Edition
    inputs_digest: str


@dataclass(frozen=True)
class _RecordPlan:
    """How each sample runs: the runner, the judge, the run count and fail-fast.

    ``fail_fast`` is ``False`` under ``--full-scoring``, as for ``eval --run``.
    """

    runner: HarnessRunner
    judge: Judge | None
    judge_samples: int
    runs: int
    fail_fast: bool = True
    #: ``[evals.judge] endpoint``, set only when the run has a judge.
    judge_endpoint: Endpoint | None = None
    #: ``[evals.judge] reasoning_effort``, set only when the run has a judge.
    judge_reasoning_effort: str | None = None

    def recorded_target(
        self, target: EvalTarget, *, judge_model: str | None, isolated: bool
    ) -> RecordedTarget:
        """The target block's facts and the setup parts (#329 ticket 04) of this run.

        The harness and judge CLIs' versions are probed once each (once in all
        when both are the same CLI), time-bounded; a failed probe is ``None`` in
        the target block and :data:`UNKNOWN_VERSION` in the setup parts.
        """
        judge_cli = self.judge.cli if self.judge is not None else None
        versions = _cli_versions(self.runner.cli, judge_cli)
        recorded = RecordedTarget(
            target=target,
            harness_version=versions[self.runner.cli],
            judge_model=judge_model,
            runs=self.runs,
            isolated=isolated,
        )
        judge_version = _setup_version(judge_cli, versions[judge_cli])
        return dataclasses.replace(recorded, setup=self._setup_parts(recorded, judge_version))

    def _setup_parts(self, recorded: RecordedTarget, judge_version: str | None) -> SetupParts:
        """Everything outside the samples that decides this run's scores, by name."""
        target = recorded.target
        judged = self.judge is not None
        return SetupParts(
            harness=target.harness,
            harness_version=_setup_version(self.runner.cli, recorded.harness_version),
            model=target.model,
            endpoint_fingerprint=_fingerprint(target.endpoint),
            small_model=target.small_model,
            runs=recorded.runs,
            judge_model=recorded.judge_model,
            judge_endpoint_fingerprint=_fingerprint(self.judge_endpoint) if judged else None,
            judge_samples=self.judge_samples if judged else None,
            judge_version=judge_version,
            fail_fast=self.fail_fast,
            isolated=recorded.isolated,
            scoring_digest=scoring_digest(),
            judge_reasoning_effort=self.judge_reasoning_effort if judged else None,
        )

    def check_prompts(self, samples: list[EvalSample]) -> dict[str, str]:
        """Render every sample's prompt before the first paid run; refuse on the first bad one.

        Returns each sample's inputs digest, by id, hashed from that one render (#329).
        """
        digests: dict[str, str] = {}
        for sample in samples:
            try:
                text = render_prompt(sample, strict=self.runner.requires_resolved_prompt)
            except PromptResolutionError as exc:
                raise RecordRefusedError(
                    f"sample {sample.id!r} has no prompt to run, so nothing was run: {exc}"
                ) from exc
            digests[sample.id] = inputs_digest(sample, text)
        return digests

    def control_editions(self, samples: list[EvalSample]) -> dict[str, _Control]:
        """Each pinned sample's control, its edition loaded and rendered before the first paid run."""
        controls: dict[str, _Control] = {}
        for sample in samples:
            if sample.edition is None:
                continue
            try:
                edition = graded_source(sample).edition
                assert edition is not None  # a pinned sample without head grades its edition
                strict = self.runner.requires_resolved_prompt
                text = render_prompt(sample, strict=strict, edition=edition)
            except (EditionError, PromptResolutionError) as exc:
                raise RecordRefusedError(
                    f"pinned sample {sample.id!r} cannot run on edition {sample.edition} as a "
                    f"control, so nothing was run: {exc}"
                ) from exc
            controls[sample.id] = _Control(edition, inputs_digest(sample, text))
        return controls

    def run(
        self,
        sample: EvalSample,
        index: int,
        total: int,
        inputs: str,
        *,
        edition: Edition | None = None,
        parts: Mapping[str, object] | None = None,
    ) -> SampleRuns:
        """``sample``'s runs and digests on the current text, or on ``edition`` as a control.

        ``inputs`` is the inputs digest of the render checked before the first run.
        A run on the current text keeps its answers, naming the judge ``parts``.

        Each run is reported on stderr as it ends.
        """
        label = sample.id if edition is None else f"{sample.id} (control, edition {edition.tag})"
        results, answers = [], []
        for run_index in range(self.runs):
            result, judge = self._run_once(sample, edition)
            verdict = "PASS" if result.passed else "FAIL"
            print(
                f"[{index + 1}/{total}] {label} run {run_index + 1}/{self.runs}: "
                f"{verdict} (score={result.aggregate_score:.3f})",
                file=sys.stderr,
            )
            results.append(result)
            if edition is None:  # an edition control keeps no answers (spec D8)
                answers.append(stored_run(sample, inputs, run_index, result, judge, parts or {}))
        return SampleRuns(
            sample_id=sample.id,
            prompt_id=sample.prompt_id,
            graded=GRADED_HEAD if edition is None else edition.tag,
            prompt_digest=prompt_digest(sample, edition=edition),
            sample_digest=sample_digest(sample),
            results=results,
            inputs_digest=inputs,
            answers=tuple(answers),
        )

    def _run_once(
        self, sample: EvalSample, edition: Edition | None
    ) -> tuple[SampleResult, CapturingJudge | None]:
        """One run, graded by its own capturing judge (never ``self.judge``, whose ``cli`` is read)."""
        judge = capturing(self.judge)
        try:
            with tempfile.TemporaryDirectory(prefix="playbook-record-") as tmp:
                result = self.runner.run_sample(
                    sample,
                    Path(tmp) / "scratch",
                    judge=judge,
                    judge_samples=self.judge_samples,
                    fail_fast=self.fail_fast,
                    edition=edition,
                )
        except (PromptResolutionError, JudgeError, UnscorableSuiteError) as exc:
            raise RecordRefusedError(
                f"sample {sample.id!r} could not be scored, so nothing was recorded: {exc}"
            ) from exc
        return result, judge


def _cli_versions(*clis: str | None) -> dict[str | None, str | None]:
    """Each distinct CLI's ``--version``, probed once; ``None`` (no CLI) maps to ``None``.

    Example::

        >>> _cli_versions(None)
        {None: None}
    """
    return {cli: harness_cli_version(cli) for cli in dict.fromkeys(clis)}


def _setup_version(cli: str | None, version: str | None) -> str | None:
    """A CLI's setup part: :data:`UNKNOWN_VERSION` when its probe failed, ``None`` without a CLI.

    Example::

        >>> _setup_version("claude", None), _setup_version(None, None), _setup_version("claude", "2")
        ('unknown', None, '2')
    """
    return UNKNOWN_VERSION if cli is not None and version is None else version


def _fingerprint(endpoint: Endpoint | None) -> str | None:
    """The endpoint's URL fingerprint, or ``None`` without an endpoint."""
    return endpoint.fingerprint if endpoint is not None else None
