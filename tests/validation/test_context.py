"""Tests for ``SyncContext`` (PR 10; specs/prK-lifecycle-hooks.md §A.5, §A.6, §P P8c).

:meth:`SyncContext.from_repo` loads the config, detects facts and resolves the
overlays; :meth:`SyncContext.from_config` is the same minus the config load. Its
hook step splits a source's flat hook list into real layers and either fails
loudly on a malformed hook or, with ``tolerate_load_errors``, records it. It also
carries the committed ``[hooks]`` / ``[guardrails]`` tables raw (§B.1). The
config-less context of ``playbook validate`` is tested in ``tests/cli/test_validate.py``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.artifacts.identity import artifact_id_of
from coding_agent_playbook.artifacts.rule import RuleLoadError
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.resolve import Collision
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.config.tables.hooks import PolicyTables
from coding_agent_playbook.validation.context import SyncContext

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill


def _local(hooks: Sequence[Hook]) -> list[Hook]:
    """The repo-local hooks; the engine's own pack (Track K5 on) resolves alongside them."""
    return [hook for hook in hooks if hook.source_package == "<repo-local>"]


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
    ``FileNotFoundError`` and ``SyncContext`` does not swallow it."""
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


def _package_hooks(name: str) -> Path:
    module = importlib.import_module(name)
    assert module.__file__ is not None
    return Path(module.__file__).parent / "resources" / "hooks"


def test_from_repo_resolves_repo_local_hook(tmp_path, make_synthetic_repo, make_hook):
    repo = make_synthetic_repo(tmp_path)
    make_hook(repo / "playbook" / "hooks", "guard-x")

    ctx = SyncContext.from_repo(repo)

    [local] = _local(ctx.hooks_resolved)
    assert local.frontmatter.id == "guard-x"
    assert ctx.hook_definitions["guard-x"] == (local,)
    assert {h.source_package for h in ctx.hooks_resolved} == {ENGINE_PACKAGE, "<repo-local>"}
    assert ctx.hook_load_errors == []
    assert ctx.hook_violations == []


def test_from_repo_without_hooks_has_only_the_engine_pack(tmp_path, make_synthetic_repo):
    ctx = SyncContext.from_repo(make_synthetic_repo(tmp_path))

    assert _local(ctx.hooks_resolved) == []
    assert {hook.source_package for hook in ctx.hooks_resolved} <= {ENGINE_PACKAGE}
    assert set(ctx.hook_definitions) == {hook.frontmatter.id for hook in ctx.hooks_resolved}
    assert (ctx.hook_load_errors, ctx.hook_violations) == ([], [])


def test_from_repo_tolerate_load_errors_records_load_errors(
    tmp_path, make_synthetic_repo, make_hook
):
    repo = make_synthetic_repo(tmp_path)
    bad = make_hook(repo / "playbook" / "hooks", "bad", timeout="2s")
    make_hook(repo / "playbook" / "hooks", "good")

    ctx = SyncContext.from_repo(repo, tolerate_load_errors=True)

    assert [hook.frontmatter.id for hook in _local(ctx.hooks_resolved)] == ["good"]
    assert [error.where for error in ctx.hook_load_errors] == [str(bad)]


def _write_rule(repo: Path, name: str, extra_yaml: str = "") -> Path:
    path = repo / "playbook" / "rules" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {name}\nname: R\ndescription: d\nscope: always\n{extra_yaml}---\nBody\n",
        encoding="utf-8",
    )
    return path


def test_from_repo_tolerate_load_errors_records_rule_load_errors(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path)
    _write_rule(repo, "good")
    bad = _write_rule(repo, "bad", "impact: HIGH\n")

    ctx = SyncContext.from_repo(repo, tolerate_load_errors=True)

    assert [error.path for error in ctx.rule_load_errors] == [bad]
    local = [r.frontmatter.id for r in ctx.rules_resolved if r.source_package == "<repo-local>"]
    assert local == ["good"]
    assert "bad" not in {r.frontmatter.id for r in ctx.rule_definitions}
    assert {r.frontmatter.id for r in ctx.rules_resolved} <= {
        r.frontmatter.id for r in ctx.rule_definitions
    }


def test_from_repo_default_raises_rule_load_error(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path)
    bad = _write_rule(repo, "bad", "impact: HIGH\n")

    with pytest.raises(RuleLoadError) as caught:
        SyncContext.from_repo(repo)

    assert caught.value.path == bad


def test_from_repo_default_raises_hook_schema_error(tmp_path, make_synthetic_repo, make_hook):
    repo = make_synthetic_repo(tmp_path)
    bad = make_hook(repo / "playbook" / "hooks", "bad", timeout="2s")

    with pytest.raises(HookSchemaError) as caught:
        SyncContext.from_repo(repo)

    assert caught.value.where == str(bad)


def test_from_config_merges_hook_layers_across_packages(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    make_package: Callable[..., str],
    make_hook: Callable[..., Path],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    engine = make_package("k1_orch_engine", resources=True)
    overlay = make_package("k1_orch_overlay", resources=True)
    make_hook(_package_hooks(engine), "guard-x", decisions=["deny", "ask", "none"])
    make_hook(_package_hooks(overlay), "guard-x", decisions=["ask", "none"])
    source = FileSystemArtifactSource(
        repo_root=repo, engine_package=engine, overlay_packages=[overlay]
    )

    ctx = SyncContext.from_config(repo, SyncContext.from_repo(repo).config, artifact_source=source)

    assert [hook.source_package for hook in ctx.hooks_resolved] == [overlay]
    assert Collision("hook", "guard-x", winner=overlay, losers=(engine,)) in ctx.overlay_collisions
    assert [violation.message for violation in ctx.hook_violations] == [
        "overlay 'k1_orch_overlay' override of 'guard-x' drops decision 'deny'"
    ]


_POLICY_CONFIG = """\
schema_version = 1
adapters_enabled = ["claude_code"]

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[hooks]
enabled = true
"""


def test_from_repo_reads_policy_tables_from_the_committed_config(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_POLICY_CONFIG)
    (repo / ".coding-agent-playbook.local.toml").write_text(
        "[hooks]\nenabled = false\n", encoding="utf-8"
    )

    ctx = SyncContext.from_repo(repo)

    assert ctx.policy_tables.hooks == {"enabled": True}
    assert ctx.policy_tables.local_keys == ("hooks.enabled",)


def test_from_repo_keeps_a_malformed_hooks_table_raw(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """Parsed lazily, so validate can report it (H21) instead of dying at load."""
    config_text = _POLICY_CONFIG.replace("enabled = true", 'enabled = "yes"')
    repo = make_synthetic_repo(tmp_path, config_text=config_text)

    ctx = SyncContext.from_repo(repo)

    assert ctx.policy_tables.hooks == {"enabled": "yes"}
    with pytest.raises(ValueError, match="enabled: must be true or false"):
        ctx.policy_tables.hooks_config()


def test_from_config_defaults_to_no_policy_tables(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """Config-less validate builds its context here: no consumer config, so no
    [hooks] table and hooks are off."""
    repo = make_synthetic_repo(tmp_path, config_text=_POLICY_CONFIG)

    ctx = SyncContext.from_config(repo, SyncContext.from_repo(repo).config)

    assert ctx.policy_tables == PolicyTables()
