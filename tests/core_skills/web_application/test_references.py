"""The web-application skill's references and their ``playbook.references`` entries.

prU C-web-application-refs: the mapping (specs/prU-core-python-skills/mapping-
web-application.md, "References") names three references, each with an open-when
line, a gate and the rule ids it routes to. D47 lists each in ``playbook.references``;
D49 caps the internal decision guide at 120 lines. The routes are read from the
mapping through ``tests._mapping_references``, which the other skills' refs tests share.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from tests._catalog import core_skill_root
from tests._mapping_references import mapped_references, missing_rule_ids
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    cross_skill_mentions,
    guide_line_count,
    known_rule_ids,
    names_a_rule,
    reference_text,
    references_block,
    rule_id_like_names,
    skill_rule_ids,
)

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("web-application")
#: D23, D46(3): FastAPI-only material gates on FastAPI, stack-neutral web material on any framework.
_FASTAPI: Final = {"has_framework": ["fastapi"]}
_ANY_WEB_FRAMEWORK: Final = {"any_framework": ["fastapi", "flask", "django", "starlette"]}
#: The mapping's references, in its order: path -> gate.
MAPPED_GATES: Final = {
    "references/add-an-endpoint.md": _FASTAPI,
    "references/api-review-checklist.md": _ANY_WEB_FRAMEWORK,
    "references/request-lifecycle.md": _FASTAPI,
}
#: The mapping's "Routes to" column, read from the mapping: the rule ids each reference names.
ROUTES_TO: Final = {
    path: reference.routes_to
    for path, reference in mapped_references("web-application").items()
    if path in MAPPED_GATES
}
#: The engine-written decision guide D49 budgets.
INTERNAL_GUIDE: Final = "references/request-lifecycle.md"
#: The prefixes of this skill's rule ids.
_RULE_ID_PREFIXES: Final = ("fastapi", "web", "sqlalchemy", "alembic", "httpx")
#: Names with those prefixes that are no rule of this skill: the skill itself and its
#: example app. Other skills' rules are named "<skill>'s <id>" and checked apart.
_NOT_THIS_SKILLS_RULES: Final = frozenset({"web-application", "fastapi-hotel-api"})
#: The checklist whose every line names the rule that holds its detail (mapping).
CHECKLIST: Final = "references/api-review-checklist.md"
_CHECKLIST_LINE_RE: Final = re.compile(r"^- \[ \] .*$", re.MULTILINE)


def test_skill_lists_each_mapped_reference_with_its_gate_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    listed = {entry["path"]: entry.get("applies_if") for entry in entries}

    assert list(listed) == list(MAPPED_GATES)
    assert listed == MAPPED_GATES
    assert all(entry["open_when"].strip() for entry in entries)


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    text = reference_text(SKILL_ROOT, path)

    missing = missing_rule_ids(text, ROUTES_TO[path])

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    text = reference_text(SKILL_ROOT, path)

    other_skills = {rule_id for _, rule_id in cross_skill_mentions(text)}
    named = rule_id_like_names(text, _RULE_ID_PREFIXES, _NOT_THIS_SKILLS_RULES | other_skills)
    unknown = sorted(named - skill_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{path} names rule ids web-application does not ship: {unknown}"


def test_internal_guide_stays_within_the_d49_budget() -> None:
    lines = guide_line_count(SKILL_ROOT, INTERNAL_GUIDE)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{INTERNAL_GUIDE} is {lines} lines"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_only_rules_other_skills_ship_or_plan(path: str) -> None:
    """A "<skill>'s <id>" pointer names a rule that skill ships or its mapping plans."""
    mentions = cross_skill_mentions(reference_text(SKILL_ROOT, path))

    dangling = sorted(
        (skill, rule) for skill, rule in mentions if rule not in known_rule_ids(skill)
    )

    assert dangling == [], f"{path} names rules their skills neither ship nor plan: {dangling}"


def test_cross_skill_parser_finds_the_lifecycle_pointers() -> None:
    mentions = cross_skill_mentions(reference_text(SKILL_ROOT, INTERNAL_GUIDE))

    assert ("python-architecture", "sqlalchemy-repositories") in mentions
    assert ("python-architecture", "arch-tests-by-layer") in mentions
    assert ("python-coding", "pydantic-typed-settings") in mentions


def test_every_checklist_line_names_a_rule() -> None:
    lines = _CHECKLIST_LINE_RE.findall(reference_text(SKILL_ROOT, CHECKLIST))
    rule_ids = skill_rule_ids(SKILL_ROOT)

    bare = [line for line in lines if not names_a_rule(line, rule_ids)]

    assert lines, f"{CHECKLIST} has no checklist lines"
    assert bare == [], f"{CHECKLIST} lines name no rule: {bare}"
