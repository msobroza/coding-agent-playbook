"""Shared native Agent-Skills directory writer (SPEC §6.3, §10.8).

The **single source of truth** for emitting a native skills tree. Every adapter
that ships skills natively delegates here, differing only in the root:

- ``claude_code``   -> ``.claude/skills/<id>/``
- ``opencode``      -> ``.opencode/skills/<id>/``
- ``shared_skills`` -> ``shared_skills/<id>/`` (the cross-agent skills hub)

Because the bytes never depend on the root, the same skill is byte-identical in
every root. Each directory holds ``SKILL.md`` plus byte-copies (copies, not
symlinks) of the canonical ``scripts/`` and ``references/`` subtrees.

``SKILL.md`` follows the Agent Skills standard read by Claude Code and OpenCode:
frontmatter ``name`` is forced to the skill id (= the directory name) and must
match :data:`AGENT_SKILL_NAME_PATTERN`; ``description`` must be non-empty. The
playbook :data:`~coding_agent_playbook.renderer.SENTINEL` cannot sit on line 1
(agent parsers require ``^---`` there), so it is the first body line after the
closing fence — the same placement as the ``agent_harness`` adapter (§10.7.3).

Ownership is decided **before** any write: ``<root>/<id>/`` is engine-owned iff
its ``SKILL.md`` carries the sentinel anywhere (or the previous sync's lockfile
lists it — pre-sentinel engines wrote ``.claude/skills/`` without one). A
user-authored directory with a colliding id is skipped with a warning, never
overwritten, and cleanup never touches it.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from coding_agent_playbook.harness.emitter import with_sentinel_body
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.types import format_frontmatter

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from coding_agent_playbook.types import Skill

#: The primary file of a native skill directory.
SKILL_FILENAME = "SKILL.md"

#: Agent Skills ``name`` rule (OpenCode + Claude Code): lowercase alphanumerics
#: separated by single hyphens, 1-64 chars. OpenCode silently skips a skill whose
#: name fails it, which is why ``playbook validate`` checks it up front.
AGENT_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
AGENT_SKILL_NAME_MAX_CHARS = 64
AGENT_SKILL_DESCRIPTION_MAX_CHARS = 1024

#: Fallback id for a skill without an ``id`` key — mirrors the orchestrator's
#: overlay-merge key and :meth:`Skill.to_prompt`.
_DEFAULT_SKILL_ID = "skill"

_SENTINEL_BYTES = SENTINEL.encode("utf-8")

#: ``(st_dev, st_ino)`` — a file's identity, independent of path spelling.
_FileIdentity = tuple[int, int]


def skill_id_of(skill: Skill) -> str:
    """Return the canonical id of ``skill`` (its ``id`` frontmatter key).

    Example: ``skill_id_of(skill)`` -> ``"query-database"``.
    """
    return str(skill.frontmatter.get("id", _DEFAULT_SKILL_ID))


def has_declared_id(skill: Skill) -> bool:
    """Return whether ``skill`` declares an ``id`` key in its frontmatter.

    Id-less skills all merge under the fallback id ``"skill"`` (so all but one
    are silently dropped); ``playbook validate`` uses this to flag each of them.

    Example: ``has_declared_id(skill)`` -> ``True`` for ``id: query-db``.
    """
    return "id" in skill.frontmatter


def ensure_path_safe_skill_id(skill_id: str) -> str:
    """Return ``skill_id`` unchanged if it is one relative path segment.

    Rejects empty ids, ``.``/``..``, path separators, NUL bytes and absolute or
    drive-qualified ids, so a skill can never be written outside its root.

    Example: ``ensure_path_safe_skill_id("demo")`` -> ``"demo"``;
    ``ensure_path_safe_skill_id("../escape")`` raises ``ValueError``.
    """
    if _is_single_relative_segment(skill_id):
        return skill_id
    raise ValueError(
        f"skill id {skill_id!r} is not path-safe: expected a single relative "
        "directory name (no '/', '\\', '..', '.', NUL, drive or absolute path)"
    )


def _is_single_relative_segment(skill_id: str) -> bool:
    if skill_id in {"", ".", ".."} or "\x00" in skill_id:
        return False
    if "/" in skill_id or "\\" in skill_id:
        return False
    return not PureWindowsPath(skill_id).drive


def agent_skill_issues(skill: Skill) -> list[str]:
    """List the Agent Skills standard violations of ``skill`` (empty = valid).

    Checks that an ``id`` string is declared, the id (emitted as ``name``)
    against :data:`AGENT_SKILL_NAME_PATTERN` and its 1-64 char limit, and that
    ``description`` is 1-1024 chars.

    Example: a skill with ``id: My_Skill`` and no description yields two issues.
    """
    return [*_id_issues(skill), *_description_issues(skill)]


def _id_issues(skill: Skill) -> list[str]:
    if not has_declared_id(skill):
        return [
            f"skill has no 'id'; it is emitted as {_DEFAULT_SKILL_ID!r} and collides "
            "with every other id-less skill (declare 'id:' in its SKILL.md frontmatter)"
        ]
    raw_id = skill.frontmatter["id"]
    if not isinstance(raw_id, str):
        return [f"skill 'id' must be a string, got {type(raw_id).__name__} {raw_id!r}"]
    return _name_issues(raw_id)


def _name_issues(skill_id: str) -> list[str]:
    if len(skill_id) > AGENT_SKILL_NAME_MAX_CHARS:
        return [
            f"skill id {skill_id!r} is {len(skill_id)} chars; the Agent Skills "
            f"name limit is {AGENT_SKILL_NAME_MAX_CHARS}"
        ]
    if AGENT_SKILL_NAME_PATTERN.fullmatch(skill_id):
        return []
    return [
        f"skill id {skill_id!r} is not a valid Agent Skills name (must match "
        f"{AGENT_SKILL_NAME_PATTERN.pattern}); OpenCode silently skips it"
    ]


def _description_issues(skill: Skill) -> list[str]:
    description = str(skill.frontmatter.get("description") or "").strip()
    if not description:
        return ["skill has no 'description'; Agent Skills requires a non-empty description"]
    if len(description) > AGENT_SKILL_DESCRIPTION_MAX_CHARS:
        return [
            f"skill description is {len(description)} chars; the Agent Skills "
            f"limit is {AGENT_SKILL_DESCRIPTION_MAX_CHARS}"
        ]
    return []


def render_skill_md(skill: Skill) -> str:
    """Render the ``SKILL.md`` text for ``skill``.

    Frontmatter stays on line 1 with ``name`` forced to the skill id (every
    other key, including ``id``, is kept in authored order after it); the
    sentinel HTML comment is the first body line.

    Example: ``render_skill_md(skill).splitlines()[0]`` -> ``"---"``.
    """
    skill_id = ensure_path_safe_skill_id(skill_id_of(skill))
    others = {key: value for key, value in skill.frontmatter.items() if key != "name"}
    frontmatter = format_frontmatter({"name": skill_id, **others}, "")
    return with_sentinel_body(frontmatter, skill.body)


@dataclass(frozen=True)
class SkillWriter:
    """Write and clean one native skills root (``root`` is repo-relative).

    Example::

        writer = SkillWriter(Path(".claude") / "skills")
        written = writer.write(skill, repo_root)        # SKILL.md + scripts/ + references/
        removed = writer.cleanup({p.resolve() for p in written}, repo_root)
    """

    root: Path

    def skills_root(self, repo_root: Path) -> Path:
        """Return the absolute skills root under ``repo_root``."""
        return repo_root / self.root

    def write(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Write ``<root>/<id>/`` for ``skill`` and return every file written.

        Returns ``[]`` (and warns on stderr) when ``<root>/<id>/`` already
        exists and is not engine-owned: a user-authored skill dir is never
        overwritten. Raises ``ValueError`` for a non-path-safe id or a
        destination that would resolve outside the skills root (e.g. through
        a symlink).
        """
        skill_md_text = render_skill_md(skill)  # validates the id before any I/O
        skill_dir = self._skill_dir(repo_root, skill_id_of(skill))
        if not _may_claim(skill_dir, repo_root):
            _warn_not_engine_owned(skill_dir)
            return []
        return _write_skill_files(skill, skill_md_text, skill_dir)

    def _skill_dir(self, repo_root: Path, skill_id: str) -> Path:
        root = self.skills_root(repo_root)
        skill_dir = root / ensure_path_safe_skill_id(skill_id)
        if not skill_dir.resolve().is_relative_to(root.resolve()):
            raise ValueError(
                f"skill directory {skill_dir} resolves to {skill_dir.resolve()}, "
                f"outside the skills root {root.resolve()}"
            )
        _adopt_case_variant(skill_dir)
        return skill_dir

    def cleanup(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Delete stale files from engine-owned skill dirs; return the deleted paths.

        A ``<root>/<id>/`` is engine-owned iff its ``SKILL.md`` (a regular file,
        not a symlink) contains the sentinel. In such a dir every regular file
        that is not one of ``written_paths`` is deleted, then empty directories
        are pruned (including the skill dir itself). "Is one of" compares file
        identity (``st_dev``/``st_ino``), not path spelling, so a relative or
        symlinked ``repo_root`` or a case-insensitive filesystem never deletes a
        file written this sync. Directories without the sentinel are
        user-authored and never touched; symlinks are never followed nor deleted.
        """
        root = self.skills_root(repo_root)
        if not root.is_dir():
            return []
        written_ids = _file_identities(written_paths)
        deleted: list[Path] = []
        for skill_dir in sorted(root.iterdir()):
            if not is_engine_owned_skill_dir(skill_dir):
                continue
            deleted.extend(_delete_unwritten_files(skill_dir, written_ids))
            _prune_empty_dirs(skill_dir)
        return deleted


def is_engine_owned_skill_dir(skill_dir: Path) -> bool:
    """Return whether ``skill_dir`` is a real dir whose ``SKILL.md`` has the sentinel.

    Binary or unreadable files never raise: the sentinel is searched as bytes.
    """
    if skill_dir.is_symlink() or not skill_dir.is_dir():
        return False
    skill_md = skill_dir / SKILL_FILENAME
    if skill_md.is_symlink() or not skill_md.is_file():
        return False
    try:
        return _SENTINEL_BYTES in skill_md.read_bytes()
    except OSError:
        return False


# --- ownership (decided before any write) ----------------------------------


def _may_claim(skill_dir: Path, repo_root: Path) -> bool:
    """Return whether the engine may write into ``skill_dir``.

    Claimable: absent, an empty real directory, engine-owned (sentinel), or a
    real directory whose ``SKILL.md`` the previous sync's lockfile lists (the
    pre-sentinel ``.claude/skills/`` output). Anything else — a user-authored
    skill dir, a symlink, a plain file — is left alone, because writing the
    sentinel ``SKILL.md`` would make cleanup treat the user's files as stale.
    """
    if skill_dir.is_symlink():
        return False
    if not skill_dir.exists():
        return True
    if is_engine_owned_skill_dir(skill_dir) or _is_empty_dir(skill_dir):
        return True
    return skill_dir.is_dir() and _listed_in_prior_lockfile(skill_dir / SKILL_FILENAME, repo_root)


def _is_empty_dir(path: Path) -> bool:
    return path.is_dir() and next(path.iterdir(), None) is None


def _listed_in_prior_lockfile(path: Path, repo_root: Path) -> bool:
    """Return whether the last sync's lockfile records ``path`` as engine-written.

    Any lockfile read/parse failure answers ``False`` — the fail-safe choice,
    since ``False`` only ever means "leave the directory alone".
    """
    # Lazy import: only this rare sentinel-less path needs the lockfile, and
    # sources.filesystem pulls in the whole eval-loader stack at import time.
    from coding_agent_playbook.sources.filesystem import FileSystemStateSource

    try:
        lockfile = FileSystemStateSource(repo_root=repo_root).load_lockfile()
    except (OSError, ValueError, KeyError, TypeError):  # TOMLDecodeError is a ValueError
        return False
    rel = path.relative_to(repo_root).as_posix()
    return lockfile is not None and lockfile.find(rel) is not None


def _warn_not_engine_owned(skill_dir: Path) -> None:
    # Plain stderr, not ``warnings.warn``: this is user-facing CLI output, and
    # pytest runs with ``filterwarnings = ["error"]``.
    print(
        f"warning: not writing {skill_dir}: it exists but is not playbook-managed "
        f"(its {SKILL_FILENAME} has no playbook sentinel); rename or remove it to "
        "let 'playbook sync' manage this skill",
        file=sys.stderr,
    )


def _adopt_case_variant(skill_dir: Path) -> None:
    """Rename an engine-owned ``<root>/<Id>/`` to ``<root>/<id>/`` (case-only change).

    Only fires on a case-insensitive filesystem, where the old-cased directory
    *is* ``skill_dir``: without the rename the new id is written into the old
    name, so the dir no longer matches the emitted ``name`` (Agent Skills needs
    name == dir name). Staged through a temporary name for portability.
    """
    variant = _case_variant_of(skill_dir)
    if variant is None or not is_engine_owned_skill_dir(variant):
        return
    staging = variant.with_name(f"{variant.name}.playbook-case-rename")
    variant.rename(staging)
    staging.rename(skill_dir)


def _case_variant_of(skill_dir: Path) -> Path | None:
    """Return the on-disk entry that is ``skill_dir`` spelled with other case."""
    if not skill_dir.parent.is_dir():
        return None
    wanted = skill_dir.name.casefold()
    for entry in skill_dir.parent.iterdir():
        if entry.name != skill_dir.name and entry.name.casefold() == wanted:
            return entry if _is_same_file(entry, skill_dir) else None
    return None


def _is_same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:  # ``second`` is absent on a case-sensitive filesystem
        return False


# --- writing ----------------------------------------------------------------


def _write_skill_files(skill: Skill, skill_md_text: str, skill_dir: Path) -> list[Path]:
    """Write ``SKILL.md`` plus the copied subtrees into the claimed ``skill_dir``."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / SKILL_FILENAME
    _prepare_destination(skill_md, skill_dir)
    skill_md.write_text(skill_md_text, encoding="utf-8")
    written = [skill_md]
    written.extend(_copy_subtree(skill.scripts_dir, skill_dir / "scripts", skill_dir))
    written.extend(_copy_subtree(skill.references_dir, skill_dir / "references", skill_dir))
    return written


