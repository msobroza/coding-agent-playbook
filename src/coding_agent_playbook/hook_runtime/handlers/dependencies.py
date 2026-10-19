"""dependency-allowlist-guard: the detected package manager, new direct deps, lockfiles (specs/prK-hook-pack.md §E.4).

``pre_tool_use``; a boundary for manifest edits, a speed bump for Bash. The
requests come from ``judges.install_commands`` (install-shaped segments) and
``judges.manifest_diff`` (an Edit/Write of a manifest, simulated by
``edit_preview``); only NEWLY added names count, so existing dependencies are
grandfathered. ``judges.dependency_tiers`` judges them, strongest first:

- (c) a hand edit of ``uv.lock`` / ``poetry.lock`` -> deny (regenerate it);
- (a) the wrong installer for ``facts.package_manager`` -> deny with the
  corrected command; inert without the fact;
- overlay: ``required_index`` set -> any other index denies; ``allowlist``
  set -> a name outside it denies with "did you mean" hints, one inside passes;
- (d) index mixing -> ``index_mode`` (``ask``; the stricter of it and
  ``[guardrails.dependencies] mode``);
- (b) a new direct dependency -> ask, once per package per session (a deny
  marks nothing, so the corrected command still asks).

It never fires on ``uv sync``, ``uv run`` without ``--with`` or a
self-install, and never queries an index (egress that leaks the name). A
``-r`` file inside the worktree is the project's own manifest (grandfathered);
one outside it is read. ``tomllib`` loads only for a ``pyproject.toml`` edit
and ``difflib`` only on the allowlist branch (§D.1 branch-local rows).
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.detector.pep503 import requirement_names
from coding_agent_playbook.hook_runtime.config.reader import read_small_file
from coding_agent_playbook.hook_runtime.dispatch.caps import quote_data
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.dispatch.event import ToolClass
from coding_agent_playbook.hook_runtime.dispatch.paths import normalize_path
from coding_agent_playbook.hook_runtime.judges.dependency_tiers import (
    NEW_DEPENDENCY,
    DependencyPolicy,
    Finding,
    adding_line,
    dependency_policy,
    index_finding,
    mismatch,
    name_findings,
)
from coding_agent_playbook.hook_runtime.judges.install_commands import install_requests
from coding_agent_playbook.hook_runtime.judges.manifest_diff import (
    LOCKFILES,
    added_indexes,
    added_names,
    manifest_kind,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.judges.install_commands import InstallRequest
    from coding_agent_playbook.hook_runtime.judges.manifest_diff import ManifestKind
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["CONFIG_SCHEMA", "dependency_guard"]

_MODES: Final = ("ask", "deny")
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "index_mode": ConfigKey("string", "strictest", _MODES),
    "mode": ConfigKey("string", "strictest", _MODES),
    "allowlist": ConfigKey("list", "relax"),
    "required_index": ConfigKey("string"),
}
#: An outside ``-r`` file is read this far; a manifest being edited up to 1 MiB.
_FILE_LIMIT: Final = 64 * 1024
_MANIFEST_LIMIT: Final = 1024 * 1024
_REASON_LINES: Final = 4
#: The install shapes, for a command the parser could not follow (it then asks).
_RAW_INSTALL: Final = re.compile(
    r"\b(?:pip3?|uv|pipx|poetry|pdm|conda|mamba|npm)\b[^\n;|&]{0,64}?"
    r"\b(?:install|add|download|wheel|exec|--with)\b|\b(?:uvx|npx)\b"
)


@register_hook_handler(
    "dependency_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
    config_domain="dependencies",
)
def dependency_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny the wrong installer or a lockfile edit; ask before a new dependency or index.

    Example::

        >>> dependency_guard(bash("pip install requests"), uv_repo_ctx).reason  # doctest: +SKIP
        'This repository uses uv: run `uv add requests` instead of `pip install`. ...'
    """
    tool = ev.tool
    if tool is None or ev.repo is None:
        return None
    policy = dependency_policy(ctx.cfg.tables.facts(), ctx.config)
    if tool.tool_class is ToolClass.SHELL:
        found = _shell_findings(ev, ctx, policy)
    else:
        found = _manifest_findings(tool, policy)
    return _result(found, ctx)


def _shell_findings(
    ev: CanonicalEvent, ctx: HandlerContext, policy: DependencyPolicy
) -> list[Finding]:
    command = ev.tool.command if ev.tool is not None else None
    if command is None:
        return []
    if command.parse_error is not None or command.kind == "powershell":
        return _unreadable(command.text)
    found: list[Finding] = []
    for segment in command.segments:
        for request in install_requests(segment):
            names = (*request.names, *_outside_file_names(request, segment, ev, ctx))
            found.extend(_request_findings(request, tuple(dict.fromkeys(names)), policy))
    return found


