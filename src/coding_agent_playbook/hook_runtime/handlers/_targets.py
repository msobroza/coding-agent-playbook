"""The paths a tool call writes, shared by the §E path guards (specs/prK-hook-pack.md §E.1).

guard-generated-outputs and control-plane-guard judge the same targets: the
file tool's write paths, and the Bash write targets ``shell.parse.write_targets``
extracts from each segment, normalized against that segment's cwd exactly
like a file-tool path (repo-relative, folded on darwin/win32). One helper,
so the two guards can never disagree about where a redirect lands.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.event import ToolClass
from coding_agent_playbook.hook_runtime.dispatch.paths import normalize_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = [
    "FILE_WRITE_CLASSES",
    "file_write_paths",
    "repo_file",
    "shell_target",
    "shell_write_targets",
]

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


def repo_file(
    path: NormalizedPath, root: str, cfg: GuardConfig, *, suffixes: tuple[str, ...]
) -> tuple[str, str] | None:
    """``(realpath, repo-relative POSIX name)`` of a file the §E.3 hooks may read, else ``None``.

    The realpath must end in one of ``suffixes`` and lie inside ``root`` (the
    worktree's realpath: a symlink out of it is not this repo's code); secret
    paths and frozen eval fixtures are never read, whatever their spelling.

    Example::

        >>> repo_file(edited_app_py, "/repo", cfg, suffixes=(".py",))  # doctest: +SKIP
        ('/repo/src/app.py', 'src/app.py')
    """
    real = path.realpath
    if path.repo_rel is None or path.sibling_worktree or not real.endswith(suffixes):
        return None
    if not real.startswith(root + os.sep):
        return None
    rel = real[len(root) + 1 :].replace(os.sep, "/")
    fixtures = cfg.path_classes.get("eval_fixture")
    for key in (path.key, rel):
        if cfg.secret_paths.matches(key) or (fixtures is not None and fixtures.matches(key)):
            return None
    return real, rel
