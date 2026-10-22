"""The domino-jobs skill's decision guide and its navigation (prU C-domino-jobs-refs).

Two seams: the Domino probe as sync leaves it (the emitted skill lists the
reference under "References and examples" and ships its file), and the
reference file itself, an engine-written decision guide (D49): a title, at most
120 lines, no link and no URL, rule ids in plain text, routing to every rule the
mapping names, one table per question with the three project types as columns
and the environment variable behind each location. ``_OPEN_WHEN``, ``_ROUTES``,
``_SEE_FROM`` and ``_SOURCES`` are a pinned snapshot of the reference row of
``specs/prU-core-python-skills/mapping-domino-jobs.md`` (a generated file the
tests do not parse): a mapping change must update them by hand.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests._attributions import MappingRow, load_core_attributions
from tests._catalog import core_rules, core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SKILL: Final = "domino-jobs"
_PATH: Final = "references/where-outputs-go.md"
_OPEN_WHEN: Final = (
    "Deciding where a job's file goes, or a job's output is missing, unexpectedly in"
    " Results, too slow to sync or overwritten by another run."
)
#: The rule ids the guide routes to (the mapping's "Routes to" column).
_ROUTES: Final = (
    "domino-project-types",
    "domino-paths-from-env",
    "domino-secrets-in-env-vars",
    "domino-datasets-for-large-data",
    "domino-run-scoped-writes",
    "domino-dataset-snapshots",
    "domino-materialize-external-data",
    "domino-spot-checkpoints",
    "domino-flow-task-io",
    "domino-job-results",
    "domino-job-logging",
    "domino-job-stats-file",
    "domino-job-email-report",
    "domino-run-manifest",
)
#: The rules that name the guide in their Notes (the mapping's "see" column).
_SEE_FROM: Final = (
    "domino-project-types",
    "domino-paths-from-env",
    "domino-datasets-for-large-data",
    "domino-flow-task-io",
    "domino-job-results",
)
#: The domino-docs pages the mapping names as the guide's sources.
_SOURCES: Final = frozenset(
    {
        "user_guide/de4abb",
        "user_guide/ccaee6",
        "user_guide/910370",
        "user_guide/6942ab",
        "user_guide/e09156",
        "user_guide/b4f02f",
        "user_guide/56938d",
        "user_guide/5b84c5",
        "user_guide/2629d4",
        "user_guide/b4cb04",
    }
)
#: The variables that give each location (the guide names the variable, D65).
_VARIABLES: Final = (
    "DOMINO_WORKING_DIR",
    "DOMINO_ARTIFACTS_DIR",
    "DOMINO_DATASETS_DIR",
    "DOMINO_IMPORTED_DATA_DIR",
    "DOMINO_IS_GIT_BASED",
    "DOMINO_IS_WORKFLOW_JOB",
)
_PROJECT_TYPE_COLUMNS: Final = "| DFS project | Git-based project | Flow task |"
_BACKTICKED_RULE_ID: Final = re.compile(r"`domino-[a-z0-9-]+`")
_LINK_OR_URL: Final = re.compile(r"\]\(|https?://|www\.")
_MAX_LINES: Final = 120
#: Sections that are tables but not per-project-type questions.
_NOT_PER_TYPE: Final = frozenset({"Limits next to each location", "When an output goes wrong"})


def _whole_id(pattern: str) -> re.Pattern[str]:
    """Match ``pattern`` as a whole hyphenated id, never inside a longer one."""
    return re.compile(rf"(?<![\w-]){pattern}(?![\w-])")


_RULE_ID_LIKE: Final = _whole_id(r"domino-[a-z0-9-]+")


def _guide_path() -> Path:
    return core_skill_root(_SKILL) / _PATH


def _guide() -> str:
    return _guide_path().read_text(encoding="utf-8")


def _sections() -> dict[str, str]:
    """The guide's level-two sections, by heading."""
    parts = _guide().split("\n## ")[1:]
    return {part.partition("\n")[0]: part.partition("\n")[2] for part in parts}


def _domino_docs_rows() -> tuple[MappingRow, ...]:
    return load_core_attributions().sources["domino-docs"].skills[_SKILL].rows


def test_domino_probe_lists_the_guide_with_its_open_when(domino_probe_repo: Path) -> None:
    skill_md = (domino_probe_repo / ".claude" / "skills" / _SKILL / "SKILL.md").read_text(
        encoding="utf-8"
    )
    listed = skill_md.partition("## References and examples\n")[2]
    lines = [line for line in listed.splitlines() if line.startswith("- [")]
    assert lines == [f"- [{_PATH}]({_PATH}) — Open when: {_OPEN_WHEN}"]


def test_domino_probe_ships_the_guide(domino_probe_repo: Path) -> None:
    emitted = domino_probe_repo / ".claude" / "skills" / _SKILL / _PATH
    assert emitted.read_bytes() == _guide_path().read_bytes()


def test_guide_has_the_decision_guide_shape() -> None:
    text = _guide()
    assert text.startswith("# "), "the guide opens with a title"
    assert len(text.splitlines()) <= _MAX_LINES
    assert not _LINK_OR_URL.search(text), "the guide holds no link and no URL"
    assert not _BACKTICKED_RULE_ID.search(text), "the guide backticks a rule id"


@pytest.mark.parametrize("rule_id", _ROUTES)
def test_guide_routes_to_each_mapped_rule(rule_id: str) -> None:
    assert _whole_id(re.escape(rule_id)).search(_guide()), rule_id


def test_every_rule_id_the_guide_names_exists() -> None:
    unknown = set(_RULE_ID_LIKE.findall(_guide())) - set(core_rules())
    assert not unknown, f"the guide names rule ids no skill ships: {sorted(unknown)}"


def test_every_question_table_has_the_project_types_as_columns() -> None:
    tables = {
        heading: body
        for heading, body in _sections().items()
        if heading not in _NOT_PER_TYPE and "| --- |" in body
    }
    assert len(tables) >= 3
    for heading, body in tables.items():
        assert _PROJECT_TYPE_COLUMNS in body, f"{heading!r} lacks the project-type columns"


@pytest.mark.parametrize("variable", _VARIABLES)
def test_guide_names_the_variable_behind_each_location(variable: str) -> None:
    assert variable in _sections()["Where each location comes from"], variable


def test_limits_and_symptoms_sections_route_to_rules() -> None:
    for heading in _NOT_PER_TYPE:
        body = _sections()[heading]
        assert "| --- |" in body, heading
        assert _RULE_ID_LIKE.search(body), f"{heading!r} routes to no rule"


@pytest.mark.parametrize("rule_id", _SEE_FROM)
def test_rule_names_the_guide_by_bare_file_name(rule_id: str) -> None:
    rule = core_skill_root(_SKILL) / "rules" / f"{rule_id}.md"
    notes = rule.read_text(encoding="utf-8").partition("## Notes\n")[2]
    assert "where-outputs-go.md" in notes


def test_guide_is_engine_written_in_attributions() -> None:
    assert _PATH in load_core_attributions().engine_written[_SKILL]


def test_exactly_the_mapped_sources_credit_the_guide() -> None:
    crediting = {row.upstream for row in _domino_docs_rows() if _PATH in row.targets}
    assert crediting == _SOURCES


def test_attribution_rows_have_no_stray_punctuation() -> None:
    stray = [row.upstream for row in _domino_docs_rows() if ".;" in row.changes]
    assert not stray, f"rows with '.;': {stray}"
