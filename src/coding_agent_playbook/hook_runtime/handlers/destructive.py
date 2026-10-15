"""destructive-command-guard: catastrophic shell commands deny, lossy ones ask (specs/prK-hook-pack.md §E.4).

``pre_tool_use`` on shell calls, a speed bump against accidents (the real
barriers are server-side branch protection, DB grants and an OS sandbox). The
dispatcher's argv0 prefilter calls it only when a segment runs one of
:data:`ARGV0S` (or an overlay row's ``argv0``). Each unwrapped segment goes
through the filesystem rows (``_destructive_paths``) and, for ``git``, the git
rows (``_destructive_git``, whose local git queries run only for the row that
needs them); the strongest verdict wins, deny before ask.

- A command the parser could not follow is matched against raw regexes of the
  same shapes and asks; PowerShell asks on any recursive delete or force.
- Overlay ``config.extra_rows`` (``{argv0, regex, decision, reason}``; the
  ``regex`` key is the screened ``regex`` config kind) add deny/ask rows:
  union-only, a row can never relax an engine verdict.

Reasons are at most two lines and name the safe alternative.
"""

from __future__ import annotations

import os
import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import clean_text, clip
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._destructive_git import (
    DEFAULT_PROTECTED_BRANCHES,
    GitFacts,
    git_hit,
)
from coding_agent_playbook.hook_runtime.handlers._destructive_paths import (
    DEFAULT_SAFE_RM_DIRS,
    PATH_ARGV0S,
    Hit,
    Where,
    fork_bomb,
    path_hit,
    pipe_hit,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from typing import Any

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell import Segment, ShellCommand

__all__ = ["ARGV0S", "CONFIG_SCHEMA", "destructive_command_guard", "extra_row_hits"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "protected_branches": ConfigKey("list", "extend"),
    "safe_rm_dirs": ConfigKey("list", "relax"),
    "extra_rows": ConfigKey("regex", "extend"),
}
#: The argv0s the engine rows inspect; overlay rows add theirs (``argv0_rows``).
ARGV0S: Final = (*PATH_ARGV0S, "git", "git.exe")
_ROW_DECISIONS: Final = {"deny": Decision.DENY, "ask": Decision.ASK}
_ROW_REASON_CHARS: Final = 240
_DEFAULT_ROW_REASON: Final = (
    "An overlay rule marks this command as destructive.\nConfirm it with the user first."
)
_FORK_BOMB_REASON: Final = "A fork bomb exhausts the machine. It is never allowed."
_GAP: Final = r"[^\n;|&]{0,128}?"
#: The shapes of the engine rows, for a command the parser could not follow (it then asks).
_RAW_SHAPES: Final = re.compile(
    "|".join(
        (
            rf"\brm\b{_GAP}\s(?:-[a-zA-Z]*[rR]|--recursive)",
            rf"\bgit\b{_GAP}\bpush\b{_GAP}\s(?:--force|-f\b|--mirror|--delete|\+)",
            rf"\bgit\b{_GAP}\b(?:reset{_GAP}--hard|clean{_GAP}\s-[a-zA-Z]*f|branch{_GAP}\s-D\b)",
            rf"\bgit\b{_GAP}\b(?:stash|filter-branch|filter-repo|update-ref)\b",
            r"\bmkfs",
            rf"\bdd\b{_GAP}\bof=/dev/",
            r"\b(?:curl|wget)\b[^\n;&]{0,256}?\|",
            rf"\bchmod\b{_GAP}\s(?:-R|--recursive)\b",
            rf"\bfind\b{_GAP}\s-delete\b",
            rf"\brsync\b{_GAP}\s--del",
        )
    )
)
#: PowerShell: a recursive delete or any force (its argv is never parsed, §D.2.5).
_POWERSHELL_SHAPES: Final = re.compile(
    rf"(?i)\b(?:remove-item|ri|rm|rmdir|rd|del|erase)\b[^\n;|]{{0,256}}?\s(?:-r(?:ecurse)?\b|/s\b)"
    rf"|\s-force\b|\bgit\b{_GAP}\bpush\b{_GAP}\s(?:--force|-f\b|--mirror|--delete)"
)
_compiled: dict[str, re.Pattern[str] | None] = {}


@register_hook_handler(
    "destructive_command_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
    config_domain="git",
    argv0s=ARGV0S,
    argv0_rows="extra_rows",
)
def destructive_command_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny a catastrophic shell command; ask before one that loses work.

    Example::

        >>> destructive_command_guard(bash("rm -rf /"), ctx).rule_id  # doctest: +SKIP
        'rm_root'
    """
    command = ev.tool.command if ev.tool is not None else None
    if command is None or ev.repo is None:
        return None
    hit = _command_hit(command, ev.repo, ctx)
    if hit is None:
        return None
    return HandlerResult(
        decision=hit.decision, hook_id=ctx.hook.id, rule_id=hit.rule, reason=hit.reason
    )


def extra_row_hits(segments: Sequence[Segment], rows: object) -> list[Hit]:
    """The overlay rows (``{argv0, regex, decision, reason}``) the segments trip.

    A row whose decision is not ``deny`` or ``ask``, or whose regex does not
    compile, is ignored: rows only add verdicts (validate screens them first).

    Example::

        >>> rows = [{"argv0": "kubectl", "regex": r"\\bdelete\\b", "decision": "deny"}]
        >>> [h.rule for h in extra_row_hits(parse("kubectl delete ns x").segments, rows)]
        ... # doctest: +SKIP
        ['extra_row:kubectl']
    """
    from coding_agent_playbook.hook_runtime._prefilter import argv0_matches

    hits: list[Hit] = []
    for row in rows if isinstance(rows, list | tuple) else ():
        decision = _ROW_DECISIONS.get(str(row.get("decision"))) if isinstance(row, dict) else None
        pattern = _pattern(row.get("regex")) if decision is not None else None
        argv0 = row.get("argv0") if isinstance(row, dict) else None
        if decision is None or pattern is None or not isinstance(argv0, str):
            continue
        for segment in segments:
            program = posixpath.basename(segment.argv[0]) if segment.argv else ""
            if argv0_matches([program], [argv0]) and pattern.search(" ".join(segment.argv)):
                hits.append(Hit(decision, f"extra_row:{argv0}", _row_reason(row.get("reason"))))
                break
    return hits


def _command_hit(command: ShellCommand, repo: RepoInfo, ctx: HandlerContext) -> Hit | None:
    if fork_bomb(command.text):
        return Hit(Decision.DENY, "fork_bomb", _FORK_BOMB_REASON)
    if command.kind == "powershell":
        return _unreadable_hit(_POWERSHELL_SHAPES, command.text, "powershell")
    if command.parse_error is not None:
        return _unreadable_hit(_RAW_SHAPES, command.text, "unparsed")
    where = _where(repo, ctx)
    facts = GitFacts(ctx.git, repo)
    protected = _strings(ctx.config.get("protected_branches"), DEFAULT_PROTECTED_BRANCHES)
    hits = [*_segment_hits(command.segments, where, facts, protected)]
    hits.extend(filter(None, [pipe_hit(command.segments)]))
    hits.extend(extra_row_hits(command.segments, ctx.config.get("extra_rows")))
    return _strongest(hits)


def _segment_hits(
    segments: Sequence[Segment], where: Where, facts: GitFacts, protected: tuple[str, ...]
) -> Iterable[Hit]:
    from coding_agent_playbook.hook_runtime.gitargv import parse_git

    for segment in segments:
        found = path_hit(segment, where)
        if found is None:
            git = parse_git(segment)
            found = None if git is None else git_hit(git, facts, protected)
        if found is not None:
            yield found
            if found.decision is Decision.DENY:
                return  # a deny is final: no git query for the segments after it


def _where(repo: RepoInfo, ctx: HandlerContext) -> Where:
    safe = _strings(ctx.config.get("safe_rm_dirs"), DEFAULT_SAFE_RM_DIRS)
    return Where(
        root=os.path.realpath(repo.worktree_root),
        git_dirs=(os.path.realpath(repo.git_dir), os.path.realpath(repo.common_dir)),
        home=None if not ctx.home else os.path.realpath(ctx.home),
        safe_dirs=frozenset(safe),
    )


def _strongest(hits: Sequence[Hit]) -> Hit | None:
    return next((h for h in hits if h.decision is Decision.DENY), None) or next(iter(hits), None)


def _unreadable_hit(shapes: re.Pattern[str], text: str, rule: str) -> Hit | None:
    if shapes.search(text) is None:
        return None
    reason = (
        "This command could not be read and looks destructive (a recursive delete, "
        "a force or a lossy git command).\nConfirm it with the user before it runs."
    )
    return Hit(Decision.ASK, rule, reason)


def _pattern(source: Any) -> re.Pattern[str] | None:
    """``source`` compiled once per process; ``None`` when it is not a valid regex."""
    if not isinstance(source, str):
        return None
    if source not in _compiled:
        try:
            _compiled[source] = re.compile(source)
        except re.error:
            _compiled[source] = None
    return _compiled[source]


def _row_reason(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return _DEFAULT_ROW_REASON
    lines = clean_text(value).strip().splitlines()[:2]
    return clip("\n".join(lines), _ROW_REASON_CHARS)


def _strings(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return default
    return tuple(item for item in value if isinstance(item, str) and item)
