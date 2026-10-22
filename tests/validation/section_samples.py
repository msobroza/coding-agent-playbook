"""Shared samples for the skill sections and references checks (``validation._sections``).

A sectioned ``python-testing`` skill from package ``pkg`` and member rules built
from one helper, so ``test_sections.py`` and ``test_skill_references.py`` read
the same fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.validation._sections import check_skill_sections

if TYPE_CHECKING:
    from coding_agent_playbook.validation.findings import ValidationFindings

SKILL_ID = "python-testing"
SKILL_LABEL = f"skills/{SKILL_ID} (pkg)"
MOCKING = {
    "id": "mocking",
    "title": "Mocking",
    "impact": "CRITICAL",
    "summary": "Fakes at the boundary.",
    "open_when": "Replacing a collaborator in a test.",
}
FIXTURES = {
    "id": "fixtures",
    "title": "Fixtures",
    "impact": "MEDIUM",
    "summary": "Shared setup.",
    "open_when": "Adding or sharing test setup.",
}
SECTIONED_BLOCK: dict[str, Any] = {"use_when": "writing tests", "sections": [MOCKING, FIXTURES]}
SECTIONLESS_BLOCK: dict[str, Any] = {"use_when": "writing tests"}


def make_rule(
    rule_id: str = "pytest-fakes",
    *,
    skill: str | None = SKILL_ID,
    section: str | None = "mocking",
    priority: int = 20,
    scope: Literal["always", "scoped"] = "scoped",
    package: str = "pkg",
    body: str = "# Use fakes\n\nBody\n",
) -> Rule:
    """A member rule of ``python-testing`` at ``<package>/rules/<rule_id>.md``."""
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id,
        description="One line.",
        scope=scope,
        priority=priority,
        skill=skill,
        section=section,
    )
    path = Path(package) / "rules" / f"{rule_id}.md"
    return Rule(frontmatter, body, body, False, path, package)


def make_skill(block: Any = None, *, source_dir: Path | None = None, package: str = "pkg") -> Skill:
    """``python-testing`` with ``block`` as its ``playbook:`` block (the sectioned one by default)."""
    frontmatter: dict[str, Any] = {"id": SKILL_ID, "description": "Tests."}
    frontmatter["playbook"] = SECTIONED_BLOCK if block is None else block
    return Skill(frontmatter, "# Body\n", None, None, package, source_dir=source_dir)


def check(rules: list[Rule], skill: Skill) -> ValidationFindings:
    """Every section and reference check over ``rules`` and the one ``skill``."""
    return check_skill_sections(rules, [skill], check_predicate=_check_predicate)


def errors_of(rules: list[Rule], skill: Skill) -> list[tuple[str, str]]:
    """The ``(path, message)`` errors; asserts there is no warning."""
    findings = check(rules, skill)
    assert findings.warnings == []
    return [(error.path, error.message) for error in findings.errors]


def _check_predicate(predicate: dict[str, Any]) -> None:
    evaluate_predicate(predicate, {}, repo_root=Path())