def _prepare_destination(dst: Path, skill_dir: Path) -> None:
    """Make ``dst`` a fresh path for a regular file inside engine-owned ``skill_dir``.

    Refuses a parent that resolves outside ``skill_dir`` (an escaping symlink).
    Otherwise clears whatever is in the way: a file or symlink where a parent
    directory must go (a file became a folder), a real directory at ``dst`` (a
    folder became a file), and any existing file or symlink at ``dst`` —
    unlinked, never written through, so a read-only copy from an earlier sync
    cannot block the rewrite and the engine never writes outside the root.
    """
    # Check before mkdir: resolve() follows any existing symlinked component,
    # so an escaping intermediate directory is refused before anything is created.
    if not dst.parent.resolve().is_relative_to(skill_dir.resolve()):
        raise ValueError(
            f"refusing to write {dst}: its directory resolves to "
            f"{dst.parent.resolve()}, outside {skill_dir.resolve()}"
        )
    _clear_non_dir_ancestors(dst, skill_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _remove_existing(dst)


def _clear_non_dir_ancestors(dst: Path, skill_dir: Path) -> None:
    """Unlink any file or symlink sitting where a parent directory of ``dst`` goes."""
    current = skill_dir
    for part in dst.parent.relative_to(skill_dir).parts:
        current = current / part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            current.unlink()


def _remove_existing(dst: Path) -> None:
    """Remove ``dst`` if present: ``rmtree`` a real directory, unlink anything else."""
    if dst.is_dir() and not dst.is_symlink():
        shutil.rmtree(dst)
        return
    dst.unlink(missing_ok=True)


def _copy_subtree(src: Path | None, dst_root: Path, skill_dir: Path) -> list[Path]:
    """Byte-copy every file under ``src`` into ``dst_root`` (``shutil.copy2``).

    Returns the destination files in sorted source order; ``[]`` when ``src``
    is absent. Source symlinks are dereferenced (copies, not symlinks). Each
    recorded path is the file ``copy2`` actually wrote, never a directory.
    """
    if src is None or not src.is_dir():
        return []
    written: list[Path] = []
    for source_file in sorted(path for path in src.rglob("*") if path.is_file()):
        dst = dst_root / source_file.relative_to(src)
        _prepare_destination(dst, skill_dir)
        written.append(Path(shutil.copy2(source_file, dst)))
    return written


# --- cleanup ----------------------------------------------------------------


def _file_identity(path: Path) -> _FileIdentity | None:
    """Return ``(st_dev, st_ino)`` of ``path`` (not following symlinks), or ``None``."""
    try:
        status = path.stat(follow_symlinks=False)
    except OSError:
        return None
    return (status.st_dev, status.st_ino)


def _file_identities(paths: Iterable[Path]) -> set[_FileIdentity]:
    identities = (_file_identity(path) for path in paths)
    return {identity for identity in identities if identity is not None}


def _iter_regular_files(top: Path) -> Iterator[Path]:
    """Yield regular (non-symlink) files under ``top`` without following symlinks."""
    for dirpath, _dirnames, filenames in os.walk(top, followlinks=False):
        for filename in filenames:
            path = Path(dirpath) / filename
            if not path.is_symlink():
                yield path


def _delete_unwritten_files(skill_dir: Path, written_ids: set[_FileIdentity]) -> list[Path]:
    deleted: list[Path] = []
    for path in sorted(_iter_regular_files(skill_dir)):
        identity = _file_identity(path)
        if identity is None or identity in written_ids:
            continue
        path.unlink()
        deleted.append(path)
    return deleted


def _prune_empty_dirs(top: Path) -> None:
    """Remove now-empty directories under (and including) ``top``, bottom-up."""
    for dirpath, _dirnames, _filenames in os.walk(top, topdown=False, followlinks=False):
        with contextlib.suppress(OSError):
            Path(dirpath).rmdir()
