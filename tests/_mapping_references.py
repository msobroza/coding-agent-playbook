"""A core skill's references as its mapping spec plans them, and the checks they share (prU D47, D49).

Each ``specs/prU-core-python-skills/mapping-<skill>.md`` has one references table
(``| File | Kind | Open when | Gate | Purpose | Routes to | Sources or outline |``)
and a rule table whose last cell ends with ``see: `<path>```. The refs tests of
each skill read both here instead of pinning a hand copy, so a mapping change
reaches them without an edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from tests._attributions import MAPPING_SPECS_DIR

#: D49: an engine-written decision guide is at most 120 lines.
D49_MAX_LINES: Final = 120
_REFERENCES_HEADER: Final = (
    "| File | Kind | Open when | Gate | Purpose | Routes to | Sources or outline |"
)
_PATH_CELL_RE: Final = re.compile(r"^`([^`]+)`$")
#: ``domino-docs:`user_guide/de4abb` (why)`` -> ("domino-docs", "user_guide/de4abb").
_SOURCE_RE: Final = re.compile(r"([a-z][a-z0-9-]*):`([^`]+)`")
_RULE_ROW_RE: Final = re.compile(r"^\| `rules/([a-z0-9-]+)\.md(?:\.j2)?` \|.*$", re.MULTILINE)
_SEE_RE: Final = re.compile(r"see: ((?:`[^`]+`(?:, )?)+) \|$")
_BACKTICKED_RE: Final = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class MappedReference:
    """One row of a mapping's references table."""

    path: str
    kind: str
    open_when: str
    gate: str
    routes_to: tuple[str, ...]
    sources: frozenset[tuple[str, str]]


def _mapping_text(skill: str) -> str:
    return (MAPPING_SPECS_DIR / f"mapping-{skill}.md").read_text(encoding="utf-8")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_reference(line: str) -> MappedReference:
    path, kind, open_when, gate, _purpose, routes, sources = _cells(line)
    match = _PATH_CELL_RE.match(path)
    if match is None:
        raise ValueError(f"a references row needs a `path` first: {line!r}")
    return MappedReference(
        path=match.group(1),
        kind=kind,
        open_when=open_when,
        gate=gate,
        routes_to=() if routes == "—" else tuple(part.strip() for part in routes.split(",")),
        sources=frozenset(_SOURCE_RE.findall(sources)),
    )


def mapped_references(skill: str) -> dict[str, MappedReference]:
    """The references ``skill``'s mapping plans, by path, in mapping order.

    >>> mapped_references("domino-jobs")["references/where-outputs-go.md"].kind
    'internal'
    """
    lines = _mapping_text(skill).splitlines()
    start = lines.index(_REFERENCES_HEADER) + 2
    rows: dict[str, MappedReference] = {}
    for line in lines[start:]:
        if not line.startswith("| `"):
            break
        reference = _parse_reference(line)
        rows[reference.path] = reference
    return rows


def rules_that_see(skill: str, path: str) -> tuple[str, ...]:
    """The rule ids whose mapping row names ``path`` in its ``see:`` list, in mapping order."""
    seeing: list[str] = []
    for row in _RULE_ROW_RE.finditer(_mapping_text(skill)):
        see = _SEE_RE.search(row.group(0))
        if see is not None and path in _BACKTICKED_RE.findall(see.group(1)):
            seeing.append(row.group(1))
    return tuple(seeing)


def whole_id(pattern: str) -> re.Pattern[str]:
    """Match ``pattern`` as a whole hyphenated id, never inside a longer one.

    >>> bool(whole_id("a-b").search("x a-b-c")), bool(whole_id("a-b").search("(a-b)"))
    (False, True)
    """
    return re.compile(rf"(?<![\w-]){pattern}(?![\w-])")


def missing_rule_ids(text: str, rule_ids: tuple[str, ...] | list[str]) -> list[str]:
    """The ids of ``rule_ids`` that ``text`` never names as a whole id, in their order."""
    return [rule_id for rule_id in rule_ids if not whole_id(re.escape(rule_id)).search(text)]


def line_count(text: str) -> int:
    """The number of lines D49 budgets: ``line_count("a\\nb\\n") == 2``."""
    return len(text.splitlines())
