"""The design-patterns skill's references and their ``playbook.references`` entries.

prU C-design-patterns-refs: the mapping (specs/prU-core-python-skills/mapping-
design-patterns.md, "References") names eleven references, each with an open-when
line and the rule ids it routes to; none is gated. D47 lists each in
``playbook.references`` and ends the Notes of the rules that point to one with a
see line naming it by bare file name; D49 caps the internal decision guide at 120
lines; a reference over 100 lines opens with a table of contents.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, get_args

import pytest

from tests._catalog import core_skill_root
from tests.core_skills._references import (
    cross_skill_mentions,
    known_rule_ids,
    references_block,
    shipped_rule_ids,
)

if TYPE_CHECKING:
    from types import ModuleType

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("design-patterns")
#: The mapping's "Routes to" column, in its order: the rule ids each reference names.
ROUTES_TO: Final = {
    "references/smell-catalog.md": [
        "design-start-with-the-data",
        "design-value-objects",
        "design-name-for-intent",
        "design-split-god-class",
        "design-lightest-construct",
        "design-tell-dont-ask",
        "design-composition-over-inheritance",
        "design-open-closed",
        "design-low-coupling",
        "design-complete-construction",
        "design-pattern-from-smell",
        "design-review-by-severity",
    ],
    "references/quality-checklist.md": [
        "design-review-by-severity",
        "design-start-with-the-data",
        "design-value-objects",
        "design-name-for-intent",
        "design-split-god-class",
        "design-lightest-construct",
        "design-tell-dont-ask",
        "design-composition-over-inheritance",
        "design-open-closed",
        "design-low-coupling",
        "design-dependency-inversion",
        "design-complete-construction",
        "design-pattern-from-smell",
    ],
    "references/principles-and-grasp.md": [
        "design-single-responsibility",
        "design-split-god-class",
        "design-tell-dont-ask",
        "design-grasp-responsibilities",
        "design-low-coupling",
        "design-dependency-inversion",
        "design-open-closed",
        "design-composition-over-inheritance",
        "design-liskov-substitution",
        "design-interface-segregation",
        "design-dry-yagni-kiss",
        "design-start-with-the-data",
    ],
    "references/refactoring-moves.md": [
        "design-start-with-the-data",
        "design-open-closed",
        "design-tell-dont-ask",
        "design-lightest-construct",
        "design-complete-construction",
    ],
    "references/lint-guardrails.md": [
        "design-review-by-severity",
        "design-tell-dont-ask",
        "design-low-coupling",
    ],
    "references/strategy-progression.md": ["design-strategy", "design-function-builder"],
    "references/abstract-factory-progression.md": [
        "design-abstract-factory",
        "design-function-builder",
    ],
    "references/bridge-progression.md": ["design-bridge"],
    "references/command-progression.md": ["design-command"],
    "references/observer-mediator-pubsub.md": ["design-domain-events", "design-callback"],
    "references/rule-neighbors.md": [
        "design-singleton",
        "design-value-objects",
        "design-start-with-the-data",
        "design-function-builder",
        "design-function-wrapper",
        "design-lazy-loading",
        "design-dependency-inversion",
        "design-tell-dont-ask",
        "design-open-closed",
        "design-single-responsibility",
        "design-low-coupling",
        "design-adapter",
        "design-name-for-intent",
        "design-lightest-construct",
        "design-grasp-responsibilities",
        "design-facade",
        "design-domain-events",
        "design-plugin-loading",
        "design-split-god-class",
        "design-composition-over-inheritance",
        "design-liskov-substitution",
        "design-interface-segregation",
        "design-dry-yagni-kiss",
        "design-pattern-from-smell",
    ],
}
#: D49: an engine-written decision guide is at most 120 lines.
INTERNAL_GUIDE: Final = "references/rule-neighbors.md"
INTERNAL_GUIDE_MAX_LINES: Final = 120
#: The content-ticket template: a reference over 100 lines opens with a table of contents.
TOC_THRESHOLD_LINES: Final = 100
TOC_HEADING: Final = "## Contents"
#: The see lines this ticket adds (mapping "Body plan" columns): rule -> the reference
#: file names its last Notes bullet names, by bare file name.
SEE_LINES: Final = {
    "design-single-responsibility": ["rule-neighbors.md"],
    "design-dependency-inversion": ["rule-neighbors.md"],
    "design-grasp-responsibilities": ["principles-and-grasp.md"],
    "design-strategy": ["strategy-progression.md"],
    "design-domain-events": ["observer-mediator-pubsub.md"],
    "design-lightest-construct": ["rule-neighbors.md"],
    "design-review-by-severity": [
        "quality-checklist.md",
        "smell-catalog.md",
        "lint-guardrails.md",
        "refactoring-moves.md",
    ],
}
SMELL_CATALOG: Final = "references/smell-catalog.md"
CHECKLIST: Final = "references/quality-checklist.md"
LINT_GUARDRAILS: Final = "references/lint-guardrails.md"
#: A token shaped like one of this skill's rule ids.
_RULE_ID_LIKE_RE: Final = re.compile(r"\bdesign-[a-z0-9-]*[a-z0-9]\b")
#: The skill's own name has the rule-id prefix but is no rule.
_NOT_A_RULE: Final = frozenset({"design-patterns"})
_BACKTICKED_ID_RE: Final = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")
#: A bare reference file name in a rule body: ``rule-neighbors.md``.
_BARE_REFERENCE_RE: Final = re.compile(r"\b([a-z0-9]+(?:-[a-z0-9]+)*\.md)\b")
_NOTES_RE: Final = re.compile(r"^## Notes\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
_HEADING_RE: Final = re.compile(r"^### ([a-z0-9-]+)$", re.MULTILINE)
_NUMBERED_ITEM_RE: Final = re.compile(r"^\d+\. .*$", re.MULTILINE)
#: The smell-id cell of a lint-guardrails row: ``| `E722` | bare except | `bare-except` | ...``.
_LINT_SMELL_CELL_RE: Final = re.compile(r"^\| `[^|]+` \| [^|]+ \| ([^|]+) \|", re.MULTILINE)


def _reference_text(path: str) -> str:
    """The text of one of the skill's files: ``_reference_text(CHECKLIST)``."""
    return (SKILL_ROOT / path).read_text(encoding="utf-8")


