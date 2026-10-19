"""``playbook check-deps`` — dependency-allowlist-guard's off-workstation twin (specs/prK-hook-pack.md §E.4).

The hook asks before the agent adds a dependency; this twin judges the change
itself, the human's included, in CI (SPEC §17.2 assigns enforcement to "a
separate package-check step"). Each manifest that changed since the base
(``--base REF``, default the default branch, through its merge base with
``HEAD``) or is untracked is read at the base (``git show``) and in the working
tree, and only NEWLY declared names and indexes count (``_manifest_diff``,
PEP 503 names), so existing dependencies are grandfathered.

The rules are the hook's own (``_dependency_tiers``), from its merged config
whatever ``[hooks]`` says (``policy``): a name outside the overlay
``allowlist`` and an index other than ``required_index`` are deny-class; index
mixing follows ``index_mode``; without an allowlist the new names are listed.
Output: one ``<path>: <deny|ask> <rule>: <detail>`` line per finding.

Exit codes: 0 no deny-class finding, 1 a deny-class finding, 2 a git or config error.
"""

from __future__ import annotations

import posixpath
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands.twins._git_scope import open_git, resolve_merge_base
from coding_agent_playbook.commands.twins.policy import dependency_twin_config
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.git import GitError
from coding_agent_playbook.hook_runtime.handlers._dependency_tiers import (
    DependencyPolicy,
    Finding,
    dependency_policy,
    index_finding,
    name_findings,
)
from coding_agent_playbook.hook_runtime.handlers._manifest_diff import (
    added_indexes,
    added_names,
    manifest_kind,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.git import GitPort
    from coding_agent_playbook.hook_runtime.handlers._manifest_diff import ManifestKind

__all__ = ["finding_lines", "manifest_findings", "run"]

_MANIFEST_LIMIT: Final = 1024 * 1024


def run(args: argparse.Namespace, *, git: GitPort | None = None) -> int:
    """Check the manifests changed since the base; returns 0, 1 or 2.

    Example::

        >>> run(build_parser().parse_args(["check-deps", "--base", "origin/main"]))
        ... # doctest: +SKIP
        0
    """
    repo_root = Path(args.repo_root or ".").resolve()
    try:
        policy = dependency_policy({}, dependency_twin_config(repo_root))
        port = git if git is not None else open_git(repo_root)
        base = resolve_merge_base(port, args.base).sha
        found = manifest_findings(port, repo_root, base, policy)
    except (GitError, ValueError, OSError) as exc:  # GitBaseError is a ValueError
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for line in finding_lines(found):
        print(line)
    return 1 if any(finding.decision is Decision.DENY for _, finding in found) else 0


def manifest_findings(
    git: GitPort, repo_root: Path, base: str, policy: DependencyPolicy
) -> list[tuple[str, Finding]]:
    """``(path, finding)`` for every manifest changed since ``base`` (or untracked).

    Example::

        >>> manifest_findings(git, root, "abc123", policy)  # doctest: +SKIP
        [('pyproject.toml', Finding(decision=<Decision.ASK: 'ask'>, rule='new_dependency', ...))]
    """
    paths = sorted({*git.diff_worktree(base).paths, *git.ls_untracked()})
    found: list[tuple[str, Finding]] = []
    for rel in paths:
        kind = manifest_kind(posixpath.basename(rel))
        after = _worktree_text(repo_root / rel) if kind is not None else None
        if kind is None or after is None:
            continue  # not a manifest, or deleted in the working tree
        before = _decoded(git.show(base, rel))
        found.extend((rel, finding) for finding in _judged(kind, before, after, rel, policy))
    return found


def finding_lines(found: Iterable[tuple[str, Finding]]) -> list[str]:
    """``<path>: <deny|ask> <rule>: <detail>`` per finding (names, or the hook's first line).

    Example::

        >>> finding_lines([("pyproject.toml", Finding(Decision.ASK, "new_dependency",
        ...                                            names=("rich",)))])
        ['pyproject.toml: ask new_dependency: rich']
    """
    lines: list[str] = []
    for path, finding in found:
        detail = ", ".join(finding.names) if finding.names else finding.lines[0]
        lines.append(f"{path}: {finding.decision.value} {finding.rule}: {detail}")
    return lines


def _judged(
    kind: ManifestKind, before: str | None, after: str, rel: str, policy: DependencyPolicy
) -> list[Finding]:
    added = added_names(kind, before, after)
    if added is None:
        line = f"{rel} does not parse, so its dependencies cannot be checked."
        return [Finding(Decision.ASK, "unreadable_manifest", (line,))]
    new_indexes = added_indexes(kind, before, after)
    index = index_finding(new_indexes, policy, via=rel) if new_indexes else None
    return [*filter(None, [index]), *name_findings(sorted(added), policy, python=True)]


def _worktree_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()[: _MANIFEST_LIMIT + 1]
    except (FileNotFoundError, IsADirectoryError):
        return None
    return data[:_MANIFEST_LIMIT].decode("utf-8", errors="replace")


def _decoded(data: bytes | None) -> str | None:
    return None if data is None else data[:_MANIFEST_LIMIT].decode("utf-8", errors="replace")
