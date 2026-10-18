"""The public checks of ``commands/_validate_skills.py`` on in-memory rules and skills.

The exact messages are pinned end to end in ``tests/cli/test_validate_skills.py``;
these tests pin what each check looks at and what it leaves alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.commands._validate_skills import (
    check_rule_skills,
    check_skill_membership,
    is_skill_safe_name,
)
from coding_agent_playbook.types import Rule, RuleFrontmatter, Skill

_BLOCK = {"use_when": "editing Python code", "files": "Any Python file"}


def _rule(rule_id: str, *, skill: object = "python-coding", scope: str = "scoped") -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id.title(),
        description="One line.",
        scope=scope,  # type: ignore[arg-type]
        skill=skill,  # type: ignore[arg-type]
    )
    return Rule(frontmatter, "Body\n", "Body\n", False, Path(f"rules/{rule_id}.md"), "pkg")


def _skill(skill_id: str, *, block: Any = None, body: str = "# Body\n") -> Skill:
    frontmatter: dict[str, Any] = {"id": skill_id, "description": "Conventions."}
    if block is not None:
        frontmatter["playbook"] = block
    return Skill(frontmatter, body, None, None, "pkg")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("python-typing", True),
        ("a" * 64, True),
        ("a" * 65, False),
        ("Py_Typing", False),
        ("python--typing", False),
        ("", False),
        (42, False),
        (None, False),
    ],
)
def test_is_skill_safe_name(value: object, expected: bool) -> None:
    assert is_skill_safe_name(value) is expected


def test_check_skill_membership_ignores_rules_without_skill() -> None:
    rules = [_rule("loose", skill=None), _rule("house-style", skill=None, scope="always")]

    assert check_skill_membership(rules, [_skill("python-coding", block=_BLOCK)]) == []


def test_check_skill_membership_reports_the_rule_path() -> None:
    errors = check_skill_membership([_rule("python-typing", skill="nope")], [])

    assert [error.path for error in errors] == ["rules/python-typing.md"]
    assert "expected one of: none, no skill declares a 'playbook:' block" in errors[0].message


def test_check_skill_membership_reports_an_unsafe_id_and_a_missing_skill_together() -> None:
    errors = check_skill_membership([_rule("Py_Typing", skill="nope")], [])

    assert [error.message.split(" ", 3)[:3] for error in errors] == [
        ["rule", "id", "'Py_Typing'"],
        ["skill", "'nope'", "does"],
    ]


def test_check_rule_skills_leaves_plain_skills_alone() -> None:
    plain = _skill("query-db", body="## References\n")

    findings = check_rule_skills([_rule("db", skill="query-db")], [plain])

    assert findings.errors == []
    assert findings.warnings == []


def test_check_rule_skills_counts_members_on_every_layer_regardless_of_applies_if() -> None:
    """A member gated off by ``applies_if`` still counts: no W1 for its skill (E7)."""
    gated = _rule("python-typing")
    gated.frontmatter.applies_if = {"python_version": ">=9.0"}

    findings = check_rule_skills([gated], [_skill("python-coding", block=_BLOCK)])

    assert findings.errors == []
    assert findings.warnings == []


def test_check_rule_skills_skips_the_description_fit_on_a_malformed_block() -> None:
    """V11 reads the block, so a broken block reports only its own error (V7)."""
    skill = _skill("python-coding", block=["use_when"], body="x")
    skill.frontmatter["description"] = "x" * 400

    findings = check_rule_skills([_rule("python-typing")], [skill])

    assert len(findings.errors) == 1
    assert "'playbook' must be a mapping" in findings.errors[0].message


def _long_named_members() -> list[Rule]:
    """Four members whose 68-char names cannot all fit the composed description (W3)."""
    members = [_rule(f"member-{letter}") for letter in "abcd"]
    for rule in members:
        rule.frontmatter.name = f"{rule.frontmatter.id} " + "x" * 59
    return members


def test_check_rule_skills_warns_when_a_sound_block_truncates_the_member_list() -> None:
    """The control for the test below: these members do trip W3 on a sound block."""
    findings = check_rule_skills(_long_named_members(), [_skill("python-coding", block=_BLOCK)])

    assert findings.errors == []
    assert ["... and 1 more" in warning.message for warning in findings.warnings] == [True]


@pytest.mark.parametrize(
    "block",
    [
        {"use_when": "Use when editing", "files": "Any"},
        {**_BLOCK, "covers": "x"},
        {**_BLOCK, "files": "f" * 90},
    ],
    ids=["V10-use-when-prefix", "V8-unknown-key", "V9-long-files"],
)
def test_check_rule_skills_skips_the_truncation_warning_on_a_malformed_block(
    block: dict[str, str],
) -> None:
    """W3 measures the block's phrases, so a rejected block reports only its error."""
    findings = check_rule_skills(_long_named_members(), [_skill("python-coding", block=block)])

    assert len(findings.errors) == 1
    assert findings.warnings == []
