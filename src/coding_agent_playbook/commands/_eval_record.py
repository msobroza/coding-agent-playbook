"""``playbook eval --run --all --runs N --record <path>``: write one release metrics file (ticket 07).

Every eval sample (or the one ``<id>`` names) runs ``N`` times on one Eval
target (``--runs``, else the target's ``runs``, else 1), and the results are
written as a release metrics file, schema version 1
(``evals.release_metrics_schema``). Before any paid run, ``--record`` refuses a
target without an explicit model, a moving model alias and, with ``--judge``,
an unpinned ``[evals.judge] model`` (``evals.model_pins``), ``--format``, and
a sample whose prompt cannot be resolved. ``--full-scoring`` grades every check,
as for ``--run``. A sample that cannot
be scored stops the recording, so a file never silently lacks a sample. The
file is written whatever the scores are: exit ``0`` once it is written, ``2`` on
a refusal or an unscorable sample.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import coding_agent_playbook
from coding_agent_playbook.commands._eval_options import (
    build_judge,
    build_target_runner,
    judge_sample_count,
    select_target,
)
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.model_pins import RecordRefusedError, check_recordable
from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.release_metrics import (
    GRADED_HEAD,
    RecordedTarget,
    SampleRuns,
    build_release_metrics,
)
from coding_agent_playbook.evals.release_metrics_schema import validate_release_metrics
from coding_agent_playbook.evals.run.git_env import without_repo_location
from coding_agent_playbook.evals.run.harness_version import harness_cli_version
from coding_agent_playbook.evals.sample_digest import prompt_digest, sample_digest
from coding_agent_playbook.evals.task_registry import TaskRegistry, TaskRegistryError
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.catalog.prompt_sets import PromptSet
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner, SampleResult
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.evals.targets import EvalSettings, EvalTarget

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


def wants_record(args: argparse.Namespace) -> bool:
    """Whether ``args`` ask for a recording (``--record``, ``--all`` or ``--runs``)."""
    flags = (getattr(args, "record", None), getattr(args, "runs", None))
    return getattr(args, "all_samples", False) or any(flag is not None for flag in flags)


def run_record(args: argparse.Namespace, repo_root: Path, settings: EvalSettings) -> int:
    """Run the samples on the target and write the release metrics file; see the module doc.

    Example::

        >>> run_record(args, Path("."), load_eval_settings(Path(".")))  # doctest: +SKIP
        0
    """
    out_path = _record_path(args)
    _refuse_format(args)
    target = select_target(args, settings)
    runs = _run_count(getattr(args, "runs", None), target.runs)
    uses_judge = getattr(args, "judge", None) is not None
    check_recordable(target, judge_model=settings.judge.model, uses_judge=uses_judge)
    samples = _selected_samples(args, repo_root)
    plan = _build_plan(args, settings, target, runs)
    if plan is None:
        return 2
    plan.check_prompts(samples)
    recorded = RecordedTarget(
        target=target,
        harness_version=harness_cli_version(plan.runner.cli),
        judge_model=settings.judge.model if uses_judge else None,
        runs=runs,
    )
    metrics = build_release_metrics(
        release=coding_agent_playbook.__version__,
        commit=_head_commit(repo_root),
        recorded=recorded,
        samples=[plan.run(sample, index, len(samples)) for index, sample in enumerate(samples)],
    )
    validate_release_metrics(metrics)
    _write(out_path, metrics)
    print(f"recorded {len(samples)} samples x {runs} runs on target {target.name!r} to {out_path}")
    return 0


def _build_plan(
    args: argparse.Namespace, settings: EvalSettings, target: EvalTarget, runs: int
) -> _RecordPlan | None:
    """The runner, judge and judge sample count of the run; ``None`` after an error line."""
    runner = build_target_runner(target)
    judge_name = getattr(args, "judge", None)
    judge = build_judge(judge_name, settings.judge) if judge_name is not None else None
    judge_samples = judge_sample_count(args, default=settings.judge.samples or 1)
    if runner is None or (judge_name is not None and judge is None) or judge_samples is None:
        return None
    fail_fast = not getattr(args, "full_scoring", False)
    return _RecordPlan(runner, judge, judge_samples, runs, args.prompt_set, fail_fast)


@dataclass(frozen=True)
class _RecordPlan:
    """How each sample runs: the runner, the judge, the run count, the prompt set and fail-fast.

    ``fail_fast`` is ``False`` under ``--full-scoring``, as for ``eval --run``.
    """

    runner: HarnessRunner
    judge: Judge | None
    judge_samples: int
    runs: int
    prompt_set: PromptSet
    fail_fast: bool = True

    def check_prompts(self, samples: list[EvalSample]) -> None:
        """Resolve every sample's prompt before the first paid run; refuse on the first bad one."""
        for sample in samples:
            try:
                render_prompt(
                    sample, strict=self.runner.requires_resolved_prompt, prompt_set=self.prompt_set
                )
            except PromptResolutionError as exc:
                raise RecordRefusedError(
                    f"sample {sample.id!r} has no prompt to run, so nothing was run: {exc}"
                ) from exc

    def run(self, sample: EvalSample, index: int, total: int) -> SampleRuns:
        """``sample``'s runs and digests, each run reported on stderr as it ends."""
        results = []
        for run_index in range(self.runs):
            result = self._run_once(sample)
            verdict = "PASS" if result.passed else "FAIL"
            print(
                f"[{index + 1}/{total}] {sample.id} run {run_index + 1}/{self.runs}: "
                f"{verdict} (score={result.aggregate_score:.3f})",
                file=sys.stderr,
            )
            results.append(result)
        return SampleRuns(
            sample_id=sample.id,
            prompt_id=sample.prompt_id,
            graded=GRADED_HEAD,
            prompt_digest=prompt_digest(sample, self.prompt_set),
            sample_digest=sample_digest(sample),
            results=results,
        )

    def _run_once(self, sample: EvalSample) -> SampleResult:
        try:
            with tempfile.TemporaryDirectory(prefix="playbook-record-") as tmp:
                return self.runner.run_sample(
                    sample,
                    Path(tmp) / "scratch",
                    judge=self.judge,
                    judge_samples=self.judge_samples,
                    fail_fast=self.fail_fast,
                    prompt_set=self.prompt_set,
                )
        except (PromptResolutionError, JudgeError) as exc:
            raise RecordRefusedError(
                f"sample {sample.id!r} could not be scored, so nothing was recorded: {exc}"
            ) from exc


def _record_path(args: argparse.Namespace) -> Path:
    record = getattr(args, "record", None)
    if record is None:
        raise RecordRefusedError("--all and --runs belong to --record <path>; pass --record too")
    return Path(record)


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
