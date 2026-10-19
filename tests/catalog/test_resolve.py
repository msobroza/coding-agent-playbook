"""Tests for the overlay merge (PR 10): :class:`OverlayResolver` merges three layers by ID
and tracks collisions.

Its hook merge is tested in ``test_resolve_hooks.py``; the ``SyncContext`` that runs
it in ``tests/validation/test_context.py``.
"""

from __future__ import annotations

from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.catalog.resolve import OverlayResolver


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


def _make_prompt(prompt_id: str, source: str) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name="Prompt",
            description="desc",
            slash=prompt_id,
        ),
        body="body\n",
        template_body="body\n",
        is_templated=False,
        source_path=None,
        source_package=source,
    )


def _make_skill(skill_id: str, source: str) -> Skill:
    return Skill(
        frontmatter={"id": skill_id, "name": "Skill"},
        body="body\n",
        scripts_dir=None,
        references_dir=None,
        source_package=source,
    )


# --- OverlayResolver -------------------------------------------------------


def test_overlay_resolver_engine_only_passes_through():
    resolver = OverlayResolver()
    engine = [_make_rule("a", "engine"), _make_rule("b", "engine")]
    result = resolver.resolve_rules(engine, [], [])
    assert [rule.frontmatter.id for rule in result] == ["a", "b"]
    assert resolver.collisions == []


def test_overlay_resolver_overlay_overrides_engine():
    resolver = OverlayResolver()
    engine = [_make_rule("a", "engine", name="Engine A")]
    overlay = [_make_rule("a", "overlay-bnp", name="BNP A")]
    result = resolver.resolve_rules(engine, [overlay], [])
    assert len(result) == 1
    assert result[0].frontmatter.name == "BNP A"
    assert result[0].source_package == "overlay-bnp"
    assert len(resolver.collisions) == 1
    collision = resolver.collisions[0]
    assert collision.kind == "rule"
    assert collision.artifact_id == "a"
    assert collision.winner == "overlay-bnp"
    assert collision.losers == ("engine",)


def test_overlay_resolver_repo_local_overrides_overlay_and_engine():
    resolver = OverlayResolver()
    engine = [_make_rule("a", "engine")]
    overlay = [_make_rule("a", "overlay-bnp")]
    repo_local = [_make_rule("a", "<repo-local>")]
    result = resolver.resolve_rules(engine, [overlay], repo_local)
    assert len(result) == 1
    assert result[0].source_package == "<repo-local>"
    # Two losers recorded: engine first, overlay second.
    collision = resolver.collisions[0]
    assert collision.losers == ("engine", "overlay-bnp")
    assert collision.winner == "<repo-local>"


def test_overlay_resolver_handles_prompts_and_skills():
    resolver = OverlayResolver()
    engine_prompts = [_make_prompt("p", "engine")]
    overlay_prompts = [_make_prompt("p", "overlay")]
    result = resolver.resolve_prompts(engine_prompts, [overlay_prompts], [])
    assert result[0].source_package == "overlay"
    skill_resolver = OverlayResolver()
    engine_skills = [_make_skill("s", "engine")]
    repo_skills = [_make_skill("s", "<repo-local>")]
    skill_result = skill_resolver.resolve_skills(engine_skills, [], repo_skills)
    assert skill_result[0].source_package == "<repo-local>"
