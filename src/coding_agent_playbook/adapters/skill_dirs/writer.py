"""Shared native Agent-Skills directory writer (SPEC §6.3, §10.8).

The **single source of truth** for emitting a native skills tree. Every adapter
that ships skills natively delegates here, differing only in the root:

- ``claude_code``   -> ``.claude/skills/<id>/``
- ``opencode``      -> ``.opencode/skills/<id>/``
- ``shared_skills`` -> ``.agents/skills/<id>/`` (the shared skill root: Codex, OpenCode)

Because the bytes never depend on the root, the same skill is byte-identical in
every root. Each directory holds ``SKILL.md`` plus byte-copies (copies, not
symlinks) of the canonical ``scripts/`` and ``references/`` subtrees, minus
Python bytecode caches (:mod:`coding_agent_playbook.adapters._skill_files`).

A skill with member rules (ADR 0001) also gets one ``references/<rule-id>.md``
per active member, written from ``MemberReference.text`` after the copies and
guarded like them; its ``SKILL.md`` carries the composed description and the
generated ``## References`` index (:mod:`coding_agent_playbook.skills.document`).
The catalog-only ``playbook:`` block is never emitted, so a skill without
members (a bundled plugin's) is written exactly as authored.

``SKILL.md`` follows the Agent Skills standard read by Claude Code and OpenCode:
frontmatter ``name`` is forced to the skill id (= the directory name) and must
match :data:`~coding_agent_playbook.skills.naming.AGENT_SKILL_NAME_PATTERN`;
``description`` must be non-empty. The
playbook :data:`~coding_agent_playbook._sentinel.SENTINEL` cannot sit on line 1
(agent parsers require ``^---`` there), so it is the first body line after the
closing fence — the same placement as the ``agent_harness`` adapter (§10.7.3).

Ownership is decided **before** any write: ``<root>/<id>/`` is engine-owned iff
its ``SKILL.md`` carries the sentinel at an anchored position
(``_sentinel.has_sentinel``: here the first body line, so a ``SKILL.md`` that
only quotes it in prose is the user's), or the previous sync's lockfile lists
it with unchanged bytes (pre-sentinel engines wrote ``.claude/skills/`` without
one). A user-authored directory with a colliding id is skipped with a
warning, never overwritten; so is a skills root that cannot hold directories (a
dangling symlink or a plain file where it should be), and a ``<root>/<id>`` that
is a link leading out of the root, as is a file under such a link inside a
claimed dir (never a write outside the root). ``playbook sync --check``/
``--check-staged`` render into an empty scratch dir but decide ownership against
the real tree (:func:`deciding_ownership_against`), so they skip exactly what
write mode skips.

The writer never deletes stale files. Output an earlier sync left behind in a
skill dir is settled by the one lockfile-based leftover policy
(``commands/_sync_orphans.py``, SPEC §4.2 step 9): a file the engine never
wrote is never deleted, even inside an engine-owned dir.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from coding_agent_playbook._sentinel import has_sentinel
from coding_agent_playbook._symlinks import is_dangling_symlink, link_leaving, real_path
from coding_agent_playbook.adapters._skill_sources import copyable_skill_files
from coding_agent_playbook.adapters.skill_dirs.ownership import PriorOutput
from coding_agent_playbook.artifacts.member_reference import member_reference_path
from coding_agent_playbook.harness.emitter import with_sentinel_body
from coding_agent_playbook.skills.document import emitted_body, emitted_frontmatter
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.types import format_frontmatter

if TYPE_CHECKING:
    from collections.abc import Iterator

    from coding_agent_playbook.types import Skill

#: The primary file of a native skill directory.
SKILL_FILENAME = "SKILL.md"

#: The real repo root ownership is decided against while rendering elsewhere
#: (``--check`` renders into an empty scratch dir); ``None`` = the output root.
_OWNERSHIP_ROOT: ContextVar[Path | None] = ContextVar("playbook_skill_ownership_root", default=None)


@contextlib.contextmanager
def deciding_ownership_against(repo_root: Path) -> Iterator[None]:
    """Decide skill-dir ownership against ``repo_root`` while writing elsewhere.

    ``playbook sync --check``/``--check-staged`` render into an empty scratch
    dir, where every ``<root>/<id>/`` is claimable. Inside this context a
    :class:`SkillWriter` asks the *real* tree instead, so a skill dir write mode
    would skip (hand-written, symlinked, a plain file) is skipped in the scratch
    render too — no false drift, and a user's own files are never "generated".

    Example::

        with deciding_ownership_against(repo_root):
            written = writer.write(skill, scratch_root)  # [] if repo's dir is user-owned
    """
    token = _OWNERSHIP_ROOT.set(repo_root)
    try:
        yield
    finally:
        _OWNERSHIP_ROOT.reset(token)


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


def render_skill_md(skill: Skill) -> str:
    """Render the ``SKILL.md`` text for ``skill``.

    Frontmatter stays on line 1 with ``name`` forced to the skill id (every
    other key, including ``id``, is kept in authored order after it); the
    sentinel HTML comment is the first body line. Frontmatter and body come
    from :mod:`~coding_agent_playbook.skills.document`: the catalog-only
    ``playbook`` block is never emitted, and a skill with member rules gets its
    composed description and the ``## References`` index. A plain skill (a
    bundled plugin's) is rendered exactly as authored.

    Example: ``render_skill_md(skill).splitlines()[0]`` -> ``"---"``.
    """
    skill_id = ensure_path_safe_skill_id(skill_id_of(skill))
    emitted = emitted_frontmatter(skill)
    others = {key: value for key, value in emitted.items() if key != "name"}
    frontmatter = format_frontmatter({"name": skill_id, **others}, "")
    return with_sentinel_body(frontmatter, emitted_body(skill))


@dataclass(frozen=True)
class SkillWriter:
    """Write one native skills root (``root`` is repo-relative).

    It never deletes stale output: files an earlier sync left in a skill dir
    are settled by ``playbook sync``'s lockfile leftover policy (§4.2 step 9).

    Example::

        writer = SkillWriter(Path(".claude") / "skills")
        written = writer.write(skill, repo_root)  # SKILL.md + scripts/ + references/
    """

    root: Path

    @property
    def location(self) -> str:
        """The root as an adapter ``output_locations`` directory entry (``".claude/skills/"``)."""
        return f"{self.root.as_posix()}/"

    def skills_root(self, repo_root: Path) -> Path:
        """Return the absolute skills root under ``repo_root``."""
        return repo_root / self.root

    def write(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Write ``<root>/<id>/`` for ``skill`` and return every file written.

        Returns ``[]`` (and warns on stderr) when ``<root>/<id>/`` already
        exists and is not engine-owned — a user-authored skill dir is never
        overwritten — when the skills root is unusable (a dangling symlink, a
        plain file), or when ``<root>/<id>`` is a link leading out of the root.
        A file under a link leading out of ``<root>/<id>/`` is skipped the same
        way, the rest of the skill still written. Ownership is judged under
        :func:`deciding_ownership_against`'s root when one is active (``--check``
        modes), else under ``repo_root``. Raises ``ValueError`` for a
        non-path-safe id.
        """
        skill_md_text = render_skill_md(skill)  # validates the id before any I/O
        skill_id = skill_id_of(skill)
        owner_root = _OWNERSHIP_ROOT.get() or repo_root
        owner_skills = self.skills_root(owner_root)
        unusable = _unusable_component(owner_skills, owner_root)
        if unusable is not None:
            _warn_unusable_root(unusable)
            return []
        owner_dir = owner_skills / ensure_path_safe_skill_id(skill_id)
        if not real_path(owner_dir).is_relative_to(real_path(owner_skills)):
            # Regression: a ValueError here stopped every sync mode with a traceback.
            where = f"it resolves to {real_path(owner_dir)}, outside the skills root {owner_skills}"
            _warn_through_link(owner_dir, where)
            return []
        skill_dir = self._skill_dir(repo_root, skill_id)
        if not _may_claim(owner_dir, owner_root):
            _warn_not_engine_owned(owner_dir)
            return []
        return _write_skill_files(skill, skill_md_text, skill_dir, PriorOutput(repo_root))

    def _skill_dir(self, repo_root: Path, skill_id: str) -> Path:
        skill_dir = self._contained(repo_root, skill_id)
        _adopt_case_variant(skill_dir)
        return skill_dir

    def _contained(self, repo_root: Path, skill_id: str) -> Path:
        """``<root>/<id>`` under ``repo_root``; ``ValueError`` if it resolves outside the root
        (defensive: :meth:`write` has already skipped such a dir with a warning)."""
        root = self.skills_root(repo_root)
        skill_dir = root / ensure_path_safe_skill_id(skill_id)
        if not real_path(skill_dir).is_relative_to(real_path(root)):
            raise ValueError(
                f"skill directory {skill_dir} resolves to {real_path(skill_dir)}, "
                f"outside the skills root {real_path(root)}"
            )
        return skill_dir


