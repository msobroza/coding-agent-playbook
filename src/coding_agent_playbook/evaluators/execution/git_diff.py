"""The Python lines a change touched since a diff base, for ``diff_coverage`` (prK §F.1.1).

:func:`changed_lines` asks git two things through one injectable
:data:`~coding_agent_playbook.evaluators.baseline_git.GitRunner` (so a hook can
hand it its hardened ``SafeGit``): the zero-context diff of the working tree
against the base, and the untracked ``*.py`` files, which count every line.
:func:`parse_unified_zero` turns the diff into line sets and is pure, so the
hunk grammar is table-tested without git.

The argv never lets repository config run code or reshape the output: no
external diff drivers or textconv filters (``--no-ext-diff``,
``--no-textconv``), no colour, and explicit ``a/`` / ``b/`` prefixes so
``diff.noprefix`` or ``diff.mnemonicPrefix`` cannot change the headers this
module parses. ``-M`` keeps a moved file from counting as all-new.
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evaluators.baseline_git import (
    BaselineGitError,
    GitTimeoutError,
    SubprocessGitRunner,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evaluators.baseline_git import GitRunner

__all__ = ["changed_lines", "parse_unified_zero"]

#: Only Python files: ``*`` crosses ``/`` in a git pathspec, so this matches at any depth.
_PY_PATHSPEC: Final = "*.py"
_DIFF: Final = (
    "diff",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "-M",
    "--unified=0",
    "--relative",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)
_UNTRACKED: Final = ("ls-files", "--others", "--exclude-standard", "-z", "--", _PY_PATHSPEC)

#: ``@@ -a[,b] +c[,d] @@``: the new side starts at ``c`` and spans ``d`` lines (default 1).
_HUNK: Final = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
#: One C-style escape in a quoted git path: three octal digits or one character.
_C_ESCAPE: Final = re.compile(rb"\\([0-7]{3}|.)", re.DOTALL)
_C_SIMPLE: Final = {
    b"a": b"\a",
    b"b": b"\b",
    b"t": b"\t",
    b"n": b"\n",
    b"v": b"\v",
    b"f": b"\f",
    b"r": b"\r",
}


def changed_lines(
    root: Path, base: str, *, timeout_s: float, git: GitRunner | None = None
) -> dict[str, frozenset[int]]:
    """``{root-relative path: line numbers}`` added or changed since ``base``, ``*.py`` only.

    The working tree is compared (staged or not); untracked, non-ignored files
    count all their lines; deleted lines count nothing. ``git`` defaults to a
    :class:`SubprocessGitRunner` at ``root`` bounded by ``timeout_s``. A git
    failure or timeout raises :class:`RuntimeError` naming ``base``.

    Example::

        >>> changed_lines(Path("."), "HEAD", timeout_s=10.0)  # doctest: +SKIP
        {'src/pkg/api.py': frozenset({12, 13, 14, 40})}
    """
    if base.startswith("-"):
        # git would read it as an option (``--output=<file>`` writes a file).
        raise RuntimeError(f"cannot list the lines changed since {base!r}: not a revision")
    runner = git if git is not None else SubprocessGitRunner(root, timeout_s)
    try:
        diff = runner([*_DIFF, base, "--", _PY_PATHSPEC])
        untracked = runner(list(_UNTRACKED))
    except GitTimeoutError as exc:
        raise RuntimeError(
            f"cannot list the lines changed since {base!r}: "
            f"git {exc.command} timed out after {exc.timeout_s:g}s"
        ) from exc
    except BaselineGitError as exc:
        raise RuntimeError(f"cannot list the lines changed since {base!r}: {exc}") from exc
    changed = parse_unified_zero(os.fsdecode(diff))
    for rel in (os.fsdecode(name) for name in untracked.split(b"\0") if name):
        lines = _every_line(root / rel)
        if lines:
            changed[rel] = lines
    return changed


def parse_unified_zero(text: str) -> dict[str, frozenset[int]]:
    """``{new-side path: added line numbers}`` from ``git diff --unified=0`` output.

    Each ``+++ b/<path>`` names the file and each ``@@ -a[,b] +c[,d] @@`` hunk
    adds lines ``c … c+d-1`` (``d`` defaults to 1; ``d=0``, a pure deletion,
    adds nothing). A deleted file (``+++ /dev/null``) adds nothing. Headers are
    read only between ``diff --git`` and the first hunk, so an added line that
    begins ``++`` is never taken for one.

    Example::

        >>> parse_unified_zero("diff --git a/m.py b/m.py\\n+++ b/m.py\\n@@ -1,0 +2,2 @@\\n")
        {'m.py': frozenset({2, 3})}
    """
    changed: dict[str, set[int]] = {}
    path: str | None = None
    in_header = False
    # split("\n"), not splitlines(): a form feed inside an added line is content.
    for line in text.split("\n"):
        if line.startswith("diff --git "):
            path, in_header = None, True
        elif in_header and line.startswith("+++ "):
            path = _new_side_path(line[4:])
        elif line.startswith("@@"):
            in_header = False
            _add_hunk(changed, path, line)
    return {name: frozenset(lines) for name, lines in changed.items() if lines}


def _add_hunk(changed: dict[str, set[int]], path: str | None, header: str) -> None:
    match = _HUNK.match(header)
    if path is None or match is None:
        return
    start, count = int(match[1]), int(match[2] or "1")
    changed.setdefault(path, set()).update(range(start, start + count))


def _new_side_path(field: str) -> str | None:
    """The path in a ``+++`` header, without its ``b/`` prefix; ``None`` for ``/dev/null``."""
    # git appends a TAB to a name containing a space, so patch(1) can tell where it ends.
    name = field.removesuffix("\t")
    if name == "/dev/null":
        return None
    if name.startswith('"'):
        name = _c_unquote(name)
    return name.removeprefix("b/")


def _c_unquote(quoted: str) -> str:
    """A git C-quoted path (``"b/sp\\303\\251cial.py"``) as the file name it encodes."""
    body = os.fsencode(quoted[1:-1] if quoted.endswith('"') else quoted[1:])

    def one(match: re.Match[bytes]) -> bytes:
        code = match[1]
        if len(code) == 3:
            return bytes([int(code, 8) % 256])
        return _C_SIMPLE.get(code, code)

    return os.fsdecode(_C_ESCAPE.sub(one, body))


def _every_line(path: Path) -> frozenset[int]:
    """Lines ``1..n`` of an untracked regular file; nothing for a symlink or an unreadable file."""
    if path.is_symlink() or not path.is_file():
        return frozenset()
    try:
        with path.open("rb") as handle:
            count = sum(1 for _ in handle)
    except OSError:
        return frozenset()
    return frozenset(range(1, count + 1))
