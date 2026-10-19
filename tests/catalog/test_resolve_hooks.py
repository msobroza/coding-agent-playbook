"""Hooks in the overlay merge (specs/prK-lifecycle-hooks.md §A.5, §A.6).

:meth:`OverlayResolver.resolve_hooks` hands every layer's definition of an id to
the additive layer merge and records ``Collision(kind="hook")``, violations and
definitions. How ``SyncContext`` splits a source's hooks into those layers is
tested in ``tests/validation/test_context.py``. Kept apart from
``test_resolve.py`` for the file-size budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.catalog.resolve import Collision, OverlayResolver
from coding_agent_playbook.hook_policy import (
    NO_HANDLER_SCHEMAS,
    ConfigKeySpec,
    ConfigSchemaLookup,
    HookViolation,
    merge_hook_layers,
    split_hook_layers,
)
from tests.fakes import FakeHandlerSchemas
from tests.hook_samples import sample_hook

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.artifacts.hook import Hook


def _make_hook(hook_id: str, source: str, **overrides: Any) -> Hook:
    return sample_hook(source, id=hook_id, **overrides)


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
