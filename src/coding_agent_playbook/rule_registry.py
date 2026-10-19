"""The rule registry: how a prompt reaches the rules it includes (SPEC §6.2.5).

- :class:`RuleRegistryImpl` — concrete ``RuleRegistry`` from the renderer
  Protocol and ``SkillReferenceIndex`` from ``prompt_rule_delivery``. Built
  once per sync from the applies_if-filtered rule list: it renders an included
  rule's text for the ``## Reference rules`` appendix and names the skill
  reference a command's ``## Before you start`` block points at (D15).
- :func:`skill_reference_of` — the reference that delivers one rule.
- :func:`build_prompt_environment` — the registry plus the Jinja environment
  every prompt render (``sync``, ``render``, the eval runner) builds the same way.

Moved out of ``orchestrator`` (specs/prS-skills-context.md §7.4.4), then given
``reference_for`` for D15.
This module imports ``template_source`` from the orchestrator, so the
orchestrator must never import this module back (a cycle), nor re-export its
names (a shim): importers take them from here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook._member_reference import member_reference_path
from coding_agent_playbook.orchestrator import template_source
from coding_agent_playbook.prompt_rule_delivery import SkillReference
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

    def reference_for(self, rule_id: str) -> SkillReference | None:
        """The skill reference that holds ``rule_id`` in this sync, or ``None`` (D15).

        ``None`` when the rule is unknown, filtered out by ``applies_if`` (the
        registry holds only applicable rules), or ``scope: always`` (it is
        already in always-loaded context).

        Example: ``registry.reference_for("pytest")`` ->
        ``SkillReference("python-testing", "references/pytest.md")``.
        """
        rule = self._by_id.get(rule_id)
        return None if rule is None else skill_reference_of(rule)


def skill_reference_of(rule: Rule) -> SkillReference | None:
    """Where ``rule`` is delivered as a skill reference, or ``None`` when it is not one.

    Only a scoped rule that names its skill in ``skill:`` is a member rule; an
    always rule is in always-loaded context instead. The one decision
    :meth:`RuleRegistryImpl.reference_for` and ``playbook render --show-rules`` share.

    Example: ``skill_reference_of(pytest_rule)`` ->
    ``SkillReference("python-testing", "references/pytest.md")``.
    """
    frontmatter = rule.frontmatter
    if frontmatter.scope != "scoped" or frontmatter.skill is None:
        return None
    return SkillReference(frontmatter.skill, member_reference_path(frontmatter.id))


def build_prompt_environment(
    rules: list[Rule], facts: Facts
) -> tuple[RuleRegistryImpl, Environment]:
    """Build the rule registry and the Jinja environment prompts render in.

    One base environment serves both: there is no ``rule()`` helper (D15), so
    a prompt and an included rule render alike, and neither can include a
    rule. It sees ``facts`` for the ``has_framework``/``has_ml_dep`` helpers.

    Example::

        registry, prompt_env = build_prompt_environment(applicable_rules, facts)
    """
    env = build_environment([])
    env.globals["_facts"] = dict(facts)
    return RuleRegistryImpl(rules, facts, env), env
