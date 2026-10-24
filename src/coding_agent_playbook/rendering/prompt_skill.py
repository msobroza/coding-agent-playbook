"""A prompt rendered as a skill body: the prompt-as-skill pattern.

The body a prompt gets when it is delivered as a skill rather than as a slash
command: its title, its rendered body, its ``includes_rules`` inlined as the
``## Reference rules`` appendix (there is no skill to point at), then a note of
its input variables. It carries no command frontmatter and no sentinel: the
``SKILL.md`` envelope holds both. Two adapters share it so their bodies never
drift: ``agent_harness`` (its ``prompts/<slash>/SKILL.md`` leaves) and
``shared_skills`` (the ``review-core`` skill Codex reads, #274).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.rendering.formats import render_inline_prompt_markdown

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.rendering.rule_registry import RuleRegistry


def prompt_skill_body(prompt: Prompt, rule_registry: RuleRegistry | None) -> str:
    """The skill body of ``prompt``: titled body, its rules inline, an input-variable note.

    ``includes_rules:`` is inlined through ``rule_registry`` (a rule its gate
    filters out drops silently); ``None`` inlines nothing. Input variables are
    noted so the agent knows what to substitute.

    Example::

        body = prompt_skill_body(review_prompt, registry)  # "# Review\\n..."
    """
    rendered = render_inline_prompt_markdown(
        prompt.body, dataclasses.asdict(prompt.frontmatter), rule_registry
    )
    note = input_variables_note(prompt.frontmatter.input_variables)
    if note:
        return f"{rendered.rstrip(chr(10))}\n\n{note}"
    return rendered


def input_variables_note(variables: Sequence[Mapping[str, Any]]) -> str:
    """A ``## Input variables`` list telling the agent what to substitute; ``""`` without any.

    Example::

        >>> input_variables_note([{"name": "path", "description": "file to review"}])
        '## Input variables\\n\\n- `path` — file to review\\n'
    """
    if not variables:
        return ""
    lines = ["## Input variables", ""]
    for var in variables:
        varname = str(var.get("name", ""))
        desc = str(var.get("description", "")).strip()
        lines.append(f"- `{varname}`" + (f" — {desc}" if desc else ""))
    return "\n".join(lines) + "\n"
