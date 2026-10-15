"""The ``apply_patch`` envelope: which files a patch touches and what it adds (§D.2.2).

OpenCode's GPT models edit through ``apply_patch`` instead of edit/write, so
the file guards read the envelope headers (``*** Add File:``, ``*** Update
File:``, ``*** Delete File:``, ``*** Move to:``) for paths and the ``+``
lines for content. One parser, shared with a future Codex adapter (§C.3.3).
The patch is never applied or validated here: a header the agent writes is a
path the guard must judge, whether or not the patch would apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

__all__ = ["PatchEnvelope", "parse_patch"]

_FILE_HEADERS: Final = ("*** Add File:", "*** Update File:", "*** Delete File:", "*** Move to:")
_END = "*** End Patch"


@dataclass(frozen=True, slots=True)
class PatchEnvelope:
    """The files a patch names, in order of appearance, and the lines it adds per file.

    A ``Move to`` destination receives the ``+`` lines that follow it.

    Example::

        >>> parse_patch("*** Add File: a.py\\n+x = 1\\n").added
        (('a.py', 'x = 1'),)
    """

    paths: tuple[str, ...] = ()
    added: tuple[tuple[str, str], ...] = field(default=(), repr=False)


def parse_patch(text: str) -> PatchEnvelope:
    """Read the file headers and ``+`` lines of an ``apply_patch`` envelope.

    Example::

        >>> parse_patch("*** Delete File: old.py\\n").paths
        ('old.py',)
    """
    paths: dict[str, None] = {}
    added: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        header = _header_path(line)
        if header is not None:
            current = header or None
            if current:
                paths[current] = None
        elif line.startswith(_END):
            current = None
        elif current is not None and line.startswith("+"):
            added.setdefault(current, []).append(line[1:])
    return PatchEnvelope(
        tuple(paths), tuple((path, "\n".join(lines)) for path, lines in added.items())
    )


def _header_path(line: str) -> str | None:
    """The path a file header names (``""`` when blank), or ``None`` for any other line."""
    for header in _FILE_HEADERS:
        if line.startswith(header):
            return line[len(header) :].strip()
    return None
