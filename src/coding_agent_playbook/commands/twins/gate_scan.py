"""``playbook gate-scan`` — gate-weakening-guard's off-workstation twin (specs/prK-hook-pack.md §E.2).

Scans a commit range with the same :func:`coding_agent_playbook.hook_runtime.judges.gate_weakening.scan`
the ``gate-integrity`` Stop stage uses, so CI and the hook share one policy:

- ``--range A..B`` diffs ``A`` to ``B``; ``A...B`` diffs their merge base to
  ``B``; without ``--range`` the range is ``<merge base with the default
  branch>..HEAD`` (``_git_scope``).
- The policy is the engine default extended by the
  ``[hooks.gate-weakening-guard]`` table **as committed at the range's base**:
  a change cannot loosen the rules it is judged by (a new pattern applies once
  merged). ``.coding-agent-playbook.local.toml`` never applies (§B.1).
- Source roots: ``src`` when the checkout has one, else the repo root.

Exit codes: 0 clean (justified notes only), 1 blocking findings, 2 a usage
error, an unresolvable base, a malformed policy table, or a git failure.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands.twins._git_scope import (
    RANGE_FLAG_HELP,
    ScanRange,
    open_git,
    resolve_range,
)
from coding_agent_playbook.commands.twins._runner import TwinOutcome, run_twin
from coding_agent_playbook.config.files import CONFIG_FILENAME, CommittedDocument
from coding_agent_playbook.hook_runtime.judges.gate_weakening import (
    ConfigPair,
    ScanPolicy,
    ScanReport,
    is_config_path,
    policy_from_table,
    scan,
)

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort

__all__ = ["HELP", "NAME", "configure", "load_policy", "run", "scan_range"]

NAME: Final = "gate-scan"
HELP: Final = "flag gate-weakening changes in a commit range (prK §E.2)"
HOOK_ID: Final = "gate-weakening-guard"
_FIX_HINT: Final = "Fix the root cause, or justify each line inline with a trailing `# <reason>`."


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook gate-scan [--range A..B] [--format F]`` (SPEC §12.14, prK §E.2).

    Example::

        >>> configure(argparse.ArgumentParser(prog="playbook gate-scan"))  # doctest: +SKIP
    """
    parser.add_argument(
        "--range",
        dest="rev_range",
        help=RANGE_FLAG_HELP,
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--repo-root", help="repo to scan (defaults to cwd)")


def run(args: argparse.Namespace, *, git: GitPort | None = None) -> int:
    """Scan ``args.rev_range`` and print the findings; returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["gate-scan", "--range", "HEAD~1..HEAD"]))  # doctest: +SKIP
        1
    """
    return run_twin(args.repo_root, lambda root: _outcome(args, root, git))


def _outcome(args: argparse.Namespace, repo_root: Path, git: GitPort | None) -> TwinOutcome:
    port = git if git is not None else open_git(repo_root)
    span = resolve_range(port, args.rev_range)
    report = scan_range(port, span, load_policy(port, span.base, repo_root))
    text = _json(report, span) if args.format == "json" else _text(report, span)
    return TwinOutcome(report.exit_code, text)


def load_policy(git: GitPort, base: str, repo_root: Path) -> ScanPolicy:
    """The engine policy extended by ``[hooks.gate-weakening-guard]`` as committed at ``base``.

    Example::

        >>> load_policy(git, "HEAD~1", Path(".")).source_roots  # doctest: +SKIP
        ('src',)
    """
    roots = ("src",) if (repo_root / "src").is_dir() else ("",)
    raw = git.show(base, CONFIG_FILENAME)
    committed = CommittedDocument.decode(raw, where=f"{CONFIG_FILENAME} at {base}")
    return policy_from_table(committed.table("hooks", HOOK_ID), ScanPolicy(source_roots=roots))


def scan_range(git: GitPort, span: ScanRange, policy: ScanPolicy) -> ScanReport:
    """Scan the diff of ``span`` and its changed TOML config files.

    Example::

        >>> scan_range(git, ScanRange("HEAD~1", "HEAD", "HEAD~1..HEAD"), ScanPolicy())  # doctest: +SKIP
        ScanReport(findings=(...))
    """
    diff = git.diff_range(span.base, span.head)
    pairs = [
        ConfigPair(path, _decoded(git.show(span.base, path)), _decoded(git.show(span.head, path)))
        for path in diff.paths
        if is_config_path(path)
    ]
    return scan(diff.added, diff.removed, pairs, policy)


def _decoded(raw: bytes | None) -> str | None:
    return None if raw is None else raw.decode("utf-8", errors="replace")


def _text(report: ScanReport, span: ScanRange) -> str:
    lines = [finding.line_text() for finding in report.blocking]
    lines += [f"note: {finding.line_text()}" for finding in report.notes if finding.justified]
    if report.blocking:
        noted = len(report.findings) - len(report.blocking)
        lines += [
            _FIX_HINT,
            f"gate-scan {span.label}: {len(report.blocking)} blocking, {noted} noted",
        ]
    else:
        lines.append(f"gate-scan {span.label}: clean ({len(report.findings)} noted)")
    return "\n".join(lines)


def _json(report: ScanReport, span: ScanRange) -> str:
    document = {
        "range": span.label,
        "base": span.base,
        "head": span.head,
        "findings": [finding.to_json() for finding in report.findings],
        "blocking": len(report.blocking),
        "exit": report.exit_code,
    }
    return json.dumps(document, indent=2, ensure_ascii=False)
