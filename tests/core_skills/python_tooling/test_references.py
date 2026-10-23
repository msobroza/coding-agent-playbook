"""The python-tooling skill's references and their ``playbook.references`` entries.

prU C-python-tooling-refs: the mapping (specs/prU-core-python-skills/mapping-
python-tooling.md, "References") names two engine-written decision guides, each with
an open-when line, a gate and the rule ids it routes to. D47 lists each in
``playbook.references``; D49 caps an internal decision guide at 120 lines; D29 keeps
every package-manager command out of the ungated guide.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from tests._catalog import core_skill_root
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    cross_skill_mentions,
    guide_line_count,
    known_rule_ids,
    reference_text,
    references_block,
    unknown_rule_ids,
)

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("python-tooling")
CHECK_FAILURES: Final = "references/check-failures.md"
UV_FAILURES: Final = "references/uv-dependency-failures.md"
#: The mapping's references, in its order: path -> gate (``None``: every Python repo).
MAPPED_GATES: Final = {
    CHECK_FAILURES: None,
    UV_FAILURES: {"package_manager": "uv"},
}
#: The mapping's "Routes to" column: the rule ids each reference must name.
ROUTES_TO: Final = {
    CHECK_FAILURES: [
        "python-static-checks",
        "ruff-lint",
        "ruff-format",
        "mypy-type-checking",
        "pytest-configuration",
    ],
    UV_FAILURES: ["python-uv-workflow", "python-pyproject-dependencies", "mypy-type-checking"],
}
#: A token shaped like one of this skill's rule ids (their prefixes).
_RULE_ID_LIKE_RE: Final = re.compile(r"\b(?:python|ruff|mypy|pytest)-[a-z0-9-]*[a-z0-9]\b")
#: Tokens with those prefixes that are no rule id: skill names, another skill's
#: reference (named by bare file name) and uv's ``.python-version`` file. Other
#: skills' rules are named "<skill>'s <id>" and checked apart.
_RULE_ID_LOOKALIKES: Final = frozenset(
    {"python-coding", "python-testing", "python-tooling", "python-version-idioms", "python-version"}
)
#: D29: a package-manager command or file, which only a guide gated on that manager shows.
_PACKAGE_MANAGER_RE: Final = re.compile(r"\b(?:uv|uvx|pip|poetry|pdm|conda)\b")
#: A guide's table row, between its outer pipes.
_TABLE_ROW_RE: Final = re.compile(r"^\|(.+)\|$", re.MULTILINE)
#: A Rule cell that routes to another skill as a whole: "the ml-data skill".
_OTHER_SKILL_CELL_RE: Final = re.compile(r"^the [a-z0-9-]+ skill$")
#: The repo kind a pointer to another skill's reference is scoped to: "In pytest repos".
_REPO_KIND_RE: Final = re.compile(r"\bIn [^.;]+ repos\b")


def _reference_text(path: str) -> str:
    """The text of one of the skill's files: ``_reference_text(CHECK_FAILURES)``."""
    return reference_text(SKILL_ROOT, path)


def _rows_routed_to_another_skill(text: str) -> list[list[str]]:
    """The cells of each table row whose last (Rule) cell names another skill as a whole.

    Example: ``_rows_routed_to_another_skill("| PT | ... | the python-testing skill |")``
    -> ``[["PT", "...", "the python-testing skill"]]``.
    """
    rows = [[cell.strip() for cell in row.split("|")] for row in _TABLE_ROW_RE.findall(text)]
    return [cells for cells in rows if _OTHER_SKILL_CELL_RE.match(cells[-1])]


def test_skill_lists_each_mapped_reference_with_its_gate_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    listed = {entry["path"]: entry.get("applies_if") for entry in entries}

    assert list(listed) == list(MAPPED_GATES)
    assert listed == MAPPED_GATES
    assert all(entry["open_when"].strip() for entry in entries)


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    text = _reference_text(path)

    missing = [rule_id for rule_id in ROUTES_TO[path] if rule_id not in text]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    text = _reference_text(path)

    unknown = unknown_rule_ids(text, _RULE_ID_LIKE_RE, _RULE_ID_LOOKALIKES, SKILL_ROOT)

    assert unknown == [], f"{path} names rule ids python-tooling does not ship: {unknown}"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_only_rules_other_skills_ship_or_plan(path: str) -> None:
    """A "<skill>'s <id>" pointer names a rule that skill ships or its mapping plans."""
    mentions = cross_skill_mentions(_reference_text(path))

    dangling = sorted(
        (skill, rule) for skill, rule in mentions if rule not in known_rule_ids(skill)
    )

    assert dangling == [], f"{path} names rules their skills neither ship nor plan: {dangling}"


def test_cross_skill_parser_finds_the_check_failure_pointers() -> None:
    mentions = cross_skill_mentions(_reference_text(CHECK_FAILURES))

    assert ("python-coding", "python-typing") in mentions
    assert ("python-coding", "python-function-signatures") in mentions
    assert ("python-testing", "pytest-deterministic-tests") in mentions


def test_rows_routed_to_another_skill_scope_the_pointer_and_stand_alone() -> None:
    """Mapping: such a row names its repo kind, and its fix holds where that skill is absent."""
    rows = _rows_routed_to_another_skill(_reference_text(CHECK_FAILURES))

    unscoped = [cells[0] for cells in rows if not _REPO_KIND_RE.search(cells[-2])]
    no_own_fix = [cells[0] for cells in rows if "`ruff rule <CODE>`" not in cells[-2]]

    assert len(rows) == 2, rows
    assert unscoped == [], f"rows that do not name the repos their pointer is for: {unscoped}"
    assert no_own_fix == [], f"rows with no fix of their own: {no_own_fix}"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_internal_guide_stays_within_the_d49_budget(path: str) -> None:
    lines = guide_line_count(SKILL_ROOT, path)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{path} is {lines} lines"


def test_ungated_guide_names_no_package_manager_command() -> None:
    """D29: a reference is byte-copied, so uv's commands live only in the uv-gated guide."""
    hits = _PACKAGE_MANAGER_RE.findall(_reference_text(CHECK_FAILURES))

    assert hits == [], f"{CHECK_FAILURES} names package-manager commands: {hits}"
