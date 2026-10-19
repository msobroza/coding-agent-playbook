"""``playbook gate-scan`` — gate-weakening-guard's off-workstation twin (specs/prK-hook-pack.md §E.2).

Scans a commit range with the same :func:`coding_agent_playbook.hook_runtime.judges.gate_weakening.scan`
the ``gate-integrity`` Stop stage uses, so CI and the hook share one policy:

- ``--range A..B`` diffs ``A`` to ``B``; ``A...B`` diffs their merge base to
  ``B``; without ``--range`` the range is ``<merge base with the default
  branch>..HEAD`` (``_git_base``).
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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._git_base import open_git, resolve_merge_base
from coding_agent_playbook.hook_runtime.git import GitError
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

    from coding_agent_playbook.hook_runtime.git import GitPort

__all__ = ["ScanRange", "load_policy", "resolve_range", "run", "scan_range"]

CONFIG_FILE: Final = ".coding-agent-playbook.toml"
HOOK_ID: Final = "gate-weakening-guard"
_FIX_HINT: Final = "Fix the root cause, or justify each line inline with a trailing `# <reason>`."


@dataclass(frozen=True, slots=True)
class ScanRange:
    """The revisions a scan diffs (``base`` to ``head``) and how to name the range.

    Example: ``ScanRange("HEAD~1", "HEAD", "HEAD~1..HEAD")``.
    """

    base: str
    head: str
    label: str


def run(args: argparse.Namespace, *, git: GitPort | None = None) -> int:
    """Scan ``args.rev_range`` and print the findings; returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["gate-scan", "--range", "HEAD~1..HEAD"]))  # doctest: +SKIP
        1
    """
    repo_root = Path(args.repo_root or ".").resolve()
    try:
        port = git if git is not None else open_git(repo_root)
        span = resolve_range(port, args.rev_range)
        report = scan_range(port, span, load_policy(port, span.base, repo_root))
    except (GitError, ValueError) as exc:  # GitBaseError and policy errors are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(_json(report, span) if args.format == "json" else _text(report, span))
    return report.exit_code


def resolve_range(git: GitPort, text: str | None) -> ScanRange:
    """``A..B``, ``A...B`` (from their merge base) or, for ``None``, the default range.

    An empty side means ``HEAD``. Raises ``ValueError`` for any other form.

    Example::

        >>> resolve_range(git, "HEAD~1..HEAD")  # doctest: +SKIP
        ScanRange(base='HEAD~1', head='HEAD', label='HEAD~1..HEAD')
    """
    if text is None:
        base = resolve_merge_base(git, None)
        return ScanRange(base.sha, "HEAD", f"{base.sha[:12]}..HEAD")
    if "..." in text:
        left, _, right = text.partition("...")
        head = right or "HEAD"
        return ScanRange(_symmetric_base(git, left or "HEAD", head), head, text)
    if ".." in text:
        left, _, right = text.partition("..")
        return ScanRange(left or "HEAD", right or "HEAD", text)
    raise ValueError(f"--range {text!r}: expected A..B or A...B (revisions)")


def load_policy(git: GitPort, base: str, repo_root: Path) -> ScanPolicy:
    """The engine policy extended by ``[hooks.gate-weakening-guard]`` as committed at ``base``.

    Example::

        >>> load_policy(git, "HEAD~1", Path(".")).source_roots  # doctest: +SKIP
        ('src',)
    """
    roots = ("src",) if (repo_root / "src").is_dir() else ("",)
    table = _hook_table(git.show(base, CONFIG_FILE))
    return policy_from_table(table, ScanPolicy(source_roots=roots))


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


def _symmetric_base(git: GitPort, left: str, right: str) -> str:
    sha = git.merge_base(left, right)
    if sha is None:
        raise ValueError(f"--range {left}...{right}: the two share no history")
    return sha


def _hook_table(raw: bytes | None) -> dict[str, object]:
    """The ``[hooks.gate-weakening-guard]`` table of a committed config, ``{}`` when absent."""
    import tomllib

    if raw is None:
        return {}
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{CONFIG_FILE} at the range base is not valid TOML: {exc}") from None
    hooks = doc.get("hooks", {})
    table = hooks.get(HOOK_ID, {}) if isinstance(hooks, dict) else {}
    if not isinstance(table, dict):
        raise ValueError(f"[hooks.{HOOK_ID}] = {table!r} in {CONFIG_FILE}: expected a table")
    return table


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
