"""The domino-jobs skill's decision guide and its ``playbook.references`` entry (prU C-domino-jobs-refs).

The mapping (specs/prU-core-python-skills/mapping-domino-jobs.md, "References")
names one engine-written decision guide (D49): a title, at most 120 lines, no
link and no URL, rule ids in plain text, routing to every rule the mapping
names, one table per location question with the three project types as columns
and the environment variable behind each location. The mapping's open_when,
gate, routes, sources and ``see:`` rules are read from the mapping through
``tests._mapping_references``. That the emitted skill lists and ships the guide
is checked on the Domino probe in tests/integration/test_domino_jobs_skill.py.
"""

from __future__ import annotations

import re
from typing import Any, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._attributions import MappingRow, load_core_attributions
from tests._catalog import core_rules, core_skill_root
from tests._mapping_references import (
    D49_MAX_LINES,
    MappedReference,
    line_count,
    mapped_references,
    missing_rule_ids,
    rules_that_see,
    whole_id,
)

pytestmark = pytest.mark.catalog

_SKILL: Final = "domino-jobs"
SKILL_ROOT: Final = core_skill_root(_SKILL)
GUIDE: Final = "references/where-outputs-go.md"
#: The variables that give each location (the guide names the variable, D65).
_VARIABLES: Final = (
    "DOMINO_WORKING_DIR",
    "DOMINO_ARTIFACTS_DIR",
    "DOMINO_DATASETS_DIR",
    "DOMINO_IMPORTED_DATA_DIR",
    "DOMINO_IS_GIT_BASED",
    "DOMINO_IS_WORKFLOW_JOB",
)
_VARIABLES_SECTION: Final = "Where each location comes from"
_SYMPTOMS_SECTION: Final = "When an output goes wrong"
#: The guide's sections, in order, and whether each is a per-project-type question.
#: The symptom table asks "what went wrong", not "where does it go": its rows are
#: symptoms and causes, so it has no project-type columns.
SECTIONS: Final = {
    _VARIABLES_SECTION: True,
    "Will this file survive the run?": True,
    "Where each kind of output goes": True,
    "Which files become results?": True,
    "Limits next to each location": True,
    _SYMPTOMS_SECTION: False,
}
_PROJECT_TYPE_COLUMNS: Final = "| DFS project | Git-based project | Flow task |"
_TABLE_RULE: Final = "| --- |"
_BACKTICKED_RULE_ID: Final = re.compile(r"`domino-[a-z0-9-]+`")
_LINK_OR_URL: Final = re.compile(r"\]\(|https?://|www\.")
_RULE_ID_LIKE: Final = whole_id(r"domino-[a-z0-9-]+")
_DOMINO_DOCS: Final = "domino-docs"


def _mapped() -> MappedReference:
    return mapped_references(_SKILL)[GUIDE]


def _guide() -> str:
    return (SKILL_ROOT / GUIDE).read_text(encoding="utf-8")


def _sections() -> dict[str, str]:
    """The guide's level-two sections, by heading, in order."""
    parts = _guide().split("\n## ")[1:]
    return {part.partition("\n")[0]: part.partition("\n")[2] for part in parts}


def _references_block() -> list[dict[str, Any]]:
    """The SKILL.md ``playbook.references`` entries, as YAML gives them."""
    frontmatter, _ = split_frontmatter((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"))
    entries = frontmatter["playbook"].get("references", [])
    assert isinstance(entries, list), entries
    return entries


def _domino_docs_rows() -> tuple[MappingRow, ...]:
    return load_core_attributions().sources[_DOMINO_DOCS].skills[_SKILL].rows


def test_skill_lists_the_mapped_guide_with_its_open_when_and_gate() -> None:
    entries = _references_block()

    assert [entry["path"] for entry in entries] == [GUIDE]
    assert entries[0]["open_when"].strip() == _mapped().open_when
    assert entries[0].get("applies_if") == {"domino_project": True}
    assert _mapped().gate == "domino_project: True"


def test_guide_has_the_decision_guide_shape() -> None:
    text = _guide()

    assert text.startswith("# "), "the guide opens with a title"
    assert line_count(text) <= D49_MAX_LINES, f"{GUIDE} is {line_count(text)} lines"
    assert not _LINK_OR_URL.search(text), "the guide holds no link and no URL"
    assert not _BACKTICKED_RULE_ID.search(text), "the guide backticks a rule id"


def test_guide_has_exactly_the_expected_sections() -> None:
    assert list(_sections()) == list(SECTIONS)


def test_guide_routes_to_every_mapped_rule() -> None:
    routes = _mapped().routes_to

    missing = missing_rule_ids(_guide(), routes)

    assert routes, "the mapping routes the guide to no rule"
    assert missing == [], f"{GUIDE} does not name {missing}"


def test_every_rule_id_the_guide_names_exists() -> None:
    unknown = set(_RULE_ID_LIKE.findall(_guide())) - set(core_rules())

    assert not unknown, f"the guide names rule ids no skill ships: {sorted(unknown)}"


@pytest.mark.parametrize("heading", list(SECTIONS))
def test_every_section_is_a_table_that_routes_to_rules(heading: str) -> None:
    body = _sections()[heading]

    assert _TABLE_RULE in body, f"{heading!r} has no table"
    assert _RULE_ID_LIKE.search(body), f"{heading!r} routes to no rule"


@pytest.mark.parametrize("heading", [heading for heading, per_type in SECTIONS.items() if per_type])
def test_every_location_question_has_the_project_types_as_columns(heading: str) -> None:
    assert _PROJECT_TYPE_COLUMNS in _sections()[heading], heading


@pytest.mark.parametrize("variable", _VARIABLES)
def test_guide_names_the_variable_behind_each_location(variable: str) -> None:
    assert variable in _sections()[_VARIABLES_SECTION], variable


@pytest.mark.parametrize("rule_id", rules_that_see(_SKILL, GUIDE))
def test_rule_names_the_guide_by_bare_file_name(rule_id: str) -> None:
    """The content template names a reference in a rule body by its bare file name."""
    notes = (SKILL_ROOT / "rules" / f"{rule_id}.md").read_text(encoding="utf-8")
    last_note = notes.partition("## Notes\n")[2].strip().splitlines()[-1]

    assert "where-outputs-go.md" in last_note
    assert GUIDE not in last_note


def test_mapping_names_the_rules_that_see_the_guide() -> None:
    assert rules_that_see(_SKILL, GUIDE), "the mapping's see column names no rule"


def test_guide_is_engine_written_in_attributions() -> None:
    assert GUIDE in load_core_attributions().engine_written[_SKILL]


def test_exactly_the_mapped_sources_credit_the_guide() -> None:
    mapped = {upstream for source, upstream in _mapped().sources if source == _DOMINO_DOCS}

    crediting = {row.upstream for row in _domino_docs_rows() if GUIDE in row.targets}

    assert mapped, "the mapping names no domino-docs source for the guide"
    assert crediting == mapped


def test_attribution_rows_have_no_stray_punctuation() -> None:
    stray = [row.upstream for row in _domino_docs_rows() if ".;" in row.changes]

    assert not stray, f"rows with '.;': {stray}"
