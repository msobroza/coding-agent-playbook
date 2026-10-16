"""prompt-write-scope-guard: enforce the active playbook prompt's write scope (specs/prK-hook-pack.md §E.3).

Default, ``pre_tool_use``, Claude Code only: the defense in depth behind the
native constraints (``disallowed-tools`` in the Claude command, ``agent: plan``
on OpenCode). The active prompt is resolved per turn
(``hook_runtime.active_prompt``: the transcript's turn-opening entry, or a
model-run ``Skill``; no ``user_prompt_submit`` process); its scope comes from
this hook's ``scopes`` config, rendered at sync from each prompt's
``write_scope``. After the first call of a turn, the guard costs one small
state read.

- ``read_only``: a file-tool write into the repository is denied (a boundary);
  a write-shaped Bash command (a write target in the repository, ``git apply``,
  ``git commit``, ``patch``) asks (a speed bump).
- ``globs``: a write into the repository outside the globs asks, quoting the
  prompt's own "do not silently fix the code" line.

Writes outside the repository (scratch files) are not the code under review,
so they pass. Uncertain detection passes; an internal error asks (``on_error``).
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.active_prompt import resolve_active_prompt
from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.globs import compile_globs
from coding_agent_playbook.hook_runtime.handlers._targets import (
    file_write_paths,
    shell_write_targets,
)
from coding_agent_playbook.hook_runtime.registry import register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["READ_ONLY_REASON", "TESTS_ONLY_REASON", "PromptScope", "prompt_scope_guard", "scope_of"]

#: The deny/ask tail of a read-only prompt (§E.3): what to do instead.
READ_ONLY_REASON: Final = "report findings; the user will ask for fixes in a follow-up."
#: generate-tests.md.j2's own line (step 4 of its workflow), quoted on a glob-scope ask.
TESTS_ONLY_REASON: Final = (
    'Do not silently "fix" the code to make the test pass. Report the failure; let the user decide.'
)
#: Shell commands that write files the segment's ``write_targets`` cannot name.
_UNNAMED_WRITERS: Final = frozenset({"patch"})
_GIT_WRITERS: Final = frozenset({"apply", "am"})
_GIT_COMMIT: Final = "commit"
_PATH_CHARS: Final = 60


@dataclass(frozen=True, slots=True)
class PromptScope:
    """One prompt's write scope: read-only, or the globs it may write.

    Example: ``PromptScope(read_only=False, globs=("tests/**",))``.
    """

    read_only: bool
    globs: tuple[str, ...] = ()


@register_hook_handler(
    "prompt_scope_guard", events=["pre_tool_use"], decisions=["deny", "ask", "none"]
)
def prompt_scope_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny or ask on a write the active prompt's scope forbids; ``None`` (pass) otherwise.

    Example::

        >>> prompt_scope_guard(edit_during_review, ctx).decision  # doctest: +SKIP
        <Decision.DENY: 'deny'>
    """
    if ev.tool is None or ev.repo is None:
        return None
    active = resolve_active_prompt(ev, ctx.cfg, ctx.session.store)
    scope = None if active is None else scope_of(ctx.config, active.slash)
    if active is None or scope is None:
        return None
    if scope.read_only:
        return _read_only(ev, ctx, active.slash)
    return _outside_globs(ev, ctx, active.slash, scope.globs)


def scope_of(config: Mapping[str, object], slash: str) -> PromptScope | None:
    """``slash``'s scope from the hook config's ``scopes`` table; ``None`` when it has none.

    A malformed row (validate rejects its source) is no scope: fail open.

    Example::

        >>> scope_of({"scopes": {"review": {"read_only": True}}}, "review")
        PromptScope(read_only=True, globs=())
    """
    scopes = config.get("scopes")
    row = scopes.get(slash) if isinstance(scopes, Mapping) else None
    if not isinstance(row, Mapping):
        return None
    if row.get("read_only") is True:
        return PromptScope(read_only=True)
    globs = row.get("globs")
    if isinstance(globs, list) and globs and all(isinstance(g, str) for g in globs):
        return PromptScope(read_only=False, globs=tuple(globs))
    return None


def _read_only(ev: CanonicalEvent, ctx: HandlerContext, slash: str) -> HandlerResult | None:
    """Deny a file-tool write into the repo; ask on a write-shaped Bash command."""
    assert ev.tool is not None  # checked by the handler
    if any(path.repo_rel is not None for path in file_write_paths(ev.tool)):
        return _result(ctx, Decision.DENY, "read_only_prompt", f"/{slash} is read-only: ")
    written = _in_repo(shell_write_targets(ev, ctx, _write_targets))
    if written:
        head = f"/{slash} is read-only and this command writes {_quoted(written[0])}: "
        return _result(ctx, Decision.ASK, "read_only_prompt", head)
    if _shell_writes_unnamed(ev, commits=True):
        head = f"/{slash} is read-only and this command changes the repository: "
        return _result(ctx, Decision.ASK, "read_only_prompt", head)
    return None


def _outside_globs(
    ev: CanonicalEvent, ctx: HandlerContext, slash: str, globs: Sequence[str]
) -> HandlerResult | None:
    """Ask on a write into the repo outside ``globs`` (file tool or Bash)."""
    assert ev.tool is not None  # checked by the handler
    allowed = compile_globs(globs, platform=ctx.platform, home=ctx.home)
    written = _in_repo([*file_write_paths(ev.tool), *shell_write_targets(ev, ctx, _write_targets)])
    outside = [path for path in written if not allowed.matches(path.key)]
    if not outside and not _shell_writes_unnamed(ev, commits=False):
        return None
    where = _quoted(outside[0]) if outside else "files it cannot name"
    reason = f"/{slash} writes only {', '.join(globs)}; this writes {where}.\n{TESTS_ONLY_REASON}"
    return HandlerResult(
        decision=Decision.ASK, hook_id=ctx.hook.id, rule_id="outside_write_scope", reason=reason
    )


def _write_targets(segment: Segment) -> list[str]:
    """``shell.write_targets``, imported on the Bash branch only (§D.1)."""
    from coding_agent_playbook.hook_runtime.shell import write_targets

    return write_targets(segment)


def _shell_writes_unnamed(ev: CanonicalEvent, *, commits: bool) -> bool:
    """A segment that changes files without naming them: ``patch``, ``git apply``/``am``.

    ``commits`` adds ``git commit``: it changes no working-tree file, but a
    read-only prompt must not record changes either.
    """
    command = ev.tool.command if ev.tool is not None else None
    if command is None:
        return False
    return any(_unnamed_writer(segment, commits=commits) for segment in command.segments)


def _unnamed_writer(segment: Segment, *, commits: bool) -> bool:
    if not segment.argv:
        return False
    if posixpath.basename(segment.argv[0]) in _UNNAMED_WRITERS:
        return True
    from coding_agent_playbook.hook_runtime.gitargv import parse_git  # Bash branch only

    git = parse_git(segment)
    if git is None:
        return False
    return git.subcommand in _GIT_WRITERS or (commits and git.subcommand == _GIT_COMMIT)


def _in_repo(paths: Sequence[NormalizedPath]) -> list[NormalizedPath]:
    return [path for path in paths if path.repo_rel is not None]


def _quoted(path: NormalizedPath) -> str:
    return quote_data(path.repo_rel or path.key, _PATH_CHARS)


def _result(ctx: HandlerContext, decision: Decision, rule_id: str, head: str) -> HandlerResult:
    return HandlerResult(
        decision=decision, hook_id=ctx.hook.id, rule_id=rule_id, reason=head + READ_ONLY_REASON
    )
