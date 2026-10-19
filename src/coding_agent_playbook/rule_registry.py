"""The rule registry: how a prompt reaches the rules it includes (SPEC §6.2.5).

- :class:`RuleRegistryImpl` — concrete ``RuleRegistry`` from the renderer
  Protocol. Built once per sync from the applies_if-filtered rule list.
- :func:`build_prompt_environment` — the registry plus the rule-aware Jinja
  environment every prompt render (``sync``, ``render``, the eval runner)
  builds the same way.

Moved out of ``orchestrator`` unchanged (specs/prS-skills-context.md §7.4.4).
This module imports ``template_source`` from the orchestrator, so the
orchestrator must never import this module back (a cycle), nor re-export its
names (a shim): importers take them from here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.orchestrator import template_source
from coding_agent_playbook.renderer import build_environment, render_sandboxed

if TYPE_CHECKING:
    from jinja2 import Environment

    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.types import Rule


class RuleRegistryImpl:
    """Concrete :class:`RuleRegistry` used by the orchestrator.

    Built once per sync from the merged + applies_if-filtered rule list. The
    ``render_for_inclusion`` method returns the inline body for a rule (with
    ``### {rule.name}`` header) or ``""`` when the rule is filtered out — the
    silent-omission contract from SPEC §6.2.5.
    """

    def __init__(self, rules: list[Rule], facts: Facts, env: Environment) -> None:
        self._by_id = {rule.frontmatter.id: rule for rule in rules}
        self._facts = facts
        self._env = env

    def render_for_inclusion(self, rule_id: str, context: dict[str, object]) -> str:
        """Render ``rule_id`` for inline placement in a prompt (``""`` if filtered out).

        A sandbox violation raises :class:`TemplateSecurityError` naming the
        rule's source file (specs/prK-lifecycle-hooks.md §P1).
        """
        rule = self._by_id.get(rule_id)
        if rule is None:
            return ""
        if rule.is_templated:
            # Merge stored facts beneath the caller-supplied context so callers
            # can pass {} (the auto-appended-appendix path in
            # prompt_rule_delivery.py does) without hitting StrictUndefined on
            # every templated rule that references a fact. Caller-supplied keys
            # win on collision.
            merged_context = {**self._facts, **context}
            body = render_sandboxed(
                rule.template_body, merged_context, env=self._env, source=template_source(rule)
            )
        else:
            body = rule.body
        return f"### {rule.frontmatter.name}\n\n{body}"


def build_prompt_environment(
    rules: list[Rule], facts: Facts
) -> tuple[RuleRegistryImpl, Environment]:
    """Build the rule registry and the prompt Jinja environment that renders through it.

    The registry renders included rules in an environment *without* ``rule()``
    (rules cannot include rules, SPEC §6.2.5); the returned prompt environment
    registers ``rule()`` against that registry. Both see ``facts`` for the
    ``has_framework``/``has_ml_dep`` helpers.

    Example::

        registry, prompt_env = build_prompt_environment(applicable_rules, facts)
    """
    rule_env = build_environment([], is_prompt_context=False)
    rule_env.globals["_facts"] = dict(facts)
    registry = RuleRegistryImpl(rules, facts, rule_env)
    prompt_env = build_environment([], is_prompt_context=True, rule_registry=registry)
    prompt_env.globals["_facts"] = dict(facts)
    return registry, prompt_env
