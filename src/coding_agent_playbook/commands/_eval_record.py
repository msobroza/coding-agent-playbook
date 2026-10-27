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
another target, prints the plan (each rerun with its reason, the carried count)
before the first paid run, runs only new samples, samples whose inputs digest
changed and every edition control (every sample when the setup differs or the
baseline lacks the digests), and carries the other entries. The
file is written whatever the scores are: exit ``0`` once it is written, ``2`` on
a refusal or an unscorable sample.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import coding_agent_playbook
from coding_agent_playbook.commands._eval_options import (
    build_judge,
    build_target_runner,
    judge_sample_count,
    select_target,
)
from coding_agent_playbook.evals import registry
from coding_agent_playbook.evals.graded_source import graded_source
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.model_pins import RecordRefusedError, check_recordable
from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.record_isolation import check_record_credentials
from coding_agent_playbook.evals.release_carry import (
    CarryPlan,
    carry_plan_lines,
    load_baseline,
    merge_carried,
    plan_carry,
)
from coding_agent_playbook.evals.release_metrics import (
    GRADED_HEAD,
    RecordedTarget,
    SampleRuns,
    build_release_metrics,
)
from coding_agent_playbook.evals.release_metrics_schema import validate_release_metrics
from coding_agent_playbook.evals.run.git_env import without_repo_location
from coding_agent_playbook.evals.run.harness_version import harness_cli_version
from coding_agent_playbook.evals.sample_digest import inputs_digest, prompt_digest, sample_digest
from coding_agent_playbook.evals.setup_digest import UNKNOWN_VERSION, SetupParts, scoring_digest
from coding_agent_playbook.evals.task_registry import TaskRegistry, TaskRegistryError
from coding_agent_playbook.release.edition import EditionError
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping

    from coding_agent_playbook.evals.endpoints import Endpoint
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner, SampleResult
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.evals.targets import EvalSettings, EvalTarget
    from coding_agent_playbook.release.edition import Edition

#: Wall-clock bound (seconds) of the ``git rev-parse HEAD`` that names the commit.
_GIT_TIMEOUT: Final = 30.0


def configure_record(parser: argparse.ArgumentParser) -> None:
    """Declare ``--all``, ``--runs`` and ``--record`` on ``playbook eval``.

    Example::

        >>> configure_record(argparse.ArgumentParser())  # doctest: +SKIP
    """
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_samples",
        help="--record: run every eval sample (instead of the sample <id>)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        help="--record: runs per eval sample (default: the target's runs, else 1)",
    )
    parser.add_argument(
        "--record",
        metavar="PATH",
        help="with --run: write the release metrics file (schema version 1) of the "
        "samples on one target to PATH; refuses unpinned models",
    )
    parser.add_argument(
        "--carry-from",
        metavar="PREVIOUS",
        dest="carry_from",
        help="--record --all: rerun only new samples, samples whose inputs changed and "
        "edition controls, copying the other entries from the metrics file PREVIOUS of "
        "the same target; a different setup reruns everything",
    )


def wants_record(args: argparse.Namespace) -> bool:
    """Whether ``args`` ask for a recording (``--record``, ``--all``, ``--runs`` or ``--carry-from``)."""
    flags = (
        getattr(args, "record", None),
        getattr(args, "runs", None),
        getattr(args, "carry_from", None),
    )
    return getattr(args, "all_samples", False) or any(flag is not None for flag in flags)


def run_record(args: argparse.Namespace, repo_root: Path, settings: EvalSettings) -> int:
    """Run the samples on the target and write the release metrics file; see the module doc.

    Example::

        >>> run_record(args, Path("."), load_eval_settings(Path(".")))  # doctest: +SKIP
        0
    """
    out_path = _record_path(args)
    _refuse_format(args)
    carry_from = _carry_from_path(args)
    target = select_target(args, settings)
    baseline = load_baseline(carry_from, target.name) if carry_from is not None else None
    runs = _run_count(getattr(args, "runs", None), target.runs)
    uses_judge = getattr(args, "judge", None) is not None
    check_recordable(target, judge_model=settings.judge.model, uses_judge=uses_judge)
    isolated = _check_credentials(target, settings, getattr(args, "judge", None))
    samples = _selected_samples(args, repo_root)
    plan = _build_plan(args, settings, target, runs)
    if plan is None:
        return 2
    inputs = plan.check_prompts(samples)
    controls = plan.control_editions(samples)
    judge_model = settings.judge.model if uses_judge else None
    recorded = plan.recorded_target(target, judge_model=judge_model, isolated=isolated)
    carry = _plan_carry(baseline, recorded, inputs, controls)
    metrics = _record_metrics(plan, recorded, samples, inputs, controls, carry, repo_root)
    validate_release_metrics(metrics)
    _write(out_path, metrics)
    extra = f" (+{len(controls)} edition controls)" if controls else ""
    carried = "" if carry is None else f" ({len(carry.rerun)} rerun, {len(carry.carried)} carried)"
    print(
        f"recorded {len(samples)} samples{carried}{extra} x {runs} runs on target "
        f"{target.name!r} to {out_path}"
    )
    return 0


def _plan_carry(
    baseline: Mapping[str, Any] | None,
    recorded: RecordedTarget,
    inputs: Mapping[str, str],
    controls: Mapping[str, _Control],
) -> CarryPlan | None:
    """The ``--carry-from`` plan, printed before the first paid run; ``None`` without a baseline."""
    if baseline is None:
        return None
    assert recorded.setup is not None  # a record always computes its setup parts
    carry = plan_carry(baseline, setup=recorded.setup.as_dict(), inputs=inputs)
    for line in carry_plan_lines(carry, controls=sorted(controls)):
        print(line)
    return carry


