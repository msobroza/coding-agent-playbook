"""How an ``includes_rules`` list becomes prompt text (specs/prS-skills-context.md §7.4.2).

:func:`includes_rules_appendix` builds the ``## Reference rules`` appendix, with
every included rule's text inline, that ``renderer.render_for`` adds to every
prompt format: Continue prompts, Claude Code commands and OpenCode commands
(``prompt_continue``, ``prompt_claude_command``, ``prompt_opencode_command``).
The agent_harness prompt leaf gets it through the Claude command format.
``render_for`` decides whether a prompt gets it (its template placed no
``rule()`` call itself) and calls this.

Stdlib only, and ``RuleRegistry`` is imported for type checking only:
``renderer`` imports this module, so a runtime import back would be a cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.renderer import RuleRegistry


def includes_rules_appendix(includes_rules: Sequence[str], registry: RuleRegistry | None) -> str:
    """The ``## Reference rules`` appendix of a prompt: each included rule's text, or ``""``.

    Every id in ``includes_rules`` is rendered through ``registry``, in order
    (an id listed twice is rendered twice); a rule that renders ``""`` (filtered
    out by ``applies_if``, or unknown) is skipped. ``""`` when there is nothing
    to list: no ids, no registry, or every fragment empty.

    The registry is asked with an empty context: it merges its stored detector
    facts beneath the caller's, so a templated rule renders without the caller
    knowing them.

    Example::

        includes_rules_appendix(["python-typing"], registry)
        # "\\n## Reference rules\\n\\n### Python typing\\n\\n<the rule text>\\n"
    """
    if not includes_rules or registry is None:
        return ""
    fragments: list[str] = []
    for rule_id in includes_rules:
        fragment = registry.render_for_inclusion(rule_id, {})
        if fragment:
            fragments.append(fragment.rstrip("\n"))
    if not fragments:
        return ""
    return "\n## Reference rules\n\n" + "\n\n".join(fragments) + "\n"
