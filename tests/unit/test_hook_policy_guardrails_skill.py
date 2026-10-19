"""The ``playbook-guardrails`` skill: split out of dispatch, then composed from the on hooks (D6).

Sync takes the authored skill out of the skills every adapter receives
(``split_guardrails_skill``) and composes it with one section per on hook that
has guardrail text (``compose_guardrails_skill``); only the adapters whose
``writes_guardrails_skill`` says so receive the result
(specs/prS-skills-context.md 8.4.3).
"""

from __future__ import annotations

from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.hook_policy.guardrails_skill import (
    GUARDRAILS_SKILL_ID,
    compose_guardrails_skill,
    has_guardrail_text,
    split_guardrails_skill,
)
from tests.hook_samples import resolved_hook

_INTRO = "\n# Playbook guardrails\n\nEach section is one guardrail.\n"
_BOTH = ("claude_code", "opencode")


def _skill(skill_id: str, body: str = "Body.\n") -> Skill:
    frontmatter = {"id": skill_id, "name": skill_id, "description": f"About {skill_id}."}
    return Skill(frontmatter, body, None, None, "coding_agent_playbook")


def test_split_removes_the_guardrails_skill_from_dispatch() -> None:
    coding, authored, testing = _skill("python-coding"), _skill(GUARDRAILS_SKILL_ID), _skill("t")

    regular, found = split_guardrails_skill([coding, authored, testing])

    assert regular == [coding, testing]
    assert found is authored


def test_split_without_the_guardrails_skill_keeps_every_skill() -> None:
    skills = [_skill("python-coding"), _skill("python-testing")]

    assert split_guardrails_skill(skills) == (skills, None)


_CLAUDE_ONLY = (
    "*Enforced by lifecycle hooks on: Claude Code. "
    "Everywhere else this is guidance: apply it yourself.*\n"
)
_CLAUDE_AND_OPENCODE = (
    "*Enforced by lifecycle hooks on: Claude Code, OpenCode. "
    "Everywhere else this is guidance: apply it yourself.*\n"
)


def test_compose_appends_sections_sorted_by_hook_id_with_enforcement_lines() -> None:
    authored = _skill(GUARDRAILS_SKILL_ID, _INTRO)
    hooks = [
        resolved_hook("guard-y", name="Guard Y", body="Ask first.\n", supports=_BOTH),
        resolved_hook("guard-a", name="Guard A", body="\nAdvice A.\n\n"),
    ]

    composed = compose_guardrails_skill(authored, hooks)

    assert composed is not None
    assert composed.body == (
        "\n# Playbook guardrails\n\nEach section is one guardrail.\n\n"
        f"## Guard A (`guard-a`)\n\nAdvice A.\n\n{_CLAUDE_ONLY}\n"
        f"## Guard Y (`guard-y`)\n\nAsk first.\n\n{_CLAUDE_AND_OPENCODE}"
    )
    assert composed.frontmatter == authored.frontmatter
    assert composed.source_package == authored.source_package
    assert authored.body == _INTRO, "the authored skill is never mutated"


def test_compose_skips_a_hook_without_an_advisory() -> None:
    hooks = [resolved_hook("guard-a", name="Guard A"), resolved_hook("quiet", body="")]

    composed = compose_guardrails_skill(_skill(GUARDRAILS_SKILL_ID, _INTRO), hooks)

    assert composed is not None
    assert "(`guard-a`)" in composed.body
    assert "quiet" not in composed.body


def test_compose_is_none_without_an_advisory() -> None:
    authored = _skill(GUARDRAILS_SKILL_ID, _INTRO)

    assert compose_guardrails_skill(authored, []) is None
    assert compose_guardrails_skill(authored, [resolved_hook("quiet", body="")]) is None


def test_compose_is_none_without_the_authored_skill() -> None:
    assert compose_guardrails_skill(None, [resolved_hook("guard-a")]) is None


def test_compose_without_an_authored_body_holds_only_the_sections() -> None:
    composed = compose_guardrails_skill(_skill(GUARDRAILS_SKILL_ID, ""), [resolved_hook()])

    assert composed is not None
    assert composed.body == f"## Guard X (`guard-x`)\n\nAdvice.\n\n{_CLAUDE_ONLY}"


def test_has_guardrail_text_needs_one_hook_with_an_advisory() -> None:
    quiet = resolved_hook("quiet", body="")

    assert has_guardrail_text([quiet, resolved_hook()]) is True
    assert has_guardrail_text([quiet]) is False
    assert has_guardrail_text([]) is False
