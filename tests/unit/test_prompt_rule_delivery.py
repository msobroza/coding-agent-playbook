"""Tests for how ``includes_rules`` becomes prompt text (specs/prS-skills-context.md §7.4.2).

``prompt_rule_delivery`` builds the ``## Reference rules`` appendix that
``renderer.render_for`` adds to every prompt format (Continue, Claude Code and
OpenCode commands, and the agent_harness prompt leaf through it). Two seams:
- :func:`includes_rules_appendix` — one ``### <name>`` section per included rule.
- The module boundary: stdlib-only, with ``RuleRegistry`` imported for type
  checking only, so ``renderer`` can import it without a cycle.

Whether a prompt gets the appendix at all (its template placed no ``rule()``
call) is decided by ``renderer.render_for``; ``test_renderer.py`` covers that.
"""

from __future__ import annotations

from typing import Any

from coding_agent_playbook.prompt_rule_delivery import includes_rules_appendix
from coding_agent_playbook.rule_registry import build_prompt_environment
from coding_agent_playbook.types import Rule, RuleFrontmatter
from tests.import_probe import new_modules_after


class FakeRuleRegistry:
    """In-memory ``RuleRegistry``: a fixed fragment per rule id, ``""`` for any other id."""

    def __init__(self, fragments: dict[str, str]) -> None:
        self._fragments = fragments

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        return self._fragments.get(rule_id, "")


def _rule(rule_id: str, name: str, text: str, *, templated: bool = False) -> Rule:
    """A rule whose text is ``text``: rendered through Jinja when ``templated``, else verbatim."""
    return Rule(
        frontmatter=RuleFrontmatter(
            id=rule_id, name=name, description="d", scope="always", priority=50
        ),
        body=text,
        template_body=text,
        is_templated=templated,
        source_path=None,
        source_package="engine",
    )


# --- includes_rules_appendix -----------------------------------------------


def test_includes_rules_appendix_lists_the_fragment_of_one_rule() -> None:
    registry = FakeRuleRegistry({"x": "### X\n\nrule body\n"})

    appendix = includes_rules_appendix(["x"], registry)

    assert appendix == "\n## Reference rules\n\n### X\n\nrule body\n"


def test_includes_rules_appendix_lists_fragments_in_includes_rules_order() -> None:
    registry = FakeRuleRegistry({"x": "### X\n\nrule body\n", "y": "### Y\n\nother body\n"})

    appendix = includes_rules_appendix(["y", "x"], registry)

    assert appendix == "\n## Reference rules\n\n### Y\n\nother body\n\n### X\n\nrule body\n"


def test_includes_rules_appendix_joins_fragments_with_exactly_one_blank_line() -> None:
    registry = FakeRuleRegistry({"x": "### X\n\nrule body\n\n\n", "y": "### Y\n\nother body"})

    appendix = includes_rules_appendix(["x", "y"], registry)

    assert appendix == "\n## Reference rules\n\n### X\n\nrule body\n\n### Y\n\nother body\n"


def test_includes_rules_appendix_skips_a_rule_the_registry_renders_empty() -> None:
    """A rule filtered out by ``applies_if``, or unknown, renders ``""``: no section, no gap."""
    registry = FakeRuleRegistry({"x": "### X\n\nrule body\n", "y": "### Y\n\nother body\n"})

    appendix = includes_rules_appendix(["x", "filtered-out", "y"], registry)

    assert appendix == "\n## Reference rules\n\n### X\n\nrule body\n\n### Y\n\nother body\n"


def test_includes_rules_appendix_is_empty_when_every_fragment_is_empty() -> None:
    registry = FakeRuleRegistry({})

    assert includes_rules_appendix(["foo", "bar"], registry) == ""


def test_includes_rules_appendix_is_empty_without_rule_ids() -> None:
    registry = FakeRuleRegistry({"x": "### X\n\nrule body\n"})

    assert includes_rules_appendix([], registry) == ""


def test_includes_rules_appendix_is_empty_without_a_registry() -> None:
    assert includes_rules_appendix(["x"], None) == ""


def test_includes_rules_appendix_renders_templated_rules_with_the_registry_facts() -> None:
    """The appendix asks with an empty context; the registry supplies the detector facts."""
    version = _rule("ver", "Version", "Python {{ python_version }}\n", templated=True)
    registry, _ = build_prompt_environment([version], {"python_version": "3.12"})

    appendix = includes_rules_appendix(["ver"], registry)

    assert appendix == "\n## Reference rules\n\n### Version\n\nPython 3.12\n"


def test_includes_rules_appendix_omits_a_rule_the_real_registry_does_not_hold() -> None:
    """The registry holds only the rules whose ``applies_if`` passed: others render ``""``."""
    kept = _rule("kept", "Kept", "kept body\n")
    registry, _ = build_prompt_environment([kept], {})

    appendix = includes_rules_appendix(["not-applicable", "kept"], registry)

    assert appendix == "\n## Reference rules\n\n### Kept\n\nkept body\n"


# --- module boundary --------------------------------------------------------


def test_prompt_rule_delivery_imports_nothing_from_the_engine_at_runtime() -> None:
    """Stdlib only: ``renderer`` imports it, so any runtime import back would be a cycle."""
    loaded = new_modules_after("import coding_agent_playbook.prompt_rule_delivery")

    assert loaded == ["coding_agent_playbook.prompt_rule_delivery"]
