"""The ml-data skill's references and their ``playbook.references`` entries.

prU C-ml-data-refs: the mapping (specs/prU-core-python-skills/mapping-ml-data.md,
"References") names two internal decision guides, each with an open-when line, the
array-and-frame gate and the rule ids it routes to. D47 lists each in
``playbook.references``; D49 caps an internal decision guide at 120 lines and has it
name rule ids in plain text.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Final

import pytest

from tests._catalog import core_skill_root
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    backticked_ids,
    guide_line_count,
    missing_sibling_guides,
    reference_text,
    references_block,
    rule_id_like_names,
    skill_md_parts,
    skill_rule_ids,
)

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("ml-data")
#: The mapping's gate for both guides: the array and frame libraries.
_ARRAY_GATE: Final = {"any_ml_stack": ["numpy", "pandas", "polars"]}
#: The mapping's references, in its order: path -> gate.
MAPPED_GATES: Final = {
    "references/library-equivalents.md": _ARRAY_GATE,
    "references/review-signals.md": _ARRAY_GATE,
}
#: The mapping's "Routes to" column: both guides route to every ml-data rule.
ROUTES_TO: Final = (
    "ml-serialization-security",
    "ml-vectorization",
    "ml-build-once",
    "ml-data-transforms",
    "ml-loc-assignment",
    "ml-dtypes-at-load",
    "ml-check-after-load",
    "ml-frame-validation",
    "ml-numpy-dtypes",
    "ml-categorical-labels",
    "ml-seeded-randomness",
    "ml-method-chaining",
    "ml-named-aggregation",
    "ml-array-typing",
    "ml-numeric-assertions",
)
#: The mapping's SKILL.md See Also: plain-text skill names (D32).
SEE_ALSO_SKILLS: Final = ("python-coding", "python-testing")
#: The prefix of this skill's rule ids, and the names with it that are no rule: the skill.
_RULE_ID_PREFIXES: Final = ("ml",)
_NOT_THIS_SKILLS_RULES: Final = frozenset({"ml-data"})


def _rule_id_like_names(text: str) -> set[str]:
    """The ml-data rule-id-shaped names ``text`` mentions, the skill name left out."""
    return rule_id_like_names(text, _RULE_ID_PREFIXES, _NOT_THIS_SKILLS_RULES)


def test_skill_lists_each_mapped_reference_with_its_gate_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    listed = {entry["path"]: entry.get("applies_if") for entry in entries}

    assert list(listed) == list(MAPPED_GATES)
    assert listed == MAPPED_GATES


def test_each_listed_reference_says_when_to_open_it() -> None:
    entries = references_block(SKILL_ROOT)

    blank = [entry["path"] for entry in entries if not entry["open_when"].strip()]

    assert blank == [], f"references with a blank open_when: {blank}"


@pytest.mark.parametrize("path", MAPPED_GATES)
def test_guide_names_every_rule_it_routes_to(path: str) -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, path))

    missing = [rule_id for rule_id in ROUTES_TO if rule_id not in named]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", MAPPED_GATES)
def test_guide_names_only_rule_ids_the_skill_ships(path: str) -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, path))

    unknown = sorted(named - skill_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{path} names rule ids ml-data does not ship: {unknown}"


def test_rule_id_pattern_skips_file_names_and_the_skill_name() -> None:
    text = "see library-equivalents.md; ml-build-once and ml-numpy-dtypes; ml-data"

    assert _rule_id_like_names(text) == {"ml-build-once", "ml-numpy-dtypes"}


@pytest.mark.parametrize("path", MAPPED_GATES)
def test_guide_names_rule_ids_in_plain_text(path: str) -> None:
    """D49: a guide names rule ids in plain text, never in backticks."""
    backticked = sorted(backticked_ids(reference_text(SKILL_ROOT, path)) & set(ROUTES_TO))

    assert backticked == [], f"{path} backticks rule ids: {backticked}"


@pytest.mark.parametrize("path", MAPPED_GATES)
def test_guide_routes_without_code_blocks(path: str) -> None:
    """The mapping: call names only; the rules and the Quick Reference keep the code."""
    assert "```" not in reference_text(SKILL_ROOT, path)


@pytest.mark.parametrize("path", MAPPED_GATES)
def test_internal_guide_stays_within_the_d49_budget(path: str) -> None:
    lines = guide_line_count(SKILL_ROOT, path)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{path} is {lines} lines"


@pytest.mark.parametrize("path", MAPPED_GATES)
def test_guide_ends_naming_its_sibling_guide_by_bare_file_name(path: str) -> None:
    missing = missing_sibling_guides(SKILL_ROOT, path, MAPPED_GATES)

    assert missing == [], f"{path}'s last line lacks or misnames {missing}"


def _body() -> str:
    _, body = skill_md_parts(SKILL_ROOT)
    return body


def test_body_has_only_the_quick_reference_and_see_also_headings() -> None:
    """D47: no hand-written picking bullets; D32: Quick Reference and See Also."""
    headings = re.findall(r"^## (.+)$", _body(), re.MULTILINE)

    assert headings == ["Quick Reference", "See Also"]


def test_body_leaves_reference_file_names_to_the_engine() -> None:
    named = [path for path in MAPPED_GATES if PurePosixPath(path).name in _body()]

    assert named == [], f"SKILL.md body names reference files: {named}"


def test_body_names_no_rule_ids() -> None:
    named = sorted(_rule_id_like_names(_body()))

    assert named == [], f"the Quick Reference names rule ids: {named}"


@pytest.mark.parametrize("marker", ["{%", "{{", "]("])
def test_body_has_no_jinja_and_no_links(marker: str) -> None:
    assert marker not in _body(), f"SKILL.md body contains {marker!r}"


def test_see_also_names_the_mapped_skills_in_order_in_plain_text() -> None:
    see_also = _body().partition("## See Also")[2]

    assert re.findall(r"^- ([a-z-]+):", see_also, re.MULTILINE) == list(SEE_ALSO_SKILLS)


def test_body_keeps_the_security_first_reading_instruction() -> None:
    assert "open the Serialization Security rules first" in _body()
