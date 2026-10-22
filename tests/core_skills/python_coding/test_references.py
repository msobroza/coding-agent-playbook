"""The python-coding skill's references and their ``playbook.references`` entries.

prU C-python-coding-refs: the mapping (specs/prU-core-python-skills/mapping-
python-coding.md, "References") names three internal decision guides, each with an
open-when line, no gate and the rule ids it routes to. D47 lists each in
``playbook.references``; D49 caps an internal decision guide at 120 lines.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from tests._catalog import core_skill_root
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    guide_line_count,
    missing_sibling_guides,
    reference_text,
    references_block,
    rule_id_like_names,
    skill_md_parts,
    skill_rule_ids,
)

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("python-coding")
#: The mapping's references, in its order; none carries a gate.
MAPPED_REFERENCES: Final = (
    "references/python-version-idioms.md",
    "references/choosing-a-data-shape.md",
    "references/error-flow.md",
)
#: The mapping's "Routes to" column: the rule ids each reference must name.
ROUTES_TO: Final = {
    "references/python-version-idioms.md": [
        "python-typing",
        "python-type-aliases",
        "python-async",
        "python-async-tasks",
        "python-async-fanout",
        "python-async-generators",
        "python-enums",
        "pydantic-model-validators",
        "python-match-fallback",
        "python-match-destructuring",
        "python-pure-core",
        "python-decorators",
        "python-context-managers",
    ],
    "references/choosing-a-data-shape.md": [
        "python-data-shapes",
        "python-frozen-dataclasses",
        "python-dataclass-post-init",
        "python-enums",
        "python-type-aliases",
        "python-protocols",
        "python-properties",
        "python-hide-internal-state",
        "python-optional-keys",
        "python-match-destructuring",
        "python-error-boundaries",
        "pydantic-boundaries",
        "pydantic-typed-settings",
        "pydantic-field-constraints",
        "pydantic-model-validators",
        "pydantic-special-types",
        "pydantic-serializers",
    ],
    "references/error-flow.md": [
        "python-custom-exceptions",
        "python-error-handling",
        "python-error-boundaries",
        "python-early-return",
        "python-dataclass-post-init",
        "python-match-fallback",
        "python-optional-keys",
        "pydantic-boundaries",
        "python-context-managers",
        "python-custom-context-managers",
        "python-async",
        "python-async-tasks",
        "python-retries-and-timeouts",
        "python-decorators",
    ],
}
#: The mapping's SKILL.md See Also: plain-text skill names (D32).
SEE_ALSO_SKILLS: Final = (
    "python-testing",
    "python-tooling",
    "design-patterns",
    "python-architecture",
    "web-application",
    "ml-data",
)
#: The prefixes of this skill's rule ids.
_RULE_ID_PREFIXES: Final = ("python", "pydantic")
#: Names with those prefixes that are no rule of this skill: skill names.
_NOT_THIS_SKILLS_RULES: Final = frozenset(
    {"python-coding", "python-architecture", "python-testing", "python-tooling"}
)


def _rule_id_like_names(text: str) -> set[str]:
    """The rule-id-shaped names ``text`` mentions, skill names left out."""
    return rule_id_like_names(text, _RULE_ID_PREFIXES, _NOT_THIS_SKILLS_RULES)


def test_skill_lists_each_mapped_reference_ungated_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    assert [entry["path"] for entry in entries] == list(MAPPED_REFERENCES)
    assert all("applies_if" not in entry for entry in entries)
    assert all(entry["open_when"].strip() for entry in entries)


def test_hand_written_body_leaves_navigation_to_the_engine() -> None:
    """D47: no hand-written picking bullets; D32: Quick Reference and plain-text See Also."""
    _, body = skill_md_parts(SKILL_ROOT)
    headings = re.findall(r"^## (.+)$", body, re.MULTILINE)

    assert headings == ["Quick Reference", "Pythonic rewrites", "See Also"]
    assert not any(path in body for path in MAPPED_REFERENCES)
    see_also = body.partition("## See Also")[2]
    for skill in SEE_ALSO_SKILLS:
        assert f"- {skill}:" in see_also, skill


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, path))

    missing = [rule_id for rule_id in ROUTES_TO[path] if rule_id not in named]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, path))

    unknown = sorted(named - skill_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{path} names rule ids python-coding does not ship: {unknown}"


def test_rule_id_pattern_skips_file_names_and_skill_names() -> None:
    text = "see python-version-idioms.md; python-async and pydantic-boundaries; python-coding"

    assert _rule_id_like_names(text) == {"python-async", "pydantic-boundaries"}


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_internal_guide_stays_within_the_d49_budget(path: str) -> None:
    lines = guide_line_count(SKILL_ROOT, path)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{path} is {lines} lines"


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_guide_ends_naming_its_sibling_guides_by_bare_file_name(path: str) -> None:
    missing = missing_sibling_guides(SKILL_ROOT, path, MAPPED_REFERENCES)

    assert missing == [], f"{path}'s last line lacks or misnames {missing}"
