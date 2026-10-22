"""Docs-consistency guard: MIGRATION.md opens v0.21, the skills-first release (spec 6.8.14).

One ``## v0.21`` section carries the whole release, newest first, with one TL;DR table
that each change of the release adds a row to. The guard pins the version prefix of the
heading, not its title, so retitling the section stays a docs-only edit. Prose-only: these
tests read markdown, never engine behaviour.
"""

from __future__ import annotations

import re

import pytest

from coding_agent_playbook.validation._skills import SCOPED_RULE_NEEDS_SKILL_MESSAGE
from tests._catalog import CORE_SKILLS_ROOT, RETIRED_RULE_IDS, core_rule_skill_ids, core_rules
from tests._markdown import markdown_section
from tests.unit.test_docs_migration_hooks import _migration

_V021_HEADING = re.compile(r"^## v0\.21\b.*$", re.MULTILINE)
_TLDR_HEADING = "### TL;DR — who needs to do anything"
_TABLE_SEPARATOR = re.compile(r"\|(\s*:?-{3,}:?\s*\|)+")


def _v021_section() -> str:
    """The v0.21 section, up to the next ``## `` heading outside a code fence.

    Fence-aware because the section quotes generated markdown (``## Before you
    start`` inside a fenced block), which is no release heading.
    """
    text = _migration()
    heading = _V021_HEADING.search(text)
    assert heading is not None, "MIGRATION.md has no '## v0.21' section"
    return markdown_section(text, heading.start())


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
        "playbook validate",
        "NotebookEdit",
        # Member rules render at <skill>/rules/<id>.md (D5, ADR 0005, D22).
        "rules/<rule-id>.md",
        "note: kept output",
        "skills/<skill>/rules/<rule-id>.md",
        # Sections and impact bands (D17, S4, S6).
        "section:",
        "is outside the band of section",
        "declares sections, so its member rule needs 'section:'",
        # Vendored upstream guidance (D1, D19, ADR 0004) and the new gates (D23).
        "Vendored upstream Python guidance",
        "LICENSE.python-best-practices",
        "LICENSE.python-clean-architecture",
        "has_dependency",
        "any_dependency",
        # The gates read root requirements files too (D78(2)).
        "`requirements*.txt` files",
        "Tool configuration and pyproject.toml",
        # L0-22: the new always rules and the layout guard.
        "code-legibility",
        "document-layout",
        "document-layout-guard",
        "holds seven conventions",
    ],
)
def test_migration_v0_21_covers_topic(phrase: str) -> None:
    assert phrase in _v021_section(), f"the v0.21 MIGRATION section never mentions {phrase!r}"


#: Kept ids whose Continue file is renamed because its priority follows the bands.
_RENAMED_CONTINUE_IDS = (
    "python-data-shapes",
    "python-idioms",
    "pytest-test-doubles",
    "pytest-fixtures",
    "python-static-checks",
    "ml-vectorization",
    "fastapi-app-wiring",
)


@pytest.mark.parametrize("rule_id", _RENAMED_CONTINUE_IDS)
def test_migration_v0_21_names_the_new_continue_file(rule_id: str) -> None:
    """The new name is built from the catalog's priority, the one home of it."""
    name = f"{core_rules()[rule_id].frontmatter.priority:02d}-{rule_id}.md"
    assert f"`{name}`" in _v021_section(), f"the v0.21 section never names Continue file {name!r}"


def test_migration_v0_21_does_not_say_the_gates_read_pyproject_only() -> None:
    """The detector also reads root requirements files (D78(2)), so the gates do too."""
    assert "reads `pyproject.toml` only" not in _v021_section()


def _successor_cell(row: str) -> str:
    """The third cell (the successors) of a ``| retired | skill | successors |`` row."""
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    return cells[2] if len(cells) >= 3 else ""


@pytest.mark.parametrize("rule_id", sorted(RETIRED_RULE_IDS))
def test_migration_v0_21_names_each_retired_id_with_its_successors(rule_id: str) -> None:
    """A table row opens with the retired id and names at least one successor id (D21)."""
    rows = [
        line
        for line in (raw.strip() for raw in _v021_section().splitlines())
        if line.startswith(f"| `{rule_id}` |") and re.search(r"`[a-z0-9-]+`", _successor_cell(line))
    ]
    assert rows, f"no v0.21 table row names retired id {rule_id!r} with its successors"


@pytest.mark.parametrize(
    "skill_id", sorted(p.name for p in CORE_SKILLS_ROOT.iterdir() if p.is_dir())
)
def test_migration_v0_21_names_every_core_skill(skill_id: str) -> None:
    assert f"`{skill_id}`" in _v021_section(), f"the v0.21 section never names skill {skill_id!r}"


@pytest.mark.parametrize(
    ("marker", "reason"),
    [
        ("references/", "consumers with edited references/ copies of member rules"),
        ("joining a core skill", "repo-local rules joining a sectioned core skill"),
    ],
)
def test_migration_v0_21_tldr_has_row_for(marker: str, reason: str) -> None:
    rows = [row for row in _tldr_table(_v021_section())[2:] if marker in row]
    assert rows, f"the v0.21 TL;DR table needs a row for {reason}"


def test_migration_quotes_the_engine_skill_required_message() -> None:
    """V1's text, ``{known}`` filled for core, is quoted verbatim (prS §6.9.4)."""
    known = core_rule_skill_ids()
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
