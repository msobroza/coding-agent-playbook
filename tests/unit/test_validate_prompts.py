"""Tests for the prompt rule-reference checks of ``playbook validate`` (prS §7.4.8, §7.5).

``includes_rules`` is the only declaration of the rules a prompt needs (D15),
so :func:`check_prompt_rule_references` refuses a ``{{ rule() }}`` call, an
``includes_rules`` that is not a list of rule ids, and an id that names no rule.
The CLI wiring is covered in ``tests/cli/test_validate.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.commands._validate_prompts import check_prompt_rule_references
from coding_agent_playbook.commands._validation import ValidationError
from coding_agent_playbook.types import Prompt, PromptFrontmatter

_RULE_IDS = frozenset({"python-typing", "pytest", "python-error-handling"})


def _prompt(body: str = "Review.\n", includes_rules: Any = ()) -> Prompt:
    """A repo-local prompt ``p`` with no source file, so findings name it by id."""
    frontmatter = PromptFrontmatter(
        id="p", name="P", description="d", slash="p", includes_rules=includes_rules
    )
    return Prompt(frontmatter, body, body, True, None, "<repo-local>")


def test_a_prompt_listing_existing_rules_passes() -> None:
    prompt = _prompt(includes_rules=["python-typing", "pytest", "python-typing"])

    assert check_prompt_rule_references([prompt], _RULE_IDS) == []


@pytest.mark.parametrize(
    "call",
    ['{{ rule("python-typing") }}', "{{- rule('python-typing') -}}", '{{rule("python-typing")}}'],
    ids=["plain", "trim-markers", "no-spaces"],
)
def test_a_rule_call_is_refused_with_the_migration_message(call: str) -> None:
    """Even an id that ``includes_rules`` lists: prompts no longer inline rules."""
    prompt = _prompt(f"Review.\n{call}\n", includes_rules=["python-typing"])

    assert check_prompt_rule_references([prompt], _RULE_IDS) == [
        ValidationError(
            path="p",
            message=(
                'body calls {{ rule("python-typing") }}; prompts no longer inline rules. '
                "Remove the call and keep 'python-typing' in includes_rules: Claude Code "
                "and OpenCode commands then point at its skill, Continue appends its text"
            ),
        )
    ]


@pytest.mark.parametrize(
    "value",
    ["python-typing", ["python-typing", ""], ["python-typing", 3], {"python-typing": True}],
    ids=["bare-string", "empty-id", "non-string-id", "mapping"],
)
def test_includes_rules_that_is_no_list_of_ids_is_one_error(value: Any) -> None:
    """Regression: a bare string used to be iterated character by character."""
    prompt = _prompt(includes_rules=value)

    assert check_prompt_rule_references([prompt], _RULE_IDS) == [
        ValidationError(
            path="p",
            message=(
                f"includes_rules {value!r}: expected a list of rule ids, "
                "e.g. ['python-typing', 'pytest']"
            ),
        )
    ]


def test_an_unknown_id_names_the_closest_rule() -> None:
    prompt = _prompt(includes_rules=["python-typng"])

    assert check_prompt_rule_references([prompt], _RULE_IDS) == [
        ValidationError(
            path="p",
            message=(
                "includes_rules names 'python-typng', which is no rule in core, an enabled "
                "overlay or playbook/rules/; did you mean 'python-typing'?"
            ),
        )
    ]


def test_an_unknown_id_far_from_every_rule_gets_no_suggestion() -> None:
    prompt = _prompt(includes_rules=["zzz"])

    [error] = check_prompt_rule_references([prompt], _RULE_IDS)

    assert error.message.endswith("an enabled overlay or playbook/rules/")


def test_a_finding_names_the_prompt_source_file(tmp_path: Any) -> None:
    source = tmp_path / "playbook" / "prompts" / "p.md"
    prompt = _prompt(includes_rules=["zzz"])
    prompt = Prompt(prompt.frontmatter, "b", "b", False, source, "<repo-local>")

    [error] = check_prompt_rule_references([prompt], _RULE_IDS)

    assert error.path == str(source)
