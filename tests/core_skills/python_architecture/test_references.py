"""The python-architecture skill's references and their ``playbook.references`` entries.

prU C-python-architecture-refs: the mapping (specs/prU-core-python-skills/mapping-
python-architecture.md, "References") names two references, ungated, each with an
open-when line and the rule ids it routes to: architecture-review.md (vendored, the
review procedure around layer_map.py) and where-code-goes.md (internal, D49). D47
lists each in ``playbook.references`` and ends the Notes of the rules whose mapping
row sees one with a line naming it by bare file name. Open-when lines, routes and
see rows are read from the mapping through ``tests._mapping_references``.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import load_core_attributions
from tests._catalog import core_skill_root
from tests._mapping_references import mapped_references, missing_rule_ids, rules_that_see
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    TOC_HEADING,
    TOC_THRESHOLD_LINES,
    backticked_ids,
    cross_skill_mentions,
    guide_line_count,
    known_rule_ids,
    last_notes_bullets,
    opens_with_table_of_contents,
    reference_text,
    references_block,
    skill_rule_ids,
)

if TYPE_CHECKING:
    from types import ModuleType

pytestmark = pytest.mark.catalog

_SKILL: Final = "python-architecture"
SKILL_ROOT: Final = core_skill_root(_SKILL)
REVIEW: Final = "references/architecture-review.md"
ROUTING_GUIDE: Final = "references/where-code-goes.md"
#: The mapping's references (license copy left out), in mapping order.
MAPPED: Final = {
    path: reference
    for path, reference in mapped_references(_SKILL).items()
    if reference.kind != "license"
}
#: A token shaped like one of this skill's rule ids (their prefixes).
_RULE_ID_LIKE_RE: Final = re.compile(r"(?<![\w.-])(?:arch|sqlalchemy)-[a-z0-9-]*[a-z0-9](?![\w.-])")
#: A long option in prose or a code block: ``--root-module``.
_FLAG_RE: Final = re.compile(r"(?<![\w-])--[a-z][a-z-]*[a-z]")
#: D47: a rule's Notes end with one see line per mapped reference it sees, so
#: arch-dependency-direction, which sees both references, ends with two.
SEE_LINE_COUNTS: Final = Counter(
    rule_id for path in MAPPED for rule_id in rules_that_see(_SKILL, path)
)


def test_mapping_names_the_two_references_this_ticket_ships() -> None:
    assert list(MAPPED) == [REVIEW, ROUTING_GUIDE]


def test_skill_lists_each_mapped_reference_ungated_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    assert [entry["path"] for entry in entries] == list(MAPPED)
    assert [entry.get("applies_if") for entry in entries] == [None] * len(MAPPED)
    assert [entry["open_when"] for entry in entries] == [ref.open_when for ref in MAPPED.values()]


@pytest.mark.parametrize("path", list(MAPPED))
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    missing = missing_rule_ids(reference_text(SKILL_ROOT, path), MAPPED[path].routes_to)

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", list(MAPPED))
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    text = reference_text(SKILL_ROOT, path)

    other_skills = {rule_id for _, rule_id in cross_skill_mentions(text)}
    named = set(_RULE_ID_LIKE_RE.findall(text)) - other_skills
    unknown = sorted(named - skill_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{path} names rule ids {_SKILL} does not ship: {unknown}"


@pytest.mark.parametrize("path", list(MAPPED))
def test_reference_names_only_rules_other_skills_ship_or_plan(path: str) -> None:
    """A "<skill>'s <id>" pointer names a rule that skill ships or its mapping plans."""
    mentions = cross_skill_mentions(reference_text(SKILL_ROOT, path))

    dangling = sorted(
        (skill, rule) for skill, rule in mentions if rule not in known_rule_ids(skill)
    )

    assert dangling == [], f"{path} names rules their skills neither ship nor plan: {dangling}"


@pytest.mark.parametrize("path", list(MAPPED))
def test_long_reference_opens_with_a_table_of_contents(path: str) -> None:
    text = reference_text(SKILL_ROOT, path)
    if text.count("\n") <= TOC_THRESHOLD_LINES:
        pytest.skip(f"{path} is short enough to need no table of contents")

    assert opens_with_table_of_contents(text), f"{path} opens with no {TOC_HEADING}"


def test_routing_guide_stays_within_the_d49_budget() -> None:
    lines = guide_line_count(SKILL_ROOT, ROUTING_GUIDE)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{ROUTING_GUIDE} is {lines} lines"


def test_routing_guide_names_rule_ids_in_plain_text() -> None:
    """D49: an internal guide names rule ids in plain text, never in backticks."""
    backticked = backticked_ids(reference_text(SKILL_ROOT, ROUTING_GUIDE))

    assert backticked & known_rule_ids(_SKILL) == set()


def test_routing_guide_sends_whole_graph_coupling_to_the_review() -> None:
    """The mapping: cycles, hidden globals and god modules are the review's checklist."""
    assert "architecture-review.md" in reference_text(SKILL_ROOT, ROUTING_GUIDE)


def test_review_documents_exactly_the_flags_layer_map_accepts(layer_map: ModuleType) -> None:
    parser = layer_map.build_parser()
    accepted = set(_FLAG_RE.findall(parser.format_help())) - {"--help"}

    documented = set(_FLAG_RE.findall(reference_text(SKILL_ROOT, REVIEW)))

    assert documented == accepted


@pytest.mark.parametrize("path", list(MAPPED))
def test_rules_that_see_a_reference_end_their_notes_naming_it(path: str) -> None:
    """D47: the last Notes bullets name the reference by bare file name, never by path."""
    name = path.removeprefix("references/")
    seeing = rules_that_see(_SKILL, path)

    for rule_id in seeing:
        tail = " ".join(last_notes_bullets(SKILL_ROOT, rule_id, SEE_LINE_COUNTS[rule_id]))
        assert f"see {name}" in tail, f"{rule_id}: Notes do not end naming {name}"
    assert seeing, f"no rule sees {path}"


def test_no_rule_names_a_literal_references_path() -> None:
    """D46.9: rules name references by bare file name."""
    offenders = sorted(
        rule.name
        for rule in (SKILL_ROOT / "rules").iterdir()
        if "references/" in rule.read_text(encoding="utf-8")
    )

    assert offenders == []


def test_review_is_vendored_and_the_guide_engine_written_in_attributions() -> None:
    attributions = load_core_attributions()
    pca_rows = attributions.sources["python-clean-architecture"].skills[_SKILL].rows
    crediting = {row.upstream for row in pca_rows if REVIEW in row.targets}

    assert crediting == {"commands/review-architecture.md", "commands/decouple.md"}
    assert ROUTING_GUIDE in attributions.engine_written[_SKILL]
    assert REVIEW not in attributions.engine_written[_SKILL]
