"""Docs-consistency guard: MIGRATION.md opens v0.21, the skills-first release (spec 6.8.14).

One ``## v0.21`` section carries the whole release, newest first, with one TL;DR table
that each change of the release adds a row to. The guard pins the version prefix of the
heading, not its title, so retitling the section stays a docs-only edit. Prose-only: these
tests read markdown, never engine behaviour.
"""

from __future__ import annotations

import re

from tests.unit.test_docs_migration_hooks import _migration

_V021_HEADING = re.compile(r"^## v0\.21\b.*$", re.MULTILINE)
_TLDR_HEADING = "### TL;DR — who needs to do anything"
_TABLE_SEPARATOR = re.compile(r"\|(\s*:?-{3,}:?\s*\|)+")


def _v021_section() -> str:
    """The v0.21 section: its heading up to the next ``## `` heading."""
    text = _migration()
    heading = _V021_HEADING.search(text)
    assert heading is not None, "MIGRATION.md has no '## v0.21' section"
    end = text.find("\n## ", heading.end())
    return text[heading.start() : end if end > 0 else len(text)]


def _tldr_table(section: str) -> list[str]:
    """The table lines right after the TL;DR heading of ``section`` (blank lines skipped)."""
    after = section.partition(_TLDR_HEADING)[2]
    lines = [line.strip() for line in after.splitlines() if line.strip()]
    table: list[str] = []
    for line in lines:
        if not line.startswith("|"):
            break
        table.append(line)
    return table


def test_migration_v0_21_section_is_first_with_tldr() -> None:
    first = re.search(r"^## v.*$", _migration(), re.MULTILINE)
    assert first is not None, "MIGRATION.md has no '## v' release heading"
    assert first.group(0).startswith("## v0.21"), f"first release heading is {first.group(0)!r}"
    section = _v021_section()
    assert section.count(_TLDR_HEADING) == 1, f"expected one {_TLDR_HEADING!r} in the v0.21 section"
    table = _tldr_table(section)
    assert len(table) >= 3, f"TL;DR must be a table of a header, a separator and rows: {table}"
    assert _TABLE_SEPARATOR.fullmatch(table[1]), f"second table line is no separator: {table[1]!r}"


def test_migration_v0_21_tldr_names_the_glossary_move() -> None:
    rows = [row for row in _tldr_table(_v021_section())[2:] if "CONTEXT.md" in row]
    assert rows, "the v0.21 TL;DR table needs a row saying the glossary moved to CONTEXT.md"
