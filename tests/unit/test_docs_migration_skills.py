"""Docs-consistency guard: MIGRATION.md opens v0.21, the skills-first release (spec 6.8.14).

One ``## v0.21`` section carries the whole release, newest first, with one TL;DR table
that each change of the release adds a row to. The guard pins the version prefix of the
heading, not its title, so retitling the section stays a docs-only edit. Prose-only: these
tests read markdown, never engine behaviour.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters._agent_skill_rules import skill_id_of
from coding_agent_playbook.catalog import ENGINE_PACKAGE
from coding_agent_playbook.commands._validate_skills import SCOPED_RULE_NEEDS_SKILL_MESSAGE
from coding_agent_playbook.skill_membership import is_rule_skill
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource
from tests.unit.test_docs_migration_hooks import _migration

if TYPE_CHECKING:
    from pathlib import Path

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


@pytest.mark.parametrize(
    "phrase",
    [
        "skill:",
        "Where guidance lives",
        "CLAUDE_RULES_PATH",
        "python-coding",
        "44-python-data-shapes.md",
        "58-python-idioms.md",
        "playbook validate",
        "Distilled python-best-practices content",
        "53-python-classes-and-protocols.md",
    ],
)
def test_migration_v0_21_covers_topic(phrase: str) -> None:
    assert phrase in _v021_section(), f"the v0.21 MIGRATION section never mentions {phrase!r}"


def _core_rule_skill_ids(repo_root: Path) -> list[str]:
    """The sorted ids of the skills in core that take member rules, as V1 lists them."""
    skills = FileSystemArtifactSource(repo_root=repo_root).list_skills()
    return sorted(
        skill_id_of(skill)
        for skill in skills
        if skill.source_package == ENGINE_PACKAGE and is_rule_skill(skill)
    )


def test_migration_quotes_the_engine_skill_required_message(tmp_path: Path) -> None:
    """V1's text, ``{known}`` filled for core, is quoted verbatim (prS §6.9.4)."""
    known = _core_rule_skill_ids(tmp_path)
    assert known, "core ships no skill that takes member rules"
    quote = SCOPED_RULE_NEEDS_SKILL_MESSAGE.format(known=", ".join(known))
    section = _v021_section()
    assert f"\n    {quote}\n" in section, f"MIGRATION.md v0.21 must quote {quote!r}"


def test_migration_v0_21_tldr_tells_scoped_rule_owners_to_add_skill() -> None:
    rows = [row for row in _tldr_table(_v021_section())[2:] if "own scoped rules" in row]
    assert rows, "the v0.21 TL;DR table needs a row for repos keeping their own scoped rules"
    assert "`skill: <skill-id>`" in rows[0]


def test_migration_heads_up_leads_with_v0_21_skill() -> None:
    text = _migration()
    heads_up = text[: text.index("\n## ")]
    assert heads_up.index("v0.21") < heads_up.index("v0.20"), "v0.21 leads the heads-up"
    assert "`skill: <skill-id>`" in heads_up


def _subsection_titles(section: str) -> list[str]:
    """The ``### `` subsection titles of ``section``, in file order."""
    return re.findall(r"^### (.+)$", section, re.MULTILINE)


def test_migration_v0_21_tldr_pointers_follow_subsection_order() -> None:
    """Rows that name a subsection ("See ...") name them in file order (SPEC v0.21 entry)."""
    section = _v021_section()
    titles = _subsection_titles(section)
    rows = _tldr_table(section)[2:]
    quoted = [name for row in rows for name in re.findall(r'"([^"]+)"', row)]
    pointed = [titles.index(name) for name in quoted if name in titles]
    assert len(pointed) >= 4, f"expected the TL;DR to point at subsections, found {quoted}"
    assert pointed == sorted(pointed), f"TL;DR points at {quoted} out of subsection order {titles}"
