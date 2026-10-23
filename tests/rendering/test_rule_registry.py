"""Tests for the rule registry (specs/prS-skills-context.md §7.4.4).

Covers :class:`RuleRegistryImpl` of ``coding_agent_playbook.rendering.rule_registry``:
the inline-inclusion contract from SPEC §6.2.5 and ``reference_for`` (D15). The
registry a render pass builds from the applies_if-filtered rules, in the
environment its prompts render in, is ``tests/rendering/test_session.py``.

The module boundary (``rule_registry`` takes ``template_source`` from the stdlib
leaf ``artifacts.identity``, never from the sync context) is
``tests/rendering/test_jinja.py::test_rendering_never_imports_the_sync_context``.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest
from jinja2 import UndefinedError

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.rendering.jinja import TemplateSecurityError, build_environment
from coding_agent_playbook.rendering.prompt_rule_delivery import SkillReference
from coding_agent_playbook.rendering.rule_registry import RuleRegistryImpl

if TYPE_CHECKING:
    from pathlib import Path


def _make_rule(rule_id: str, source: str, name: str = "Rule", body: str = "body\n") -> Rule:
    return Rule(
        frontmatter=RuleFrontmatter(
            id=rule_id,
            name=name,
            description="desc",
            scope="always",
            priority=50,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package=source,
    )


def _make_templated_rule(rule_id: str, template_body: str) -> Rule:
    """A rule whose body is rendered from ``template_body`` (its ``body`` is a placeholder)."""
    return dataclasses.replace(
        _make_rule(rule_id, "engine", name=rule_id.title(), body="placeholder"),
        template_body=template_body,
        is_templated=True,
    )


# --- RuleRegistryImpl ------------------------------------------------------


def test_rule_registry_returns_formatted_body_for_known_rule() -> None:
    rule = _make_rule("style", "engine", name="Style", body="Body of style\n")
    env = build_environment([])
    env.globals["_facts"] = {}
    registry = RuleRegistryImpl([rule], {}, env)
    assert registry.render_for_inclusion("style", {}) == "### Style\n\nBody of style\n"


def test_rule_registry_names_the_rule_file_on_a_sandbox_violation(tmp_path: Path) -> None:
    """The ``includes_rules`` render runs inside adapters; a sandbox violation there
    must name the rule's source file, never surface as a bare ``SecurityError``."""
    source = tmp_path / "playbook" / "rules" / "gated.md.j2"
    rule = dataclasses.replace(
        _make_rule("gated", "<repo-local>"),
        template_body='{{ lipsum.__globals__["os"] }}',
        is_templated=True,
        source_path=source,
    )
    env = build_environment([])
    env.globals["_facts"] = {}
    registry = RuleRegistryImpl([rule], {}, env)
    with pytest.raises(TemplateSecurityError) as caught:
        registry.render_for_inclusion("gated", {})
    assert caught.value.source == str(source)


def test_rule_registry_names_the_rule_id_on_a_sandbox_violation_without_a_file() -> None:
    rule = dataclasses.replace(
        _make_rule("gated", "engine"),
        template_body='{{ lipsum.__globals__["os"] }}',
        is_templated=True,
    )
    env = build_environment([])
    env.globals["_facts"] = {}
    registry = RuleRegistryImpl([rule], {}, env)
    with pytest.raises(TemplateSecurityError) as caught:
        registry.render_for_inclusion("gated", {})
    assert caught.value.source == "gated"


def test_rule_registry_returns_empty_string_for_unknown_rule() -> None:
    env = build_environment([])
    env.globals["_facts"] = {}
    registry = RuleRegistryImpl([], {}, env)
    assert registry.render_for_inclusion("missing", {}) == ""


def test_rule_registry_re_renders_templated_body() -> None:
    rule = Rule(
        frontmatter=RuleFrontmatter(
            id="ver",
            name="Version",
            description="d",
            scope="always",
            priority=50,
        ),
        body="placeholder",
        template_body="Python {{ python_version }}\n",
        is_templated=True,
        source_path=None,
        source_package="engine",
    )
    env = build_environment([])
    env.globals["_facts"] = {"python_version": "3.12"}
    registry = RuleRegistryImpl([rule], {}, env)
    assert registry.render_for_inclusion("ver", {"python_version": "3.12"}) == (
        "### Version\n\nPython 3.12\n"
    )


def test_rule_registry_falls_back_to_stored_facts_when_caller_passes_empty_context() -> None:
    """Regression — the ``includes_rules`` appendix path in
    ``prompt_rule_delivery`` calls ``render_for_inclusion(rule_id, {})``. The
    registry must merge its stored facts into the render context so templated
    rule bodies don't fail under StrictUndefined. Caller-supplied keys still win.
    """
    rule = Rule(
        frontmatter=RuleFrontmatter(
            id="ver",
            name="Version",
            description="d",
            scope="always",
            priority=50,
        ),
        body="placeholder",
        template_body="Python {{ python_version }}\n",
        is_templated=True,
        source_path=None,
        source_package="engine",
    )
    env = build_environment([])
    env.globals["_facts"] = {"python_version": "3.12"}
    registry = RuleRegistryImpl([rule], {"python_version": "3.12"}, env)
    # Auto-append path passes {} — must still succeed
    assert registry.render_for_inclusion("ver", {}) == "### Version\n\nPython 3.12\n"
    # Caller override wins on key collision
    assert registry.render_for_inclusion("ver", {"python_version": "3.13"}) == (
        "### Version\n\nPython 3.13\n"
    )


# --- reference_for (D15) -----------------------------------------------------


def _member_rule(rule_id: str, skill: str) -> Rule:
    """A scoped rule owned by ``skill``: a member rule, delivered as one of its ``rules/`` files."""
    rule = _make_rule(rule_id, "engine")
    scoped = dataclasses.replace(rule.frontmatter, scope="scoped", skill=skill)
    return dataclasses.replace(rule, frontmatter=scoped)


def test_rule_registry_keeps_rules_from_including_rules() -> None:
    """Rules cannot include rules (SPEC §6.2.5): ``rule`` is undefined in a rule's own render."""
    inner = _make_rule("inner", "engine", name="Inner")
    outer = _make_templated_rule("outer", '{{ rule("inner") }}')
    registry = RuleRegistryImpl([inner, outer], {}, build_environment([]))

    with pytest.raises(UndefinedError, match="'rule' is undefined"):
        registry.render_for_inclusion("outer", {})


def test_reference_for_names_the_skill_and_reference_of_an_active_scoped_rule() -> None:
    registry = RuleRegistryImpl(
        [_member_rule("pytest", "python-testing")], {}, build_environment([])
    )

    assert registry.reference_for("pytest") == SkillReference("python-testing", "rules/pytest.md")


def test_reference_for_is_none_for_unknown_filtered_and_always_rules() -> None:
    """The registry holds only applicable rules, so a filtered-out rule is simply absent."""
    always = _make_rule("project-context", "engine")
    registry = RuleRegistryImpl([always], {}, build_environment([]))

    assert registry.reference_for("no-such-rule") is None
    assert registry.reference_for("pytest") is None  # filtered out: never registered
    assert registry.reference_for("project-context") is None
