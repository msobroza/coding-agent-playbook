"""Unit tests for ``check_rule_shape``: the rule's ``scope``, ``priority`` and ``section`` (prU D21)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.validation._frontmatter import check_rule_shape

_PATH = Path("playbook/rules/x.md")


def _rule(**overrides: Any) -> Rule:
    fields: dict[str, Any] = {"id": "x", "name": "X", "description": "d", "scope": "always"}
    fields.update(overrides)
    return Rule(RuleFrontmatter(**fields), "Body\n", "Body\n", False, _PATH, "<repo-local>")


def test_a_well_formed_rule_has_no_finding() -> None:
    assert check_rule_shape([_rule(priority=0, section="error-handling")]) == []


def test_an_unset_section_has_no_finding() -> None:
    assert check_rule_shape([_rule(section=None)]) == []


def test_a_non_string_section_names_the_value() -> None:
    [error] = check_rule_shape([_rule(section=5)])

    assert error.path == str(_PATH)
    assert "section: expected a kebab-case string" in error.message
    assert error.message.endswith("got 5")


def test_a_list_section_is_rejected() -> None:
    [error] = check_rule_shape([_rule(section=["a"])])

    assert error.message.endswith("got ['a']")


def test_a_bad_scope_and_a_bad_priority_give_two_errors_on_one_path() -> None:
    errors = check_rule_shape([_rule(scope="sometimes", priority=True)])

    assert [e.path for e in errors] == [str(_PATH), str(_PATH)]
    assert [e.message for e in errors] == [
        "scope: expected 'always' or 'scoped', got 'sometimes'",
        "priority: expected an int in 0-99, got True",
    ]
