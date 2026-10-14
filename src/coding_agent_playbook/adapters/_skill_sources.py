"""Which canonical skill files a native copy may publish (SPEC §10.8, §17.3).

A skill's ``scripts/`` and ``references/`` are byte-copied into every skills
root and the ``agent_harness`` tree, so a copied file is *published*: hashed
into the lockfile, committed under ``[output] commit = true``, and written to
the ``playbook sync --check`` scratch tree. Two kinds of source file are
therefore never copied; each is named in a stderr warning instead:

- a **secret path** (``security.paths.is_secret_path``), judged both by its name
  inside the skill and by where it resolves, so ``scripts/notes.txt ->
  ~/.aws/credentials`` is refused, not laundered under an innocent name;
- a file whose real location lies **outside the skill's own source directory**
  (a symlink leaving it): it would publish any file the user can read. Links
  that stay inside the skill are dereferenced and copied as before.

``playbook validate`` reports the same files (:func:`refused_skill_files`).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.security.files import is_secret_file, user_home

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.types import Skill


@dataclass(frozen=True)
class RefusedSkillFile:
    """A canonical skill file that is never copied, and why.

    Example::

        RefusedSkillFile(Path("playbook/skills/demo/scripts/.env"), "a secret path")
    """

    path: Path
    reason: str


def copyable_skill_files(src: Path | None, dst_root: Path) -> list[Path]:
    """Every file under ``src`` a skill copy may publish, sorted.

    Warns on stderr, naming ``dst_root`` (the copy's destination), for each
    refused file. ``[]`` when ``src`` is absent.

    Example::

        for source_file in copyable_skill_files(skill.scripts_dir, skill_dir / "scripts"):
            ...  # copy it
    """
    if src is None or not src.is_dir():
        return []
    copyable, refused = _partition(src, home=user_home())
    for item in refused:
        _warn_refused(item, dst_root)
    return copyable


def refused_skill_files(skill: Skill) -> list[RefusedSkillFile]:
    """The files of ``skill``'s ``scripts/`` and ``references/`` no copy will publish.

    Example::

        refused_skill_files(skill)  # [] for a skill without secrets or escaping links
    """
    home = user_home()
    refused: list[RefusedSkillFile] = []
    for src in (skill.scripts_dir, skill.references_dir):
        if src is not None and src.is_dir():
            refused.extend(_partition(src, home=home)[1])
    return refused


def _partition(src: Path, *, home: str) -> tuple[list[Path], list[RefusedSkillFile]]:
    """Split the files under ``src`` (sorted) into copyable and refused."""
    skill_root = src.parent.resolve()
    copyable: list[Path] = []
    refused: list[RefusedSkillFile] = []
    for source_file in sorted(path for path in src.rglob("*") if path.is_file()):
        reason = _refusal_reason(source_file, src, skill_root, home)
        if reason is None:
            copyable.append(source_file)
        else:
            refused.append(RefusedSkillFile(source_file, reason))
    return copyable, refused


def _refusal_reason(source_file: Path, src: Path, skill_root: Path, home: str) -> str | None:
    """Why ``source_file`` must not be copied, or ``None`` when it may be."""
    if is_secret_file(source_file, relative_to=src, home=home):
        return "it is a secret path, or links to one (SPEC §17.3)"
    target = source_file.resolve()
    if not target.is_relative_to(skill_root):
        return f"it links to {target}, outside the skill's source directory {skill_root}"
    return None


def _warn_refused(item: RefusedSkillFile, dst_root: Path) -> None:
    # Plain stderr, not ``warnings.warn``: user-facing CLI output, and pytest
    # runs with ``filterwarnings = ["error"]``.
    print(f"warning: not copying {item.path} into {dst_root}: {item.reason}", file=sys.stderr)