def _rule_text(rule_id: str) -> str:
    """The source text of one of the skill's rules (``.md``; none is a template)."""
    return (SKILL_ROOT / "rules" / f"{rule_id}.md").read_text(encoding="utf-8")


def _last_notes_bullet(rule_id: str) -> str:
    """The last ``- `` bullet of a rule's Notes section."""
    match = _NOTES_RE.search(_rule_text(rule_id))
    assert match, f"{rule_id} has no Notes section"
    bullets = [line for line in match.group(1).splitlines() if line.startswith("- ")]
    assert bullets, f"{rule_id} has no Notes bullet"
    return bullets[-1]


def _names_a_rule(text: str, rule_ids: set[str]) -> bool:
    """True when ``text`` names one of ``rule_ids`` in backticks, or another skill's rule."""
    return bool(set(_BACKTICKED_ID_RE.findall(text)) & rule_ids or cross_skill_mentions(text))


def _smell_sections() -> dict[str, str]:
    """The smell catalog's ``### <smell id>`` entries: id -> the entry's text."""
    text = _reference_text(SMELL_CATALOG)
    heads = list(_HEADING_RE.finditer(text))
    ends = [head.start() for head in heads[1:]] + [len(text)]
    return {head.group(1): text[head.end() : end] for head, end in zip(heads, ends, strict=True)}


def test_skill_lists_each_mapped_reference_ungated_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    assert [entry["path"] for entry in entries] == list(ROUTES_TO)
    assert [entry.get("applies_if") for entry in entries] == [None] * len(ROUTES_TO)
    assert all(entry["open_when"].strip() for entry in entries)