def is_engine_owned_skill_dir(skill_dir: Path) -> bool:
    """Return whether ``skill_dir`` is a real dir whose ``SKILL.md`` has the sentinel.

    The sentinel must sit at an anchored position (``_sentinel.has_sentinel``;
    :func:`render_skill_md` writes it as the first body line), so a hand-written
    ``SKILL.md`` that merely quotes it is never claimed. Binary, undecodable or
    unreadable files never raise: they are user-owned (``False``).

    Example: ``is_engine_owned_skill_dir(repo / ".claude/skills/demo")`` -> ``True``
    after ``playbook sync`` wrote it.
    """
    if skill_dir.is_symlink() or not skill_dir.is_dir():
        return False
    skill_md = skill_dir / SKILL_FILENAME
    if skill_md.is_symlink() or not skill_md.is_file():
        return False
    try:
        return has_sentinel(skill_md.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return False


# --- ownership (decided before any write) ----------------------------------


def _may_claim(skill_dir: Path, repo_root: Path) -> bool:
    """Return whether the engine may write into ``skill_dir``.

    Claimable: absent, an empty real directory, engine-owned (sentinel), or a
    real directory whose ``SKILL.md`` the previous sync's lockfile lists with
    unchanged bytes (the pre-sentinel ``.claude/skills/`` output). Anything else
    — a user-authored skill dir, a symlink, a plain file, a listed ``SKILL.md``
    the user has since rewritten (an adopted leftover, a stripped sentinel) — is
    left alone: writing the sentinel ``SKILL.md`` would turn the user's
    directory into engine output.
    """
    if skill_dir.is_symlink():
        return False
    if not skill_dir.exists():
        return True
    if is_engine_owned_skill_dir(skill_dir) or _is_empty_dir(skill_dir):
        return True
    return skill_dir.is_dir() and PriorOutput(repo_root).wrote_unchanged(skill_dir / SKILL_FILENAME)


def _is_empty_dir(path: Path) -> bool:
    return path.is_dir() and next(path.iterdir(), None) is None


def _warn_not_engine_owned(skill_dir: Path) -> None:
    # Plain stderr, not ``warnings.warn``: this is user-facing CLI output, and
    # pytest runs with ``filterwarnings = ["error"]``.
    print(
        f"warning: not writing {skill_dir}: it exists but is not playbook-managed "
        f"(its {SKILL_FILENAME} has no playbook sentinel); rename or remove it to "
        "let 'playbook sync' manage this skill",
        file=sys.stderr,
    )


def _unusable_component(skills_root: Path, repo_root: Path) -> Path | None:
    """The first path from ``repo_root`` to ``skills_root`` that cannot be a directory.

    A dangling symlink (e.g. ``.claude/skills -> ../.agents/skills`` after its
    target was removed) or a plain file: ``mkdir`` would crash through it.
    """
    try:
        parts = skills_root.relative_to(repo_root).parts
    except ValueError:
        return None
    current = repo_root
    for part in parts:
        current = current / part
        if is_dangling_symlink(current):
            return current
        if current.exists() and not current.is_dir():
            return current
    return None


def _warn_unusable_root(blocker: Path) -> None:
    print(
        f"warning: not writing skills under {blocker}: it is a dangling symlink or a "
        "file, not a directory; fix or remove it, then re-run 'playbook sync'",
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


def _write_skill_files(
    skill: Skill, skill_md_text: str, skill_dir: Path, prior: PriorOutput
) -> list[Path]:
    """Write ``SKILL.md``, the copied subtrees, then the member references into ``skill_dir``."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / SKILL_FILENAME
    if not _prepare_destination(skill_md, skill_dir, prior):
        return []
    skill_md.write_text(skill_md_text, encoding="utf-8")
    written = [skill_md]
    written.extend(_copy_subtree(skill.scripts_dir, skill_dir / "scripts", skill_dir, prior))
    written.extend(_copy_subtree(skill.references_dir, skill_dir / "references", skill_dir, prior))
    written.extend(_write_member_references(skill, skill_dir, prior))
    return written


def _write_member_references(skill: Skill, skill_dir: Path, prior: PriorOutput) -> list[Path]:
    """Write ``references/<rule-id>.md`` for every member, as UTF-8 LF bytes.

    The same ``_prepare_destination`` guard as copied files: inside this
    engine-owned skill dir a regular file at the destination is replaced, as a
    copied reference is; a real directory there, or a file where a parent
    directory must go, that holds files the previous lockfile does not list is
    kept with a warning and the reference is skipped. The bytes are
    ``MemberReference.text``, computed once per sync, so every root gets the
    same file (specs/prS-skills-context.md section 6.4.5). Validation (V12)
    keeps a hand-written reference from taking a member's file name. Example::

        written = _write_member_references(skill, repo / ".claude/skills/python-coding", prior)
    """
    written: list[Path] = []
    for member in skill.member_references:
        destination = skill_dir / member_reference_path(member.rule_id)
        if _prepare_destination(destination, skill_dir, prior):
            destination.write_bytes(member.text.encode("utf-8"))
            written.append(destination)
    return written


def _prepare_destination(dst: Path, skill_dir: Path, prior: PriorOutput) -> bool:
    """Make ``dst`` a fresh path for a regular file inside engine-owned ``skill_dir``.

    Refuses a parent that resolves outside ``skill_dir`` (an escaping symlink).
    Otherwise clears whatever is in the way: a symlink where a parent directory
    must go, and any existing file or symlink at ``dst`` — unlinked, never
    written through, so a read-only copy from an earlier sync cannot block the
    rewrite and the engine never writes outside the root. A regular file where
    a parent directory must go (a file became a folder) or a real directory at
    ``dst`` (a folder became a file) is displaced only if it holds nothing but
    files the previous lockfile lists; otherwise ``dst`` is skipped with a
    warning and ``False`` is returned, so a user file is never deleted. A link
    leading out of ``skill_dir`` on the way skips ``dst`` the same way: the
    engine never writes outside the root, nor deletes the user's link.
    """
    # Check before mkdir, which would create directories through the link.
    link = link_leaving(dst.parent, skill_dir)
    if link is not None:
        # was a ValueError: a traceback for sync
        _warn_through_link(dst, f"{link} is a symbolic link leading outside the skill directory")
        return False
    blocker = swap_blocker(dst, skill_dir)
    if blocker is not None and not prior.may_displace(blocker):
        _warn_blocked(dst, blocker)
        return False
    _clear_non_dir_ancestors(dst, skill_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _remove_existing(dst)
    return True


def swap_blocker(dst: Path, skill_dir: Path) -> Path | None:
    """The real file where a parent dir of ``dst`` must go, or a real dir at ``dst``.

    Symlinks never block (unlinking one loses no data). What is returned is
    displaced only when the leftover policy allows it (a file/folder swap,
    SPEC §10.8); ``sync --check`` names it otherwise.

    Example: ``swap_blocker(skill_dir / "scripts" / "run.sh", skill_dir)`` ->
    ``skill_dir / "scripts"`` when that is a regular file.
    """
    current = skill_dir
    for part in dst.parent.relative_to(skill_dir).parts:
        current = current / part
        if not current.is_symlink() and current.exists() and not current.is_dir():
            return current
    return dst if dst.is_dir() and not dst.is_symlink() else None


def _warn_through_link(target: Path, where: str) -> None:
    print(
        f"warning: not writing {target}: {where}, and sync never writes through such a link; "
        "remove or re-point it, then re-run 'playbook sync'",
        file=sys.stderr,
    )


def _warn_blocked(dst: Path, blocker: Path) -> None:
    print(
        f"warning: not writing {dst}: {blocker} is in the way and holds files "
        "'playbook sync' did not write; move them, then re-run 'playbook sync'",
        file=sys.stderr,
    )


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


def _copy_subtree(
    src: Path | None, dst_root: Path, skill_dir: Path, prior: PriorOutput
) -> list[Path]:
    """Byte-copy every publishable file under ``src`` into ``dst_root`` (``shutil.copy2``).

    Returns the destination files in sorted source order; ``[]`` when ``src``
    is absent. Source symlinks inside the skill are dereferenced (copies, not
    symlinks); bytecode caches (``__pycache__/``, ``*.pyc``/``*.pyo``) are
    skipped, so they never reach a skills root or the lockfile; a secret path or
    a link leaving the skill's source dir is never copied
    (:func:`_skill_sources.copyable_skill_files` warns instead). Each recorded
    path is the file ``copy2`` actually wrote, never a directory; a destination
    blocked by user files is skipped (see :func:`_prepare_destination`).
    """
    if src is None:
        return []
    written: list[Path] = []
    for source_file in copyable_skill_files(src, dst_root):
        dst = dst_root / source_file.relative_to(src)
        if _prepare_destination(dst, skill_dir, prior):
            written.append(Path(shutil.copy2(source_file, dst)))
    return written
