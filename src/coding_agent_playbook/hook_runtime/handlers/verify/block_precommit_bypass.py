"""block-precommit-bypass: the repo's playbook pre-commit hooks must run (specs/prK-hook-pack.md §E.2).

``pre_tool_use``, active only when ``guard_config.precommit.playbook_hook_ids``
is non-empty (the repo's ``.pre-commit-config.yaml`` declares a ``playbook-*``
or ``coding-agent-playbook-*`` hook). It is the single owner of
``.git/hooks/**`` and ``core.hooksPath``:

- **Bash.** One ``shell.parse.parse_shell`` per event; each segment through
  :func:`._bypass_rules.segment_verdict` (``--no-verify``, commit ``-n``,
  ``SKIP=``, ``pre-commit uninstall``, injected ``core.hooksPath`` /
  ``alias.*``; plumbing asks), plus every write, ``rm``, ``mv`` or ``chmod``
  of a path under the hooks directory. A command the parser could not follow
  asks when its text names a bypass.
- **File tools.** An Edit/Write under ``.git/hooks/`` denies, and so does one
  of the git config file that adds, changes or removes ``hooksPath``.

The reason names the ids and never teaches a bypass. This is a speed bump
(plumbing, ``subprocess`` and scripts get past any argv matcher); ``playbook
ci`` as a required status check is the control.
"""

from __future__ import annotations

import os
import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.path_globs import fold_key
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.handlers._shared.git_config_file import (
    ConfigEdit,
    config_edits,
)
from coding_agent_playbook.hook_runtime.handlers._shared.targets import (
    file_write_paths,
    shell_write_targets,
)
from coding_agent_playbook.hook_runtime.handlers.verify._bypass_rules import segment_verdict

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, RepoInfo, ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

    type Verdict = tuple[Decision, str]

__all__ = ["CONFIG_SCHEMA", "block_precommit_bypass", "reason_for"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {"strict_skip": ConfigKey("boolean")}
#: What a command the parser could not follow must not mention (it then asks).
_UNPARSED_BYPASS: Final = re.compile(
    r"--no-verify|hookspath|\bSKIP=|PRE_COMMIT_ALLOW_NO_CONFIG|\.git/hooks|pre-commit\s+uninstall",
    re.IGNORECASE,
)
_HOOKS_PATH_LINE: Final = re.compile(r"^\s*hookspath\s*=.*$", re.IGNORECASE | re.MULTILINE)
#: Commands whose every operand a hooks-dir check must see (``mv``: the source is removed).
_OPERAND_COMMANDS: Final = frozenset({"rm", "mv", "chmod", "chown", "ln", "unlink", "truncate"})
#: A rebase in progress owns its plumbing (``git rebase`` runs commit-tree itself).
_REBASE_DIRS: Final = ("rebase-merge", "rebase-apply")
_IDS_CHARS: Final = 120


@register_hook_handler(
    "block_precommit_bypass",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
)
def block_precommit_bypass(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny skipping the repo's playbook pre-commit hooks; ask on plumbing commits.

    Example::

        >>> block_precommit_bypass(bash("git commit --no-verify -m x"), ctx).decision
        ... # doctest: +SKIP
        <Decision.DENY: 'deny'>
    """
    ids = ctx.cfg.tables.precommit_hook_ids()
    if not ids or ev.tool is None or ev.repo is None:
        return None
    found = _shell_verdict(ev, ctx, ids, ev.repo) or _file_verdict(ev.tool, ctx, ev.repo)
    if found is None:
        return None
    decision, rule = found
    return HandlerResult(
        decision=decision, hook_id=ctx.hook.id, rule_id=rule, reason=reason_for(decision, ids)
    )


def reason_for(decision: Decision, ids: tuple[str, ...]) -> str:
    """The model-facing reason: the ids that must run, the safe alternative, no bypass.

    Example::

        >>> reason_for(Decision.DENY, ("playbook-validate",)).splitlines()[0]
        "Blocked: this repo's pre-commit hooks (playbook-validate) must run."
    """
    shown = clip(clean_text(", ".join(ids)), _IDS_CHARS)
    if decision is Decision.ASK:
        return (
            f"Plumbing commits skip this repo's pre-commit hooks ({shown}).\n"
            "Use git commit so they run; if plumbing is really needed, the user decides."
        )
    return (
        f"Blocked: this repo's pre-commit hooks ({shown}) must run.\n"
        "Fix what the hook reported (playbook validate && playbook sync, or the metrics "
        "regression).\nIf you believe it is a false positive, stop and tell the user."
    )


def _shell_verdict(
    ev: CanonicalEvent, ctx: HandlerContext, ids: tuple[str, ...], repo: RepoInfo
) -> Verdict | None:
    command = ev.tool.command if ev.tool is not None else None
    if command is None:
        return None
    if command.parse_error is not None:  # unknown: ask only when the text names a bypass
        return (Decision.ASK, "unparsed") if _UNPARSED_BYPASS.search(command.text) else None
    strict = HookConfig(ctx.config, CONFIG_SCHEMA).flag("strict_skip", False)
    in_rebase = _rebase_in_progress(repo)
    if any(_hooks_dir(path, repo, ctx.platform) for path in shell_write_targets(ev, ctx, _touched)):
        return Decision.DENY, "hooks_dir"
    verdicts = [
        segment_verdict(segment, ids=frozenset(ids), strict_skip=strict, in_rebase=in_rebase)
        for segment in command.segments
    ]
    found = [verdict for verdict in verdicts if verdict is not None]
    denied = [verdict for verdict in found if verdict[0] is Decision.DENY]
    return next(iter(denied or found), None)


def _touched(segment: Segment) -> list[str]:
    """Every path ``segment`` writes, plus each operand of ``rm``/``mv``/``chmod``/..."""
    from coding_agent_playbook.hook_runtime.shell.writes import operands, write_targets

    targets = write_targets(segment)
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    if program in _OPERAND_COMMANDS:
        targets.extend(operands(list(segment.argv[1:])))
    return targets


def _file_verdict(tool: ToolCall, ctx: HandlerContext, repo: RepoInfo) -> Verdict | None:
    if any(_hooks_dir(path, repo, ctx.platform) for path in file_write_paths(tool)):
        return Decision.DENY, "hooks_dir"
    if any(_changes_hooks_path(edit) for edit in config_edits(tool, repo, ctx.platform)):
        return Decision.DENY, "hooks_path"
    return None


def _hooks_dir(path: NormalizedPath, repo: RepoInfo, platform: str) -> bool:
    """``.git/hooks`` or below, in this worktree's git dir or the common one."""
    if path.key == ".git/hooks" or path.key.startswith(".git/hooks/"):
        return True
    real = fold_key(path.realpath, platform)
    for base in {repo.git_dir, repo.common_dir}:
        hooks = fold_key(os.path.join(base, "hooks"), platform)
        if real == hooks or real.startswith(f"{hooks}/"):
            return True
    return False


def _changes_hooks_path(edit: ConfigEdit) -> bool:
    """Whether the edit adds, changes or removes a ``hooksPath =`` line of the config file."""
    if edit.after is None:  # cannot simulate: judge what the call writes
        return "hookspath" in edit.written.lower()
    return _HOOKS_PATH_LINE.findall(edit.before or "") != _HOOKS_PATH_LINE.findall(edit.after)


def _rebase_in_progress(repo: RepoInfo) -> bool:
    """``rebase-merge/`` or ``rebase-apply/`` in the git dir: plumbing is the rebase's own."""
    return any(os.path.isdir(os.path.join(repo.git_dir, name)) for name in _REBASE_DIRS)
