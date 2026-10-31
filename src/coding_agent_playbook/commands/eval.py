"""``playbook eval`` — Tier 0 enumeration + the R1 live runner (SPEC §12.8, §15).

``playbook eval`` is both a read-only enumeration of the prompt-to-sample graph and
— with ``--run`` (PR R1d) — the entry point that *executes* one sample end-to-end
through a :class:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner` and grades it
via the unified PR-M :class:`EvaluationReport`.

Sub-modes:

Samples are found by task (``evals.task_registry``): ``<task>`` names every
sample of a prompt, ``<task>/<name>`` (a sample id, e.g. ``review/spot-the-bug``)
one sample.

- ``playbook eval --list`` (also the default when no arg is given): tree-shape
  coverage report grouped by task, one block per prompt, with per-sample summary lines.
- ``playbook eval --show <id>``: detailed dump for one sample — sections from
  SPEC §12.8 (Sample / Source / Prompt under test / Description / Setup /
  Invocation / Expected / Rubric).
- ``playbook eval <task>`` or ``<id>`` (no ``--run``): prints how to run the
  selected samples. Exits 0 if the name is known, exits 1 if it isn't (so typos
  still surface).
- ``playbook eval --targets``: list the Eval targets of the ``[evals]`` config,
  where each comes from and whether its harness CLI is installed
  (``commands/_eval_targets.py``); ``--targets --check`` also runs a one-turn
  prompt through each target's harness and exits ``1`` if any fails.
- ``playbook eval <task>|<id> --run [--target NAME|HARNESS:MODEL] [--runner NAME] [--judge NAME]
  [--judge-samples N] [--format text|json]``: load the selected samples,
  pick its Eval target (``--target``, then ``PLAYBOOK_EVAL_TARGET``, then the local
  and the committed ``[evals] default``, else ``claude_code`` on its default model,
  recorded as ``default``; ``--runner NAME`` is the target with that harness and no
  model), build that harness's runner from the ``coding_agent_playbook.runners``
  entry-point group with the target's model, run it in a throwaway scratch dir,
  and render ``result.report`` (reusing ``commands/metrics.py``'s text/json renderer). Exits ``0`` on a passing report,
  ``1`` on a failing one, ``2`` on usage errors (unknown sample,
  unknown/unavailable runner, unknown/unavailable judge, bad ``--format``) and
  when the sample cannot be scored at all (its prompt fails to render, or the judge
  gives no score) — that is neither a pass nor a fail.

  ``--judge`` (R2) selects a Tier-2 judge from the
  ``coding_agent_playbook.judges`` group (``llm`` ships, opt-in/CLI-gated) so the
  sample's ``[rubric]`` criteria are scored too; omitted ⇒ deterministic-only (no
  judge); ``[evals.judge] model`` is the judge's model for every target.
  ``--judge-samples N`` (default ``[evals.judge] samples``, else 1) is how many
  times the judge scores each rubric criterion before averaging; it is not a count of eval samples, and a
  count below 1 is a usage error (exit ``2``). The old
  ``--samples N`` spelling is a deprecated alias for one release (D80): hidden
  from ``--help``, it still works, prints one stderr line naming
  ``--judge-samples``, and passing both flags is a usage error (exit ``2``).

  A core sample pinned to an edition (``edition = "vX"`` in ``sample.toml``)
  grades the frozen copy in ``catalog/editions/vX/``, ignores overlay and local
  overrides, and its result line ends ``graded edition vX (frozen; overrides
  ignored)``; ``--edition head`` grades the current text instead
  (``evals.graded_source``, #281 ticket 09), and ``--edition-dir DIR`` grades
  the edition built at ``DIR`` (what ``--compare edition:<tag>`` passes, #281
  ticket 14). The JSON report records the graded
  source, the prompt and sample digests and the engine version.

  ``--prompt-set`` and ``--base-prompt-set`` were removed with the prompt sets
  (ADR 0012): hidden from ``--help``, either one is a usage error (exit ``2``)
  saying so.

  ``--run --all --runs N --record PATH`` (spec #281 ticket 07; ``commands/_eval_record.py``)
  runs every sample (or the sample ``<id>``) N times on one Eval target and writes
  a release metrics file (schema version 1); it refuses a target without an
  explicit model, a moving model alias and an unpinned judge model. With
  ``--all``, ``--carry-from PREVIOUS`` (#329 ticket 05) reruns only what changed
  since that metrics file of the same target and carries the other entries.

  ``--check-regressions NEW --against BASELINE [--accept SAMPLE=REASON]`` (spec #281
  ticket 08; ``commands/_eval_regressions.py``) compares two release metrics files
  of one target, stores the comparison in NEW and exits ``1`` on an unaccepted
  regression.

  ``--compare BASE [HEAD]`` (D37, opt-in and paid; ``commands/_eval_compare.py``)
  runs every eval sample on two sides (a git ref, ``head`` for the current text
  in place, or ``edition:<tag>``; HEAD defaults to the ``HEAD`` ref) and prints
  a comparison table that flags regressions.

  Unlike ``playbook metrics``, there is **no ``--run-tests`` flag**: whether the
  execution evaluators (``coverage``/``test_pass_rate``) run is declared by the
  sample's own ``[metrics]`` block (``run_tests``), so the eval sample — not a CLI
  flag — carries that intent.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._eval_compare import configure_compare, run_compare
from coding_agent_playbook.commands._eval_enumerate import (
    _print_list,
    _print_run_hint,
    _print_show,
)
from coding_agent_playbook.commands._eval_options import (
    build_judge,
    build_target_runner,
    judge_sample_count,
    removed_flag_error,
    select_target,
)
from coding_agent_playbook.commands._eval_record import run_record
from coding_agent_playbook.commands._eval_record_flags import configure_record, wants_record
from coding_agent_playbook.commands._eval_regressions import (
    configure_regressions,
    run_regressions,
    wants_regressions,
)
from coding_agent_playbook.commands._eval_targets import check_targets, print_targets
from coding_agent_playbook.evals.graded_source import graded_record, graded_source
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.model_pins import RecordRefusedError
from coding_agent_playbook.evals.prompting import PromptResolutionError
from coding_agent_playbook.evals.report_format import (
    format_sample_result_text,
    sample_result_to_dict,
)
from coding_agent_playbook.evals.run.comparison_sides import EDITION_DIR_FLAG
from coding_agent_playbook.evals.run.scoring_suite import UnscorableSuiteError
from coding_agent_playbook.evals.target_config import load_eval_settings
from coding_agent_playbook.evals.targets import TargetError
from coding_agent_playbook.evals.task_registry import TaskRegistry, TaskRegistryError
from coding_agent_playbook.release.edition import EditionError
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner, SampleResult
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.evals.targets import EvalTarget


NAME: Final = "eval"
HELP: Final = "eval enumeration + `--run` a sample (SPEC §12.8, §15)"

_VALID_FORMATS = ("text", "json")
#: ``--edition``'s one value: grade the current text, even for a pinned sample.
_EDITION_HEAD: Final = "head"


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook eval``'s flags (PR 11 enumeration; PR R1d adds ``--run``).

    Example::

        >>> configure(argparse.ArgumentParser(prog="playbook eval"))  # doctest: +SKIP
    """
    # Every other subcommand exposes ``--repo-root <path>`` for testability
    # and so users can run against a non-cwd checkout; eval gets the same
    # surface for parity. ``run`` falls back to ``Path.cwd()`` when this is absent.
    parser.add_argument(
        "--repo-root", help="repo to enumerate eval samples against (defaults to cwd)"
    )
    eval_group = parser.add_mutually_exclusive_group()
    eval_group.add_argument("--list", action="store_true")
    eval_group.add_argument("--show", help="show one sample by id")
    eval_group.add_argument(
        "--targets",
        action="store_true",
        help="list the eval targets ([evals] config), where each comes from and "
        "whether its harness CLI is installed",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="with --targets: run a one-turn prompt through each target's harness "
        "(paid; the harness makes the calls, the engine makes none)",
    )
    parser.add_argument(
        "id",
        nargs="?",
        help="a task (every sample of one prompt) or a sample id <task>/<name> "
        "(enumerate, or run with --run)",
    )
    # PR R1d — execute one sample end-to-end and grade it through the unified
    # EvaluationReport. Whether execution evaluators run is the sample's own
    # [metrics] decision, so there is intentionally no --run-tests flag here.
    parser.add_argument(
        "--run",
        action="store_true",
        help="execute the samples <task> or <task>/<name> selects through a runner "
        "and grade them (SPEC §15)",
    )
    parser.add_argument(
        "--runner",
        help="runner name from the coding_agent_playbook.runners group "
        "(default: claude_code; use 'fake' for a hermetic no-op run); "
        "the eval target with that harness and no model",
    )
    parser.add_argument(
        "--target",
        help="eval target to run: a name from [evals.targets] or HARNESS:MODEL "
        "(default: $PLAYBOOK_EVAL_TARGET, then [evals] default, then claude_code)",
    )
    # ADR 0012: removed with the prompt sets, hidden; removed_flag_error() refuses it.
    parser.add_argument("--prompt-set", dest="removed_prompt_set", help=argparse.SUPPRESS)
    parser.add_argument(
        "--edition",
        choices=(_EDITION_HEAD,),
        help="head: grade the current text, even for a sample pinned to a frozen "
        "edition (default: a pinned sample grades its edition)",
    )
    parser.add_argument(
        EDITION_DIR_FLAG,
        dest="edition_dir",
        metavar="DIR",
        help="grade the edition built at DIR for every selected sample, pinned or not "
        "(what --compare edition:<tag> passes to each run)",
    )
    _configure_scoring(parser)
    configure_compare(parser)
    configure_record(parser)
    configure_regressions(parser)


