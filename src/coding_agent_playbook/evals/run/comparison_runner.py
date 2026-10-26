"""Run the same eval samples on two sides and compare them (D37, D76; prU F-01; #281 ticket 14).

``playbook eval --compare <base> [<head>]`` is opt-in and paid: every run drives a
real agent. Each side is a git ref, ``head`` (the current text in place) or
``edition:<tag>`` (``evals.run.comparison_sides`` prepares them). Every eval
sample runs ``runs`` times per side through ``python -m coding_agent_playbook.cli
eval <id> --run --format json`` in the side's directory (a git ref's checkout with
its ``src/`` first on ``PYTHONPATH``, so the base grades the base ref's text), plus
the side's flags.

Before the first paid run, every sample must render on both sides
(:class:`SideRenderCheck`); one that does not is a :class:`ComparisonError`
(exit 2) and nothing runs. Every run's JSON report is kept under
``<work_dir>/reports/<side>/``; :mod:`coding_agent_playbook.evals.comparison` turns
the outcomes into the table.
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.evals.comparison import RunOutcome, SampleComparison, compare_sample
from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.run.comparison_sides import (
    ComparisonError,
    ComparisonSide,
    PreparedSide,
    SideSources,
    prepare_side,
)
from coding_agent_playbook.evals.run.git_env import without_repo_location

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample

#: Bound on one paid eval run; a run past it counts as an unscorable run.
DEFAULT_RUN_TIMEOUT_S: Final = 3600.0
#: Bound on one hermetic ``--runner fake`` render check of a git-ref side.
RENDER_CHECK_TIMEOUT_S: Final = 600.0
#: Render failures listed in full before the rest are counted.
_MAX_LISTED_FAILURES: Final = 20


@dataclass(frozen=True)
class EvalRunOutput:
    """What one ``playbook eval <id> --run --format json`` run printed, and its exit code."""

    exit_code: int
    stdout: str
    stderr: str = ""


class SampleRunner(Protocol):
    """Runs one eval sample once in a directory with a side's flags (``PlaybookEvalRun`` in prod)."""

    def __call__(
        self, checkout: Path, sample_id: str, side_flags: tuple[str, ...]
    ) -> EvalRunOutput: ...


class RenderCheck(Protocol):
    """Why ``sample_id`` does not render on ``side``, or ``None`` (``SideRenderCheck`` in prod)."""

    def __call__(self, side: PreparedSide, sample_id: str) -> str | None: ...


@dataclass(frozen=True)
class ComparisonPlan:
    """What both sides run: the eval samples, the runs of each, how to run, check and prepare.

    Example::

        >>> plan = ComparisonPlan(["refactor/extract-helper"], 3, PlaybookEvalRun(),  # doctest: +SKIP
        ...                       sources, work_dir, SideRenderCheck(samples))
    """

    sample_ids: Sequence[str]
    runs: int
    run_sample: SampleRunner
    sources: SideSources
    work_dir: Path
    check_render: RenderCheck


@dataclass(frozen=True)
class PlaybookEvalRun:
    """Run an eval sample through the directory's own engine as a child process.

    ``flags`` are passed through (``--runner``, ``--judge``, ``--full-scoring``),
    then the side's own flags. A run past ``timeout_s`` is unscorable (exit 2).

    Example::

        >>> PlaybookEvalRun(("--runner", "fake")).flags
        ('--runner', 'fake')
    """

    flags: tuple[str, ...] = ()
    timeout_s: float = DEFAULT_RUN_TIMEOUT_S

    def __call__(
        self, checkout: Path, sample_id: str, side_flags: tuple[str, ...] = ()
    ) -> EvalRunOutput:
        argv = [sys.executable, "-m", "coding_agent_playbook.cli", "eval", sample_id, "--run"]
        argv += ["--format", "json", "--repo-root", str(checkout), *self.flags, *side_flags]
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


