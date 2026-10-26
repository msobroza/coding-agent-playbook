"""``playbook eval --compare BASE [HEAD]``: the opt-in two-side eval comparison (D37, D76; #281 ticket 14).

Off by default, never run by CI or the final gate: each run drives a real agent,
so it needs the owner's credentials and costs money. A side is a git ref
(checked out as a detached worktree), ``head`` (the current text in place) or
``edition:<tag>`` (release ``<tag>``'s graded set, built from the tag's manifest
into the work directory, never committed); HEAD defaults to the ``HEAD`` ref.
The compared samples come from the task registry: every sample, or, against an
edition, the samples of the prompts the edition grades (or the samples a task
name or a sample id selects). Each runs ``--compare-runs`` times (default 3)
per side; ``--base-prompt-set`` and ``--prompt-set`` pick each side's prompt
set. Every sample must render on both sides before the first paid run.
``--runner``, ``--judge``, ``--judge-samples`` and ``--full-scoring`` pass through
to every run, so both sides run with the same runner (and its configured model)
and judge. The table (or ``--format json``) names them, flags regressions by the
D37 thresholds and reports a side with no scorable run as unscorable; it is
advisory, so the exit code is ``0`` whatever it shows, and ``2`` on a usage
error, a side that cannot be prepared or a sample that does not render
(``ComparisonError``, an ``ExitTwoError``).
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.prompt_sets import DEFAULT_PROMPT_SET, PROMPT_SETS
from coding_agent_playbook.commands._eval_enumerate import _DEFAULT_RUNNER
from coding_agent_playbook.commands._eval_options import (
    judge_sample_count,
    load_usable_judge,
    load_usable_runner,
)
from coding_agent_playbook.evals.comparison import (
    ComparisonSetup,
    SampleComparison,
    compared_sample_ids,
    comparison_to_dict,
    format_comparison_table,
)
from coding_agent_playbook.evals.run.comparison_runner import (
    ComparisonPlan,
    PlaybookEvalRun,
    SideRenderCheck,
    run_comparison,
)
from coding_agent_playbook.evals.run.comparison_sides import (
    ComparisonSide,
    SideSources,
    git_edition_builder,
    git_worktree_checkout,
)
from coding_agent_playbook.evals.task_registry import TaskRegistry, TaskRegistryError
from coding_agent_playbook.release.edition_build import EditionBuildError, tag_manifest
from coding_agent_playbook.release.edition_freeze import graded_prompt_ids
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    import argparse

#: Runs per eval sample on each side (D37).
_DEFAULT_COMPARE_RUNS: Final = 3
#: The HEAD side when ``--compare`` names only the base: the committed ``HEAD``.
_DEFAULT_HEAD_SIDE: Final = "HEAD"
#: A comparison has a base and a head side.
_SIDES: Final = 2
_NO_JUDGE_NOTE: Final = (
    "note: no --judge, so the compared score is the deterministic gate score only; "
    "pass --judge llm to compare judge scores"
)


def configure_compare(parser: argparse.ArgumentParser) -> None:
    """Declare the ``--compare`` flags on ``playbook eval``.

    Example::

        >>> configure_compare(argparse.ArgumentParser())  # doctest: +SKIP
    """
    parser.add_argument(
        "--compare",
        nargs="+",
        metavar=("BASE", "HEAD"),
        help="opt-in and paid: run the eval samples on BASE and on HEAD (default: the "
        "HEAD ref) and compare them; a side is a git ref, head (the current text in "
        "place) or edition:<tag> (needs the agent's credentials)",
    )
    parser.add_argument(
        "--base-prompt-set",
        choices=PROMPT_SETS,
        dest="base_prompt_set",
        default=DEFAULT_PROMPT_SET,
        help="--compare: prompt set the base side grades (default: v1; --prompt-set picks HEAD's)",
    )
    parser.add_argument(
        "--compare-runs",
        type=int,
        dest="compare_runs",
        default=_DEFAULT_COMPARE_RUNS,
        help="--compare: runs per eval sample on each side (default: 3)",
    )
    parser.add_argument(
        "--compare-out",
        dest="compare_out",
        help="--compare: directory for the checkouts, built editions and every run's "
        "JSON report (default: a new temporary directory)",
    )


@dataclass(frozen=True)
class _AgentOptions:
    """The runner and judge both sides use, and the flags that pass them to every run."""

    runner: str
    judge: str | None
    flags: tuple[str, ...]


def run_compare(args: argparse.Namespace, repo_root: Path) -> int:
    """Run the comparison ``args`` describe and print it; ``2`` on a usage error.

    A side that cannot be prepared or a sample that does not render raises
    ``ComparisonError``, which the CLI maps to 2.

    Example::

        >>> argv = ["eval", "--compare", "edition:v0.1.0", "head", "--judge", "llm"]
        >>> run_compare(build_parser().parse_args(argv), repo)  # doctest: +SKIP
        0
    """
    options = _agent_options(args) if _runs_valid(args.compare_runs) else None
    sides = _sides(args) if options is not None else None
    if options is None or sides is None:
        return 2
    registry = _registry(repo_root)
    sample_ids = _selected_samples(args, registry, repo_root, sides) if registry else None
    if registry is None or sample_ids is None:
        return 2
    if options.judge is None:
        print(_NO_JUDGE_NOTE, file=sys.stderr)
    work_dir = Path(args.compare_out or tempfile.mkdtemp(prefix="playbook-eval-compare-"))
    sources = SideSources(
        repo_root, git_worktree_checkout(repo_root), git_edition_builder(repo_root)
    )
    samples = {sample_id: registry.sample(sample_id) for sample_id in sample_ids}
    plan = ComparisonPlan(
        sample_ids,
        args.compare_runs,
        PlaybookEvalRun(options.flags),
        sources,
        work_dir,
        SideRenderCheck(samples),
    )
    base, head = sides
    rows = run_comparison(plan, base, head)
    setup = ComparisonSetup(base.label, head.label, options.runner, options.judge)
    _print_comparison(rows, setup, getattr(args, "format", None) or "text")
    print(f"reports kept in {work_dir / 'reports'}", file=sys.stderr)
    return 0


def _print_comparison(rows: list[SampleComparison], setup: ComparisonSetup, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(comparison_to_dict(rows, setup), indent=2, sort_keys=True))
    else:
        print(format_comparison_table(rows, setup))


def _runs_valid(runs: int) -> bool:
    if runs < 1:
        print(f"error: --compare-runs must be >= 1, got {runs}", file=sys.stderr)
    return runs >= 1


def _sides(args: argparse.Namespace) -> tuple[ComparisonSide, ComparisonSide] | None:
    """The base and HEAD sides ``--compare`` names, or ``None`` after an error line."""
    names: list[str] = list(args.compare)
    if len(names) > _SIDES:
        print(f"error: --compare takes a base and a head side, got {names}", file=sys.stderr)
        return None
    head_name = names[1] if len(names) == _SIDES else _DEFAULT_HEAD_SIDE
    base = ComparisonSide.parse(names[0], args.base_prompt_set)
    head = ComparisonSide.parse(head_name, args.prompt_set)
    _warn_ignored_prompt_set(base, "--base-prompt-set")
    _warn_ignored_prompt_set(head, "--prompt-set")
    return base, head


def _warn_ignored_prompt_set(side: ComparisonSide, flag: str) -> None:
    """Warn that ``flag`` does not apply to ``side`` when it is an edition (it holds one text)."""
    if side.kind == "edition" and side.prompt_set != DEFAULT_PROMPT_SET:
        print(
            f"warning: {flag} {side.prompt_set} is ignored for {side.ref}: "
            "an edition grades its own text",
            file=sys.stderr,
        )


def _hint_id_as_side(names: list[str], registry: TaskRegistry) -> None:
    """Hint that a second ``--compare`` side naming an eval sample or task goes before ``--compare``.

    ``--compare`` takes one or two sides, so ``--compare origin/main review/x``
    reads ``review/x`` as the HEAD side.
    """
    if len(names) != _SIDES:
        return
    try:
        registry.select(names[1])
    except TaskRegistryError:
        return
    print(
        f"hint: {names[1]!r} names an eval sample or task, not a side; put it before "
        f"--compare: playbook eval {names[1]} --compare {names[0]}",
        file=sys.stderr,
    )


def _registry(repo_root: Path) -> TaskRegistry | None:
    ctx = SyncContext.from_repo(repo_root)
    try:
        return TaskRegistry.from_catalog(ctx.artifact_source, ctx.prompts_resolved)
    except TaskRegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _selected_samples(
    args: argparse.Namespace,
    registry: TaskRegistry,
    repo_root: Path,
    sides: tuple[ComparisonSide, ComparisonSide],
) -> list[str] | None:
    """The compared eval samples, or those the positional name selects.

    Against an edition, the default is the samples of the prompts every edition
    side grades. ``None`` (after an error line) on an unknown name, an
    unreadable tag or an empty selection. A HEAD side that names an eval sample
    or task prints a hint first.
    """
    _hint_id_as_side(list(args.compare), registry)
    name: str | None = getattr(args, "id", None)
    try:
        if name is not None:
            return [sample.id for sample in registry.select(name)]
        selected = compared_sample_ids(registry, _edition_prompts(repo_root, sides))
    except (TaskRegistryError, EditionBuildError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    if not selected:
        print("error: no eval sample to compare: the editions grade no task", file=sys.stderr)
        return None
    return selected


def _edition_prompts(
    repo_root: Path, sides: tuple[ComparisonSide, ComparisonSide]
) -> set[str] | None:
    """The prompts every edition side grades (its tag's manifest), ``None`` without an edition."""
    graded: set[str] | None = None
    for side in sides:
        if side.kind != "edition":
            continue
        prompts = set(graded_prompt_ids(tag_manifest(repo_root, side.tag)[1]))
        graded = prompts if graded is None else graded & prompts
    return graded


def _agent_options(args: argparse.Namespace) -> _AgentOptions | None:
    """The runner, judge and run flags, or ``None`` (after an error line) when unusable.

    The checks are ``playbook eval --run``'s own (``_eval_options``), run once here
    so a bad runner or judge fails before any checkout instead of in every run.
    """
    runner = getattr(args, "runner", None) or _DEFAULT_RUNNER
    judge: str | None = getattr(args, "judge", None)
    judge_samples = judge_sample_count(args)
    if load_usable_runner(runner) is None or judge_samples is None:
        return None
    flags: list[str] = ["--runner", runner]
    if judge is not None:
        if load_usable_judge(judge) is None:
            return None
        flags += ["--judge", judge, "--judge-samples", str(judge_samples)]
    if getattr(args, "full_scoring", False):
        flags.append("--full-scoring")
    return _AgentOptions(runner, judge, tuple(flags))
