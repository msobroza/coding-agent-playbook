"""``playbook`` / ``coding-agent-playbook`` entry point.

PR 10 wires every subcommand documented in SPEC §12 into the argparse
dispatcher. Each subcommand lives in its own module under
``coding_agent_playbook.commands`` and exposes a ``run(args) -> int`` that
returns the process exit code.

The dispatch pattern is the standard ``subparser.set_defaults(func=...)``
idiom: ``main()`` parses argv, then calls ``args.func(args)`` if a subcommand
was selected, else falls back to printing help.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__
from coding_agent_playbook.commands import check as check_cmd
from coding_agent_playbook.commands import eval as eval_cmd
from coding_agent_playbook.commands import import_harness as import_harness_cmd
from coding_agent_playbook.commands import init as init_cmd
from coding_agent_playbook.commands import metrics as metrics_cmd
from coding_agent_playbook.commands import render as render_cmd
from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.commands import validate as validate_cmd
from coding_agent_playbook.commands import validate_harness as validate_harness_cmd

if TYPE_CHECKING:
    from collections.abc import Sequence


# Canonical list of subcommand names. The argparse subparser
# declarations below must match this tuple — keeping it as a module-level
# constant lets tests assert the full surface in one place.
_SUBCOMMANDS: tuple[str, ...] = (
    "init",
    "sync",
    "check",
    "validate",
    "render",
    "eval",
    "metrics",
    "import-harness",
    "validate-harness",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playbook",
        description="coding-agent-playbook — multi-harness playbook engine.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"coding-agent-playbook {__version__}",
    )
    subcommands = parser.add_subparsers(dest="command")

    # playbook init
    init_p = subcommands.add_parser(_SUBCOMMANDS[0], help="bootstrap a fresh repo (SPEC §12.1)")
    init_p.add_argument("--repo-root", help="repo to initialise (defaults to cwd)")
    init_p.add_argument("--non-interactive", action="store_true")
    init_p.add_argument("--name", help="project name (required in non-interactive mode)")
    init_p.add_argument("--kind", help="project kind (required in non-interactive mode)")
    init_p.add_argument("--description", default="")
    init_p.add_argument("--adapters", help="comma-separated adapter names")
    init_p.add_argument("--overlays", help="comma-separated overlay package names")
    init_p.set_defaults(func=init_cmd.run)

    # playbook sync
    sync_p = subcommands.add_parser(_SUBCOMMANDS[1], help="regenerate all artifacts (SPEC §12.2)")
    sync_p.add_argument("--repo-root", help="repo to sync (defaults to cwd)")
    sync_p.add_argument(
        "--check",
        action="store_true",
        help="verify against the lockfile without writing (SPEC §12.3)",
    )
    sync_p.set_defaults(func=sync_cmd.run)

    # playbook check
    check_p = subcommands.add_parser(_SUBCOMMANDS[2], help="diagnostic dump (SPEC §12.4)")
    check_p.add_argument("--repo-root", help="repo to check (defaults to cwd)")
    check_p.add_argument(
        "--refresh",
        action="store_true",
        help="re-run detector and persist facts to detector_cache (SPEC §12.5)",
    )
    check_p.set_defaults(func=check_cmd.run)

    # playbook validate
    validate_p = subcommands.add_parser(_SUBCOMMANDS[3], help="cross-reference checks (SPEC §12.6)")
    validate_p.add_argument("--repo-root", help="repo to validate (defaults to cwd)")
    validate_p.set_defaults(func=validate_cmd.run)

    # playbook render
    render_p = subcommands.add_parser(_SUBCOMMANDS[4], help="render one artifact (SPEC §12.7)")
    render_p.add_argument("id", help="artifact id to render")
    render_p.add_argument("--repo-root", help="repo to render against (defaults to cwd)")
    render_p.add_argument("--format", help="format alias or full name")
    render_p.add_argument("--show-source", action="store_true")
    render_p.add_argument("--show-rules", action="store_true")
    render_p.set_defaults(func=render_cmd.run)

    # playbook eval (PR 11 enumeration; PR R1d adds --run)
    eval_p = subcommands.add_parser(
        _SUBCOMMANDS[5], help="eval enumeration + `--run` a task (SPEC §12.8, §15)"
    )
    # Every other subcommand exposes ``--repo-root <path>`` for testability
    # and so users can run against a non-cwd checkout; eval gets the same
    # surface for parity. The command runner in ``commands/eval.py`` already
    # falls back to ``Path.cwd()`` when this is absent.
    eval_p.add_argument(
        "--repo-root", help="repo to enumerate eval tasks against (defaults to cwd)"
    )
    eval_group = eval_p.add_mutually_exclusive_group()
    eval_group.add_argument("--list", action="store_true")
    eval_group.add_argument("--show", help="show one task by id")
    eval_p.add_argument("id", nargs="?", help="task id (enumerate, or run with --run)")
    # PR R1d — execute one task end-to-end and grade it through the unified
    # EvaluationReport. Whether execution evaluators run is the task's own
    # [metrics] decision, so there is intentionally no --run-tests flag here.
    eval_p.add_argument(
        "--run",
        action="store_true",
        help="execute the task <id> through a runner and grade it (SPEC §15)",
    )
    eval_p.add_argument(
        "--runner",
        help="runner name from the coding_agent_playbook.runners group "
        "(default: claude_code; use 'fake' for a hermetic no-op run)",
    )
    # PR R2 — judged [rubric] scoring. --judge selects a Tier-2 judge from the
    # coding_agent_playbook.judges group (e.g. 'llm', opt-in/CLI-gated); omitted
    # means deterministic-only. --samples is the per-criterion average count.
    eval_p.add_argument(
        "--judge",
        help="judge name from the coding_agent_playbook.judges group to score "
        "[rubric] criteria (e.g. 'llm'); omit for a deterministic-only run",
    )
    eval_p.add_argument(
        "--samples",
        type=int,
        help="per-criterion judge samples to average (default: 1)",
    )
    # By default --run is fail-fast: a lost deterministic gate skips the costlier
    # judge tier (saving an LLM call). --full-scoring grades every check.
    eval_p.add_argument(
        "--full-scoring",
        action="store_true",
        help="grade every check even after the gate is lost (disables fail-fast; "
        "scores the judge tier regardless of a failing deterministic check)",
    )
    eval_p.add_argument(
        "--format",
        choices=("text", "json"),
        help="--run output format (default: text)",
    )
    eval_p.set_defaults(func=eval_cmd.run)

    # playbook metrics (PR-M Track M3 — standalone static code-quality gate)
    metrics_p = subcommands.add_parser(
        _SUBCOMMANDS[6],
        help="static code-quality gate (cyclomatic complexity, MI, ...) (PR-M)",
    )
    metrics_p.add_argument(
        "paths",
        nargs="*",
        help="Python files or directories to measure (default: the repo's src/ dir)",
    )
    metrics_p.add_argument(
        "--baseline",
        help="non-regression baseline: 'git:<ref>' (via git show) or a directory path",
    )
    metrics_p.add_argument(
        "--mode",
        choices=("regression", "absolute", "both"),
        help="comparison mode (default: from [metrics] config, else 'regression')",
    )
    metrics_p.add_argument(
        "--strict",
        action="store_true",
        help="promote warnings to gate failures (non-zero exit)",
    )
    metrics_p.add_argument(
        "--run-tests",
        dest="run_tests",
        action="store_true",
        help="also run the execution evaluators (test_pass_rate, coverage): "
        "shells out to the target's pytest (opt-in, has side effects)",
    )
    metrics_p.add_argument(
        "--test-cmd",
        dest="test_cmd",
        help="override the test command used by --run-tests (a shell-style "
        "string, split with shlex; default: python -m pytest with junit+cov XML)",
    )
    metrics_p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    metrics_p.add_argument("--repo-root", help="repo to measure against (defaults to cwd)")
    metrics_p.set_defaults(func=metrics_cmd.run)

    # playbook import-harness (PR H Track H3)
    import_p = subcommands.add_parser(
        _SUBCOMMANDS[7], help="import an Agent Harness tree into canonical artifacts"
    )
    import_p.add_argument("path", nargs="?", help="path to the harness root (contains HARNESS.md)")
    import_p.add_argument(
        "--into",
        help="overlay directory to write canonical artifacts into (defaults to ./playbook)",
    )
    import_p.set_defaults(func=import_harness_cmd.run)

    # playbook validate-harness (PR H Track H4)
    validate_harness_p = subcommands.add_parser(
        _SUBCOMMANDS[8],
        help="lint an Agent Harness tree (structural checks, harnesses-ref-equivalent)",
    )
    validate_harness_p.add_argument(
        "path", nargs="?", help="path to the harness root (contains HARNESS.md)"
    )
    validate_harness_p.add_argument(
        "--strict",
        action="store_true",
        help="promote warnings (missing routing file / content description) to errors",
    )
    validate_harness_p.set_defaults(func=validate_harness_cmd.run)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
