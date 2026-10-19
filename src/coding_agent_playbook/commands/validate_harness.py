"""``playbook validate-harness``: exit codes and the report of ``agent_harness.lint`` (SPEC §12.10)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.agent_harness.lint import lint_harness
from coding_agent_playbook.agent_harness.models import NotAHarnessError
from coding_agent_playbook.agent_harness.parser import parse_harness

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.agent_harness.lint import HarnessFindings

NAME: Final = "validate-harness"
HELP: Final = "lint an Agent Harness tree (structural checks, harnesses-ref-equivalent)"
_STRICT_HELP: Final = "promote warnings (missing routing file / content description) to errors"


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook validate-harness [PATH] [--strict]`` (SPEC §12.10)."""
    parser.add_argument("path", nargs="?", help="path to the harness root (contains HARNESS.md)")
    parser.add_argument("--strict", action="store_true", help=_STRICT_HELP)


def run(args: argparse.Namespace) -> int:
    """``playbook validate-harness <path> [--strict]``: 0 passed, 1 failed, 2 usage error."""
    root = Path(args.path) if getattr(args, "path", None) else None
    if root is None or not root.is_dir():
        problem = (
            f"{root} is not a directory" if root else "validate-harness requires a harness path"
        )
        print(f"error: {problem}", file=sys.stderr)
        return 2
    try:
        tree = parse_harness(root)
    except (NotAHarnessError, ValueError) as exc:
        # Deliberately 1, unlike import-harness's usage error 2: a missing or malformed
        # HARNESS.md is precisely the failure a validator exists to report.
        print(f"ERROR {root}: {exc}\nvalidation failed with 1 error(s), 0 warning(s)")
        return 1
    return _report(lint_harness(tree), strict=bool(getattr(args, "strict", False)))


def _report(findings: HarnessFindings, *, strict: bool) -> int:
    """Errors to stdout, warnings to stderr, then the summary line; return the exit code."""
    for error in findings.errors:
        print(f"ERROR {error.path}: {error.message}")
    for warning in findings.warnings:
        print(f"warning: {warning.path}: {warning.message}", file=sys.stderr)
    if not findings.failed(strict=strict):
        print(f"OK harness validated ({len(findings.warnings)} warning(s))")
        return 0
    promoted = "" if findings.errors else " (warnings promoted by --strict)"
    counts = f"{len(findings.errors)} error(s), {len(findings.warnings)} warning(s)"
    print(f"validation failed with {counts}{promoted}")
    return 1