def _configure_scoring(parser: argparse.ArgumentParser) -> None:
    """Declare the ``--run`` grading flags: judge, judge samples, fail-fast and output format."""
    # PR R2 — judged [rubric] scoring. --judge selects a Tier-2 judge from the
    # coding_agent_playbook.judges group (e.g. 'llm', opt-in/CLI-gated); omitted
    # means deterministic-only. --judge-samples is the per-criterion average count.
    parser.add_argument(
        "--judge",
        help="judge name from the coding_agent_playbook.judges group to score "
        "[rubric] criteria (e.g. 'llm'); omit for a deterministic-only run",
    )
    parser.add_argument(
        "--judge-samples",
        type=int,
        dest="judge_samples",
        help="how many times the judge scores each rubric criterion before averaging (default: 1)",
    )
    # D80: deprecated alias, hidden from --help; resolved by _judge_samples().
    parser.add_argument("--samples", type=int, dest="deprecated_samples", help=argparse.SUPPRESS)
    # By default --run is fail-fast: a lost deterministic gate skips the costlier
    # judge tier (saving an LLM call). --full-scoring grades every check.
    parser.add_argument(
        "--full-scoring",
        action="store_true",
        help="grade every check even after the gate is lost (disables fail-fast; "
        "scores the judge tier regardless of a failing deterministic check)",
    )
    parser.add_argument(
        "--format",
        choices=_VALID_FORMATS,
        help="--run output format (default: text)",
    )


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())

    removed = removed_flag_error(args)
    if removed is not None:
        print(removed, file=sys.stderr)
        return 2

    # ``--check-regressions`` (spec #281 ticket 08) only reads two metrics files.
    if wants_regressions(args):
        return run_regressions(args)

    # ``--compare`` (D37) is opt-in and paid: it runs eval samples on two checkouts.
    if getattr(args, "compare", None) is not None:
        if getattr(args, "target", None) is not None:
            raise TargetError("--compare does not take --target yet; pick the agent with --runner")
        return run_compare(args, repo_root)

    if getattr(args, "check", False) and not getattr(args, "targets", False):
        print(
            "error: --check goes with --targets (playbook eval --targets --check)", file=sys.stderr
        )
        return 2
    if getattr(args, "targets", False):
        if getattr(args, "check", False):
            return check_targets(repo_root)
        return print_targets(repo_root)

    # ``--record`` (spec #281 ticket 07) runs samples N times on one target and
    # writes a release metrics file instead of printing one report.
    if wants_record(args):
        if not getattr(args, "run", False):
            raise RecordRefusedError("--record, --all, --runs and --carry-from need --run")
        return run_record(args, repo_root, load_eval_settings(repo_root))

    # ``--run`` is the only path that *executes* samples: a task name runs every
    # sample of the task, ``<task>/<name>`` one sample.
    if getattr(args, "run", False):
        return _run_sample_cli(args, repo_root)

    ctx = SyncContext.from_repo(repo_root)
    registry = _task_registry(ctx)
    if registry is None:
        return 2

    if getattr(args, "list", False):
        return _print_list(ctx.prompts_resolved, registry)
    show_id = getattr(args, "show", None)
    if show_id:
        return _print_show(show_id, registry, ctx.prompts_resolved)
    bare_id = getattr(args, "id", None)
    if bare_id:
        return _print_run_hint(bare_id, registry, ctx.prompts_resolved)
    # No flag — default to --list (matches the "helpful empty invocation" rule).
    return _print_list(ctx.prompts_resolved, registry)


