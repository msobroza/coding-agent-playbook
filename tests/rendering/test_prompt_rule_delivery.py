"""Tests for how ``includes_rules`` becomes prompt text (specs/prS-skills-context.md §7.4.2).

``prompt_rule_delivery`` turns ``includes_rules`` into prompt text (D15). Seams:
- :func:`skill_pointer_block` — the ``## Before you start`` block of a Claude
  Code or OpenCode command, one step per owning skill.
- :func:`insert_pointer_block` — where that block goes in a body.
- :func:`includes_rules_appendix` — the ``## Reference rules`` appendix of
  Continue prompts, the agent_harness leaf and the eval runner.
- The module boundary: stdlib-only, with ``RuleRegistry`` imported for type
  checking only, so ``rendering.rule_registry`` (which defines it) can import
  this module without a cycle.

Which format gets which is decided by ``rendering.formats.render_for``;
``test_formats.py`` covers that.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.rendering.jinja import build_environment
from coding_agent_playbook.rendering.prompt_rule_delivery import (
    SkillReference,
    SkillReferenceIndex,
    includes_rules_appendix,
    insert_pointer_block,
    skill_pointer_block,
)
from coding_agent_playbook.rendering.rule_registry import RuleRegistryImpl
from tests.fakes import FakeRuleRegistry
from tests.import_probe import new_modules_after


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


def test_includes_rules_appendix_lists_fragments_in_order_each_once() -> None:
    """An id listed twice is inlined once (§7.4.10), at its first position."""
    registry = FakeRuleRegistry({"x": "### X\n\nrule body\n", "y": "### Y\n\nother body\n"})

    appendix = includes_rules_appendix(["y", "x", "y"], registry)

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
    registry = RuleRegistryImpl([version], {"python_version": "3.12"}, build_environment([]))

    appendix = includes_rules_appendix(["ver"], registry)

    assert appendix == "\n## Reference rules\n\n### Version\n\nPython 3.12\n"


def test_includes_rules_appendix_omits_a_rule_the_real_registry_does_not_hold() -> None:
    """The registry holds only the rules whose ``applies_if`` passed: others render ``""``."""
    kept = _rule("kept", "Kept", "kept body\n")
    registry = RuleRegistryImpl([kept], {}, build_environment([]))

    appendix = includes_rules_appendix(["not-applicable", "kept"], registry)

    assert appendix == "\n## Reference rules\n\n### Kept\n\nkept body\n"


# --- skill_pointer_block (D15) ----------------------------------------------


#: The reference probe's membership (D4): typing and error handling in python-coding.
#: Its ``None`` stands for every id the real registry answers ``None`` for: an
#: unknown id, a rule filtered out by ``applies_if`` and an always rule.
_PROBE_INDEX = FakeRuleRegistry(
    references={
        "python-typing": SkillReference("python-coding", "references/python-typing.md"),
        "python-error-handling": SkillReference(
            "python-coding", "references/python-error-handling.md"
        ),
        "pytest": SkillReference("python-testing", "references/pytest.md"),
    }
)


def test_pointer_block_groups_references_by_owning_skill_in_includes_rules_order() -> None:
    block = skill_pointer_block(["python-typing", "pytest", "python-error-handling"], _PROBE_INDEX)

    assert block == (
        "## Before you start\n"
        "\n"
        "1. Load skill `python-coding` and read its references "
        "`references/python-typing.md`, `references/python-error-handling.md`.\n"
        "2. Load skill `python-testing` and read its reference `references/pytest.md`.\n"
        "3. For each file in scope, also load any other listed skill whose description "
        "matches it.\n"
    )


def test_pointer_block_says_reference_for_one_file_and_references_for_several() -> None:
    one = skill_pointer_block(["pytest"], _PROBE_INDEX)
    several = skill_pointer_block(["python-typing", "python-error-handling"], _PROBE_INDEX)

    assert "1. Load skill `python-testing` and read its reference `references/pytest.md`." in one
    assert (
        "1. Load skill `python-coding` and read its references "
        "`references/python-typing.md`, `references/python-error-handling.md`." in several
    )


def test_pointer_block_skips_filtered_unknown_and_always_rules() -> None:
    """The index answers ``None`` for those ids, so they get no line and no gap."""
    block = skill_pointer_block(
        ["filtered-out", "pytest", "no-such-rule", "project-context"], _PROBE_INDEX
    )

    assert block == (
        "## Before you start\n"
        "\n"
        "1. Load skill `python-testing` and read its reference `references/pytest.md`.\n"
        "2. For each file in scope, also load any other listed skill whose description "
        "matches it.\n"
    )


@pytest.mark.parametrize(
    ("includes_rules", "index"),
    [
        (["filtered-out", "project-context"], _PROBE_INDEX),
        ([], _PROBE_INDEX),
        (["pytest"], None),
    ],
    ids=["no-active-reference", "no-ids", "no-index"],
)
def test_pointer_block_is_empty_without_an_active_reference(
    includes_rules: list[str], index: SkillReferenceIndex | None
) -> None:
    assert skill_pointer_block(includes_rules, index) == ""


def test_pointer_block_lists_a_repeated_id_once() -> None:
    block = skill_pointer_block(["pytest", "python-typing", "pytest"], _PROBE_INDEX)

    assert block.count("references/pytest.md") == 1
    assert "1. Load skill `python-testing`" in block
    assert "2. Load skill `python-coding`" in block


# --- insert_pointer_block ---------------------------------------------------

_BLOCK = "## Before you start\n\n1. Load skill `s` and read its reference `references/r.md`.\n"


def test_insert_pointer_block_goes_before_the_first_level_two_heading() -> None:
    body = "# Review\n\nYou are reviewing code.\n\n## Priorities\n\nCorrectness.\n\n## Tone\n"

    assert insert_pointer_block(body, _BLOCK) == (
        "# Review\n\nYou are reviewing code.\n\n"
        f"{_BLOCK}\n"
        "## Priorities\n\nCorrectness.\n\n## Tone\n"
    )


def test_insert_pointer_block_ignores_headings_inside_code_fences() -> None:
    body = "# Title\n\nRole.\n\n```markdown\n## Not a section\n```\n\n## Section\n"

    assert insert_pointer_block(body, _BLOCK) == (
        f"# Title\n\nRole.\n\n```markdown\n## Not a section\n```\n\n{_BLOCK}\n## Section\n"
    )


def test_insert_pointer_block_follows_the_title_when_there_is_no_section() -> None:
    assert insert_pointer_block("# Title\n\nJust prose.\n", _BLOCK) == (
        f"# Title\n\n{_BLOCK}\nJust prose.\n"
    )


def test_insert_pointer_block_keeps_a_blank_line_after_the_block_under_a_bare_title() -> None:
    """Prose right under the title must not become a lazy continuation of the last step."""
    assert insert_pointer_block("# Title\nJust prose.", _BLOCK) == (
        f"# Title\n\n{_BLOCK}\nJust prose."
    )


def test_insert_pointer_block_opens_a_body_without_title_or_section() -> None:
    assert insert_pointer_block("Just prose.\n", _BLOCK) == f"{_BLOCK}\nJust prose.\n"


def test_insert_pointer_block_with_empty_block_returns_the_body_unchanged() -> None:
    body = "# Review\n\nRole.\n\n## Priorities\n"

    assert insert_pointer_block(body, "") is body


# --- module boundary --------------------------------------------------------


def test_prompt_rule_delivery_imports_nothing_from_the_engine_at_runtime() -> None:
    """Stdlib only: ``rendering.rule_registry`` imports it, so a runtime import back is a cycle.

    Only engine modules count: ``SkillReference`` is a dataclass, and
    ``dataclasses`` loads stdlib modules of its own.
    """
    loaded = new_modules_after("import coding_agent_playbook.rendering.prompt_rule_delivery")

    engine = [name for name in loaded if name.split(".")[0] == "coding_agent_playbook"]
    assert engine == [
        "coding_agent_playbook.rendering",
        "coding_agent_playbook.rendering.prompt_rule_delivery",
    ]
