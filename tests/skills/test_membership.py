"""Skill membership and gating (specs/prS-skills-context.md 6.4.3, 6.8.2).

A scoped rule naming a skill in ``skill:`` is a member rule of it (ADR 0001).
``compose_skills`` decides which skills a sync writes and attaches each
written skill's active members, rendered, as ``member_references``.
"""

from __future__ import annotations

import dataclasses
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.adapters.agents_md import AgentsMdAdapter
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_ import ContinueAdapter
from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
from coding_agent_playbook.adapters.shared_skills import SharedSkillsAdapter
from coding_agent_playbook.artifacts.member_reference import member_reference_path
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.commands._sync_render import render_rule_body
from coding_agent_playbook.renderer import build_environment
from coding_agent_playbook.skills.membership import (
    MemberRuleDeliverer,
    compose_skills,
    is_rule_skill,
    is_skill_member,
    member_reference,
    member_rules_of,
    undelivered_member_warning,
)
from tests.hook_samples import sample_hook

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.prompt import Prompt


#: Every in-tree adapter class, typed so mypy checks each satisfies the protocol
#: ``undelivered_member_warning`` reads (SK-1); the entry-point test keeps it complete.
_IN_TREE_DELIVERERS: tuple[type[MemberRuleDeliverer], ...] = (
    AgentHarnessAdapter,
    AgentsMdAdapter,
    ClaudeCodeAdapter,
    ContinueAdapter,
    OpenCodeAdapter,
    SharedSkillsAdapter,
)


class _AlwaysRulesOnlyAdapter(Adapter):
    """An adapter that, like agents_md, delivers no member rule; named per instance."""

    delivers_member_rules: ClassVar[bool] = False

    def __init__(self, name: str) -> None:
        self.name = name

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        return []


def _rule(rule_id: str, *, skill: str | None = "python-coding", priority: int = 50) -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id.title(),
        description=f"{rule_id} description.",
        scope="scoped",
        globs=["**/*.py"],
        priority=priority,
        skill=skill,
    )
    body = f"\n# {rule_id}\n"
    return Rule(
        frontmatter, body, body, False, Path(f"rules/{rule_id}.md"), "coding_agent_playbook"
    )


def _skill(skill_id: str, *, playbook: bool = True) -> Skill:
    frontmatter: dict[str, object] = {"id": skill_id, "description": f"{skill_id} skill."}
    if playbook:
        frontmatter["playbook"] = {"use_when": "editing code", "files": "Any file"}
    return Skill(frontmatter, "# Body\n", None, None, "coding_agent_playbook")


def test_is_skill_member_only_for_rules_naming_a_skill() -> None:
    advisory = sample_hook(matcher={"pre_tool_use": {"paths": ["**/*.py"]}}).to_advisory_rule()
    assert advisory is not None
    assert advisory.frontmatter.scope == "scoped"
    assert is_skill_member(advisory) is False
    assert is_skill_member(_rule("python-typing")) is True
    assert is_skill_member(_rule("legacy", skill=None)) is False


def test_member_reference_path_is_references_slash_id_md() -> None:
    assert member_reference_path("pytest") == "references/pytest.md"
    assert member_reference_path("python-typing") == "references/python-typing.md"


def test_compose_skills_passes_plain_skill_through_unchanged() -> None:
    plain = _skill("brainstorming", playbook=False)
    rules = [_rule("python-typing")]
    [composed] = compose_skills([plain], rules, rules)
    assert composed is plain
    assert composed.member_references == ()


def test_compose_skills_drops_skill_whose_members_are_all_inactive() -> None:
    coding, plain = _skill("python-coding"), _skill("brainstorming", playbook=False)
    merged = [_rule("python-typing"), _rule("pytest", skill="python-testing")]
    active = [merged[1]]  # python-typing failed its applies_if
    assert compose_skills([coding, plain], merged, active) == [plain]


def test_compose_skills_drops_declared_skill_without_any_member() -> None:
    rules = [_rule("pytest", skill="python-testing")]
    assert compose_skills([_skill("python-coding")], rules, rules) == []


def test_compose_skills_orders_members_by_priority_then_id() -> None:
    rules = [
        _rule("python-docstrings", priority=56),
        _rule("python-idioms", priority=58),
        _rule("python-context-managers", priority=56),
        _rule("python-dependency-injection", priority=40),
    ]
    [composed] = compose_skills([_skill("python-coding")], rules, rules)
    expected = [
        "python-dependency-injection",
        "python-context-managers",
        "python-docstrings",
        "python-idioms",
    ]
    assert [member.rule_id for member in composed.member_references] == expected
    assert [rule.frontmatter.id for rule in member_rules_of("python-coding", rules)] == expected


def test_compose_skills_never_mutates_its_inputs() -> None:
    skill, rules = _skill("python-coding"), [_rule("python-typing")]
    skills = [skill]
    [composed] = compose_skills(skills, rules, rules)
    assert composed is not skill
    assert skill.member_references == ()
    assert skills == [skill]
    assert [member.rule_id for member in composed.member_references] == ["python-typing"]


