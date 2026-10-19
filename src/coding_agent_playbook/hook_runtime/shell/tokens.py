"""The tokens the shell lexer produces (specs/prK-lifecycle-hooks.md §D.2.5).

A ``RawWord`` keeps one word as written, quotes included, with each expansion
(``$(...)``, backticks, ``${...}``, ``$((...))``, process substitution)
replaced by a placeholder, so that ``shlex`` can never split inside one.
``RawWord.resolve`` removes the quotes and puts each expansion's source text
back. The command lists inside substitutions ride along in ``substs``,
because the shell runs them.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Final

MAX_DEPTH: Final = 4

#: Placeholder delimiters: private-use code points, refused in the lexer's input
#: so that a command can never forge a placeholder.
PLACEHOLDER_OPEN: Final = ""
PLACEHOLDER_CLOSE: Final = ""

_PLACEHOLDER = re.compile(f"{PLACEHOLDER_OPEN}(\\d+){PLACEHOLDER_CLOSE}")
_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_ANSI_ESCAPE = re.compile(r"\\(x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|.)", re.DOTALL)
_ANSI_CHARS = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "f": "\f"}
_ANSI_CHARS |= {"v": "\v", "E": "\x1b", "\\": "\\", "'": "'", '"': '"', "?": "?"}


class ScanError(ValueError):
    """The text uses a construct the lexer cannot follow; the message names it."""


class ScanLimit(ScanError):
    """The text exceeds a parse limit (nesting depth, segments, launchers)."""


@dataclass(slots=True)
class Word:
    """One word after quote removal; ``assignment`` marks an unquoted ``NAME=`` prefix.

    Example: ``Word("$HOME", dynamic=True)``.
    """

    value: str
    dynamic: bool = False
    quoted: bool = False
    assignment: bool = False


@dataclass(slots=True)
class RawWord:
    """One word as written: quotes kept, expansions replaced by placeholders."""

    chunks: list[str] = field(default_factory=list)
    spans: list[str] = field(default_factory=list)
    substs: list[list[Token]] = field(default_factory=list)
    dynamic: bool = False
    quoted: bool = False

    def resolve(self) -> Word:
        """Remove the quotes with ``shlex`` and put each expansion's source text back.

        Example: the raw word ``"$(pwd)"/x`` resolves to ``$(pwd)/x``, dynamic.
        """
        text = "".join(self.chunks)
        if not self.quoted:
            # Nothing to remove: a word holds no unquoted blank, so shlex would return it as is.
            parts = [text]
        else:
            try:
                parts = shlex.split(text)
            except ValueError as exc:  # pragma: no cover - the lexer only emits balanced words
                raise ScanError(f"unparseable word {text!r}: {exc}") from None
        value = _PLACEHOLDER.sub(lambda m: self.spans[int(m.group(1))], parts[0] if parts else "")
        return Word(value, self.dynamic, self.quoted, _ASSIGNMENT.match(text) is not None)

    def placeholder(self, span: str) -> None:
        """Stand in for one expansion whose source text is ``span``."""
        self.chunks.append(f"{PLACEHOLDER_OPEN}{len(self.spans)}{PLACEHOLDER_CLOSE}")
        self.spans.append(span)
        self.dynamic = True


@dataclass(slots=True)
class RawRedirect:
    """One redirection; a heredoc has no target and gets its ``body`` at the next newline."""

    op: str
    fd: int | None
    target: RawWord | None
    body: str = ""
    delimiter: str = ""
    strip_tabs: bool = False
    expands: bool = False
    substs: list[list[Token]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Op:
    """A control operator, ``(`` / ``)``, or ``""`` for the end of a list."""

    text: str


type Token = RawWord | RawRedirect | Op


def heredoc_body(text: str, pos: int, heredoc: RawRedirect) -> tuple[str, int]:
    """``(body, position after its delimiter line)`` for a heredoc starting at ``pos``.

    ``<<-`` strips leading tabs; a missing delimiter takes the rest of the text,
    as bash does.

    Example::

        >>> heredoc_body("hi\\nEOF\\nnext", 0, RawRedirect("<<", None, None, delimiter="EOF"))
        ('hi\\n', 7)
    """
    lines: list[str] = []
    while pos < len(text):
        end = text.find("\n", pos)
        end = len(text) if end < 0 else end
        line, pos = text[pos:end], end + 1
        if heredoc.strip_tabs:
            line = line.lstrip("\t")
        if line == heredoc.delimiter:
            break
        lines.append(line + "\n")
    return "".join(lines), min(pos, len(text))


def ansi_c_word(body: str) -> str:
    """The body of ``$'...'`` with its escapes decoded, quoted again for ``shlex``.

    Decoding matters to guards: ``rm -rf $'\\x2f'`` removes ``/``.

    Example::

        >>> ansi_c_word("\\\\x2f")
        '/'
    """
    return shlex.quote(_ANSI_ESCAPE.sub(_decode_ansi, body))


def _decode_ansi(match: re.Match[str]) -> str:
    code = match.group(1)
    if code[0] == "x" and len(code) > 1:
        return chr(int(code[1:], 16))
    if code[0] in "01234567":
        return chr(int(code, 8))
    return _ANSI_CHARS.get(code, "\\" + code)
