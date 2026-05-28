"""Tests for the orchestrator module (PR 10).

Covers the three load-bearing pieces:
- :class:`OverlayResolver` — three-layer merge by ID with collision tracking.
- :class:`RuleRegistryImpl` — inline-inclusion contract from SPEC §6.2.5.
- :func:`discover_adapters` + :class:`SyncContext.from_repo` smoke test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config import Config, ProjectMeta, StorageConfig
from coding_agent_playbook.orchestrator import (
    OverlayResolver,
    RuleRegistryImpl,
    SyncContext,
    discover_adapters,
)
from coding_agent_playbook.renderer import build_environment
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)

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


def test_overlay_resolver_engine_only_passes_through() -> None:
    resolver = OverlayResolver()
    engine = [_make_rule("a", "engine"), _make_rule("b", "engine")]
    result = resolver.resolve_rules(engine, [], [])
    assert [rule.frontmatter.id for rule in result] == ["a", "b"]
    assert resolver.collisions == []


def test_overlay_resolver_overlay_overrides_engine() -> None:
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


def test_overlay_resolver_repo_local_overrides_overlay_and_engine() -> None:
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


def test_overlay_resolver_handles_prompts_and_skills() -> None:
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


# --- RuleRegistryImpl ------------------------------------------------------


def test_rule_registry_returns_formatted_body_for_known_rule(tmp_path: Path) -> None:
    rule = _make_rule("style", "engine", name="Style", body="Body of style\n")
    env = build_environment([])
    env.globals["_facts"] = {}
    registry = RuleRegistryImpl([rule], {}, env)
    assert registry.render_for_inclusion("style", {}) == "### Style\n\nBody of style\n"


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


# --- discover_adapters + SyncContext.from_repo -----------------------------


def _make_config(adapters: list[str], overlays: list[str] | None = None) -> Config:
    return Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version="0.1.0a0",
        overlays_enabled=overlays or [],
        adapters_enabled=adapters,
        storage=StorageConfig(),
    )


def test_discover_adapters_always_includes_agents_md() -> None:
    """``agents_md`` must always be present even if not in adapters_enabled."""
    config = _make_config(adapters=["continue"])
    adapters = discover_adapters(config)
    assert "agents_md" in adapters
    assert "continue" in adapters


def test_discover_adapters_respects_enabled_list() -> None:
    config = _make_config(adapters=["claude_code"])
    adapters = discover_adapters(config)
    assert "claude_code" in adapters
    assert "continue" not in adapters
    assert "opencode" not in adapters
    assert "agents_md" in adapters  # always


def test_sync_context_from_repo_loads_synthetic_repo(
    tmp_path: Path, make_synthetic_repo
) -> None:
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("repo-rule", "Body content\n")],
    )
    ctx = SyncContext.from_repo(repo)
    assert ctx.repo_root == repo
    assert ctx.config.project.name == "synthetic"
    assert any(rule.frontmatter.id == "repo-rule" for rule in ctx.rules_resolved)
    # adapters discovered + agents_md always present
    assert "agents_md" in ctx.adapters
    # facts include something — at minimum project_kind
    assert "project_kind" in ctx.facts


def test_sync_context_from_repo_missing_config_raises(tmp_path: Path) -> None:
    """Without ``.coding-agent-playbook.toml``, FileSystemStateSource raises
    ``FileNotFoundError`` and the orchestrator does not swallow it."""
    with pytest.raises(FileNotFoundError):
        SyncContext.from_repo(tmp_path)