@dataclass(frozen=True)
class SideRenderCheck:
    """Whether a sample's prompt renders on a prepared side: ``None``, or why it does not.

    A side in place (``head``, an edition) renders in this process, strictly: a
    real agent is never driven with a placeholder. A git ref renders through its
    own engine, as one hermetic ``--runner fake`` run in its checkout that exits
    2 when the ref does not know the sample or its prompt fails to render.

    Example::

        >>> SideRenderCheck(samples)(prepared, "review/spot-the-bug") is None  # doctest: +SKIP
        True
    """

    samples: Mapping[str, EvalSample]
    fake_run: SampleRunner = PlaybookEvalRun(("--runner", "fake"), RENDER_CHECK_TIMEOUT_S)

    def __call__(self, side: PreparedSide, sample_id: str) -> str | None:
        if side.side.kind == "ref":
            done = self.fake_run(side.checkout, sample_id, side.flags)
            if done.exit_code != 2:
                return None
            return done.stderr.strip() or "the sample does not render"
        try:
            render_prompt(self.samples[sample_id], strict=True, edition=side.edition)
        except (PromptResolutionError, ValueError) as exc:
            return str(exc)
        return None


def run_comparison(
    plan: ComparisonPlan, base: ComparisonSide, head: ComparisonSide
) -> list[SampleComparison]:
    """Run every eval sample ``plan.runs`` times on each side and compare, one row each.

    Both sides are prepared and every sample's render is checked on both before
    the first run; a failure raises :class:`ComparisonError` and nothing runs.

    Example::

        >>> rows = run_comparison(plan, ComparisonSide("edition:v0.1.0"), ComparisonSide("head"))  # doctest: +SKIP
    """
    with ExitStack() as stack:
        sides = [
            stack.enter_context(prepare_side(plan.sources, side, name, plan.work_dir))
            for name, side in (("base", base), ("head", head))
        ]
        _check_renders(plan, sides)
        base_outcomes, head_outcomes = (_run_side(plan, side) for side in sides)
    return [
        compare_sample(sample_id, base_outcomes[sample_id], head_outcomes[sample_id])
        for sample_id in plan.sample_ids
    ]


def _check_renders(plan: ComparisonPlan, sides: Sequence[PreparedSide]) -> None:
    failures = [
        f"- {sample_id} on {side.side.label}: {why}"
        for side in sides
        for sample_id in plan.sample_ids
        if (why := plan.check_render(side, sample_id)) is not None
    ]
    if not failures:
        return
    listed = failures[:_MAX_LISTED_FAILURES]
    if len(failures) > len(listed):
        listed.append(f"- ... and {len(failures) - len(listed)} more")
    raise ComparisonError(
        f"{len(failures)} eval sample render(s) failed, so nothing was run:\n" + "\n".join(listed)
    )


def _run_side(plan: ComparisonPlan, side: PreparedSide) -> dict[str, list[RunOutcome]]:
    """Run each eval sample on the prepared ``side``, keep each run's report."""
    reports = plan.work_dir / "reports" / side.name
    reports.mkdir(parents=True, exist_ok=True)
    outcomes: dict[str, list[RunOutcome]] = {}
    for sample_id in plan.sample_ids:
        runs = [plan.run_sample(side.checkout, sample_id, side.flags) for _ in range(plan.runs)]
        for number, run in enumerate(runs, start=1):
            _keep_report(reports, f"{sample_id}-{number}", run)
        outcomes[sample_id] = [RunOutcome.from_run(r.exit_code, r.stdout) for r in runs]
    return outcomes


def _keep_report(reports: Path, stem: str, run: EvalRunOutput) -> None:
    # A sample id is <task>/<name> (#302), so each task's reports get their own directory.
    (reports / stem).parent.mkdir(parents=True, exist_ok=True)
    (reports / f"{stem}.json").write_text(run.stdout, encoding="utf-8")
    if run.stderr:
        (reports / f"{stem}.stderr.txt").write_text(run.stderr, encoding="utf-8")