def _request_findings(
    request: InstallRequest, names: Sequence[str], policy: DependencyPolicy
) -> list[Finding]:
    tiers = (mismatch(request, policy), index_finding(request.indexes, policy, via=request.tool))
    python = request.ecosystem == "python"
    return [*filter(None, tiers), *name_findings(names, policy, python=python)]


def _manifest_findings(tool: ToolCall, policy: DependencyPolicy) -> list[Finding]:
    found: list[Finding] = []
    for path in tool.write_paths:
        if path.repo_rel is None:
            continue
        name = posixpath.basename(path.repo_rel)
        if name in LOCKFILES:
            lines = (
                f"{name} is generated; do not edit it by hand.",
                f"Regenerate it with `{LOCKFILES[name]}`.",
            )
            found.append(Finding(Decision.DENY, "lockfile_edit", lines))
            continue
        kind = manifest_kind(name)
        if kind is not None:
            found.extend(_edit_findings(tool, path, kind, policy))
    return found


def _edit_findings(
    tool: ToolCall, path: NormalizedPath, kind: ManifestKind, policy: DependencyPolicy
) -> list[Finding]:
    """The names an edit of one manifest adds, judged; it is simulated, never written."""
    from coding_agent_playbook.hook_runtime.edit_preview import preview_after

    readable, before = _read(path)
    after = preview_after(tool, before) if readable else None
    if after is None:
        return []  # the tool itself will fail, or the edit cannot be simulated
    added = added_names(kind, before, after)
    if added is None:
        shown = quote_data(path.repo_rel or path.raw)
        lines = (
            f"This edit leaves {shown} unparsable, so its new dependencies cannot be checked.",
            "Confirm it with the user.",
        )
        return [Finding(Decision.ASK, "unreadable_manifest", lines)]
    indexes = added_indexes(kind, before, after)
    index = index_finding(indexes, policy, via=path.repo_rel or path.raw) if indexes else None
    return [*filter(None, [index]), *name_findings(sorted(added), policy, python=True)]


def _result(found: Sequence[Finding], ctx: HandlerContext) -> HandlerResult | None:
    """Any deny tier denies (marking no name asked); else one ask with every line."""
    denied = [f for f in found if f.decision is Decision.DENY]
    if denied:
        return _handler_result(Decision.DENY, denied, ctx)
    asks = [f for f in found if f.rule != NEW_DEPENDENCY]
    names = dict.fromkeys(name for f in found for name in f.names)
    fresh = [name for name in names if ctx.session.once(f"dependency:{name}")]
    if fresh:
        asks.append(Finding(Decision.ASK, NEW_DEPENDENCY, (adding_line(fresh),)))
    return _handler_result(Decision.ASK, asks, ctx) if asks else None


def _handler_result(
    decision: Decision, found: Sequence[Finding], ctx: HandlerContext
) -> HandlerResult:
    lines = [line for f in found for line in f.lines][:_REASON_LINES]
    return HandlerResult(
        decision=decision, hook_id=ctx.hook.id, rule_id=found[0].rule, reason="\n".join(lines)
    )


def _outside_file_names(
    request: InstallRequest, segment: Segment, ev: CanonicalEvent, ctx: HandlerContext
) -> list[str]:
    """The names of ``-r`` files outside the worktree (one inside is the project's manifest)."""
    names: list[str] = []
    for raw in request.files:
        path = normalize_path(
            raw, base=segment.cwd or ev.cwd, repo=ev.repo, home=ctx.home, platform=ctx.platform
        )
        if not (path.outside_repo and path.exists):
            continue
        _, text = _read(path)
        names.extend(sorted(requirement_names((text or "")[:_FILE_LIMIT])))
    return names


def _unreadable(text: str) -> list[Finding]:
    if _RAW_INSTALL.search(text) is None:
        return []
    lines = (
        "This command could not be read and looks like a package install.",
        "Confirm it with the user.",
    )
    return [Finding(Decision.ASK, "unparsed_install", lines)]


def _read(path: NormalizedPath) -> tuple[bool, str | None]:
    """``(readable, text)``; ``text`` is ``None`` for a file that does not exist yet."""
    if not path.exists:
        return True, None
    try:
        data, _ = read_small_file(Path(path.realpath), _MANIFEST_LIMIT)
        return True, data.decode("utf-8")
    except (OSError, ValueError):  # unreadable, not a regular file, too large, not UTF-8
        return False, None
