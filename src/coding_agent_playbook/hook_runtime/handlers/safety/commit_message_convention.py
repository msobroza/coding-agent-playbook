"""commit-message-convention: ``cz check`` on what a ``git commit`` or ``git push`` records (specs/prK-hook-pack.md §F.4.2).

Default, ``pre_tool_use`` on shell calls running ``git`` (the argv0
prefilter), on the shared parse with wrapper prefixes such as ``proxy``
unwrapped. The convention is the consumer's commitizen config
(``[tool.commitizen]``, default ``cz_conventional_commits``), which ``cz``
reads itself: the engine has no linter, only D-Q3's cut-over (``judges.commit_cutover``).

- **commit**: the message ``git_command.commit_message_sources`` reads (``-m``
  paragraphs, a ``-F`` file inside the worktree up to 64 KiB, heredoc bodies)
  goes to ``cz check --message``; a rejection denies with cz's own words,
  sanitized (``_cz``). With nothing to inspect (an editor would open,
  ``-C``/``-c``/``--reuse-message``, ``--amend --no-edit``,
  ``--allow-empty-message``, a ``$VAR``, backtick or other ``$(...)`` value)
  it is ``none`` with zero cz calls: the commit-msg twin covers those.
- **push** (``check_push``, opt-in, default off: every new commit already met
  the commit check or the commit-msg twin, and a scan costs 0.2-6 s per push):
  the commits ``<remote>/<dst>..<src>`` publishes, read from local refs only
  (at most 200, never a fetch) and filtered on the committer date by
  ``cutover_date`` (rendered at sync from ``[hooks.commit_convention]``): one
  ``--rev-range`` check, or ``--message`` per commit (at most 20; CI checks the
  rest). A missing tracking ref fails open.
- ``cz`` is the ``machine.json`` pin (§D.8.3). With no pin or a changed
  binary the check is ``none`` plus one user note per session.

It never asks and never rewrites the command (L6): a convention is not a
judgment call, and a user's own command-rewriting hook keeps working.
git-commit-push-policy-guard owns identity, signing and trailers on the same
parse; the dispatcher folds both decisions (deny wins).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.handlers.safety._cz import CzRunner
    from coding_agent_playbook.hook_runtime.shell.git_command import GitInvocation
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["CONFIG_SCHEMA", "LOG_LIMIT", "commit_message_convention"]

#: ``[hooks.commit-message-convention]``; ``cutover_date`` is rendered from ``[hooks.commit_convention]``.
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {"check_push": ConfigKey("boolean")}
#: The most commits one push scan reads (§F.4.2).
LOG_LIMIT: Final = 200
_GIT_ARGV0S: Final = ("git", "git.exe")


@register_hook_handler(
    "commit_message_convention",
    events=["pre_tool_use"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
    argv0s=_GIT_ARGV0S,
)
def commit_message_convention(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny a commit or push whose message breaks the repo's commitizen convention.

    Example::

        >>> commit_message_convention(bash('git commit -m "Add thing."'), ctx).decision
        ... # doctest: +SKIP
        <Decision.DENY: 'deny'>
    """
    command = ev.tool.command if ev.tool is not None else None
    if command is None or ev.repo is None:
        return None
    if command.parse_error is not None or command.kind != "posix":
        return None  # nothing to inspect reliably; the commit-msg twin covers it
    for segment in command.segments:
        found = _segment(segment, ev.repo, ctx)
        if found is not None:
            return found
    return None


def _segment(segment: Segment, repo: RepoInfo, ctx: HandlerContext) -> HandlerResult | None:
    from coding_agent_playbook.hook_runtime.shell.git_command import parse_git

    git = parse_git(segment)
    if git is None:
        return None
    if git.subcommand == "commit":
        message = _commit_message(git, segment, repo)
        return None if message is None else _check(ctx, repo, lambda cz: cz.message(message))
    if git.subcommand == "push" and HookConfig(ctx.config, CONFIG_SCHEMA).flag("check_push", False):
        return _check(ctx, repo, lambda cz: _push(git, cz, ctx))
    return None


def _commit_message(git: GitInvocation, segment: Segment, repo: RepoInfo) -> str | None:
    """The message the commit records, or ``None`` when it cannot be inspected beforehand."""
    from coding_agent_playbook.hook_runtime.shell.git_command import (
        Uninspectable,
        commit_message_sources,
    )
    from coding_agent_playbook.hook_runtime.shell.git_options import git_args

    if git_args(git.args, "commit").has("--allow-empty-message") or _unresolved(segment):
        return None
    sources = commit_message_sources(git, root=repo.worktree_root)
    if isinstance(sources, Uninspectable):
        return None
    return "\n\n".join(sources)


def _unresolved(segment: Segment) -> bool:
    """A ``$VAR``/backtick word: the parser cannot know it (``$(cat <<EOF)`` bodies it reads)."""
    return any(not segment.argv[index].startswith("$(") for index in segment.dynamic)


def _check(
    ctx: HandlerContext, repo: RepoInfo, ask: Callable[[CzRunner], str | None]
) -> HandlerResult | None:
    """Run ``ask`` with the pinned cz: a deny reason, ``None`` when it passed or could not run."""
    from coding_agent_playbook.hook_runtime.handlers.safety._cz import cz_runner, missing_note

    cz = cz_runner(ctx, repo)
    if isinstance(cz, str):
        note = missing_note(ctx, cz)
        if note is None:
            return None
        return HandlerResult(
            decision=Decision.NONE, hook_id=ctx.hook.id, rule_id="cz_missing", user_note=note
        )
    reason = ask(cz)
    notes = "\n".join(cz.notes)
    if reason is None:
        if not notes:
            return None
        return HandlerResult(
            decision=Decision.NONE, hook_id=ctx.hook.id, rule_id="not_checked", user_note=notes
        )
    return HandlerResult(
        decision=Decision.DENY,
        hook_id=ctx.hook.id,
        rule_id="commit_convention",
        reason=reason,
        user_note=notes,
    )


def _push(git: GitInvocation, cz: CzRunner, ctx: HandlerContext) -> str | None:
    """Check the commits the push publishes past the cut-over; ``None`` when they pass."""
    from coding_agent_playbook.hook_runtime.git.safe_git import GitError
    from coding_agent_playbook.hook_runtime.handlers.safety._cz import push_ranges
    from coding_agent_playbook.hook_runtime.judges.commit_cutover import (
        parse_cutover,
        plan_cz_checks,
    )

    try:
        cutover = parse_cutover(ctx.config.get("cutover_date"))
    except ValueError:
        cutover = None  # validate reports a bad date; meanwhile every commit is checked
    try:
        ranges = push_ranges(git, ctx.git)
        logs = [
            (base, src, ctx.git.commit_log(f"{base}..{src}", limit=LOG_LIMIT))
            for base, src in ranges
        ]
    except GitError:
        return None  # an unreadable range fails open: the CI twin checks it
    for base, src, commits in logs:
        truncated = len(commits) >= LOG_LIMIT
        plan = plan_cz_checks(commits, cutover, base=base, head=src, truncated=truncated)
        reason = cz.plan(plan)
        if reason is not None:
            return reason
    return None
