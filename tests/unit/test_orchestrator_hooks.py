"""Hooks in the orchestrator (specs/prK-lifecycle-hooks.md §A.5, §A.6, §P P8c).

:meth:`OverlayResolver.resolve_hooks` hands every layer's definition of an id to
the additive layer merge and records ``Collision(kind="hook")``, violations and
definitions; :class:`SyncContext` splits a source's flat hook list into real
layers and either fails loudly on a malformed hook or, with
``tolerate_hook_errors``, records it. It also carries the committed
``[hooks]`` / ``[guardrails]`` tables raw (§B.1). Kept apart from
``test_orchestrator.py`` for the file-size budget.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.config.tables.hooks import PolicyTables
from coding_agent_playbook.hook_policy import (
    NO_HANDLER_SCHEMAS,
    ConfigKeySpec,
    ConfigSchemaLookup,
    HookViolation,
    merge_hook_layers,
    split_hook_layers,
)
from coding_agent_playbook.orchestrator import Collision, OverlayResolver, SyncContext
from tests.fakes import FakeHandlerSchemas
from tests.hook_samples import sample_hook

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.types import Hook


def _make_hook(hook_id: str, source: str, **overrides: Any) -> Hook:
    return sample_hook(source, id=hook_id, **overrides)


def _local(hooks: Sequence[Hook]) -> list[Hook]:
    """The repo-local hooks; the engine's own pack (Track K5 on) resolves alongside them."""
    return [hook for hook in hooks if hook.source_package == "<repo-local>"]


class _SpyMerge:
    """Records every definition tuple handed to the layer merge, then merges for real."""

    def __init__(self) -> None:
        self.calls: list[tuple[Hook, ...]] = []

    def __call__(
        self, definitions: Sequence[Hook], *, schemas: ConfigSchemaLookup = NO_HANDLER_SCHEMAS
    ) -> tuple[Hook, list[HookViolation]]:
        self.calls.append(tuple(definitions))
        return merge_hook_layers(definitions, schemas=schemas)


def test_resolve_hooks_passes_every_layer_definition_to_merge():
    spy = _SpyMerge()
    engine_x, engine_y = _make_hook("guard-x", "engine"), _make_hook("guard-y", "engine")
    overlay_x, overlay_y = _make_hook("guard-x", "overlay-a"), _make_hook("guard-y", "overlay-b")
    repo_x = _make_hook("guard-x", "<repo-local>")
    resolver = OverlayResolver(merge_hooks=spy)

    result = resolver.resolve_hooks([engine_x, engine_y], [[overlay_x], [overlay_y]], [repo_x])

    assert spy.calls == [(engine_x, overlay_x, repo_x), (engine_y, overlay_y)]
    assert [hook.source_package for hook in result] == ["<repo-local>", "overlay-b"]
    assert resolver.hook_definitions == {
        "guard-x": (engine_x, overlay_x, repo_x),
        "guard-y": (engine_y, overlay_y),
    }


def test_resolve_hooks_records_hook_collision():
    resolver = OverlayResolver()

    resolver.resolve_hooks(
        [_make_hook("guard-x", "engine"), _make_hook("solo", "engine")],
        [[_make_hook("guard-x", "overlay-a")]],
        [],
    )

    assert resolver.collisions == [
        Collision(kind="hook", artifact_id="guard-x", winner="overlay-a", losers=("engine",))
    ]


def test_resolve_hooks_records_violations_and_keeps_the_mandatory_definition():
    resolver = OverlayResolver()
    engine = _make_hook("guard-x", "engine", tier="overlay")
    overlay = _make_hook("guard-x", "overlay-a", mandatory=True)

    result = resolver.resolve_hooks([engine], [[overlay]], [_make_hook("guard-x", "<repo-local>")])

    assert result[0].source_package == "overlay-a"
    assert [violation.rule for violation in resolver.hook_violations] == ["H15"]
    assert resolver.collisions == [
        Collision("hook", "guard-x", winner="overlay-a", losers=("engine", "<repo-local>"))
    ]


def test_resolve_hooks_hands_its_schemas_to_the_merge():
    schemas = FakeHandlerSchemas({"guard_x": {"deny": ConfigKeySpec("extend")}})
    resolver = OverlayResolver(hook_schemas=schemas)
    engine = _make_hook(
        "guard-x", "engine", handler={"builtin": "guard_x", "config": {"deny": ["a"]}}
    )
    overlay = _make_hook(
        "guard-x", "acme", handler={"builtin": "guard_x", "config": {"deny": ["b"]}}
    )

    (merged,) = resolver.resolve_hooks([engine], [[overlay]], [])

    assert merged.frontmatter.handler is not None
    assert merged.frontmatter.handler.config == {"deny": ["a", "b"]}
    assert schemas.calls == ["guard_x"]


def test_bundled_pack_hook_is_an_overlay_layer():
    """A bundled pack's package name starts with the engine's; it is still an overlay."""
    engine = _make_hook("guard-x", ENGINE_PACKAGE)
    pack = _make_hook("guard-x", "coding_agent_playbook.plugins.x")
    other = _make_hook("guard-y", "acme")
    pack_y = _make_hook("guard-y", "coding_agent_playbook.plugins.x")
    repo = _make_hook("guard-x", "<repo-local>")

    layers = split_hook_layers([engine, pack, pack_y, other, repo], engine_package=ENGINE_PACKAGE)

    assert layers == ([engine], [[pack, pack_y], [other]], [repo])


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


def test_from_repo_tolerate_hook_errors_records_load_errors(
    tmp_path, make_synthetic_repo, make_hook
):
    repo = make_synthetic_repo(tmp_path)
    bad = make_hook(repo / "playbook" / "hooks", "bad", timeout="2s")
    make_hook(repo / "playbook" / "hooks", "good")

    ctx = SyncContext.from_repo(repo, tolerate_hook_errors=True)

    assert [hook.frontmatter.id for hook in _local(ctx.hooks_resolved)] == ["good"]
    assert [error.where for error in ctx.hook_load_errors] == [str(bad)]


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
