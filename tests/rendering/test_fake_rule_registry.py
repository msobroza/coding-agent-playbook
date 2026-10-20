"""Tests for ``tests.fakes.FakeRuleRegistry``, the one in-memory rule registry (RS-3).

It stands in for ``RuleRegistryImpl`` in the adapter, agent_harness and
rendering tests, so it must answer both faces the way the real registry does
for an id it does not hold: ``""`` text and no skill reference.
"""

from __future__ import annotations

from coding_agent_playbook.rendering.prompt_rule_delivery import (
    SkillReference,
    includes_rules_appendix,
    skill_pointer_block,
)
from tests.fakes import FakeRuleRegistry


def test_fake_rule_registry_renders_its_fragment_and_empty_text_for_other_ids() -> None:
    registry = FakeRuleRegistry({"x": "### X\n\nbody\n"})

    assert registry.render_for_inclusion("x", {}) == "### X\n\nbody\n"
    assert registry.render_for_inclusion("missing", {"k": "v"}) == ""


def test_fake_rule_registry_names_its_reference_and_none_for_other_ids() -> None:
    reference = SkillReference("python-coding", "references/x.md")
    registry = FakeRuleRegistry(references={"x": reference})

    assert registry.reference_for("x") == reference
    assert registry.reference_for("missing") is None


def test_fake_rule_registry_with_no_arguments_holds_no_rule() -> None:
    registry = FakeRuleRegistry()

    assert registry.render_for_inclusion("x", {}) == ""
    assert registry.reference_for("x") is None


def test_fake_rule_registry_serves_both_prompt_rule_deliveries() -> None:
    registry = FakeRuleRegistry(
        {"x": "### X\n\nbody\n"}, {"x": SkillReference("s", "references/x.md")}
    )

    assert includes_rules_appendix(["x"], registry) == "\n## Reference rules\n\n### X\n\nbody\n"
    assert "Load skill `s` and read its reference `references/x.md`." in skill_pointer_block(
        ["x"], registry
    )
