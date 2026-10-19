"""Tests for the orchestrator module (PR 10).

Covers the load-bearing pieces:
- :class:`OverlayResolver` — three-layer merge by ID with collision tracking.
- :func:`template_source` — how an artifact's template is named in error messages.
- :func:`discover_adapters` + :class:`SyncContext.from_repo` smoke test.

The rule registry (``RuleRegistryImpl``) is tested in ``test_rule_registry.py``.
"""

from __future__ import annotations

import dataclasses

import pytest

from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.config.model import Config, ProjectMeta, StorageConfig
from coding_agent_playbook.orchestrator import (
    OverlayResolver,
    SyncContext,
    artifact_id_of,
    discover_adapters,
    template_source,
)
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)


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


# --- template_source -------------------------------------------------------


def test_template_source_names_the_source_path_else_the_artifact_id(tmp_path):
    source = tmp_path / "playbook" / "rules" / "gated.md.j2"
    rule = dataclasses.replace(_make_rule("gated", "<repo-local>"), source_path=source)

    assert template_source(rule) == str(source)
    assert template_source(dataclasses.replace(rule, source_path=None)) == "gated"
    assert template_source(_make_prompt("review", "engine")) == "review"


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


def test_discover_adapters_always_includes_agents_md():
    """``agents_md`` must always be present even if not in adapters_enabled."""
    config = _make_config(adapters=["continue"])
    adapters = discover_adapters(config)
    assert "agents_md" in adapters
    assert "continue" in adapters


def test_discover_adapters_respects_enabled_list():
    config = _make_config(adapters=["claude_code"])
    adapters = discover_adapters(config)
    assert "claude_code" in adapters
    assert "continue" not in adapters
    assert "opencode" not in adapters
    assert "agents_md" in adapters  # always


def test_sync_context_from_repo_loads_synthetic_repo(tmp_path, make_synthetic_repo):
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


def test_sync_context_from_repo_missing_config_raises(tmp_path):
    """Without ``.coding-agent-playbook.toml``, FileSystemStateSource raises
    ``FileNotFoundError`` and the orchestrator does not swallow it."""
    with pytest.raises(FileNotFoundError):
        SyncContext.from_repo(tmp_path)


def _ids(artifacts: list[Rule] | list[Prompt] | list[Skill]) -> list[str]:
    return [artifact_id_of(artifact) for artifact in artifacts]


def test_from_config_resolves_like_from_repo(tmp_path, make_synthetic_repo):
    """``from_repo`` is ``load_config`` + ``from_config``: the config-less validate
    context (prK §P P8) reuses the same detect → walk → resolve step."""
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("repo-rule", "Body content\n")],
        prompts=[("repo-prompt", {"slash": "repo-prompt"})],
    )
    by_repo = SyncContext.from_repo(repo)

    by_config = SyncContext.from_config(repo, by_repo.config)

    assert by_config.config is by_repo.config
    assert by_config.facts == by_repo.facts
    assert _ids(by_config.rules_resolved) == _ids(by_repo.rules_resolved)
    assert _ids(by_config.prompts_resolved) == _ids(by_repo.prompts_resolved)
    assert _ids(by_config.skills_resolved) == _ids(by_repo.skills_resolved)
    assert by_config.adapters.keys() == by_repo.adapters.keys()
    assert by_config.overlay_collisions == by_repo.overlay_collisions


def test_from_config_walks_the_injected_artifact_source(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path)
    config = SyncContext.from_repo(repo).config
    rules_dir = tmp_path / "src" / "acme_overlay" / "resources" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "acme.md").write_text(
        "---\nid: acme\nname: Acme\ndescription: d\nscope: always\n---\nBody\n",
        encoding="utf-8",
    )
    source = FileSystemArtifactSource(repo_root=repo, extra_resource_roots=[rules_dir.parent])

    ctx = SyncContext.from_config(repo, config, artifact_source=source)

    assert ctx.artifact_source is source
    assert "acme" in _ids(ctx.rules_resolved)
