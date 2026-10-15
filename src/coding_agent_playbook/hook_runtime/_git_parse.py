"""Pure parsers for the git output ``SafeGit`` reads (specs/prK-lifecycle-hooks.md §D.5.3).

Split from ``git.py`` to keep both under §D.1's 300-line module rule. Every
function is pure over bytes, so the formats are pinned by ``FakeProc`` tests
without a repository.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "AddedLine",
    "DiffLines",
    "RemovedLine",
    "parse_batch_blob",
    "parse_diff_added",
    "parse_diff_lines",
    "parse_status_paths",
    "parse_version",
    "split_z",
    "unquote_path",
]

_VERSION = re.compile(rb"git version (\d+)\.(\d+)(?:\.(\d+))?")
_HUNK = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_C_ESCAPE = re.compile(r"\\([0-7]{3}|.)")
_SIMPLE_ESCAPES: Final = {"a": "\a", "b": "\b", "t": "\t", "n": "\n", "v": "\v", "f": "\f"}
_OLD_FILE_PREFIX: Final = b"--- "
_NEW_FILE_PREFIX: Final = b"+++ "
_SOURCE_PREFIX: Final = "a/"
_DEST_PREFIX: Final = "b/"
#: Fields before the path in each ``git status --porcelain=v2`` entry type.
_STATUS_FIELDS: Final = {b"1": 8, b"2": 9, b"u": 10, b"?": 1, b"!": 1}


@dataclass(frozen=True, slots=True)
class AddedLine:
    """One line ``git diff HEAD`` adds: repo-relative path, 1-based new line number, text.

    Example: ``AddedLine("src/a.py", 4, "x = 1")``.
    """

    path: str
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class RemovedLine:
    """One line a diff removes: repo-relative old path, 1-based old line number, text.

    Example: ``RemovedLine("src/a.py", 4, "x = 0")``.
    """

    path: str
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class DiffLines:
    """What a ``-U0`` patch adds and removes, and every path its file headers name.

    Example: ``DiffLines(added=(), removed=(), paths=("a.py",))``.
    """

    added: tuple[AddedLine, ...] = ()
    removed: tuple[RemovedLine, ...] = ()
    paths: tuple[str, ...] = ()


def parse_version(output: bytes) -> tuple[int, int, int] | None:
    """``(major, minor, patch)`` from ``git --version``, or ``None`` when unrecognized.

    Example::

        >>> parse_version(b"git version 2.39.3 (Apple Git-146)\\n")
        (2, 39, 3)
    """
    match = _VERSION.search(output)
    if match is None:
        return None
    return int(match[1]), int(match[2]), int(match[3] or 0)


def unquote_path(raw: str) -> str:
    """A diff header path without git's C-style quoting (``core.quotePath``).

    Example::

        >>> unquote_path('"d i/caf\\\\303\\\\251.txt"')
        'd i/café.txt'
    """
    if not (len(raw) >= 2 and raw[0] == raw[-1] == '"'):
        return raw
    out = bytearray()
    # split() with one group alternates literal text and escape bodies.
    for index, piece in enumerate(_C_ESCAPE.split(raw[1:-1])):
        out += _escape_bytes(piece) if index % 2 else piece.encode("utf-8", "surrogateescape")
    return out.decode("utf-8", errors="replace")


def parse_diff_added(output: bytes) -> tuple[AddedLine, ...]:
    """Every added line of a ``git diff -U0 --src-prefix=a/ --dst-prefix=b/`` patch.

    Example::

        >>> parse_diff_added(b"+++ b/a.py\\n@@ -0,0 +1 @@\\n+x = 1\\n")
        (AddedLine(path='a.py', line=1, text='x = 1'),)
    """
    return parse_diff_lines(output).added


def parse_diff_lines(output: bytes) -> DiffLines:
    """The added and removed lines of a ``-U0`` patch, and every path its headers name.

    Hunk line counts decide what is content, so a content line that itself
    starts with ``++ `` or ``-- `` is never mistaken for a file header. Binary
    files add nothing; a created file has no removed side (``--- /dev/null``)
    and a deleted one no added side (``+++ /dev/null``).

    Example::

        >>> parse_diff_lines(b"--- a/a.py\\n+++ b/a.py\\n@@ -2 +2 @@\\n-x = 0\\n+x = 1\\n").removed
        (RemovedLine(path='a.py', line=2, text='x = 0'),)
    """
    walk = _DiffWalk()
    for line in output.split(b"\n"):
        walk.feed(line)
    return DiffLines(tuple(walk.added), tuple(walk.removed), tuple(walk.paths))


def parse_batch_blob(output: bytes) -> bytes | None:
    """The content of the one blob ``git cat-file --batch`` printed, or ``None``.

    ``None`` covers ``<name> missing``, a non-blob object and a malformed header.

    Example::

        >>> parse_batch_blob(b"ab12 blob 2\\nhi\\n")
        b'hi'
    """
    header, _, rest = output.partition(b"\n")
    fields = header.split(b" ")
    if len(fields) != 3 or fields[1] != b"blob" or not fields[2].isdigit():
        return None
    size = int(fields[2])
    return rest[:size] if len(rest) >= size else None


def split_z(output: bytes) -> tuple[str, ...]:
    """The entries of a ``-z`` listing, decoded so odd bytes round-trip.

    Example::

        >>> split_z(b"a\\x00b c\\x00")
        ('a', 'b c')
    """
    return tuple(p.decode("utf-8", "surrogateescape") for p in output.split(b"\x00") if p)


def parse_status_paths(output: bytes) -> tuple[str, ...]:
    """The paths of a ``git status --porcelain=v2 -z --no-renames`` listing.

    Example::

        >>> parse_status_paths(b"? new.txt\\x00")
        ('new.txt',)
    """
    paths: list[str] = []
    for entry in output.split(b"\x00"):
        fields = _STATUS_FIELDS.get(entry[:1])
        if fields is None:
            continue
        parts = entry.split(b" ", fields)
        if len(parts) == fields + 1:
            paths.append(parts[fields].decode("utf-8", errors="surrogateescape"))
    return tuple(paths)


class _DiffWalk:
    """The state of one pass over a patch: the current file pair and hunk counters."""

    def __init__(self) -> None:
        self.added: list[AddedLine] = []
        self.removed: list[RemovedLine] = []
        self.paths: dict[str, None] = {}  # insertion-ordered set
        self.old_path: str | None = None
        self.new_path: str | None = None
        self.old_no = self.new_no = self.old_left = self.new_left = 0

    def feed(self, line: bytes) -> None:
        if self.old_left or self.new_left:
            self._content(line)
        elif line.startswith(_OLD_FILE_PREFIX):
            self.old_path = self._header(line[len(_OLD_FILE_PREFIX) :], _SOURCE_PREFIX)
        elif line.startswith(_NEW_FILE_PREFIX):
            self.new_path = self._header(line[len(_NEW_FILE_PREFIX) :], _DEST_PREFIX)
        elif (hunk := _HUNK.match(line)) is not None:
            self.old_no, self.old_left = int(hunk[1]), _count(hunk[2])
            self.new_no, self.new_left = int(hunk[3]), _count(hunk[4])

    def _content(self, line: bytes) -> None:
        if line.startswith(b"-") and self.old_left:
            if self.old_path is not None:
                self.removed.append(RemovedLine(self.old_path, self.old_no, _text(line[1:])))
            self.old_no, self.old_left = self.old_no + 1, self.old_left - 1
        elif line.startswith(b"+") and self.new_left:
            if self.new_path is not None:
                self.added.append(AddedLine(self.new_path, self.new_no, _text(line[1:])))
            self.new_no, self.new_left = self.new_no + 1, self.new_left - 1

    def _header(self, field: bytes, prefix: str) -> str | None:
        """The repo path of a ``---`` / ``+++`` header, or ``None`` for ``/dev/null``."""
        # git appends a tab to a header path that contains a space.
        text = unquote_path(field.decode("utf-8", errors="surrogateescape").rstrip("\t"))
        path = text[len(prefix) :] if text.startswith(prefix) else None
        if path is not None:
            self.paths[path] = None
        return path


def _escape_bytes(body: str) -> bytes:
    """The bytes one C escape body stands for: ``303`` (octal) or ``t`` / ``"`` / ``\\``."""
    if len(body) == 3:
        return bytes([int(body, 8) & 0xFF])
    return _SIMPLE_ESCAPES.get(body, body).encode("utf-8")


def _count(group: bytes | None) -> int:
    """A hunk range length; an omitted one means 1."""
    return 1 if group is None else int(group)


def _text(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")
