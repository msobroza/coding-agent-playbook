"""The ``[IMPACT]`` tag in a member rule's title (prU D32, D17, D46(8)).

The tag in ``# Title [IMPACT]`` comes from the rule's section, never from the
source: ``skills.sections.section_impacts`` maps each member rule to its
section's impact once per render pass, and ``RenderSession.render_rule``
appends the tag to the first ATX ``# `` heading outside code fences, after Jinja.
Prompt and eval appendices render through the registry and stay untagged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.rendering.prompt_rule_delivery import includes_rules_appendix
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext
from coding_agent_playbook.skills.sections import Impact, section_impacts, with_impact_tag

_MOCKING = {
    "id": "mocking",
    "title": "Mocking",
    "impact": "HIGH",
    "summary": "Fakes at the boundary.",
    "open_when": "Replacing a collaborator in a test.",
}
_FIXTURES = {
    "id": "fixtures",
    "title": "Fixtures",
    "impact": "LOW",
    "summary": "Shared setup.",
    "open_when": "Adding or sharing test setup.",
}
_CONTEXT = TemplateContext(facts={"frameworks": {}}, project_name="demo", engine_version="1.0")


def _skill(skill_id: str, block: dict[str, Any]) -> Skill:
    return Skill({"id": skill_id, "playbook": block}, "# Body\n", None, None, "pkg")


_TESTING = _skill("python-testing", {"use_when": "testing", "sections": [_MOCKING, _FIXTURES]})
_CODING = _skill("python-coding", {"use_when": "coding"})


def _rule(
    rule_id: str,
    body: str = "# Monkeypatch\n\nPrefer monkeypatch.setenv.\n",
    *,
    skill: str | None = "python-testing",
    section: str | None = "mocking",
) -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id,
        description="d",
        scope="scoped" if skill else "always",
        globs=["**/*.py"] if skill else [],
        skill=skill,
        section=section,
    )
    return Rule(frontmatter, body, body, "{{" in body, None, "pkg")


# --------------------------------------------------------------------------- #
# section_impacts: rule id -> its section's impact
# --------------------------------------------------------------------------- #


def test_section_impacts_maps_each_member_to_its_sections_impact() -> None:
    rules = [_rule("mock-monkeypatch"), _rule("fixture-scope", section="fixtures")]

    assert section_impacts([_TESTING], rules) == {
        "mock-monkeypatch": Impact.HIGH,
        "fixture-scope": Impact.LOW,
    }


def test_section_impacts_skips_always_rules_and_sectionless_skills() -> None:
    rules = [
        _rule("always-rule", skill=None, section=None),
        _rule("typing", skill="python-coding", section=None),
        _rule("unknown-section", section="nowhere"),
        _rule("unknown-skill", skill="missing", section="mocking"),
    ]

    assert section_impacts([_TESTING, _CODING], rules) == {}


# --------------------------------------------------------------------------- #
# with_impact_tag: the first ATX heading outside fences
# --------------------------------------------------------------------------- #


def test_tag_goes_on_the_first_heading_only() -> None:
    body = "# Monkeypatch\n\nText.\n\n# Second\n## Sub\n"

    assert with_impact_tag(body, Impact.HIGH) == (
        "# Monkeypatch [HIGH]\n\nText.\n\n# Second\n## Sub\n"
    )


def test_tag_never_lands_inside_a_code_fence() -> None:
    body = "Intro.\n\n```python\n# not a title\n```\n\n~~~\n# nor this\n~~~\n# Title\n"

    assert with_impact_tag(body, Impact.CRITICAL) == (
        "Intro.\n\n```python\n# not a title\n```\n\n~~~\n# nor this\n~~~\n# Title [CRITICAL]\n"
    )


def test_a_second_level_heading_is_not_the_title() -> None:
    assert with_impact_tag("## Notes\n#hashtag\n", Impact.LOW) == "## Notes\n#hashtag\n"


def test_tagging_is_idempotent() -> None:
    once = with_impact_tag("# Title\n", Impact.MEDIUM)

    assert once == "# Title [MEDIUM]\n"
    assert with_impact_tag(once, Impact.MEDIUM) == once


def test_a_body_without_a_title_is_unchanged() -> None:
    assert with_impact_tag("Plain text.\n", Impact.HIGH) == "Plain text.\n"


# --------------------------------------------------------------------------- #
# RenderSession: the impacts mapping, applied after Jinja
# --------------------------------------------------------------------------- #


def _session(rules: list[Rule], impacts: dict[str, Impact]) -> RenderSession:
    return RenderSession.open(rules, _CONTEXT, repo_root=Path("."), impacts=impacts)


def test_render_rule_tags_a_listed_member_after_jinja() -> None:
    templated = _rule("mock-monkeypatch", "# Mocks in {{ project_name }}\n\nBody.\n")
    plain = _rule("fixture-scope", section="fixtures")
    impacts = section_impacts([_TESTING], [templated, plain])
    session = _session([templated, plain], impacts)

    rendered = {rule.frontmatter.id: rule.body for rule in session.render_rules()}

    assert rendered["mock-monkeypatch"].splitlines()[0] == "# Mocks in demo [HIGH]"
    assert rendered["fixture-scope"].splitlines()[0] == "# Monkeypatch [LOW]"


def test_rules_absent_from_impacts_render_unchanged() -> None:
    always = _rule("always-rule", "# Always\n", skill=None, section=None)
    sectionless = _rule("typing", "# Typing\n", skill="python-coding", section=None)
    session = _session([always, sectionless], section_impacts([_CODING], [always, sectionless]))

    assert [rule.body for rule in session.render_rules()] == ["# Always\n", "# Typing\n"]


def test_without_impacts_nothing_is_tagged() -> None:
    session = RenderSession.open([_rule("mock-monkeypatch")], _CONTEXT, repo_root=Path("."))

    assert session.render_rules()[0].body.startswith("# Monkeypatch\n")


def test_the_reference_rules_appendix_stays_untagged() -> None:
    """D46(8): prompt and eval appendices carry no [IMPACT] tag."""
    rule = _rule("mock-monkeypatch")
    session = _session([rule], section_impacts([_TESTING], [rule]))
    session.render_rules()

    appendix = includes_rules_appendix(["mock-monkeypatch"], session.registry)

    assert "Monkeypatch" in appendix
    assert "[HIGH]" not in appendix


@pytest.mark.parametrize("impact", list(Impact))
def test_every_impact_renders_its_own_name(impact: Impact) -> None:
    assert with_impact_tag("# T\n", impact) == f"# T [{impact.value}]\n"
