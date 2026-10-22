"""The public checks of ``validation/_skills.py`` on in-memory rules and skills.

The exact messages are pinned end to end in ``tests/cli/test_validate_skills.py``;
these tests pin what each check looks at and what it leaves alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.validation._skills import (
    SCOPED_RULE_NEEDS_SKILL_MESSAGE,
    check_rule_skills,
    check_skill_membership,
    is_skill_safe_name,
)

_BLOCK = {"use_when": "editing Python code", "files": "Any Python file"}


def _rule(
    rule_id: str, *, skill: object = "python-coding", scope: str = "scoped", package: str = "pkg"
) -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id.title(),
        description="One line.",
        scope=scope,  # type: ignore[arg-type]
        skill=skill,  # type: ignore[arg-type]
    )
    path = Path(package) / "rules" / f"{rule_id}.md"
    return Rule(frontmatter, "Body\n", "Body\n", False, path, package)


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


def test_check_skill_membership_ignores_always_rules_without_skill() -> None:
    rules = [_rule("house-style", skill=None, scope="always")]

    assert (
        check_skill_membership(rules, [_skill("python-coding", block=_BLOCK)], all_rules=rules)
        == []
    )


def test_check_skill_membership_reports_the_rule_path() -> None:
    rules = [_rule("python-typing", skill="nope")]

    errors = check_skill_membership(rules, [], all_rules=rules)

    assert [error.path for error in errors] == ["pkg/rules/python-typing.md"]
    assert "expected one of: none, no skill declares a 'playbook:' block" in errors[0].message


def test_check_skill_membership_reports_an_unsafe_id_and_a_missing_skill_together() -> None:
    rules = [_rule("Py_Typing", skill="nope")]

    errors = check_skill_membership(rules, [], all_rules=rules)

    assert [error.message.split(" ", 3)[:3] for error in errors] == [
        ["rule", "id", "'Py_Typing'"],
        ["skill", "'nope'", "does"],
    ]


def test_scoped_rule_without_skill_lists_only_skills_that_take_members() -> None:
    """V1's known skills are those with a ``playbook:`` block, sorted; a plain skill is not one."""
    rules = [_rule("loose", skill=None)]
    skills = [
        _skill("python-testing", block=_BLOCK),
        _skill("brainstorming"),
        _skill("ml-data", block=_BLOCK),
    ]

    errors = check_skill_membership(rules, skills, all_rules=rules)

    assert [error.message for error in errors] == [
        SCOPED_RULE_NEEDS_SKILL_MESSAGE.format(known="ml-data, python-testing")
    ]


def test_scoped_rule_without_skill_and_no_known_skill_says_why() -> None:
    rules = [_rule("loose", skill=None)]

    errors = check_skill_membership(rules, [_skill("brainstorming")], all_rules=rules)

    assert errors[0].message.endswith("known skills: none, no skill declares a 'playbook:' block")


def test_override_hint_names_the_nearest_overridden_rule_that_names_a_skill() -> None:
    """Core names python-coding, an overlay python-testing, then a skill-less overlay layer."""
    winner = _rule("python-typing", skill=None, package="repo")
    all_rules = [
        _rule("python-typing", skill="python-coding", package="core"),
        _rule("python-typing", skill="python-testing", package="overlay"),
        _rule("python-typing", skill=None, package="overlay2"),
        _rule("python-pure-core", skill="ml-data", package="core"),
        winner,
    ]

    errors = check_skill_membership([winner], [], all_rules=all_rules)

    assert errors[0].message.endswith("; the rule it overrides (overlay) names 'python-testing'")


def test_override_hint_is_absent_when_no_overridden_rule_named_a_skill() -> None:
    winner = _rule("python-typing", skill=None, package="repo")
    all_rules = [_rule("python-typing", skill=None, package="core"), winner]

    errors = check_skill_membership([winner], [], all_rules=all_rules)

    assert errors[0].message == SCOPED_RULE_NEEDS_SKILL_MESSAGE.format(
        known="none, no skill declares a 'playbook:' block"
    )


def test_check_rule_skills_leaves_plain_skills_alone() -> None:
    plain = _skill("query-db", body="## Rules\n")

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


def test_check_skill_membership_leaves_an_in_skill_always_rule_to_r6() -> None:
    """V3's 'remove skill' does not apply to a location the author cannot remove (R6 hints)."""
    rule = _rule("house-style", skill="python-coding", scope="always")
    rule.home_skill, rule.skill_from_location = "python-coding", True

    skills = [_skill("python-coding", block=_BLOCK)]
    assert check_skill_membership([rule], skills, all_rules=[rule]) == []


def test_v8_names_sections_and_references_as_allowed_keys() -> None:
    skill = _skill("python-coding", block={**_BLOCK, "when": "always"})

    findings = check_rule_skills([_rule("python-typing")], [skill])

    assert [error.message for error in findings.errors] == [
        "'playbook' has unknown key 'when'; allowed keys: files, use_when, sections, references"
    ]


def test_sections_and_references_are_known_playbook_keys() -> None:
    block = {**_BLOCK, "sections": [], "references": []}

    findings = check_rule_skills([_rule("python-typing")], [_skill("python-coding", block=block)])

    assert findings.errors == []
