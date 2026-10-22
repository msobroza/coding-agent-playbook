"""The web-application skill's references and their ``playbook.references`` entries.

prU C-web-application-refs: the mapping (specs/prU-core-python-skills/mapping-
web-application.md, "References") names three references, each with an open-when
line, a gate and the rule ids it routes to. D47 lists each in ``playbook.references``;
D49 caps the internal decision guide at 120 lines.
"""

from __future__ import annotations

import re
from typing import Any, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._catalog import core_skill_root

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
#: The mapping's "Routes to" column: the rule ids each reference must name.
ROUTES_TO: Final = {
    "references/add-an-endpoint.md": [
        "web-api-schemas",
        "sqlalchemy-2-style",
        "alembic-migrations",
        "fastapi-dependency-providers",
        "fastapi-thin-routes",
        "web-http-methods",
        "web-api-resource-naming",
        "web-api-pagination",
        "fastapi-query-parameters",
        "web-object-authorization",
        "sqlalchemy-transaction-boundary",
        "fastapi-error-boundaries",
        "fastapi-openapi-metadata",
        "fastapi-app-wiring",
        "fastapi-dependency-overrides",
        "sqlalchemy-test-rollback",
    ],
    "references/api-review-checklist.md": [
        "web-http-methods",
        "web-api-resource-naming",
        "fastapi-error-boundaries",
        "web-api-schemas",
        "web-api-pagination",
        "fastapi-query-parameters",
        "fastapi-openapi-metadata",
        "fastapi-dependency-providers",
        "fastapi-thin-routes",
        "web-object-authorization",
        "web-jwt-validation",
        "web-password-hashing",
        "web-cors-origins",
        "fastapi-app-wiring",
        "fastapi-request-id-logging",
        "httpx-shared-client",
        "alembic-migrations",
        "sqlalchemy-session-per-request",
    ],
    "references/request-lifecycle.md": [
        "fastapi-app-wiring",
        "web-cors-origins",
        "httpx-shared-client",
        "alembic-migrations",
        "fastapi-request-id-logging",
        "fastapi-dependency-providers",
        "sqlalchemy-session-per-request",
        "web-jwt-validation",
        "web-object-authorization",
        "fastapi-thin-routes",
        "web-api-schemas",
        "fastapi-query-parameters",
        "web-api-pagination",
        "web-http-methods",
        "web-api-resource-naming",
        "fastapi-no-blocking-calls",
        "sqlalchemy-transaction-boundary",
        "sqlalchemy-2-style",
        "sqlalchemy-eager-loading",
        "sqlalchemy-bound-parameters",
        "web-password-hashing",
        "web-secure-tokens",
        "fastapi-error-boundaries",
        "fastapi-openapi-metadata",
        "fastapi-dependency-overrides",
        "sqlalchemy-test-rollback",
    ],
}
#: D49: an engine-written decision guide is at most 120 lines.
INTERNAL_GUIDE: Final = "references/request-lifecycle.md"
INTERNAL_GUIDE_MAX_LINES: Final = 120
#: A token shaped like one of this skill's rule ids (their prefixes).
_RULE_ID_LIKE_RE: Final = re.compile(
    r"\b(?:fastapi|web|sqlalchemy|alembic|httpx)-[a-z0-9-]*[a-z0-9]\b"
)
#: Names with those prefixes that are no rule of this skill: the skill itself, its
#: example app, and the python-architecture rule the mapping names with its skill.
_NOT_THIS_SKILLS_RULES: Final = frozenset(
    {"web-application", "fastapi-hotel-api", "sqlalchemy-repositories"}
)


def _references_block() -> list[dict[str, Any]]:
    """The SKILL.md ``playbook.references`` list, as YAML gives it."""
    frontmatter, _ = split_frontmatter((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"))
    entries = frontmatter["playbook"].get("references", [])
    assert isinstance(entries, list), entries
    return entries


def _skill_rule_ids() -> set[str]:
    """Every rule id of the skill: the rule file names without their suffixes."""
    return {path.name.split(".")[0] for path in (SKILL_ROOT / "rules").iterdir()}


def test_skill_lists_each_mapped_reference_with_its_gate_in_mapping_order() -> None:
    entries = _references_block()

    listed = {entry["path"]: entry.get("applies_if") for entry in entries}

    assert list(listed) == list(MAPPED_GATES)
    assert listed == MAPPED_GATES
    assert all(entry["open_when"].strip() for entry in entries)


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    text = (SKILL_ROOT / path).read_text(encoding="utf-8")

    missing = [rule_id for rule_id in ROUTES_TO[path] if rule_id not in text]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", sorted(ROUTES_TO))
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    text = (SKILL_ROOT / path).read_text(encoding="utf-8")

    named = set(_RULE_ID_LIKE_RE.findall(text)) - _NOT_THIS_SKILLS_RULES
    unknown = sorted(named - _skill_rule_ids())

    assert unknown == [], f"{path} names rule ids web-application does not ship: {unknown}"


def test_internal_guide_stays_within_the_d49_budget() -> None:
    lines = (SKILL_ROOT / INTERNAL_GUIDE).read_text(encoding="utf-8").count("\n")

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{INTERNAL_GUIDE} is {lines} lines"
