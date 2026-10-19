"""The rule registry: how a prompt reaches the rules it includes (SPEC §6.2.5).

- :class:`RuleRegistry` — the protocol ``rendering.formats`` renders the
  ``## Reference rules`` appendix through.
- :class:`RuleRegistryImpl` — concrete ``RuleRegistry`` and
  ``SkillReferenceIndex`` from ``prompt_rule_delivery``. Built once per render
  pass by ``rendering.session.RenderSession`` (``sync``, ``render``, the eval
  runner) from the applies_if-filtered rule list: it renders an included
  rule's text for the ``## Reference rules`` appendix and names the skill
  reference a command's ``## Before you start`` block points at (D15).
- :func:`skill_reference_of` — the reference that delivers one rule.

Moved out of the sync context module (specs/prS-skills-context.md §7.4.4), then
given ``reference_for`` for D15.
This module imports ``template_source`` from the stdlib leaf ``artifacts.identity``
(H11), which must never import this module back (a cycle), nor re-export its names
(a shim): importers take them from here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from coding_agent_playbook.artifacts.identity import template_source
from coding_agent_playbook.artifacts.member_reference import member_reference_path
from coding_agent_playbook.rendering.jinja import render_sandboxed
from coding_agent_playbook.rendering.prompt_rule_delivery import SkillReference

if TYPE_CHECKING:
    from jinja2 import Environment

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.detector.facts import Facts


class RuleRegistry(Protocol):
    """How the ``## Reference rules`` appendix renders an included rule's text.

    ``rule_registry.RuleRegistryImpl`` implements it; this protocol is the
    contract the renderer depends on. Tests can pass an in-memory
    implementation; production passes the merged-overlay registry.
    """

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        """Return the rendered body of ``rule_id`` for inline placement in a
        prompt, with a ``### {rule.name}`` header prepended. Returns ``""``
        if the rule's ``applies_if`` evaluates to false for the current facts.
        """
        ...


class RuleRegistryImpl:
    """Concrete :class:`RuleRegistry` used by sync, render and the eval runner.

    Built once per render session from the merged + applies_if-filtered rule
    list. The ``render_for_inclusion`` method returns the inline body for a rule
    (with ``### {rule.name}`` header) or ``""`` when the rule is filtered out —
    the silent-omission contract from SPEC §6.2.5.
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
