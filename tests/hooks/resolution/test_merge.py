"""Tests for the additive hook layer merge (specs/prK-lifecycle-hooks.md §A.6, L2).

``merge_hook_layers`` folds every layer's definition of one hook id, engine
first: a repo-local definition replaces a non-mandatory hook but never a
mandatory one (H15), and an id defined twice in one layer is H2. Violations are
returned, never raised. Builtin ``handler.config`` keys merge per the handler's
key policies, injected through :class:`FakeHandlerSchemas` because the real
``CONFIG_SCHEMA`` registry is K2's. What an overlay may not change (H14) is
tested in ``test_override_rules.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.artifacts.hook_schema import HookHandler
from coding_agent_playbook.hooks.resolution.merge import (
    NO_HANDLER_SCHEMAS,
    ConfigKeySpec,
    HookViolation,
    merge_config,
    merge_hook_layers,
)
from tests.fakes import FakeHandlerSchemas
from tests.hook_samples import sample_hook

ENGINE = "coding_agent_playbook"
OVERLAY = "acme_rules"
REPO_LOCAL = "<repo-local>"

_MODES = ("off", "warn", "block")


def _config(hook: Hook) -> dict[str, Any]:
    handler = hook.frontmatter.handler
    assert handler is not None
    return handler.config


def _schemas(**specs: ConfigKeySpec) -> FakeHandlerSchemas:
    return FakeHandlerSchemas({"guard_x": dict(specs)})


def _merge_configs(
    earlier: dict[str, Any], later: dict[str, Any], *, schemas: FakeHandlerSchemas, later_from: str
) -> dict[str, Any]:
    engine = sample_hook(ENGINE, handler={"builtin": "guard_x", "config": earlier})
    override = sample_hook(later_from, handler={"builtin": "guard_x", "config": later})
    merged, violations = merge_hook_layers([engine, override], schemas=schemas)
    assert violations == []
    return _config(merged)


# --- handler.config key policies --------------------------------------------


def test_extend_unions_earlier_first_deduped() -> None:
    merged = _merge_configs(
        {"deny": ["rm -rf", "dd"]},
        {"deny": ["dd", "mkfs"]},
        schemas=_schemas(deny=ConfigKeySpec("extend")),
        later_from=OVERLAY,
    )

    assert merged == {"deny": ["rm -rf", "dd", "mkfs"]}


def test_extend_dedupes_unhashable_rows() -> None:
    rows = [{"cmd": "git push", "flags": ["--force"]}]
    merged = _merge_configs(
        {"rows": rows},
        {"rows": [*rows, {"cmd": "git reset", "flags": ["--hard"]}]},
        schemas=_schemas(rows=ConfigKeySpec("extend")),
        later_from=OVERLAY,
    )

    assert merged["rows"] == [*rows, {"cmd": "git reset", "flags": ["--hard"]}]


@pytest.mark.parametrize(
    ("earlier", "later", "expected"),
    [("block", "warn", "block"), ("warn", "block", "block"), ("off", "off", "off")],
)
def test_strictest_never_lowers_an_ordered_mode(earlier: str, later: str, expected: str) -> None:
    merged = _merge_configs(
        {"mode": earlier},
        {"mode": later},
        schemas=_schemas(mode=ConfigKeySpec("strictest", order=_MODES)),
        later_from=OVERLAY,
    )

    assert merged == {"mode": expected}


@pytest.mark.parametrize(
    ("earlier", "later", "expected"),
    [("block", "loud", "block"), ("loud", "warn", "warn"), ("loud", "quiet", "quiet")],
)
def test_strictest_prefers_a_known_mode_over_an_unknown_one(
    earlier: str, later: str, expected: str
) -> None:
    # An unknown mode is classify_hook's to report; the merge just never lets it lower a known one.
    merged = _merge_configs(
        {"mode": earlier},
        {"mode": later},
        schemas=_schemas(mode=ConfigKeySpec("strictest", order=_MODES)),
        later_from=OVERLAY,
    )

    assert merged == {"mode": expected}


def test_relax_unions_allowlists() -> None:
    merged = _merge_configs(
        {"allowed_hosts": ["pypi.org"]},
        {"allowed_hosts": ["artifactory.example"]},
        schemas=_schemas(allowed_hosts=ConfigKeySpec("relax")),
        later_from=OVERLAY,
    )

    assert merged == {"allowed_hosts": ["pypi.org", "artifactory.example"]}


def test_replace_takes_the_later_value() -> None:
    merged = _merge_configs(
        {"message": "old", "cap": 3, "kept": True},
        {"message": "new", "cap": 5},
        # ``cap`` has no spec at all: an unknown key also replaces.
        schemas=_schemas(message=ConfigKeySpec("replace")),
        later_from=OVERLAY,
    )

    assert merged == {"message": "new", "cap": 5, "kept": True}


def test_repo_local_replaces_every_key() -> None:
    merged = _merge_configs(
        {"deny": ["rm -rf"], "mode": "block", "kept": 1},
        {"deny": ["dd"], "mode": "off"},
        schemas=_schemas(
            deny=ConfigKeySpec("extend"), mode=ConfigKeySpec("strictest", order=_MODES)
        ),
        later_from=REPO_LOCAL,
    )

    assert merged == {"deny": ["dd"], "mode": "off", "kept": 1}


def test_no_handler_schemas_replaces_per_key() -> None:
    engine = sample_hook(
        ENGINE, handler={"builtin": "guard_x", "config": {"deny": ["a"], "kept": 1}}
    )
    overlay = sample_hook(OVERLAY, handler={"builtin": "guard_x", "config": {"deny": ["b"]}})

    merged, _ = merge_hook_layers([engine, overlay])

    assert _config(merged) == {"deny": ["b"], "kept": 1}
    assert NO_HANDLER_SCHEMAS.key_specs("guard_x") == {}


def test_merge_config_is_pure_and_keeps_earlier_only_keys() -> None:
    earlier = {"deny": ["a"], "kept": 1}
    later = {"deny": ["b"]}

    merged = merge_config(earlier, later, {"deny": ConfigKeySpec("extend")})

    assert merged == {"deny": ["a", "b"], "kept": 1}
    assert earlier == {"deny": ["a"], "kept": 1}
    assert later == {"deny": ["b"]}


def test_config_is_not_merged_across_different_builtins() -> None:
    # The swap itself is H14; the later handler's config stands alone.
    engine = sample_hook(ENGINE, handler={"builtin": "guard_x", "config": {"deny": ["a"]}})
    repo = sample_hook(REPO_LOCAL, handler={"builtin": "guard_y", "config": {"other": 1}})

    merged, violations = merge_hook_layers([engine, repo], schemas=_schemas())

    assert _config(merged) == {"other": 1}
    assert violations == []


def test_per_event_handlers_merge_with_the_earlier_binding() -> None:
    handlers = {
        "stop": {"builtin": "gate", "config": {"stages": ["drift"]}},
        "pre_tool_use": {"builtin": "gate:pre_edit", "config": {"paths": ["a"]}},
    }
    later_handlers = {
        "stop": {"builtin": "gate", "config": {"stages": ["tests"]}},
        "pre_tool_use": {"builtin": "gate:pre_edit", "config": {"paths": ["b"]}},
    }
    events = ["pre_tool_use", "stop"]
    engine = sample_hook(ENGINE, events=events, handler=None, handlers=handlers)
    overlay = sample_hook(OVERLAY, events=events, handler=None, handlers=later_handlers)
    schemas = FakeHandlerSchemas({"gate": {"stages": ConfigKeySpec("extend")}, "gate:pre_edit": {}})

    merged, violations = merge_hook_layers([engine, overlay], schemas=schemas)

    assert violations == []
    assert merged.frontmatter.handlers["stop"].config == {"stages": ["drift", "tests"]}
    assert merged.frontmatter.handlers["pre_tool_use"].config == {"paths": ["b"]}


# --- repo-local layer (H15) -------------------------------------------------


def test_repo_local_override_of_mandatory_is_violation() -> None:
    engine = sample_hook(ENGINE, tier="overlay")
    overlay = sample_hook(OVERLAY, tier="default", mandatory=True)
    repo = sample_hook(REPO_LOCAL, enabled=False, path="/repo/playbook/hooks/guard-x/HOOK.md")

    merged, violations = merge_hook_layers([engine, overlay, repo])

    assert merged.source_package == OVERLAY
    assert violations == [
        HookViolation(
            rule="H15",
            hook_id="guard-x",
            where="/repo/playbook/hooks/guard-x/HOOK.md",
            message="'guard-x' is mandatory (overlay acme_rules) and cannot be overridden "
            "by a repo-local definition",
        )
    ]


def test_repo_local_may_override_a_non_mandatory_hook_freely() -> None:
    engine = sample_hook(ENGINE, decisions=["deny", "ask", "none"], on_error="deny")
    repo = sample_hook(
        REPO_LOCAL,
        enabled=False,
        tier="opt-in",
        decisions=["none"],
        on_error="open",
        handler={"builtin": "guard_y"},
    )

    merged, violations = merge_hook_layers([engine, repo])

    assert violations == []
    assert merged is not engine
    assert merged.source_package == REPO_LOCAL
    assert merged.frontmatter.enabled is False


# --- one layer, one definition (H2) -----------------------------------------


def test_duplicate_id_within_one_layer_is_violation() -> None:
    first = sample_hook(ENGINE, name="First", path="/engine/protect/guard-x/HOOK.md")
    second = sample_hook(ENGINE, name="Second", path="/engine/verify/guard-x/HOOK.md")

    merged, violations = merge_hook_layers([first, second])

    assert merged.frontmatter.name == "First"
    assert violations == [
        HookViolation(
            rule="H2",
            hook_id="guard-x",
            where="/engine/verify/guard-x/HOOK.md",
            message="id 'guard-x' is defined more than once in layer 'coding_agent_playbook': "
            "/engine/protect/guard-x/HOOK.md, /engine/verify/guard-x/HOOK.md",
        )
    ]


def test_violation_where_falls_back_to_the_source_package() -> None:
    _, violations = merge_hook_layers([sample_hook(ENGINE), sample_hook(OVERLAY, enabled=False)])

    assert violations[0].where == "acme_rules"


def test_single_definition_passes_through_untouched() -> None:
    engine = sample_hook(ENGINE)

    merged, violations = merge_hook_layers([engine])

    assert merged is engine
    assert violations == []


def test_empty_definitions_is_a_value_error_naming_the_input() -> None:
    with pytest.raises(ValueError, match=r"at least one definition, got \[\]"):
        merge_hook_layers([])


def _unbound(source: str) -> Hook:
    """A hook with no handler bound to its event (an H6 error, judged by validate)."""
    frontmatter = HookFrontmatter.from_mapping(
        {
            "id": "guard-x",
            "name": "N",
            "description": "d",
            "tier": "core",
            "events": ["PreToolUse", "pre_tool_use"],
            "decisions": ["allow"],
            "timeout": 2,
            "on_error": "never",
            "supports": [],
            "matcher": {"bogus": {"tools": ["shell"]}},
        },
        where="x",
    )
    return Hook(frontmatter, "", "", False, None, source)


@pytest.mark.parametrize(
    "definitions",
    [
        [_unbound(ENGINE), _unbound(OVERLAY)],
        [sample_hook(ENGINE), _unbound(OVERLAY)],
        [_unbound(ENGINE), sample_hook(OVERLAY), _unbound(REPO_LOCAL)],
        [
            sample_hook(ENGINE, handler={"builtin": "guard_x", "config": {"mode": ["x"]}}),
            sample_hook(OVERLAY, handler={"builtin": "guard_x", "config": {"mode": {"y": 1}}}),
        ],
    ],
)
def test_merge_never_raises(definitions: list[Hook]) -> None:
    schemas = _schemas(mode=ConfigKeySpec("strictest", order=_MODES))

    merged, violations = merge_hook_layers(definitions, schemas=schemas)

    assert isinstance(merged, Hook)
    assert all(isinstance(v, HookViolation) for v in violations)


def test_merged_handler_is_a_new_object() -> None:
    engine = sample_hook(ENGINE, handler={"builtin": "guard_x", "config": {"deny": ["a"]}})
    overlay = sample_hook(OVERLAY, handler={"builtin": "guard_x", "config": {"deny": ["b"]}})

    merged, _ = merge_hook_layers([engine, overlay], schemas=_schemas(deny=ConfigKeySpec("extend")))

    assert isinstance(merged.frontmatter.handler, HookHandler)
    assert _config(overlay) == {"deny": ["b"]}
    assert _config(merged) == {"deny": ["a", "b"]}
