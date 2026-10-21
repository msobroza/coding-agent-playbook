"""The protect pack as shipped (specs/prK-hook-pack.md §E.0.6, §E.1, Track K5).

Every ``catalog/core/hooks/protect/<id>/HOOK.md`` matches its §E.0.6 row (id,
tier, events, decisions, ``on_error``), passes the H1-H21 contract in a
config-less ``playbook validate`` with no warning, and binds a builtin that
declares its config keys and never mutates tool input. Each K5 step adds its
hooks' rows to :data:`PROTECT_PACK`; a shipped hook without a row fails.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, NamedTuple

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.dispatch.registry import load_builtin
from tests.hook_runtime.handlers.pack_repo import ENGINE_HOOKS, engine_hook, engine_hook_paths

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog


class PackRow(NamedTuple):
    """One §E.0.6 row: what the shipped ``HOOK.md`` must declare."""

    tier: str
    events: tuple[str, ...]
    decisions: tuple[str, ...]
    on_error: str


#: §E.0.6 rows of the hooks shipped so far (E.0.3 maps block -> deny; a pass is none).
PROTECT_PACK: dict[str, PackRow] = {
    "guard-generated-outputs": PackRow(
        "default", ("pre_tool_use",), ("deny", "ask", "none"), "ask"
    ),
    "control-plane-guard": PackRow("default", ("pre_tool_use",), ("deny", "ask", "none"), "ask"),
    "validate-then-sync-on-canonical-edit": PackRow(
        "default", ("post_tool_use",), ("context", "none"), "open"
    ),
    "resync-on-detector-input-change": PackRow(
        "default", ("post_tool_use",), ("context", "none"), "open"
    ),
    "eval-sample-authoring-lint": PackRow(
        "default", ("post_tool_use",), ("context", "none"), "open"
    ),
    "guard-eval-fixtures": PackRow("opt-in", ("pre_tool_use",), ("ask", "none"), "open"),
    "stop-drift-and-orphan-gate": PackRow("default", ("stop",), ("deny", "none"), "open"),
    "session-start-playbook-briefing": PackRow(
        "default", ("session_start",), ("context", "none"), "open"
    ),
}


def _protect_ids() -> list[str]:
    return sorted(
        hook_id
        for hook_id, path in engine_hook_paths().items()
        if path.is_relative_to(ENGINE_HOOKS / "protect")
    )


def test_protect_hooks_match_pack_table() -> None:
    assert _protect_ids() == sorted(PROTECT_PACK)
    for hook_id, row in PROTECT_PACK.items():
        fm = engine_hook(hook_id).frontmatter
        shipped = PackRow(fm.tier, tuple(fm.events), tuple(fm.decisions), fm.on_error)
        assert (fm.id, shipped) == (hook_id, row)
        assert fm.supports == ["claude_code", "opencode"]
        assert fm.handler is not None and fm.handler.builtin == hook_id.replace("-", "_")


def test_protect_hooks_validate_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Config-less validate (an engine checkout) runs H1-H21 on the shipped hooks."""
    ns = argparse.Namespace(repo_root=str(tmp_path))

    assert _validate.run(ns) == 0

    captured = capsys.readouterr()
    shipped = [str(engine_hook_paths()[hook_id]) for hook_id in PROTECT_PACK]
    assert not [line for line in captured.out.splitlines() if line.startswith("FAIL")]
    assert not [line for line in captured.err.splitlines() if any(p in line for p in shipped)]


@pytest.mark.parametrize("hook_id", sorted(PROTECT_PACK))
def test_handlers_declare_config_schema_and_no_input_mutation(hook_id: str) -> None:
    fm = engine_hook(hook_id).frontmatter
    assert fm.handler is not None and fm.handler.builtin is not None

    declaration = load_builtin(fm.handler.builtin)

    assert declaration.mutates_input is False
    assert set(fm.handler.config) <= set(declaration.config_schema)
    assert all(
        declaration.config_schema[key].accepts(value) for key, value in fm.handler.config.items()
    )
    assert {e.value for e in declaration.events} >= set(fm.events)
    assert {d.value for d in declaration.decisions} >= set(fm.decisions)


def test_validate_matcher_paths_are_the_handler_canonical_globs() -> None:
    """The matcher selects the hook; the handler re-checks with the same globs."""
    from coding_agent_playbook.hook_runtime.handlers.protect.validate_then_sync_on_canonical_edit import (
        CANONICAL_GLOBS,
    )

    fm = engine_hook("validate-then-sync-on-canonical-edit").frontmatter

    assert tuple(fm.matcher["post_tool_use"].paths) == CANONICAL_GLOBS


def test_source_changed_child_timeout_nests_under_the_hook_timeout() -> None:
    """OQ-27: the 8 s child timeout stays below each source-changed hook's ``timeout``."""
    from coding_agent_playbook.hook_runtime.handlers.protect._source_changed import CHILD_TIMEOUT_S

    for hook_id in (
        "validate-then-sync-on-canonical-edit",
        "resync-on-detector-input-change",
        "eval-sample-authoring-lint",
    ):
        assert engine_hook(hook_id).frontmatter.timeout > CHILD_TIMEOUT_S


def test_drift_hook_declares_only_its_stage_name() -> None:
    """A Stop-stage hook names its stage in ``handler.config.stage``; order is the engine's (K-10)."""
    from coding_agent_playbook.hook_runtime.stop.stages import STOP_STAGE_ORDER

    handler = engine_hook("stop-drift-and-orphan-gate").frontmatter.handler

    assert handler is not None and handler.config == {"stage": "drift"}
    assert handler.config["stage"] in STOP_STAGE_ORDER


def test_briefing_runs_on_every_session_start_source() -> None:
    hook = engine_hook("session-start-playbook-briefing")
    fm = hook.frontmatter

    assert tuple(fm.matcher["session_start"].sources) == (
        "startup",
        "resume",
        "clear",
        "compact",
        "fork",
    )
    assert hook.body.strip() == ""  # no advisory: a hookless harness has no heartbeat to miss
