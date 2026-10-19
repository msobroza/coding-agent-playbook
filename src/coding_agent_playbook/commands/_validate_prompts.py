"""The prompt rule-reference checks of ``playbook validate`` (specs/prS-skills-context.md §7.5).

``includes_rules`` is the only declaration of the rules a prompt needs (D15):
Claude Code and OpenCode commands point at the skill references of those rules,
while Continue, the agent_harness leaf and the eval runner append their text.
A typo there would silently drop guidance, so three checks guard it (P3-7):

- the body calls no ``{{ rule() }}`` (the helper is gone; any spelling
  ``RULE_CALL_RE`` matches, in templated and plain prompts alike);
- ``includes_rules`` is a list of non-empty strings (a bare string used to be
  iterated character by character);
- every id names a rule of the merged set, with a did-you-mean.

A module of its own beside ``validate`` (which is over 400 lines), like the
other ``_validate_*`` check modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard

from coding_agent_playbook.commands._validation import RULE_CALL_RE, ValidationError
from coding_agent_playbook.hook_policy import did_you_mean

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from coding_agent_playbook.types import Prompt

#: How a well-formed ``includes_rules`` looks, quoted in the shape error.
_INCLUDES_RULES_SHAPE: Final = "expected a list of rule ids, e.g. ['python-typing', 'pytest']"

#: Where a valid id comes from: the merged rule set of every layer.
_RULE_LAYERS: Final = "which is no rule in core, an enabled overlay or playbook/rules/"


def check_prompt_rule_references(
    prompts: Sequence[Prompt], rule_ids: Collection[str]
) -> list[ValidationError]:
    """D15: prompts never call ``rule()``; ``includes_rules`` lists existing rule ids.

    ``rule_ids`` is the merged rule set before ``applies_if`` (a rule filtered
    out in this repo is still a valid id: it simply gets no pointer line).
    Each finding names the prompt's source path, else its id.

    Example::

        check_prompt_rule_references(ctx.prompts_resolved, {r.frontmatter.id for r in rules})
    """
    errors: list[ValidationError] = []
    for prompt in prompts:
        where = str(prompt.source_path or prompt.frontmatter.id)
        messages = [
            _rule_call_message(m.group(1)) for m in RULE_CALL_RE.finditer(prompt.template_body)
        ]
        messages.extend(_includes_rules_messages(prompt.frontmatter.includes_rules, rule_ids))
        errors.extend(ValidationError(path=where, message=message) for message in messages)
    return errors


def _rule_call_message(rule_id: str) -> str:
    """The migration message for a ``{{ rule("<rule_id>") }}`` call left in a prompt body."""
    return (
        f'body calls {{{{ rule("{rule_id}") }}}}; prompts no longer inline rules. '
        f"Remove the call and keep {rule_id!r} in includes_rules: Claude Code and "
        "OpenCode commands then point at its skill, Continue appends its text"
    )


def _includes_rules_messages(includes_rules: object, rule_ids: Collection[str]) -> list[str]:
    """One shape message for a malformed list, else one message per unknown id (each once)."""
    if not _is_list_of_rule_ids(includes_rules):
        return [f"includes_rules {includes_rules!r}: {_INCLUDES_RULES_SHAPE}"]
    return [
        f"includes_rules names {rule_id!r}, {_RULE_LAYERS}{did_you_mean(rule_id, rule_ids)}"
        for rule_id in dict.fromkeys(includes_rules)
        if rule_id not in rule_ids
    ]


def _is_list_of_rule_ids(value: object) -> TypeGuard[list[str]]:
    """Whether ``value`` is a list whose every entry is a non-empty string."""
    return isinstance(value, list) and all(isinstance(entry, str) and entry for entry in value)
