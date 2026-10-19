"""git-commit-push-policy-guard: identity, authorship, signing and where a commit lands (specs/prK-hook-pack.md §E.4).

``pre_tool_use`` on shell calls running ``git``, ``gh`` or ``export`` (the
argv0 prefilter); a speed bump, since a server-side push rule is the
authoritative control. It only denies or asks, never rewrites the command, so
it coexists with a user's own command-rewriting hook.

Default rows (on): the identity and signing rows of ``_git_identity`` deny;
before a ``git commit``, an empty or placeholder identity
(``config.placeholder_identity``, read with a local ``git config --get``) denies
without ever echoing the value; a commit in another worktree than the
session's, or on the default branch (``config.ask_on_default_branch``), asks.

Data rows (empty in the engine; the consumer's ``[hooks.git-commit-push-policy-guard]``
or an overlay fills them): ``forbid_trailers`` / ``allowed_coauthors`` /
``required_trailers`` judge the message through ``security.commit_trailers``
(``CP4xx``; an unreadable message asks), ``never_commit_globs`` the staged
paths, ``git add -f`` paths and ``commit -a`` / pathspec paths, and the
opt-in, advisory ``push_requires_green`` asks before a push or ``gh pr
create`` whose ``HEAD`` tree the Stop gate has not seen green.
"""

from __future__ import annotations