def _record_metrics(
    plan: _RecordPlan,
    recorded: RecordedTarget,
    samples: list[EvalSample],
    inputs: Mapping[str, str],
    controls: Mapping[str, _Control],
    carry: CarryPlan | None,
    repo_root: Path,
) -> dict[str, object]:
    """Run what reruns (every sample without ``carry``) and build the file; carry the rest."""
    total = len(samples)
    metrics = build_release_metrics(
        release=coding_agent_playbook.__version__,
        commit=_head_commit(repo_root),
        recorded=recorded,
        samples=[
            plan.run(sample, index, total, inputs[sample.id])
            for index, sample in enumerate(samples)
            if carry is None or carry.reruns(sample.id)
        ],
        controls=[
            plan.run(sample, index, total, control.inputs_digest, edition=control.edition)
            for index, sample in enumerate(samples)
            if (control := controls.get(sample.id)) is not None
        ],
    )
    return metrics if carry is None else merge_carried(metrics, carry)


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
    judge_endpoint = settings.judge.endpoint if judge is not None else None
    return _RecordPlan(runner, judge, judge_samples, runs, fail_fast, judge_endpoint)


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
    ) -> SampleRuns:
        """``sample``'s runs and digests on the current text, or on ``edition`` as a control.

        ``inputs`` is the inputs digest of the render checked before the first run.

        Each run is reported on stderr as it ends.
        """
        label = sample.id if edition is None else f"{sample.id} (control, edition {edition.tag})"
        results = []
        for run_index in range(self.runs):
            result = self._run_once(sample, edition)
            verdict = "PASS" if result.passed else "FAIL"
            print(
                f"[{index + 1}/{total}] {label} run {run_index + 1}/{self.runs}: "
                f"{verdict} (score={result.aggregate_score:.3f})",
                file=sys.stderr,
            )
            results.append(result)
        return SampleRuns(
            sample_id=sample.id,
            prompt_id=sample.prompt_id,
            graded=GRADED_HEAD if edition is None else edition.tag,
            prompt_digest=prompt_digest(sample, edition=edition),
            sample_digest=sample_digest(sample),
            results=results,
            inputs_digest=inputs,
        )

    def _run_once(self, sample: EvalSample, edition: Edition | None) -> SampleResult:
        try:
            with tempfile.TemporaryDirectory(prefix="playbook-record-") as tmp:
                return self.runner.run_sample(
                    sample,
                    Path(tmp) / "scratch",
                    judge=self.judge,
                    judge_samples=self.judge_samples,
                    fail_fast=self.fail_fast,
                    edition=edition,
                )
        except (PromptResolutionError, JudgeError) as exc:
            raise RecordRefusedError(
                f"sample {sample.id!r} could not be scored, so nothing was recorded: {exc}"
            ) from exc


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


def _record_path(args: argparse.Namespace) -> Path:
    record = getattr(args, "record", None)
    if record is None:
        raise RecordRefusedError(
            "--all, --runs and --carry-from belong to --record <path>; pass --record too"
        )
    return Path(record)


def _carry_from_path(args: argparse.Namespace) -> Path | None:
    """The ``--carry-from`` baseline path; refused unless the record runs ``--all`` samples."""
    carry_from = getattr(args, "carry_from", None)
    if carry_from is None:
        return None
    if not getattr(args, "all_samples", False):
        raise RecordRefusedError(
            f"--carry-from needs --all: a record carried from {carry_from} must cover every "
            "sample, so pass --all instead of a sample or task"
        )
    return Path(carry_from)


def _refuse_format(args: argparse.Namespace) -> None:
    """``--format`` shapes the one-sample ``--run`` report; ``--record`` writes JSON only."""
    fmt = getattr(args, "format", None)
    if fmt is not None:
        raise RecordRefusedError(
            f"--format {fmt} does not apply to --record, which always writes the release "
            "metrics JSON file; drop --format"
        )


def _run_count(flag: int | None, target_runs: int | None) -> int:
    runs = flag if flag is not None else (target_runs or 1)
    if runs < 1:
        raise RecordRefusedError(f"--runs must be >= 1, got {runs}")
    return runs


def _selected_samples(args: argparse.Namespace, repo_root: Path) -> list[EvalSample]:
    """Every sample (``--all``) or those ``<task>`` or ``<task>/<name>`` selects, sorted by id."""
    sample_id = getattr(args, "id", None)
    every = getattr(args, "all_samples", False)
    if every == (sample_id is not None):
        raise RecordRefusedError(
            "--record runs either --all samples or one sample or task (<task>/<name> or <task>), "
            f"got --all={every} and id={sample_id!r}"
        )
    ctx = SyncContext.from_repo(repo_root)
    try:
        registry = TaskRegistry.from_catalog(ctx.artifact_source, ctx.prompts_resolved)
        if every:
            chosen = [sample for task in registry.tasks() for sample in task.samples]
        else:
            chosen = list(registry.select(str(sample_id)))
    except TaskRegistryError as exc:
        raise RecordRefusedError(str(exc)) from exc
    return sorted(chosen, key=_id)


def _id(sample: EvalSample) -> str:
    return sample.id


def _head_commit(repo_root: Path) -> str | None:
    """The commit ``repo_root`` has checked out, or ``None`` outside a git checkout."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            env=without_repo_location(os.environ),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and commit else None


def _write(path: Path, metrics: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