def _task_registry(ctx: SyncContext) -> TaskRegistry | None:
    """The run's task registry, or ``None`` after an ``error:`` line naming what is wrong."""
    try:
        return TaskRegistry.from_catalog(ctx.artifact_source, ctx.prompts_resolved)
    except TaskRegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


# --------------------------------------------------------------------------- #
# --run — execute one sample through a HarnessRunner and grade it (PR R1d)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _SampleRun:
    """How every selected sample of one ``--run`` is run and graded."""

    runner: HarnessRunner
    target: EvalTarget
    judge: Judge | None
    judge_samples: int
    fail_fast: bool
    head: bool = False
    edition_root: Path | None = None


def _run_sample_cli(args: argparse.Namespace, repo_root: Path) -> int:
    """Run the samples ``<task>`` or ``<task>/<name>`` selects, print the reports, map the exit code.

    Exit codes: ``0`` every sample passed, ``1`` a failing report, ``2`` usage
    errors (no name, unknown task or sample, unknown/unavailable runner, bad
    ``--format``) or an unscorable sample (prompt render failure, judge error).
    """
    fmt = getattr(args, "format", None) or "text"
    if fmt not in _VALID_FORMATS:
        print(f"error: unknown --format {fmt!r}", file=sys.stderr)
        return 2

    settings = load_eval_settings(repo_root)
    judge_samples = judge_sample_count(args, default=settings.judge.samples or 1)
    if judge_samples is None:
        return 2

    name = getattr(args, "id", None)
    if not name:
        print("error: `playbook eval --run` requires a task or a sample id", file=sys.stderr)
        return 2

    samples = _select_samples(name, repo_root)
    if samples is None:
        return 2

    target = select_target(args, settings)
    runner = build_target_runner(target)
    if runner is None:
        return 2

    # --judge selects a Tier-2 judge from the judges entry-point group. Omitted =>
    # deterministic-only (no judge); judged [rubric] criteria are skipped.
    judge_name = getattr(args, "judge", None)
    judge: Judge | None = None
    if judge_name is not None:
        judge = build_judge(judge_name, settings.judge)
        if judge is None:
            return 2

    # Fail-fast is ON by default (a lost deterministic gate skips the costlier
    # judge tier); --full-scoring grades every check unconditionally.
    fail_fast = not bool(getattr(args, "full_scoring", False))
    head = getattr(args, "edition", None) == _EDITION_HEAD
    edition_dir = getattr(args, "edition_dir", None)
    if head and edition_dir is not None:
        print(f"error: --edition head and {EDITION_DIR_FLAG} exclude each other", file=sys.stderr)
        return 2
    edition_root = Path(edition_dir) if edition_dir is not None else None
    how = _SampleRun(runner, target, judge, judge_samples, fail_fast, head, edition_root)
    outcomes = [_run_one(sample, how) for sample in samples]
    results = [result for _, result in outcomes if result is not None]
    _print_results(results, fmt, one_sample=len(samples) == 1)
    return max(code for code, _ in outcomes)


