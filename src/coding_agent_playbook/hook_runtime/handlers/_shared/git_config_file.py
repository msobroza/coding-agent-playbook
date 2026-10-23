"""The repository's git config file, before and after a file-tool call (specs/prK-hook-pack.md §E.2, §E.4).

block-precommit-bypass judges a ``hooksPath`` line written into it and
git-commit-push-policy-guard a ``pushOption`` line (specs/prF-forge-adapter.md
§8.4), on the same file: ``.git/config``, the common dir's ``config`` or a
worktree's ``config.worktree``. :func:`config_edits` reads each such file a
call writes (at most 1 MiB) and simulates the call's result in memory, never
touching the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.path_globs import fold_key

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo, ToolCall
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath

__all__ = ["ConfigEdit", "config_edits"]

_READ_LIMIT: Final = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ConfigEdit:
    """One git config file a call writes: its text now and after, and what the call writes.

    ``before`` is ``None`` for an absent or unreadable file, ``after`` when the
    call cannot be simulated (judge ``written``, the whole edit, then).

    Example: ``ConfigEdit("[core]\\n", "[core]\\n[push]\\n\\tpushOption = ci.skip\\n", "...")``.
    """

    before: str | None
    after: str | None
    written: str


def config_edits(tool: ToolCall, repo: RepoInfo, platform: str) -> list[ConfigEdit]:
    """The repository git config files ``tool`` writes, before and after it runs.

    Example: ``config_edits(edit_of_dot_git_config, repo, "linux")[0].after`` is the new text.
    """
    from coding_agent_playbook.hook_runtime.handlers._shared.edit_preview import preview_after
    from coding_agent_playbook.hook_runtime.handlers._shared.targets import file_write_paths

    edits: list[ConfigEdit] = []
    for path in file_write_paths(tool):
        if not _is_git_config(path, repo, platform):
            continue
        before = _read(path)
        written = "\n".join(f.text for f in tool.content if f.path == path.raw)
        edits.append(ConfigEdit(before, preview_after(tool, before), written))
    return edits


def _is_git_config(path: NormalizedPath, repo: RepoInfo, platform: str) -> bool:
    """``.git/config``, or the git dir's or common dir's ``config`` / ``config.worktree``."""
    if path.key == ".git/config":
        return True
    candidates = {
        os.path.join(repo.common_dir, "config"),
        os.path.join(repo.git_dir, "config"),
        os.path.join(repo.git_dir, "config.worktree"),
    }
    real = fold_key(path.realpath, platform)
    return any(real == fold_key(candidate, platform) for candidate in candidates)


def _read(path: NormalizedPath) -> str | None:
    from coding_agent_playbook.hook_runtime.config.reader import read_small_file

    if not path.exists:
        return None
    try:
        data, _ = read_small_file(Path(path.realpath), _READ_LIMIT)
        return data.decode("utf-8")
    except (OSError, ValueError):  # unreadable or too large: judge the whole edit
        return None
