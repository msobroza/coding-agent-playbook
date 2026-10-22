"""``playbook eval --compare <base-ref>``: the opt-in base-vs-HEAD eval comparison (D37, D76).

Off by default, never run by CI or the final gate: each run drives a real agent,
so it needs the owner's credentials and costs money. With ``--compare``, every
eval task of the seven prompts whose included rule bodies change (or the one task
``<id>`` names) runs ``--compare-samples`` times (default 3) on a detached
checkout of the base ref, graded with ``--base-prompt-set``, and on one of HEAD,
graded with ``--prompt-set`` (both default v1, so v1 and v2 can be compared on one
ref with ``--compare HEAD``). ``--runner``, ``--judge``, ``--judge-samples`` and
``--full-scoring`` pass through to every run. The table (or ``--format json``)
flags regressions by the D37 thresholds; it is advisory, so the exit code is ``0``
whatever it shows, and ``2`` on a usage error or a ref that does not check out.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.prompt_sets import DEFAULT_PROMPT_SET, PROMPT_SETS
from coding_agent_playbook.commands._eval_enumerate import _DEFAULT_RUNNER
from coding_agent_playbook.evals import registry
from coding_agent_playbook.evals.comparison import (
    compared_task_ids,
    comparison_to_dict,
    format_comparison_table,
)
from coding_agent_playbook.evals.run.comparison_runner import (
    ComparisonError,
    ComparisonSide,
    PlaybookEvalTask,
    git_worktree_checkout,
    run_comparison,
)
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    import argparse

#: Runs per task on each side (D37).
_DEFAULT_COMPARE_SAMPLES: Final = 3


def configure_compare(parser: argparse.ArgumentParser) -> None:
    """Declare the ``--compare`` flags on ``playbook eval``.

    Example::

        >>> configure_compare(argparse.ArgumentParser())  # doctest: +SKIP
    """
    parser.add_argument(
        "--compare",
        metavar="BASE_REF",
        help="opt-in and paid: run the eval tasks of the rule-including prompts on "
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
        "--compare-samples",
        type=int,
        dest="compare_samples",
        default=_DEFAULT_COMPARE_SAMPLES,
        help="--compare: runs per task on each side (default: 3)",
    )
    parser.add_argument(
        "--compare-out",
        dest="compare_out",
        help="--compare: directory for the checkouts and every run's JSON report "
        "(default: a new temporary directory)",
    )


def run_compare(args: argparse.Namespace, repo_root: Path) -> int:
    """Run the comparison ``args`` describe and print it; ``2`` on a usage error."""
    samples: int = args.compare_samples
    if samples < 1:
        print(f"error: --compare-samples must be >= 1, got {samples}", file=sys.stderr)
        return 2
    task_ids = _selected_tasks(getattr(args, "id", None), repo_root)
    runner_flags = _runner_flags(args)
    if task_ids is None or runner_flags is None:
        return 2
    base = ComparisonSide(args.compare, args.base_prompt_set)
    head = ComparisonSide("HEAD", args.prompt_set)
    work_dir = Path(args.compare_out or tempfile.mkdtemp(prefix="playbook-eval-compare-"))
    try:
        rows = run_comparison(
            task_ids,
            base,
            head,
            samples=samples,
            run_task=PlaybookEvalTask(runner_flags),
            checkout_ref=git_worktree_checkout(repo_root),
            work_dir=work_dir,
        )
    except ComparisonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    labels = {"base_label": base.label, "head_label": head.label}
    if (getattr(args, "format", None) or "text") == "json":
        print(json.dumps(comparison_to_dict(rows, **labels), indent=2, sort_keys=True))
    else:
        print(format_comparison_table(rows, **labels))
    print(f"reports kept in {work_dir / 'reports'}", file=sys.stderr)
    return 0


def _selected_tasks(task_id: str | None, repo_root: Path) -> list[str] | None:
    """The compared tasks, or only ``task_id``; ``None`` (after an error line) if it is not one."""
    samples = SyncContext.from_repo(repo_root).artifact_source.list_eval_samples()
    compared = compared_task_ids(samples)
    if task_id is None:
        return compared
    if task_id not in compared:
        print(
            f"error: {task_id!r} is not an eval task of a compared prompt; "
            f"compared tasks: {', '.join(compared)}",
            file=sys.stderr,
        )
        return None
    return [task_id]


def _runner_flags(args: argparse.Namespace) -> tuple[str, ...] | None:
    """The flags every run gets, or ``None`` (after an error line) for an unusable runner."""
    runner = getattr(args, "runner", None) or _DEFAULT_RUNNER
    runner_cls = registry.load_runner_class(runner)
    guard = getattr(runner_cls, "available", None)
    if runner_cls is None or (guard is not None and not guard()):
        print(f"error: runner {runner!r} is unknown or unavailable here", file=sys.stderr)
        return None
    flags: list[str] = ["--runner", runner]
    if getattr(args, "judge", None):
        flags += ["--judge", args.judge]
    if getattr(args, "judge_samples", None) is not None:
        flags += ["--judge-samples", str(args.judge_samples)]
    if getattr(args, "full_scoring", False):
        flags.append("--full-scoring")
    return tuple(flags)
