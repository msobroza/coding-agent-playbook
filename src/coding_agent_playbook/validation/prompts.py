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

``check_prompt_set_twins`` checks the prompt sets of every layer (D76): each
prompt in ``prompts/v2/`` has a v1 twin of the same id, keeping its name, slash
command and ``includes_rules``, and once a layer has a v2 set every v1 prompt of
the layer has a twin there.

``unrendered_prompts`` lists the prompts of those sets that the sync leaves
out, so ``checks`` can run its per-prompt checks on every set.

``check_prompt_rule_calls`` is the first check alone, for ``playbook sync
--check-staged``, which is not validate-gated; sync imports it from outside the
package, so it is public, unlike the other check modules beside ``checks``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard

from coding_agent_playbook.hooks.contract.findings import did_you_mean
from coding_agent_playbook.rendering.jinja import RULE_CALL_RE
from coding_agent_playbook.validation.findings import ValidationError

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.catalog.source import ArtifactSource, PromptSetLayer

#: How a well-formed ``includes_rules`` looks, quoted in the shape error.
_INCLUDES_RULES_SHAPE: Final = "expected a list of rule ids, e.g. ['python-typing', 'pytest']"

#: The frontmatter a twin keeps from its v1 prompt: what the listing and the eval
#: comparison read (D76).
_TWIN_KEPT_KEYS: Final = ("name", "slash", "includes_rules")

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
        messages = _rule_call_messages(prompt)
        messages.extend(_includes_rules_messages(prompt.frontmatter.includes_rules, rule_ids))
        errors.extend(ValidationError(path=_where(prompt), message=m) for m in messages)
    return errors


def check_prompt_rule_calls(prompts: Sequence[Prompt]) -> list[ValidationError]:
    """D15: one finding per ``{{ rule() }}`` call left in a prompt body, nothing else.

    The one prompt check ``playbook sync --check-staged`` runs: that pre-commit
    path skips the validate gate, yet rendering such a body raises a bare
    jinja2 ``UndefinedError`` instead of the section 7.5 migration message.

    Example::

        check_prompt_rule_calls(ctx.prompts_resolved)
    """
    return [
        ValidationError(path=_where(prompt), message=message)
        for prompt in prompts
        for message in _rule_call_messages(prompt)
    ]


def check_prompt_set_twins(artifact_source: ArtifactSource) -> list[ValidationError]:
    """D76: every layer's later prompt sets are complete twins of its v1 prompts.

    A source without prompt sets (:meth:`ArtifactSource.prompt_set_layers` is
    empty) passes.

    Example::

        check_prompt_set_twins(ctx.artifact_source)
    """
    return [error for layer in artifact_source.prompt_set_layers() for error in _twin_errors(layer)]


def unrendered_prompts(artifact_source: ArtifactSource) -> list[Prompt]:
    """The prompts of every layer's prompt sets that this sync does not render (D76).

    Under the default v1 they are the v2 twins; under v2, the v1 prompts the twins
    replace. ``playbook validate`` runs its per-prompt checks on them too, so a
    broken prompt fails before a repo switches sets, not after.

    Example::

        unrendered_prompts(ctx.artifact_source)  # [] without a prompts/v2/ anywhere
    """
    return [prompt for layer in artifact_source.prompt_set_layers() for prompt in layer.unrendered]


def _twin_errors(layer: PromptSetLayer) -> list[ValidationError]:
    """One layer's twin findings for its prompt set."""
    v1, twins, prompt_set, set_dir = layer.v1, layer.twins, layer.prompt_set, layer.set_dir
    by_id = {prompt.frontmatter.id: prompt for prompt in v1}
    twin_ids = {twin.frontmatter.id for twin in twins}
    errors = [
        ValidationError(
            path=_where(prompt),
            message=f"prompt {prompt.frontmatter.id!r} has no {prompt_set} twin in {set_dir}; "
            f"add one with the same id, or remove the {prompt_set} set",
        )
        for prompt in v1
        if prompt.frontmatter.id not in twin_ids
    ]
    for twin in twins:
        original = by_id.get(twin.frontmatter.id)
        if original is None:
            errors.append(
                ValidationError(
                    path=_where(twin),
                    message=f"{prompt_set} prompt {twin.frontmatter.id!r} has no v1 twin; "
                    "a prompt set only replaces the text of prompts with the same id",
                )
            )
            continue
        errors.extend(
            ValidationError(path=_where(twin), message=message)
            for message in _kept_key_messages(original, twin, prompt_set)
        )
    return errors


def _kept_key_messages(original: Prompt, twin: Prompt, prompt_set: str) -> list[str]:
    """One message per :data:`_TWIN_KEPT_KEYS` entry ``twin`` changes."""
    messages = []
    for key in _TWIN_KEPT_KEYS:
        before, after = getattr(original.frontmatter, key), getattr(twin.frontmatter, key)
        if before != after:
            messages.append(
                f"{prompt_set} prompt {twin.frontmatter.id!r} changes {key} from "
                f"{before!r} to {after!r}; a twin keeps its v1 prompt's {key}"
            )
    return messages


def _where(prompt: Prompt) -> str:
    """A finding's path: the prompt's source path, else its id."""
    return str(prompt.source_path or prompt.frontmatter.id)


def _rule_call_messages(prompt: Prompt) -> list[str]:
    """The migration message of every ``rule()`` call in ``prompt``'s body, in order."""
    return [_rule_call_message(m.group(1)) for m in RULE_CALL_RE.finditer(prompt.template_body)]


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