def test_compose_skills_uses_the_rendered_body_of_a_templated_member(tmp_path: Path) -> None:
    source = tmp_path / "project-notes.md.j2"
    source.write_text(
        "---\nid: project-notes\nname: Project notes\ndescription: Notes.\n"
        "scope: scoped\nskill: python-coding\n---\n\n# Notes for {{ project_name }}\n",
        encoding="utf-8",
    )
    template = Rule.from_markdown(source, "<repo-local>")
    env = build_environment([])
    rendered = render_rule_body(template, {"project_name": "acme-api"}, env)
    [composed] = compose_skills([_skill("python-coding")], [template], [rendered])
    assert composed.member_references[0].text == "*Rule `project-notes`.*\n\n# Notes for acme-api\n"


def test_member_reference_carries_rule_source_package_and_globs() -> None:
    rule = dataclasses.replace(_rule("pytest", skill="python-testing"), source_package="acme")
    member = member_reference(rule)
    assert (member.rule_id, member.name, member.priority) == ("pytest", "Pytest", 50)
    assert member.description == "pytest description."
    assert member.globs == ("**/*.py",)
    assert member.source_package == "acme"
    assert member.text == "*Rule `pytest`; applies to `**/*.py`.*\n\n# pytest\n"


def test_is_rule_skill_only_for_skills_declaring_the_playbook_block() -> None:
    assert is_rule_skill(_skill("python-coding")) is True
    assert is_rule_skill(_skill("brainstorming", playbook=False)) is False


def _composed(*skill_ids: str) -> list[Skill]:
    """The ``skill_ids`` skills composed with one active member each."""
    rules = [_rule(f"{skill_id}-member", skill=skill_id) for skill_id in skill_ids]
    return compose_skills([_skill(skill_id) for skill_id in skill_ids], rules, rules)


def test_undelivered_member_warning_when_only_agents_md_is_enabled() -> None:
    skills = _composed("python-testing", "python-coding")
    assert undelivered_member_warning([AgentsMdAdapter()], skills) == (
        "warning: no enabled adapter delivers scoped rules (only agents_md is on); skills "
        "python-coding, python-testing reach no assistant: add claude_code, opencode or "
        "shared_skills to adapters_enabled"
    )
    assert undelivered_member_warning([], _composed("ml-data")) == (
        "warning: no enabled adapter delivers scoped rules (no adapter is on); skill ml-data "
        "reaches no assistant: add claude_code, opencode or shared_skills to adapters_enabled"
    )


def test_undelivered_member_warning_lists_several_enabled_adapters_sorted() -> None:
    """Section 6.4.3 gives only the one-adapter text; "only a, b are on" is this PR's reading."""
    enabled = [_AlwaysRulesOnlyAdapter("rules_b"), _AlwaysRulesOnlyAdapter("rules_a")]
    assert undelivered_member_warning(enabled, _composed("ml-data")) == (
        "warning: no enabled adapter delivers scoped rules (only rules_a, rules_b are on); "
        "skill ml-data reaches no assistant: add claude_code, opencode or shared_skills to "
        "adapters_enabled"
    )


def test_undelivered_member_warning_accepts_a_name_to_adapter_mapping_view() -> None:
    """``SyncContext.adapters`` is ``dict[str, Adapter]``: callers pass its ``.values()``."""
    adapters: dict[str, Adapter] = {"agents_md": AgentsMdAdapter()}
    warning = undelivered_member_warning(adapters.values(), _composed("python-coding"))
    assert warning is not None
    assert "(only agents_md is on)" in warning


def test_no_undelivered_member_warning_with_a_skill_adapter() -> None:
    skills = _composed("python-coding")
    assert undelivered_member_warning([AgentsMdAdapter(), SharedSkillsAdapter()], skills) is None
    plain = [_skill("brainstorming", playbook=False)]
    assert undelivered_member_warning([AgentsMdAdapter()], plain) is None


class FakeMemberRuleDeliverer:
    """A plain object, no ``Adapter`` subclass, with the two members the warning reads."""

    delivers_member_rules: ClassVar[bool] = False

    def __init__(self, name: str) -> None:
        self.name = name


def test_undelivered_member_warning_accepts_any_deliverer() -> None:
    """The warning depends on the protocol only, not on ``adapters.base.Adapter`` (SK-1)."""
    enabled = [FakeMemberRuleDeliverer("rules_only")]
    assert undelivered_member_warning(enabled, _composed("ml-data")) == (
        "warning: no enabled adapter delivers scoped rules (only rules_only is on); "
        "skill ml-data reaches no assistant: add claude_code, opencode or shared_skills to "
        "adapters_enabled"
    )


def test_in_tree_deliverers_cover_every_registered_adapter() -> None:
    """The typed tuple above names every built-in adapter, so mypy checks them all."""
    entry_points = metadata.entry_points(group="coding_agent_playbook.adapters")
    registered = {ep.load() for ep in entry_points if ep.value.startswith("coding_agent_playbook.")}
    assert set(_IN_TREE_DELIVERERS) == registered
