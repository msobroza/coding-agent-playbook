"""The stdlib half of ``playbook docs-check``: relative links and Python code blocks (D69).

Both checks read one Markdown file and need no tool the repository configures:
every relative link (inline ``[text](target)``, image ``![alt](target)`` and
reference definition ``[label]: target``) must name a file or directory that
exists, and every fenced ``python`` / ``py`` / ``python3`` block must parse
(``ast.parse``). Links inside fenced blocks and inline code are not links; a
block that opens with ``>>>`` is an interactive session, which the doctest run
checks instead. Findings are ``<path>:<line>: <message>`` lines.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from urllib.parse import unquote

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["MARKDOWN_SUFFIXES", "markdown_findings"]

#: The files the stdlib checks read.
MARKDOWN_SUFFIXES: Final = frozenset({".md", ".markdown"})
_PYTHON_INFO: Final = frozenset({"python", "py", "python3"})
_FENCE: Final = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)")
_INLINE_CODE: Final = re.compile(r"(`+)(?:(?!\1).)+?\1")
_INLINE_LINK: Final = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+[\"'(][^)]*)?\)")
_REFERENCE: Final = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
_SCHEME: Final = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True, slots=True)
class _Block:
    """One fenced code block: the line of its opening fence, its info word and its body."""

    fence_line: int
    info: str
    body: str


def markdown_findings(path: Path, label: str) -> list[str]:
    """The broken-link and unparsable-block lines of Markdown file ``path``, shown as ``label``.

    Example::

        >>> markdown_findings(Path("README.md"), "README.md")  # doctest: +SKIP
        ["README.md:4: broken relative link 'docs/gone.md' (no such file)"]
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    prose, blocks = _split_fences(text)
    found = [
        (line, f"broken relative link {target!r} (no such file)")
        for line, target in _links(prose)
        if not _resolves(path, target)
    ]
    found.extend(_block_problems(blocks))
    return [f"{label}:{line}: {message}" for line, message in sorted(found)]


def _split_fences(text: str) -> tuple[list[tuple[int, str]], list[_Block]]:
    """``(numbered prose lines, fenced blocks)``; an unclosed fence runs to the end."""
    prose: list[tuple[int, str]] = []
    blocks: list[_Block] = []
    opened: tuple[int, str, str] | None = None
    body: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        fence = _FENCE.match(line)
        if opened is None and fence:
            opened, body = (number, fence.group(1), fence.group(2).lower()), []
        elif opened is not None and fence and fence.group(1).startswith(opened[1]):
            blocks.append(_Block(opened[0], opened[2], "\n".join(body)))
            opened = None
        elif opened is not None:
            body.append(line)
        else:
            prose.append((number, line))
    if opened is not None:
        blocks.append(_Block(opened[0], opened[2], "\n".join(body)))
    return prose, blocks


def _links(prose: list[tuple[int, str]]) -> Iterator[tuple[int, str]]:
    """``(line, target)`` of every relative link target in the prose lines."""
    for number, line in prose:
        bare = _INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line)
        targets = [m.group(1) for m in _INLINE_LINK.finditer(bare)]
        reference = _REFERENCE.match(bare)
        if reference:
            targets.append(reference.group(1))
        yield from ((number, t.strip("<>")) for t in targets if _is_relative(t.strip("<>")))


def _is_relative(target: str) -> bool:
    """A target a file check can judge: no scheme, no anchor-only, no site-absolute path."""
    if not target or target.startswith(("#", "/", "{{")):
        return False
    return _SCHEME.match(target) is None


def _resolves(path: Path, target: str) -> bool:
    file_part = unquote(target.split("#", 1)[0].split("?", 1)[0])
    return not file_part or (path.parent / file_part).exists()


def _block_problems(blocks: list[_Block]) -> Iterator[tuple[int, str]]:
    for block in blocks:
        if block.info not in _PYTHON_INFO or block.body.lstrip().startswith(">>>"):
            continue
        try:
            ast.parse(block.body)
        except SyntaxError as exc:
            line = block.fence_line + (exc.lineno or 1)
            yield line, f"Python code block does not parse: {exc.msg}"