import os
import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._git_identity import (
    IDENTITY_REASON,
    identity_rule,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.shell.git_options import git_args

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.git_command import GitInvocation
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

    type Verdict = tuple[Decision, str, str]

__all__ = ["CONFIG_SCHEMA", "DEFAULT_PLACEHOLDER_IDENTITY", "git_policy_guard"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "placeholder_identity": ConfigKey("list", "extend"),
    "ask_on_default_branch": ConfigKey("boolean"),
    "forbid_trailers": ConfigKey("list", "extend"),
    "allowed_coauthors": ConfigKey("list", "relax"),
    "required_trailers": ConfigKey("table"),
    "never_commit_globs": ConfigKey("list", "extend"),
    "push_requires_green": ConfigKey("boolean"),
}
DEFAULT_PLACEHOLDER_IDENTITY: Final = ("*@example.com", "you@*", "*@localhost", "")
PLACEHOLDER_REASON: Final = (
    "Blocked: the git identity is empty or a placeholder; ask the user to fix their git "
    "identity.\nDo not change git config yourself."
)
_IDENTITY_SETTINGS: Final = (
    ("GIT_AUTHOR_NAME", "user.name"),
    ("GIT_AUTHOR_EMAIL", "user.email"),
)
_UNPARSED: Final = re.compile(
    r"--author\b|--gpg-sign|--no-gpg-sign|\bGIT_(?:AUTHOR|COMMITTER)_|"
    r"\buser\.(?:name|email)\b|\bcommit\.gpgsign\b",
    re.IGNORECASE,
)


@register_hook_handler(
    "git_policy_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
    argv0s=("git", "git.exe", "gh", "export"),
)
def git_policy_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny identity, authorship and signing changes; ask where a commit should not land.

    Example::

        >>> git_policy_guard(bash("git commit --author=x -m m"), ctx).rule_id  # doctest: +SKIP
        'author'
    """
    command = ev.tool.command if ev.tool is not None else None
    if command is None or ev.repo is None:
        return None
    if command.parse_error is not None or command.kind != "posix":
        found = _unparsed(command.text)
    else:
        found = _strongest(_segment_verdict(s, ev.repo, ctx) for s in command.segments)
    if found is None:
        return None
    decision, rule, reason = found
    return HandlerResult(decision=decision, hook_id=ctx.hook.id, rule_id=rule, reason=reason)


def _segment_verdict(segment: Segment, repo: RepoInfo, ctx: HandlerContext) -> Verdict | None:
    from coding_agent_playbook.hook_runtime.shell.git_command import parse_git

    git = parse_git(segment)
    rule = identity_rule(segment, git)
    if rule is not None:
        return Decision.DENY, rule, IDENTITY_REASON
    if git is not None:
        return _git_verdict(git, repo, ctx)
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    if program == "gh" and segment.argv[1:3] == ("pr", "create"):
        return _green_verdict(ctx)
    return None


def _git_verdict(git: GitInvocation, repo: RepoInfo, ctx: HandlerContext) -> Verdict | None:
    sub = git.subcommand or ""
    if sub == "commit":
        return _commit_verdict(git, repo, ctx)
    if sub == "add" and git_args(git.args, sub).has("--force", "f"):
        return _never_commit(lambda: _operands(git), ctx)
    if sub == "push":
        return _green_verdict(ctx)
    return None


def _commit_verdict(git: GitInvocation, repo: RepoInfo, ctx: HandlerContext) -> Verdict | None:
    if _placeholder_identity(ctx):
        return Decision.DENY, "placeholder_identity", PLACEHOLDER_REASON
    from coding_agent_playbook.hook_runtime.handlers._commit_checks import (
        message_verdict,
        staged_paths,
    )

    found = message_verdict(git, repo, ctx.config) or _never_commit(
        lambda: staged_paths(git, ctx.git), ctx
    )
    if found is not None:
        return found
    if _other_worktree(git, repo):
        reason = (
            "This commit runs in a different worktree than this session's.\n"
            "Commit from the session's worktree, or confirm with the user."
        )
        return Decision.ASK, "other_worktree", reason
    return _default_branch_verdict(ctx)


def _placeholder_identity(ctx: HandlerContext) -> bool:
    """Whether the effective author name or email is empty or matches a placeholder glob."""
    from fnmatch import fnmatchcase

    globs = HookConfig(ctx.config, CONFIG_SCHEMA).strings(
        "placeholder_identity", DEFAULT_PLACEHOLDER_IDENTITY, blanks="keep"
    )
    for variable, key in _IDENTITY_SETTINGS:
        value = ctx.env.get(variable) or ctx.git.config_value(key) or ""
        lowered = value.strip().lower()
        if not lowered or any(fnmatchcase(lowered, glob.lower()) for glob in globs if glob):
            return True
    return False


def _default_branch_verdict(ctx: HandlerContext) -> Verdict | None:
    if not HookConfig(ctx.config, CONFIG_SCHEMA).flag("ask_on_default_branch", True):
        return None
    branch = ctx.git.symbolic_ref("HEAD")
    default = ctx.git.default_branch()
    defaults = ("main", "master") if default is None else (default.removeprefix("origin/"),)
    if branch is None or branch not in defaults:
        return None
    reason = (
        f"This commits directly on the default branch {branch}.\n"
        "Commit on a feature branch, or confirm."
    )
    return Decision.ASK, "default_branch", reason


def _never_commit(listed: Callable[[], list[str]], ctx: HandlerContext) -> Verdict | None:
    """Deny when a path the commit records matches ``never_commit_globs`` (listed only then)."""
    globs = HookConfig(ctx.config, CONFIG_SCHEMA).strings("never_commit_globs", (), blanks="keep")
    paths = listed() if globs else []
    if not paths:
        return None
    from coding_agent_playbook.security.paths import PathPolicy

    policy = PathPolicy(deny=globs, allow=(), glob_exempt={})
    home = ctx.home or "/nonexistent"
    hit = next((p for p in paths if policy.matches(p, home=home, platform=ctx.platform)), None)
    if hit is None:
        return None
    shown = clip(clean_text(hit), 120)
    reason = (
        f"Blocked: this commit would record {shown}, which this repo never commits.\n"
        "Unstage it (git restore --staged <path>) and commit the rest."
    )
    return Decision.DENY, "never_commit", reason


def _green_verdict(ctx: HandlerContext) -> Verdict | None:
    """``push_requires_green``: advisory, since the green record is agent-writable state."""
    if not HookConfig(ctx.config, CONFIG_SCHEMA).flag("push_requires_green", False):
        return None
    from coding_agent_playbook.hook_runtime.stop.chain import read_last_green

    tree = ctx.git.head_tree()
    green = read_last_green(ctx.session.store) or ""
    if tree is not None and green.split(":", 1)[0] == tree:
        return None
    reason = (
        "The Stop gate has not seen this HEAD tree green (advisory).\n"
        "Let the checks run green before you push or open a PR, or confirm."
    )
    return Decision.ASK, "push_not_green", reason


def _other_worktree(git: GitInvocation, repo: RepoInfo) -> bool:
    """Whether the commit's effective cwd is known and inside another worktree."""
    from coding_agent_playbook.hook_runtime.dispatch.paths import find_repo

    if git.git_dir is not None or git.work_tree is not None:
        return True
    if git.cwd is None:
        return False
    found = find_repo(git.cwd)
    return found is not None and os.path.realpath(found.worktree_root) != os.path.realpath(
        repo.worktree_root
    )


def _operands(git: GitInvocation) -> list[str]:
    parsed = git_args(git.args, git.subcommand or "")
    return [*parsed.positionals, *parsed.pathspecs]


def _unparsed(text: str) -> Verdict | None:
    if _UNPARSED.search(text) is None:
        return None
    reason = (
        "This command could not be read and touches git identity, authorship or signing.\n"
        "Confirm it with the user before it runs."
    )
    return Decision.ASK, "unparsed", reason


def _strongest(verdicts: Iterable[Verdict | None]) -> Verdict | None:
    """The first deny, else the first ask; a deny stops reading the segments after it."""
    asked: Verdict | None = None
    for verdict in verdicts:
        if verdict is not None and verdict[0] is Decision.DENY:
            return verdict
        asked = asked or verdict
    return asked
