"""The paths a tool call writes, shared by the §E path guards (specs/prK-hook-pack.md §E.1).

guard-generated-outputs and control-plane-guard judge the same targets: the
file tool's write paths, and the Bash write targets ``shell.write_targets``
extracts from each segment, normalized against that segment's cwd exactly
like a file-tool path (repo-relative, folded on darwin/win32). One helper,
so the two guards can never disagree about where a redirect lands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.event import ToolClass
from coding_agent_playbook.hook_runtime.paths import normalize_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["FILE_WRITE_CLASSES", "file_write_paths", "shell_target", "shell_write_targets"]

#: The tool classes whose ``write_paths`` a path guard checks.
FILE_WRITE_CLASSES: Final = frozenset({ToolClass.EDIT, ToolClass.WRITE, ToolClass.NOTEBOOK_EDIT})


def file_write_paths(tool: ToolCall) -> list[NormalizedPath]:
    """The write paths of a file-tool call (Edit, Write, NotebookEdit, ``apply_patch``).

    Example::

        >>> file_write_paths(bash_call)  # doctest: +SKIP
        []
    """
    return list(tool.write_paths) if tool.tool_classes & FILE_WRITE_CLASSES else []


def shell_target(
    raw: str, segment: Segment, ev: CanonicalEvent, ctx: HandlerContext
) -> NormalizedPath:
    """``raw`` (one ``write_targets`` entry of ``segment``) normalized like a file-tool path.

    Example::

        >>> shell_target("AGENTS.md", segment, ev, ctx).repo_rel  # doctest: +SKIP
        'AGENTS.md'
    """
    return normalize_path(
        raw, base=segment.cwd or ev.cwd, repo=ev.repo, home=ctx.home, platform=ctx.platform
    )


def shell_write_targets(
    ev: CanonicalEvent, ctx: HandlerContext, extract: Callable[[Segment], list[str]]
) -> list[NormalizedPath]:
    """Every Bash write target of ``ev``: ``extract`` (``write_targets`` or a filter) per segment.

    Example::

        >>> shell_write_targets(ev, ctx, write_targets)  # doctest: +SKIP
        [NormalizedPath(raw='AGENTS.md', ...)]
    """
    command = ev.tool.command if ev.tool is not None else None
    if command is None:
        return []
    return [
        shell_target(raw, segment, ev, ctx)
        for segment in command.segments
        for raw in extract(segment)
    ]
