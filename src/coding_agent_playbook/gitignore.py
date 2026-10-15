"""Managed ``.gitignore`` block for local-only generated output (SPEC §5.3, §12.2).

With ``[output] commit = false`` (the default) everything ``playbook sync``
renders is local-only: it is listed in one engine-owned block of the consumer's
``.gitignore`` and never committed. This module owns that block and nothing
else — it is stdlib-only, never calls git, and never touches a byte of the
``.gitignore`` outside the block::

    # >>> coding-agent-playbook (managed — do not edit) >>>
    /.claude/CLAUDE.md
    /.claude/skills/review/
    /.coding-agent-playbook.lock
    /AGENTS.md
    # <<< coding-agent-playbook <<<

Entries are root-anchored (relative to the ``.gitignore``'s own directory, the
playbook repo root), one per generated file, except that a generated skill
directory (any directory holding a written ``SKILL.md``) collapses to a single
``/<dir>/`` entry. Skill roots are detected generically, never hardcoded, so a
new adapter root (``.opencode/skills/``, ``shared_skills/`` …) is covered
without touching this module.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from coding_agent_playbook._atomic_io import atomic_write_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

GITIGNORE_FILENAME = ".gitignore"
BLOCK_START = "# >>> coding-agent-playbook (managed — do not edit) >>>"
BLOCK_END = "# <<< coding-agent-playbook <<<"
# Mirrors ``FileSystemStateSource._LOCKFILE_FILENAME`` (kept as a literal so this
# module stays stdlib-only, importing only the ``_atomic_io`` leaf; a unit test
# pins the two together).
LOCKFILE_NAME = ".coding-agent-playbook.lock"
LOCKFILE_ENTRY = f"/{LOCKFILE_NAME}"

_SKILL_MANIFEST = "SKILL.md"
# gitignore glob metacharacters plus the two pattern-leading specials. ``!`` and
# ``#`` only matter at the start of a pattern (ours start with ``/``), but a
# backslash escape matches the literal character anywhere, so escaping them
# unconditionally is harmless and keeps the rule simple.
_ESCAPED_CHARS = frozenset("\\*?[!#")
# A UTF-8 BOM git skips at the start of a .gitignore (Windows editors add it).
_BOM = "\ufeff"


# --------------------------------------------------------------------------- #
# Entries
# --------------------------------------------------------------------------- #


def relative_posix_paths(paths: Iterable[Path], repo_root: Path) -> list[str]:
    """Return ``paths`` as sorted, de-duplicated POSIX paths relative to ``repo_root``.

    Paths outside ``repo_root`` (and ``repo_root`` itself) are skipped. Both sides
    are resolved, so a relative ``repo_root`` or a ``/var`` → ``/private/var``
    symlink cannot make an in-repo file look external.

    Example::

        >>> relative_posix_paths([Path("/r/a/b.md"), Path("/elsewhere")], Path("/r"))
        ['a/b.md']
    """
    root = repo_root.resolve()
    relative: set[str] = set()
    for path in paths:
        try:
            rel = path.resolve().relative_to(root)
        except ValueError:
            continue
        if rel.parts:
            relative.add(rel.as_posix())
    return sorted(relative)


def ignore_entries(written_paths: Iterable[Path], repo_root: Path) -> list[str]:
    """Return the managed-block entries for one sync's written files.

    One root-anchored entry per file (``/AGENTS.md``), except files inside a
    generated skill directory, which collapse to ``/<skill dir>/``. The lockfile
    entry is always included. The result is sorted and de-duplicated.

    Example::

        >>> ignore_entries([Path("/r/AGENTS.md"), Path("/r/x/s/SKILL.md")], Path("/r"))
        ['/.coding-agent-playbook.lock', '/AGENTS.md', '/x/s/']
    """
    rels = [PurePosixPath(p) for p in relative_posix_paths(written_paths, repo_root)]
    skill_dirs = {rel.parent for rel in rels if rel.name == _SKILL_MANIFEST and rel.parent.parts}
    entries = {entry for rel in rels for entry in _entries_for(rel, skill_dirs)}
    entries.add(LOCKFILE_ENTRY)
    return sorted(entries)


def _entries_for(rel: PurePosixPath, skill_dirs: set[PurePosixPath]) -> set[str]:
    """Anchor ``rel`` — or its shallowest enclosing skill directory — as entries.

    One entry in the NFC form git reports on macOS (``core.precomposeunicode``)
    and, when the name as written differs (a decomposed/NFD name), one in that
    form too, so Linux checkouts — which match bytes as created — are covered.
    """
    target, suffix = rel, ""
    for ancestor in reversed(rel.parents):
        if ancestor in skill_dirs:
            target, suffix = ancestor, "/"
            break
    return {f"/{escape_path(target)}{suffix}", f"/{_escape_posix(target.as_posix())}{suffix}"}


def escape_path(rel: PurePosixPath) -> str:
    """Escape every segment of ``rel`` so gitignore matches it literally (NFC form).

    Backslash-escapes ``\\ * ? [ ! #`` and leading/trailing spaces (git strips
    unescaped trailing spaces). The result is Unicode-NFC-normalised because git
    on macOS reports precomposed paths and never normalises patterns. A newline
    cannot be expressed in a gitignore pattern, so it raises ``ValueError``
    naming the path.

    Example::

        >>> escape_path(PurePosixPath("docs/we*ird name "))
        'docs/we\\\\*ird name\\\\ '
    """
    return _escape_posix(unicodedata.normalize("NFC", rel.as_posix()))


def _escape_posix(posix: str) -> str:
    """Escape a POSIX relative path as-is (no normalisation); see :func:`escape_path`."""
    if "\n" in posix or "\r" in posix:
        raise ValueError(f"cannot express a path containing a newline in .gitignore: {posix!r}")
    return "/".join(_escape_segment(segment) for segment in posix.split("/"))


def _escape_segment(segment: str) -> str:
    """Escape one path segment (see :func:`escape_path`)."""
    core = segment.strip(" ")
    lead = len(segment) - len(segment.lstrip(" "))
    trail = len(segment) - len(segment.rstrip(" ")) if core else 0
    escaped = "".join(f"\\{ch}" if ch in _ESCAPED_CHARS else ch for ch in core)
    return "\\ " * lead + escaped + "\\ " * trail


def entry_matches(rel_path: str, entry: str) -> bool:
    """True when the repo-relative POSIX ``rel_path`` is covered by ``entry``.

    A file entry matches exactly; a directory entry (trailing ``/``) matches
    every path beneath it. Both sides are compared in Unicode NFC, since git on
    macOS reports precomposed paths. Used by ``playbook sync --check-staged``.

    Example::

        >>> entry_matches(".claude/skills/s/scripts/run.sh", "/.claude/skills/s/")
        True
    """
    is_dir = entry.endswith("/")
    target = unicodedata.normalize("NFC", _unescape(entry.strip("/")))
    path = unicodedata.normalize("NFC", rel_path)
    return path.startswith(f"{target}/") if is_dir else path == target


def _unescape(pattern: str) -> str:
    """Invert :func:`escape_path`: drop each escaping backslash."""
    out: list[str] = []
    chars = iter(pattern)
    for ch in chars:
        out.append(next(chars, "") if ch == "\\" else ch)
    return "".join(out)


# --------------------------------------------------------------------------- #
# Managed block
# --------------------------------------------------------------------------- #


def render_block(entries: Sequence[str], eol: str = "\n") -> str:
    """Render the managed block (markers + sorted unique entries), ``eol``-terminated.

    Example::

        >>> render_block(["/AGENTS.md"]).splitlines()[1]
        '/AGENTS.md'
    """
    lines = [BLOCK_START, *sorted(set(entries)), BLOCK_END]
    return "".join(f"{line}{eol}" for line in lines)


def apply_managed_block(gitignore_path: Path, entries: Sequence[str]) -> bool:
    """Write ``entries`` into the managed block; return whether the file changed.

    Idempotent. An existing block is replaced in place; otherwise the block is
    appended after one blank line (the file is created if missing). Every byte
    outside the block is preserved, including CRLF endings and a missing final
    newline. Malformed markers raise ``ValueError`` naming file and line —
    the file is never clobbered.

    Example::

        >>> apply_managed_block(Path(".gitignore"), ["/AGENTS.md"])  # doctest: +SKIP
        True
    """
    current = _read(gitignore_path)
    updated = _with_block(current or "", entries, gitignore_path)
    if updated == current:
        return False
    _atomic_write(gitignore_path, updated)
    return True


def remove_managed_block(gitignore_path: Path) -> bool:
    """Remove the managed block (``[output] commit = true``); return whether it changed.

    The blank separator line :func:`apply_managed_block` added before an
    end-of-file block is removed with it. A missing file or block is a no-op.

    Example::

        >>> remove_managed_block(Path(".gitignore"))  # doctest: +SKIP
        False
    """
    current = _read(gitignore_path)
    if current is None:
        return False
    updated = _without_block(current, gitignore_path)
    if updated == current:
        return False
    _atomic_write(gitignore_path, updated)
    return True


def block_is_current(gitignore_path: Path, entries: Sequence[str]) -> bool:
    """True when :func:`apply_managed_block` would leave the file unchanged.

    Never writes. A missing file or block is not current; malformed markers
    raise ``ValueError`` (the caller reports it as drift).

    Example::

        >>> block_is_current(Path(".gitignore"), ["/AGENTS.md"])  # doctest: +SKIP
        True
    """
    current = _read(gitignore_path)
    if current is None:
        return False
    return _with_block(current, entries, gitignore_path) == current


def _with_block(text: str, entries: Sequence[str], path: Path) -> str:
    """Pure: ``text`` with the block replaced in place, or appended."""
    lines = _split_lines(text)
    span = _locate_block(lines, path)
    if span is None:
        return _appended(text, entries)
    start, end = span
    eol = _eol_of(lines[start])
    block = render_block(entries, eol)
    # Keep the end marker's original terminator so a block that ended the file
    # without a final newline still does — byte-for-byte idempotence.
    block = block[: -len(eol)] + _eol_of(lines[end])
    head = "".join(lines[:start]) + _bom_at(lines, start)
    return head + block + "".join(lines[end + 1 :])


def _appended(text: str, entries: Sequence[str]) -> str:
    """Pure: ``text`` + one blank separator line + the block."""
    eol = "\r\n" if "\r\n" in text else "\n"
    if not text:
        return render_block(entries, eol)
    if not text.endswith("\n"):
        text += eol
    if _split_lines(text)[-1].strip():
        text += eol
    return text + render_block(entries, eol)


def _without_block(text: str, path: Path) -> str:
    """Pure: ``text`` minus the block (and its blank separator at end of file)."""
    lines = _split_lines(text)
    span = _locate_block(lines, path)
    if span is None:
        return text
    before, after = lines[: span[0]], lines[span[1] + 1 :]
    if not after and before and not before[-1].strip():
        before = before[:-1]
    return _bom_at(lines, span[0]) + "".join(before + after)


def _locate_block(lines: list[str], path: Path) -> tuple[int, int] | None:
    """Return the ``(start, end)`` marker line indexes, ``None`` when absent.

    Raises ``ValueError`` (file + 1-based line) for an unmatched, duplicated, or
    out-of-order marker so a hand-mangled block is never silently clobbered.
    """
    starts = [i for i, line in enumerate(lines) if _marker_text(line, i) == BLOCK_START]
    ends = [i for i, line in enumerate(lines) if _marker_text(line, i) == BLOCK_END]
    if not starts and not ends:
        return None
    if len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0]:
        return starts[0], ends[0]
    raise ValueError(_malformed_message(path, starts, ends))


def _marker_text(line: str, index: int) -> str:
    """``line`` as compared to the markers: trailing whitespace and, on the
    first line, a UTF-8 BOM dropped (git ignores both)."""
    text = line.rstrip()
    return text.removeprefix(_BOM) if index == 0 else text


def _bom_at(lines: list[str], index: int) -> str:
    """The BOM a block starting on line ``index`` replaces, so it is kept (else ``""``)."""
    return _BOM if index == 0 and lines and lines[0].startswith(_BOM) else ""


def _malformed_message(path: Path, starts: list[int], ends: list[int]) -> str:
    """Describe the first marker problem as ``<file>:<line>: <what>``."""
    if len(starts) > 1:
        return f"{path}:{starts[1] + 1}: duplicate managed block start marker {BLOCK_START!r}"
    if len(ends) > 1:
        return f"{path}:{ends[1] + 1}: duplicate managed block end marker {BLOCK_END!r}"
    if not ends:
        return f"{path}:{starts[0] + 1}: managed block start marker has no end marker {BLOCK_END!r}"
    if not starts:
        return f"{path}:{ends[0] + 1}: managed block end marker has no start marker {BLOCK_START!r}"
    return f"{path}:{ends[0] + 1}: managed block end marker precedes its start marker"


def _split_lines(text: str) -> list[str]:
    """Split on ``\\n`` only, keeping terminators (a CRLF stays on its line)."""
    parts = text.split("\n")
    lines = [f"{part}\n" for part in parts[:-1]]
    return [*lines, parts[-1]] if parts[-1] else lines


def _eol_of(line: str) -> str:
    """The line's terminator: ``\\r\\n``, ``\\n``, or ``""`` for an unterminated last line."""
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _read(path: Path) -> str | None:
    """Read ``path`` losslessly (undecodable bytes survive), ``None`` if missing."""
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return None
    return payload.decode("utf-8", errors="surrogateescape")


def _atomic_write(target: Path, text: str) -> None:
    """Write ``text`` atomically, keeping undecodable bytes and the file's mode.

    ``.gitignore`` sits among user files: :func:`atomic_write_bytes` uses a unique
    temp name (a fixed ``.gitignore.tmp`` would clobber a user file of that name),
    writes bytes so no newline translation touches the file, and carries the
    original permission bits over.
    """
    atomic_write_bytes(target, text.encode("utf-8", errors="surrogateescape"))
