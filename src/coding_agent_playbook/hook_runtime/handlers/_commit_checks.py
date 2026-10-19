"""What a ``git commit`` will record, for git-commit-push-policy-guard's data rows (specs/prK-hook-pack.md §E.4).

- :func:`message_verdict` judges the message (``git_command.commit_message_sources``)
  with the trailer rows of ``security.commit_trailers``, the same judge the
  ``playbook check-commit-trailers`` commit-msg twin runs; a message that
  cannot be read asks, but only while a trailer row is configured.
- :func:`staged_paths` lists the paths the commit records: the index (``git
  status`` column X), plus tracked changes for ``commit -a`` and the pathspecs
  of ``git commit <paths>``.

Both run only on a ``git commit`` segment, and only when the rows they serve
are set, so a repository without data rows never spawns git for them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.shell.git_command import (
    Uninspectable,
    commit_message_sources,
)
from coding_agent_playbook.hook_runtime.shell.git_options import git_args
from coding_agent_playbook.security.commit_trailers import GitPolicy, commit_msg_violations

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.git import GitPort
    from coding_agent_playbook.hook_runtime.shell.git_command import GitInvocation

    type Verdict = tuple[Decision, str, str]

__all__ = ["message_verdict", "staged_paths"]

_VIOLATIONS_CHARS: Final = 240
#: Status columns that mean "nothing staged here" (X) or "no tracked change" (Y).
_UNSTAGED_X: Final = frozenset(" ?!")
_TRACKED_CHANGE_Y: Final = frozenset("MDT")


def message_verdict(
    inv: GitInvocation, repo: RepoInfo, config: Mapping[str, Any]
) -> Verdict | None:
    """Deny a message that breaks a trailer row; ask when it cannot be read; else ``None``.

    Example::

        >>> message_verdict(inv, repo, {"forbid_trailers": ["Co-Authored-By"]})
        ... # doctest: +SKIP
        (<Decision.DENY: 'deny'>, 'trailers', 'Blocked: ... CP401 forbidden trailer ...')
    """
    policy = GitPolicy.from_config(config)
    if not policy.has_rows:
        return None
    sources = commit_message_sources(inv, root=repo.worktree_root)
    if isinstance(sources, Uninspectable):
        reason = (
            f"This repo has commit-trailer rules, but {sources.why}.\n"
            "Pass the message with -m or a heredoc so it can be checked, or confirm."
        )
        return Decision.ASK, "message_uninspectable", reason
    lines = dict.fromkeys(v for m in sources for v in commit_msg_violations(m, policy))
    if not lines:
        return None
    shown = clip(clean_text("; ".join(lines)), _VIOLATIONS_CHARS)
    reason = (
        f"Blocked: the commit message breaks this repo's trailer rules ({shown}).\n"
        "Fix the message's trailers and commit again."
    )
    return Decision.DENY, "trailers", reason


def staged_paths(inv: GitInvocation, git: GitPort) -> list[str]:
    """The repo-relative paths ``inv`` (a ``git commit``) will record.

    Example::

        >>> staged_paths(parse_git(seg("git commit -am x")), git)  # doctest: +SKIP
        ['src/app.py', '.env']
    """
    parsed = git_args(inv.args, "commit")
    every_change = parsed.has("a", "--all")
    paths = [
        path
        for xy, path in git.porcelain_status()
        if xy[0] not in _UNSTAGED_X or (every_change and xy[1] in _TRACKED_CHANGE_Y)
    ]
    return [*paths, *parsed.positionals, *parsed.pathspecs]
