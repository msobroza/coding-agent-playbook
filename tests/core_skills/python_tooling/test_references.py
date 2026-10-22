"""The python-tooling skill's references and their ``playbook.references`` entries.

prU C-python-tooling-refs: the mapping (specs/prU-core-python-skills/mapping-
python-tooling.md, "References") names two engine-written decision guides, each with
an open-when line, a gate and the rule ids it routes to. D47 lists each in
``playbook.references``; D49 caps an internal decision guide at 120 lines; D29 keeps
every package-manager command out of the ungated guide.
"""

from __future__ import annotations

import re
from typing import Any, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._attributions import MAPPING_SPECS_DIR
from tests._catalog import core_skill_root

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
#: D49: an engine-written decision guide is at most 120 lines.
INTERNAL_GUIDE_MAX_LINES: Final = 120
#: A token shaped like one of this skill's rule ids (their prefixes).
_RULE_ID_LIKE_RE: Final = re.compile(r"\b(?:python|ruff|mypy|pytest)-[a-z0-9-]*[a-z0-9]\b")
#: Names with those prefixes that are no rule: skills, another skill's reference
#: (named by bare file name) and uv's ``.python-version`` file. Other skills' rules
#: are named "<skill>'s <id>" and checked apart.
_NOT_RULES: Final = frozenset(
    {"python-coding", "python-testing", "python-tooling", "python-version-idioms", "python-version"}
)
#: Another skill's rules, named "python-coding's python-early-return and ...".
_CROSS_SKILL_RE: Final = re.compile(
    r"\b([a-z][a-z0-9-]*)'s ([a-z0-9-]+(?:(?:, | and )[a-z0-9-]+)*)"
)
_LIST_SEPARATOR_RE: Final = re.compile(r", | and ")
#: A mapping spec's rule-table row: ``| `rules/<id>.md[.j2]` | ...``.
_SPEC_RULE_PATH_RE: Final = re.compile(r"^\| `rules/([a-z0-9-]+)\.md(?:\.j2)?` \|", re.MULTILINE)
#: D29: a package-manager command or file, which only a guide gated on that manager shows.
_PACKAGE_MANAGER_RE: Final = re.compile(r"\b(?:uv|uvx|pip|poetry|pdm|conda)\b")


def _references_block() -> list[dict[str, Any]]:
    """The SKILL.md ``playbook.references`` entries, as YAML gives them."""
    frontmatter, _ = split_frontmatter((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"))
    entries = frontmatter["playbook"].get("references", [])
    assert isinstance(entries, list), entries
    return entries


def test_skill_lists_each_mapped_reference_with_its_gate_in_mapping_order() -> None:
    entries = _references_block()

    listed = {entry["path"]: entry.get("applies_if") for entry in entries}

    assert list(listed) == list(MAPPED_GATES)
    assert listed == MAPPED_GATES
    assert all(entry["open_when"].strip() for entry in entries)


def _reference_text(path: str) -> str:
    """The text of one of the skill's files: ``_reference_text(CHECK_FAILURES)``."""
    return (SKILL_ROOT / path).read_text(encoding="utf-8")


def _python_tooling_rule_ids() -> set[str]:
    """Every rule id of the skill: the rule file names without their suffixes."""
    return {path.name.split(".")[0] for path in (SKILL_ROOT / "rules").iterdir()}


def _cross_skill_mentions(text: str) -> set[tuple[str, str]]:
    """``(skill, rule id)`` for each "<skill>'s <id>, <id> and <id>" naming a mapped skill.

    >>> sorted(_cross_skill_mentions("python-coding's a-b and c-d"))
    [('python-coding', 'a-b'), ('python-coding', 'c-d')]
    """
    mentions: set[tuple[str, str]] = set()
    for match in _CROSS_SKILL_RE.finditer(text):
        skill, ids = match.groups()
        if (MAPPING_SPECS_DIR / f"mapping-{skill}.md").is_file():
            mentions.update((skill, rule_id) for rule_id in _LIST_SEPARATOR_RE.split(ids))
    return mentions


def _known_rule_ids(skill: str) -> set[str]:
    """The rules ``skill`` ships, or its mapping spec plans while its lane has not landed."""
    spec = (MAPPING_SPECS_DIR / f"mapping-{skill}.md").read_text(encoding="utf-8")
    planned = set(_SPEC_RULE_PATH_RE.findall(spec))
    rules_dir = core_skill_root(skill) / "rules"
    if not rules_dir.is_dir():
        return planned
    return planned | {path.name.split(".")[0] for path in rules_dir.iterdir()}


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    text = _reference_text(path)

    missing = [rule_id for rule_id in ROUTES_TO[path] if rule_id not in text]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    text = _reference_text(path)

    other_skills = {rule_id for _, rule_id in _cross_skill_mentions(text)}
    named = set(_RULE_ID_LIKE_RE.findall(text)) - _NOT_RULES - other_skills
    unknown = sorted(named - _python_tooling_rule_ids())

    assert unknown == [], f"{path} names rule ids python-tooling does not ship: {unknown}"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_only_rules_other_skills_ship_or_plan(path: str) -> None:
    """A "<skill>'s <id>" pointer names a rule that skill ships or its mapping plans."""
    mentions = _cross_skill_mentions(_reference_text(path))

    dangling = sorted(
        (skill, rule) for skill, rule in mentions if rule not in _known_rule_ids(skill)
    )

    assert dangling == [], f"{path} names rules their skills neither ship nor plan: {dangling}"


def test_cross_skill_parser_finds_the_check_failure_pointers() -> None:
    mentions = _cross_skill_mentions(_reference_text(CHECK_FAILURES))

    assert ("python-coding", "python-typing") in mentions
    assert ("python-coding", "python-function-signatures") in mentions
    assert ("python-testing", "pytest-deterministic-tests") in mentions


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_internal_guide_stays_within_the_d49_budget(path: str) -> None:
    lines = _reference_text(path).count("\n")

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{path} is {lines} lines"


def test_ungated_guide_names_no_package_manager_command() -> None:
    """D29: a reference is byte-copied, so uv's commands live only in the uv-gated guide."""
    hits = _PACKAGE_MANAGER_RE.findall(_reference_text(CHECK_FAILURES))

    assert hits == [], f"{CHECK_FAILURES} names package-manager commands: {hits}"