def _run_one(sample: EvalSample, how: _SampleRun) -> tuple[int, SampleResult | None]:
    """Run and grade ``sample``: ``(0 or 1, result)``, or ``(2, None)`` when unscorable."""
    try:
        source = graded_source(sample, head=how.head, edition_root=how.edition_root)
        with tempfile.TemporaryDirectory(prefix="playbook-eval-") as tmp:
            result = how.runner.run_sample(
                sample,
                Path(tmp) / "scratch",
                judge=how.judge,
                judge_samples=how.judge_samples,
                fail_fast=how.fail_fast,
                edition=source.edition,
            )
        graded = graded_record(sample, source)
    except (PromptResolutionError, JudgeError, EditionError, UnscorableSuiteError) as exc:
        # Neither a pass nor a fail: no verdict exists, so never exit 0/1 here.
        print(f"error: sample {sample.id!r} could not be scored: {exc}", file=sys.stderr)
        return 2, None
    endpoint = how.target.endpoint
    result = replace(
        result,
        target=how.target.name,
        endpoint=endpoint.name if endpoint is not None else None,
        endpoint_fingerprint=endpoint.fingerprint if endpoint is not None else None,
        graded=graded,
    )
    # The sample verdict is ``result.passed`` — the single trial's verdict for a
    # non-aggregate sample (== report.passed), or the [aggregate] layer's pass/fail
    # when the sample aggregates across trials (every trial's verdict if that layer
    # was skipped). ``report.passed`` alone would be only the *first* trial's
    # verdict, so map the exit code off ``result.passed``.
    return (0 if result.passed else 1), result


def _print_results(results: list[SampleResult], fmt: str, *, one_sample: bool) -> None:
    """Print each report; ``--format json`` prints one object for one sample, else a list."""
    if fmt != "json":
        print("\n\n".join(format_sample_result_text(result) for result in results))
        return
    documents = [sample_result_to_dict(result) for result in results]
    payload = documents[0] if one_sample and documents else documents
    print(json.dumps(payload, indent=2, sort_keys=True))


def _select_samples(name: str, repo_root: Path) -> tuple[EvalSample, ...] | None:
    """The samples ``name`` selects, or ``None`` after an ``error:`` line.

    Uses the same task registry the read-only modes use (engine, plugin, overlay
    and repo-local samples), so ``--run`` sees exactly the sample set ``--list`` does.
    """
    registry = _task_registry(SyncContext.from_repo(repo_root))
    if registry is None:
        return None
    try:
        return registry.select(name)
    except TaskRegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
