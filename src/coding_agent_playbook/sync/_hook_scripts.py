"""The copied hook scripts of ``playbook sync`` (specs/prK-lifecycle-hooks.md §C.0, §D.8).

Byte copies (``shutil.copy2``, exec bits kept) of each external handler's
``scripts/``, which the hook's argv names repo-relatively; committed and
byte-compared by ``sync --check`` beside ``guard_config.json``. On the sync side,
not in ``hooks.guard_config``, which owns exactly the ``guard_config.json``
document (GC-D1); which source files a sync may copy is the skill copy rule of
``generated_output.source_files``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.generated_output.output_io import copy_output
from coding_agent_playbook.generated_output.source_files import copyable_skill_files
from coding_agent_playbook.hooks.resolution.tables import HOOK_SCRIPTS_DIR

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = ["CopiedScripts", "copy_hook_scripts"]


@dataclass(frozen=True)
class CopiedScripts:
    """The script copies of one external-handler hook, in sorted source order."""

    hook: ResolvedHook
    paths: tuple[Path, ...]


def copy_hook_scripts(hooks: Iterable[ResolvedHook], out_root: Path) -> list[CopiedScripts]:
    """Byte-copy each external handler's ``scripts/`` to ``<HOOK_SCRIPTS_DIR>/<id>/``, by hook id.

    Copies are ``shutil.copy2`` (bytes and mode, so the exec bit survives),
    never symlinks. A secret path or a link leaving the hook directory is never
    copied, only warned about (the skills rule, SPEC §17.3). Hooks with only
    builtin handlers have nothing to copy.

    Example::

        for copy in copy_hook_scripts(hooks, repo_root):
            recorder.record(copy.paths, Provenance(kind="hook", artifact_id=copy.hook.id))
    """
    copies: list[CopiedScripts] = []
    for hook in sorted(hooks, key=lambda h: h.id):
        scripts = None if hook.definition is None else hook.definition.scripts_dir
        if scripts is None or not _runs_a_script(hook):
            continue
        dst_root = out_root / HOOK_SCRIPTS_DIR / hook.id
        paths = tuple(
            _copy(src, dst_root / src.relative_to(scripts))
            for src in copyable_skill_files(scripts, dst_root)
        )
        copies.append(CopiedScripts(hook, paths))
    return copies


def _copy(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    return copy_output(src, dst)


def _runs_a_script(hook: ResolvedHook) -> bool:
    return any(handler.kind == "external" for handler in hook.handlers.values())