def test_every_reference_file_is_listed() -> None:
    on_disk = {f"references/{path.name}" for path in (SKILL_ROOT / "references").glob("*.md")}

    assert on_disk == set(ROUTES_TO)


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    text = _reference_text(path)

    missing = [rule_id for rule_id in ROUTES_TO[path] if rule_id not in text]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    named = set(_RULE_ID_LIKE_RE.findall(_reference_text(path))) - _NOT_A_RULE

    unknown = sorted(named - shipped_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{path} names rule ids design-patterns does not ship: {unknown}"


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_reference_names_only_rules_other_skills_ship_or_plan(path: str) -> None:
    """A "<skill>'s <id>" pointer names a rule that skill ships or its mapping plans."""
    mentions = cross_skill_mentions(_reference_text(path))

    dangling = sorted(
        (skill, rule) for skill, rule in mentions if rule not in known_rule_ids(skill)
    )

    assert dangling == [], f"{path} names rules their skills neither ship nor plan: {dangling}"


def test_internal_guide_stays_within_the_d49_budget() -> None:
    lines = _reference_text(INTERNAL_GUIDE).count("\n")

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{INTERNAL_GUIDE} is {lines} lines"


@pytest.mark.parametrize("path", list(ROUTES_TO))
def test_long_reference_opens_with_a_table_of_contents(path: str) -> None:
    text = _reference_text(path)
    if text.count("\n") <= TOC_THRESHOLD_LINES:
        pytest.skip(f"{path} is short enough to need no table of contents")

    first_section = text.find("\n## ")

    assert text.find(TOC_HEADING) == first_section + 1, f"{path} opens with no {TOC_HEADING}"


@pytest.mark.parametrize("rule_id", list(SEE_LINES))
def test_rule_notes_end_with_their_see_line(rule_id: str) -> None:
    last = _last_notes_bullet(rule_id)

    missing = [name for name in SEE_LINES[rule_id] if name not in last]

    assert "see" in last, f"{rule_id}: last Notes bullet is no see line: {last!r}"
    assert missing == [], f"{rule_id}: last Notes bullet does not name {missing}"


def test_every_reference_a_rule_names_exists() -> None:
    """Rules name references by bare file name (D47); each named file ships."""
    shipped = {path.name for path in (SKILL_ROOT / "references").glob("*.md")}
    named = {
        (rule.stem, name)
        for rule in (SKILL_ROOT / "rules").iterdir()
        for name in _BARE_REFERENCE_RE.findall(rule.read_text(encoding="utf-8"))
        if name != "SKILL.md"
    }

    dangling = sorted((rule, name) for rule, name in named if name not in shipped)

    assert named, "no rule names a reference"
    assert dangling == [], f"rules name references the skill does not ship: {dangling}"


def test_smell_catalog_has_an_entry_for_every_scanner_smell(smell_model: ModuleType) -> None:
    scanner_ids = set(get_args(smell_model.SmellId))
    sections = _smell_sections()

    missing = sorted(scanner_ids - set(sections))
    unmarked = sorted(i for i in scanner_ids & set(sections) if "(scanner" not in sections[i])

    assert missing == [], f"{SMELL_CATALOG} has no entry for scanner ids {missing}"
    assert unmarked == [], f"{SMELL_CATALOG} does not mark scanner ids {unmarked}"


def test_every_smell_entry_names_its_owning_rule() -> None:
    rule_ids = shipped_rule_ids(SKILL_ROOT)

    orphans = sorted(
        smell for smell, entry in _smell_sections().items() if not _names_a_rule(entry, rule_ids)
    )

    assert _smell_sections(), f"{SMELL_CATALOG} has no ### <smell id> entries"
    assert orphans == [], f"{SMELL_CATALOG} entries name no owning rule: {orphans}"


def test_every_checklist_item_names_a_rule() -> None:
    items = _NUMBERED_ITEM_RE.findall(_reference_text(CHECKLIST))
    rule_ids = shipped_rule_ids(SKILL_ROOT)

    bare = [item for item in items if not _names_a_rule(item, rule_ids)]

    assert items, f"{CHECKLIST} has no numbered items"
    assert bare == [], f"{CHECKLIST} items name no rule: {bare}"


def test_lint_guardrails_name_only_catalogued_smell_ids() -> None:
    cells = _LINT_SMELL_CELL_RE.findall(_reference_text(LINT_GUARDRAILS))
    smells = {smell for cell in cells for smell in _BACKTICKED_ID_RE.findall(cell)}

    uncatalogued = sorted(smells - set(_smell_sections()))

    assert smells, f"{LINT_GUARDRAILS} has no ruff-code rows"
    assert uncatalogued == [], f"{LINT_GUARDRAILS} names smell ids with no entry: {uncatalogued}"
