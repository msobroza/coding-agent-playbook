"""Which files a ``playbook sync`` owns (SPEC §12.2, §14.4).

The lockfile is the ownership record the stale-output sweep deletes from
(:mod:`coding_agent_playbook.stale_outputs`), so it must list only files the
engine itself generated. Two things could put other files in it:

- ``ClaudeCodeAdapter`` copies a skill's ``scripts/`` / ``references/`` with
  ``shutil.copytree`` and reports every file under the destination, so a file a
  user added there, or one the skill's source has since dropped, was reported
  as written. :func:`source_backed_skill_outputs` keeps only the files the
  skill's source dirs back. It lives here, not in the adapter, so the
  ``SKILL.md`` writer stays untouched.
- Recording ``path.resolve()`` turned a symlink placed among the outputs into
  an entry for its target, anywhere in the repo. :func:`owned_lock_entries`
  records logical repo-relative paths and skips any path through a symlink.

Stdlib only.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from coding_agent_playbook.lockfile import LockEntry, compute_hash

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.types import Skill

#: The file that marks a native skill output directory (SPEC §6.3.1).
SKILL_FILE_NAME = "SKILL.md"
_SCRIPTS_DIR = "scripts"
_REFERENCES_DIR = "references"


def source_backed_skill_outputs(skill: Skill, reported: Sequence[Path]) -> list[Path]:
    """Return the paths of ``reported`` that ``skill``'s sources back.

    ``reported`` is what one ``write_skill(skill, ...)`` call returned. Its
    native skill directory is the outermost parent of a reported ``SKILL.md``.
    A reported file under that directory's ``scripts/`` or ``references/`` is
    kept only when the skill's source dir has the same relative file; every
    other path (``SKILL.md``, a degraded prompt) is kept as is.

    Example::

        reported = adapter.write_skill(skill, repo_root)
        written.extend(source_backed_skill_outputs(skill, reported))
    """
    skill_dirs = {path.parent for path in reported if path.name == SKILL_FILE_NAME}
    return [path for path in reported if _is_source_backed(skill, path, skill_dirs)]


def _is_source_backed(skill: Skill, path: Path, skill_dirs: set[Path]) -> bool:
    skill_dir = _outermost_skill_dir(path, skill_dirs)
    if skill_dir is None:
        return True
    parts = path.relative_to(skill_dir).parts
    if len(parts) < 2 or parts[0] not in (_SCRIPTS_DIR, _REFERENCES_DIR):
        return True
    source_dir = skill.scripts_dir if parts[0] == _SCRIPTS_DIR else skill.references_dir
    return source_dir is not None and source_dir.joinpath(*parts[1:]).is_file()


def _outermost_skill_dir(path: Path, skill_dirs: set[Path]) -> Path | None:
    """The farthest parent of ``path`` in ``skill_dirs``: a ``references/`` file
    that is itself named ``SKILL.md`` must not anchor a nested skill dir."""
    outermost: Path | None = None
    for parent in path.parents:
        if parent in skill_dirs:
            outermost = parent
    return outermost


def owned_lock_entries(written: Iterable[Path], repo_root: Path) -> list[LockEntry]:
    """Lockfile entries for ``written``, sorted, one per repo-relative path.

    A path outside ``repo_root`` or reached through a symlink (the file itself
    or any directory between it and the repo root) is skipped: the engine owns
    the location it wrote, never a symlink's target. Unreadable files are
    skipped too.

    Example::

        entries = owned_lock_entries(outcome.written, repo_root)
        # [LockEntry(path=".claude/CLAUDE.md", sha256="...", bytes=412), ...]
    """
    root = repo_root.resolve()
    candidates = (repo_relative_path(path, repo_root, root) for path in written)
    rels = {rel for rel in candidates if rel is not None}
    entries: list[LockEntry] = []
    for rel in sorted(rels):
        target = root.joinpath(*rel.parts)
        content = _read_unlinked(target)
        if content is not None:
            entries.append(
                LockEntry(path=rel.as_posix(), sha256=compute_hash(content), bytes=len(content))
            )
    return entries


def repo_relative_path(path: Path, repo_root: Path, root: Path) -> PurePosixPath | None:
    """``path`` relative to the repo root without resolving symlinks, else ``None``.

    ``root`` is ``repo_root.resolve()``. Adapters build paths from ``repo_root``
    as given; a resolved path is matched against ``root`` instead. A path
    outside the repo, or one with a ``..`` part, gives ``None``.

    Example::

        repo_relative_path(repo / ".claude" / "CLAUDE.md", repo, repo.resolve())
        # PurePosixPath('.claude/CLAUDE.md')
    """
    for base in (repo_root, root):
        try:
            rel = PurePosixPath(path.relative_to(base).as_posix())
        except ValueError:
            continue
        return rel if rel.parts and ".." not in rel.parts else None
    return None


def _read_unlinked(target: Path) -> bytes | None:
    """``target``'s bytes when no component below the repo root is a symlink."""
    try:
        if target.resolve() != target:
            return None
        return target.read_bytes()
    except (OSError, RuntimeError, ValueError):  # RuntimeError: symlink loop (3.12)
        return None
