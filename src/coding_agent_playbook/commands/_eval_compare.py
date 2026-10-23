"""``playbook eval --compare <base-ref>``: the opt-in base-vs-HEAD eval comparison (D37, D76).

Off by default, never run by CI or the final gate: each run drives a real agent,
so it needs the owner's credentials and costs money. With ``--compare``, every
eval sample of the seven prompts whose included rule bodies change (or the one
eval sample ``<id>`` names) runs ``--compare-runs`` times (default 3) on a detached
checkout of the base ref, graded with ``--base-prompt-set``, and on one of HEAD,
graded with ``--prompt-set`` (both default v1, so v1 and v2 can be compared on one
ref with ``--compare HEAD``). ``--runner``, ``--judge``, ``--judge-samples`` and
``--full-scoring`` pass through to every run, so both sides run with the same
runner (and its configured model) and judge. The table (or ``--format json``)
names them and flags regressions by the D37 thresholds; it is advisory, so the
exit code is ``0`` whatever it shows, and ``2`` on a usage error or a ref that
does not check out (``ComparisonError``, an ``ExitTwoError``).
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
    ComparisonSide,
    PlaybookEvalRun,
    git_worktree_checkout,
    run_comparison,
)
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    import argparse

#: Runs per eval sample on each side (D37).
_DEFAULT_COMPARE_RUNS: Final = 3
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
        metavar="BASE_REF",
        help="opt-in and paid: run the eval samples of the rule-including prompts on "
        "BASE_REF and on HEAD and compare them (needs the agent's credentials)",
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
        help="--compare: directory for the checkouts and every run's JSON report "
        "(default: a new temporary directory)",
    )


@dataclass(frozen=True)
class _AgentOptions:
    """The runner and judge both sides use, and the flags that pass them to every run."""

    runner: str
    judge: str | None
    flags: tuple[str, ...]


def run_compare(args: argparse.Namespace, repo_root: Path) -> int:
    """Run the comparison ``args`` describe and print it; ``2`` on a usage error.

    A ref that does not check out raises ``ComparisonError``, which the CLI maps to 2.

    Example::

        >>> argv = ["eval", "--compare", "origin/main", "--judge", "llm"]
        >>> run_compare(build_parser().parse_args(argv), repo)  # doctest: +SKIP
        0
    """
    options = _agent_options(args) if _runs_valid(args.compare_runs) else None
    if options is None:
        return 2
    sample_ids = _selected_samples(getattr(args, "id", None), repo_root)
    if sample_ids is None:
        return 2
    if options.judge is None:
        print(_NO_JUDGE_NOTE, file=sys.stderr)
    work_dir = Path(args.compare_out or tempfile.mkdtemp(prefix="playbook-eval-compare-"))
    plan = ComparisonPlan(
        sample_ids,
        args.compare_runs,
        PlaybookEvalRun(options.flags),
        git_worktree_checkout(repo_root),
        work_dir,
    )
    base = ComparisonSide(args.compare, args.base_prompt_set)
    head = ComparisonSide("HEAD", args.prompt_set)
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


def _selected_samples(sample_id: str | None, repo_root: Path) -> list[str] | None:
    """The compared eval samples, or only ``sample_id``; ``None`` (after an error) if not one."""
    eval_samples = SyncContext.from_repo(repo_root).artifact_source.list_eval_samples()
    compared = compared_sample_ids(eval_samples)
    if sample_id is None:
        return compared
    if sample_id not in compared:
        print(
            f"error: {sample_id!r} is not an eval sample of a compared prompt; "
            f"compared eval samples: {', '.join(compared)}",
            file=sys.stderr,
        )
        return None
    return [sample_id]


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
