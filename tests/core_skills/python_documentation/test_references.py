"""The python-documentation skill's reference and its ``playbook.references`` entry.

prU C-python-documentation-refs: the mapping (specs/prU-core-python-skills/mapping-
python-documentation.md, "References") names one internal decision guide,
which-document.md, with an open-when line, no gate and the rule ids it routes to.
D47 lists it in ``playbook.references`` and ends the Notes of the rules whose see
column names it with a plain-text line naming its bare file name; D49 caps an
internal decision guide at 120 lines.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from tests._catalog import core_skill_root
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    guide_line_count,
    reference_text,
    references_block,
    rule_id_like_names,
    skill_md_parts,
    skill_rule_ids,
)

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("python-documentation")
GUIDE: Final = "references/which-document.md"
#: The mapping's "Routes to" column: the thirteen rule ids the guide must name.
ROUTES_TO: Final = (
    "docs-same-change",
    "docs-runnable-examples",
    "docs-record-why",
    "docs-document-layout",
    "docs-architecture-overview",
    "docs-readme-essentials",
    "docs-changelog",
    "docs-contributing-guide",
    "docs-citation-file",
    "docs-page-kinds",
    "sphinx-api-reference",
    "mkdocs-api-reference",
    "docs-check-in-ci",
)
#: The rules whose mapping row carries ``see: references/which-document.md``.
RULES_SEEING_THE_GUIDE: Final = ("docs-same-change", "docs-document-layout", "docs-page-kinds")
#: The prefixes of this skill's rule ids.
_RULE_ID_PREFIXES: Final = ("docs", "sphinx", "mkdocs")
#: Names with those prefixes that are no rule id: the engine's docs-check command.
_NOT_RULE_IDS: Final = frozenset({"docs-check"})


def _rule_id_like_names(text: str) -> set[str]:
    """The rule-id-shaped names ``text`` mentions, commands left out.

    >>> sorted(_rule_id_like_names("which-document.md, docs-changelog; playbook docs-check"))
    ['docs-changelog']
    """
    return rule_id_like_names(text, _RULE_ID_PREFIXES, _NOT_RULE_IDS)


def test_skill_lists_the_guide_ungated_with_its_open_when_line() -> None:
    entries = references_block(SKILL_ROOT)

    assert [entry["path"] for entry in entries] == [GUIDE]
    assert "applies_if" not in entries[0]
    assert entries[0]["open_when"] == (
        "A change needs documenting and it is unclear which file, page kind or docs/ path "
        "it belongs in."
    )


def test_hand_written_body_leaves_navigation_to_the_engine() -> None:
    """D47: no hand-written picking bullets and no path to the guide in the body."""
    _, body = skill_md_parts(SKILL_ROOT)
    headings = re.findall(r"^## (.+)$", body, re.MULTILINE)

    assert headings == ["Quick reference", "See also"]
    assert "which-document" not in body


def test_guide_names_every_rule_it_routes_to() -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, GUIDE))

    missing = [rule_id for rule_id in ROUTES_TO if rule_id not in named]

    assert missing == [], f"{GUIDE} does not name {missing}"


def test_guide_names_only_rule_ids_the_skill_ships() -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, GUIDE))

    unknown = sorted(named - skill_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{GUIDE} names rule ids python-documentation does not ship: {unknown}"


def test_guide_names_docstrings_with_their_owning_skill() -> None:
    """D53: docstrings are python-docstrings in python-coding, named, never restated."""
    text = reference_text(SKILL_ROOT, GUIDE)

    assert "python-docstrings (python-coding)" in text


def test_rule_id_pattern_skips_file_names_and_commands() -> None:
    text = "see which-document.md; docs-changelog and sphinx-api-reference; `playbook docs-check`"

    assert _rule_id_like_names(text) == {"docs-changelog", "sphinx-api-reference"}


def test_guide_stays_within_the_d49_budget() -> None:
    lines = guide_line_count(SKILL_ROOT, GUIDE)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{GUIDE} is {lines} lines"


@pytest.mark.parametrize("rule_id", RULES_SEEING_THE_GUIDE)
def test_rule_notes_end_naming_the_guide_by_bare_file_name(rule_id: str) -> None:
    text = (SKILL_ROOT / "rules" / f"{rule_id}.md").read_text(encoding="utf-8")
    last_line = text.rstrip("\n").rsplit("\n", 1)[-1]

    assert "which-document.md" in last_line, last_line
    assert "references/" not in last_line, last_line
