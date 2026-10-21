"""``playbook eval`` — Tier 0 enumeration + the R1 live runner (SPEC §12.8, §15).

``playbook eval`` is both a read-only enumeration of the prompt-to-sample graph and
— with ``--run`` (PR R1d) — the entry point that *executes* one sample end-to-end
through a :class:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner` and grades it
via the unified PR-M :class:`EvaluationReport`.

Sub-modes:

- ``playbook eval --list`` (also the default when no arg is given): tree-shape
  coverage report across every prompt, with per-sample summary lines.
- ``playbook eval --show <id>``: detailed dump for one sample — sections from
  SPEC §12.8 (Sample / Source / Prompt under test / Description / Setup /
  Invocation / Expected / Rubric).
- ``playbook eval <id>`` (no ``--run``): prints how to run the sample. Exits 0 if
  the sample is known, exits 1 if it isn't (so typos still surface).
- ``playbook eval <id> --run [--runner NAME] [--judge NAME] [--judge-samples N]
  [--format text|json]``: load the sample, select the runner ``NAME`` from the
  ``coding_agent_playbook.runners`` entry-point group (default ``claude_code``),
  run it in a throwaway scratch dir, and render ``result.report`` (reusing
  ``commands/metrics.py``'s text/json renderer). Exits ``0`` on a passing report,
  ``1`` on a failing one, ``2`` on usage errors (unknown sample,
  unknown/unavailable runner, unknown/unavailable judge, bad ``--format``) and
  when the sample cannot be scored at all (its prompt fails to render, or the judge
  gives no score) — that is neither a pass nor a fail.

  ``--judge`` (R2) selects a Tier-2 judge from the
  ``coding_agent_playbook.judges`` group (``llm`` ships, opt-in/CLI-gated) so the
  sample's ``[rubric]`` criteria are scored too; omitted ⇒ deterministic-only (no
  judge). ``--judge-samples N`` (default 1) is how many times the judge scores each
  rubric criterion before averaging; it is not a count of eval samples, and a
  count below 1 is a usage error (exit ``2``). The old
  ``--samples N`` spelling is a deprecated alias for one release (D80): hidden
  from ``--help``, it still works, prints one stderr line naming
  ``--judge-samples``, and passing both flags is a usage error (exit ``2``).

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
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._eval_enumerate import (
    _DEFAULT_RUNNER,
    _print_list,
    _print_run_hint,
    _print_show,
)
from coding_agent_playbook.evals import registry
from coding_agent_playbook.evals.judge import JudgeError
from coding_agent_playbook.evals.prompting import PromptResolutionError
from coding_agent_playbook.evals.report_format import (
    format_sample_result_text,
    sample_result_to_dict,
)
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    from coding_agent_playbook.evals.judge import Judge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner
    from coding_agent_playbook.evals.sample import EvalSample


NAME: Final = "eval"
HELP: Final = "eval enumeration + `--run` a sample (SPEC §12.8, §15)"

_VALID_FORMATS = ("text", "json")

# D80: the old --samples spelling stays one release as a hidden alias; it is
# removed in the release after v0.21. Printed (not warnings.warn): pytest runs
# with filterwarnings = error.
_SAMPLES_DEPRECATION: Final = (
    "warning: --samples is deprecated and will be removed in the next release; use --judge-samples"
)
_BOTH_SAMPLE_FLAGS: Final = (
    "error: pass --judge-samples or its deprecated alias --samples, not both"
)


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
    parser.add_argument("id", nargs="?", help="sample id (enumerate, or run with --run)")
    # PR R1d — execute one sample end-to-end and grade it through the unified
    # EvaluationReport. Whether execution evaluators run is the sample's own
    # [metrics] decision, so there is intentionally no --run-tests flag here.
    parser.add_argument(
        "--run",
        action="store_true",
        help="execute the sample <id> through a runner and grade it (SPEC §15)",
    )
    parser.add_argument(
        "--runner",
        help="runner name from the coding_agent_playbook.runners group "
        "(default: claude_code; use 'fake' for a hermetic no-op run)",
    )
    _configure_scoring(parser)


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

    # ``--run`` is the only path that *executes* a sample; it has its own loading
    # (one sample by id) so it never pays for the full list+resolve unless the sample
    # is missing (then it falls through to the SyncContext for a helpful error).
    if getattr(args, "run", False):
        return _run_sample_cli(args, repo_root)

    ctx = SyncContext.from_repo(repo_root)
    samples = ctx.artifact_source.list_eval_samples()

    if getattr(args, "list", False):
        return _print_list(ctx.prompts_resolved, samples)
    show_id = getattr(args, "show", None)
    if show_id:
        return _print_show(show_id, samples, ctx.prompts_resolved)
    bare_id = getattr(args, "id", None)
    if bare_id:
        return _print_run_hint(bare_id, samples, ctx.prompts_resolved)
    # No flag — default to --list (matches the "helpful empty invocation" rule).
    return _print_list(ctx.prompts_resolved, samples)


# --------------------------------------------------------------------------- #
# --run — execute one sample through a HarnessRunner and grade it (PR R1d)
# --------------------------------------------------------------------------- #


def _run_sample_cli(args: argparse.Namespace, repo_root: Path) -> int:
    """Load + run one sample, render its report, map ``passed`` to the exit code.

    Exit codes: ``0`` pass, ``1`` failing report, ``2`` usage errors (no sample id,
    unknown sample, unknown/unavailable runner, bad ``--format``) or an unscorable
    sample (prompt render failure, judge error).
    """
    fmt = getattr(args, "format", None) or "text"
    if fmt not in _VALID_FORMATS:
        print(f"error: unknown --format {fmt!r}", file=sys.stderr)
        return 2

    judge_samples = _judge_samples(args)
    if judge_samples is None:
        return 2

    sample_id = getattr(args, "id", None)
    if not sample_id:
        print("error: `playbook eval --run` requires a sample id", file=sys.stderr)
        return 2

    sample = _load_sample(sample_id, repo_root)
    if sample is None:
        print(f"error: no eval sample with id {sample_id!r}", file=sys.stderr)
        return 2

    runner_name = getattr(args, "runner", None) or _DEFAULT_RUNNER
    runner_cls = registry.load_runner_class(runner_name)
    if runner_cls is None:
        available = ", ".join(registry.available_runner_names()) or "(none registered)"
        print(
            f"error: unknown --runner {runner_name!r}; registered runners: {available}",
            file=sys.stderr,
        )
        return 2
    if not _runner_available(runner_cls):
        print(
            f"error: runner {runner_name!r} is unavailable in this environment "
            "(its CLI/SDK is not installed). Try `--runner fake` for a hermetic "
            "no-op run, or install the agent CLI.",
            file=sys.stderr,
        )
        return 2

    # --judge selects a Tier-2 judge from the judges entry-point group. Omitted =>
    # deterministic-only (no judge); judged [rubric] criteria are skipped.
    judge_name = getattr(args, "judge", None)
    judge: Judge | None = None
    if judge_name is not None:
        judge_cls = registry.load_judge_class(judge_name)
        if judge_cls is None:
            available = ", ".join(registry.available_judge_names()) or "(none registered)"
            print(
                f"error: unknown --judge {judge_name!r}; registered judges: {available}",
                file=sys.stderr,
            )
            return 2
        if not judge_cls.available():
            print(
                f"error: judge {judge_name!r} is unavailable in this environment "
                "(its CLI/SDK is not installed). Omit `--judge` for a "
                "deterministic-only run, or install the judge's CLI.",
                file=sys.stderr,
            )
            return 2
        judge = judge_cls()

    # Fail-fast is ON by default (a lost deterministic gate skips the costlier
    # judge tier); --full-scoring grades every check unconditionally.
    fail_fast = not bool(getattr(args, "full_scoring", False))

    runner = runner_cls()
    try:
        with tempfile.TemporaryDirectory(prefix="playbook-eval-") as tmp:
            result = runner.run_sample(
                sample,
                Path(tmp) / "scratch",
                judge=judge,
                judge_samples=judge_samples,
                fail_fast=fail_fast,
            )
    except (PromptResolutionError, JudgeError) as exc:
        # Neither a pass nor a fail: no verdict exists, so never exit 0/1 here.
        print(f"error: sample {sample_id!r} could not be scored: {exc}", file=sys.stderr)
        return 2

    if fmt == "json":
        print(json.dumps(sample_result_to_dict(result), indent=2, sort_keys=True))
    else:
        print(format_sample_result_text(result))

    # The sample verdict is ``result.passed`` — the single trial's verdict for a
    # non-aggregate sample (== report.passed), or the [aggregate] layer's pass/fail
    # when the sample aggregates across trials (every trial's verdict if that layer
    # was skipped). ``report.passed`` alone would be only the *first* trial's
    # verdict, so map the exit code off ``result.passed``.
    return 0 if result.passed else 1


def _judge_samples(args: argparse.Namespace) -> int | None:
    """The per-criterion judge sample count, or ``None`` on a usage error.

    Reads ``--judge-samples`` and its deprecated ``--samples`` alias (D80): the
    alias prints one stderr line naming ``--judge-samples``; both flags at once, or
    a count below 1, print an error and return ``None`` (the caller exits ``2``).
    A non-positive count is rejected rather than floored so a typo never silently
    changes what gets graded.

    Example::

        >>> _judge_samples(argparse.Namespace(judge_samples=3, deprecated_samples=None))
        3
    """
    new = getattr(args, "judge_samples", None)
    old = getattr(args, "deprecated_samples", None)
    if new is not None and old is not None:
        print(_BOTH_SAMPLE_FLAGS, file=sys.stderr)
        return None
    if old is not None:
        print(_SAMPLES_DEPRECATION, file=sys.stderr)
    count: int | None = old if old is not None else new
    if count is not None and count < 1:
        print(f"error: --judge-samples must be >= 1, got {count}", file=sys.stderr)
        return None
    return count or 1


def _load_sample(sample_id: str, repo_root: Path) -> EvalSample | None:
    """Resolve ``sample_id`` to its :class:`EvalSample`, or ``None`` if absent.

    Loads via the same :class:`SyncContext` enumeration the read-only modes use
    (engine + overlay + repo-local samples), so ``--run`` sees exactly the sample set
    ``--list`` does.
    """
    ctx = SyncContext.from_repo(repo_root)
    for sample in ctx.artifact_source.list_eval_samples():
        if sample.id == sample_id:
            return sample
    return None


def _runner_available(runner_cls: type[HarnessRunner]) -> bool:
    """Whether ``runner_cls`` can run here.

    Runners may expose an ``available()`` classmethod (the real
    ``ClaudeCodeRunner`` does, guarding on its CLI being on ``PATH``). A runner
    without one — the hermetic ``FakeRunner`` — is always available.
    """
    guard = getattr(runner_cls, "available", None)
    if guard is None:
        return True
    return bool(guard())
