"""The ``[IMPACT]`` tag on a member rule's rendered title (prU D32).

A member rule's first level-one ATX heading outside code fences reads
``# <Title> [IMPACT]`` once rendered; the source never carries the tag (S7).
Headings and fences follow CommonMark: up to three spaces of indent, an
optional closing ``#`` sequence, and a fence closed only by a run of the same
character at least as long as its opener.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.skills.sections import Impact

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Up to three leading spaces still make a heading or a fence in CommonMark.
_MAX_MARKDOWN_INDENT: Final = 3
#: A fence opener: three or more backticks or tildes.
_FENCE: Final = re.compile(r"(`{3,}|~{3,})")
#: A level-one ATX heading, unindented; ``heading`` excludes a trailing impact
#: tag already there and the optional closing ``#`` sequence.
_TITLE: Final = re.compile(
    rf"(?P<heading>#[ \t]+\S.*?)(?:[ \t]+\[(?:{'|'.join(Impact)})\])?(?:[ \t]+#+)?[ \t]*"
)


def with_impact_tag(body: str, impact: Impact) -> str:
    """``body`` with `` [IMPACT]`` on its first ATX ``# `` heading outside code fences.

    Idempotent: a title already ending in an impact tag gets ``impact``'s tag in
    its place, never a second one. A closing ``#`` sequence is dropped, so
    ``# Title #`` becomes ``# Title [HIGH]``. A body without such a heading is
    unchanged.

    Example: ``with_impact_tag("# Mocks\\n", Impact.HIGH)`` -> ``"# Mocks [HIGH]\\n"``.
    """
    lines = body.splitlines(keepends=True)
    for index in _lines_outside_fences(lines):
        text = lines[index].rstrip("\r\n")
        indent, head = _split_indent(text)
        title = _TITLE.fullmatch(head) if indent is not None else None
        if title is not None:
            ending = lines[index][len(text) :]
            lines[index] = f"{indent}{title['heading']} [{impact.value}]{ending}"
            return "".join(lines)
    return body


def _lines_outside_fences(lines: list[str]) -> Iterator[int]:
    """The indexes of ``lines`` that are neither a fence line nor inside a fence."""
    fence = ""
    for index, line in enumerate(lines):
        if fence:
            if _closes_fence(line, fence):
                fence = ""
        else:
            fence = _fence_opener(line)
            if not fence:
                yield index


def _split_indent(line: str) -> tuple[str | None, str]:
    """``(indent, rest)`` when ``line`` has at most three leading spaces, else ``(None, line)``."""
    rest = line.lstrip(" ")
    indent = line[: len(line) - len(rest)]
    return (indent if len(indent) <= _MAX_MARKDOWN_INDENT else None), rest


def _fence_opener(line: str) -> str:
    """The backtick or tilde run that opens a fence on ``line``; ``""`` when none does."""
    indent, rest = _split_indent(line)
    opener = _FENCE.match(rest) if indent is not None else None
    return opener.group(1) if opener else ""


def _closes_fence(line: str, fence: str) -> bool:
    """Whether ``line`` closes ``fence``: a run of its character, at least as long, alone."""
    indent, rest = _split_indent(line.rstrip("\r\n"))
    if indent is None:
        return False
    marker = rest.rstrip(" \t")
    return len(marker) >= len(fence) and marker == fence[0] * len(marker)
