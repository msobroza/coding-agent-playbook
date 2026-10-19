"""File helpers shared by ``playbook import-harness``'s per-kind readers and writers.

Skills and hooks both carry byte-copied scripts whose exec bit the sidecar
records; both restore it on import (``specs/prH-agent-harness.md`` decision #1,
specs/prK-lifecycle-hooks.md §C.6).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from coding_agent_playbook.generated_output.source_files import skill_subtree_files


def harness_root_for(absolute: Path, relative: str) -> Path:
    """Recover the harness root: ``absolute`` minus its harness-relative tail.

    Example: ``harness_root_for(Path("/h/skills/x/SKILL.md"), "skills/x/SKILL.md") == Path("/h")``.
    """
    root = absolute
    for _ in Path(relative).parts:
        root = root.parent
    return root


def restore_exec_bit(path: Path) -> None:
    """Set the execute bit on POSIX (no-op on Windows / missing file).

    Example: ``restore_exec_bit(harness_root / script.path)``.
    """
    if os.name != "posix" or not path.is_file():
        return
    os.chmod(path, os.stat(path).st_mode | 0o111)


def copy_tree(src: Path, dst: Path, *, restore_exec: bool) -> None:
    """Copy ``src`` files into ``dst`` verbatim, preserving the executable bit.

    Bytecode caches are skipped by the same rule sync uses, so running a harness
    script never plants ``__pycache__`` in the canonical ``playbook/skills/``
    (or a hook's ``scripts/``).

    Example: ``copy_tree(skill.scripts_dir, skill_dir / "scripts", restore_exec=True)``.
    """
    for path in skill_subtree_files(src):
        out = dst / path.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        if restore_exec and os.name == "posix" and (os.stat(path).st_mode & 0o111):
            restore_exec_bit(out)
