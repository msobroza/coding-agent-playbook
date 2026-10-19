"""The audit pack as shipped (specs/prK-hook-pack.md §E.0.6, §E.5, Track K9 steps 1-2).

guard-decision-log (default), local-audit-log and precompact-checkpoint
(opt-in) match their §E.5 rows, pass the H1-H21 contract in a config-less
``playbook validate`` with no warning, and bind builtins that declare their
config keys and never mutate tool input. The decision sink routes nowhere;
local-audit-log's ``post_tool_use`` is the one async route, and
``[guardrails.audit]`` reaches it. precompact-checkpoint is Claude-only.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, NamedTuple

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.dispatch.registry import load_builtin
from coding_agent_playbook.hooks.registrations.plan import member_route
from tests.hook_runtime.handlers.pack_repo import (
    ENGINE_HOOKS,
    engine_hook,
    engine_hook_paths,
    resolve_engine_hooks,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog


class PackRow(NamedTuple):
    """One §E.5 row: what the shipped ``HOOK.md`` must declare."""

    tier: str
    events: tuple[str, ...]
    decisions: tuple[str, ...]
    on_error: str
    supports: tuple[str, ...] = ("claude_code", "opencode")


#: guard-decision-log covers every dispatcher event; local-audit-log adds
#: post_tool_use_failure (exit status) to the §E.5 header's events.
AUDIT_PACK: dict[str, PackRow] = {
    "guard-decision-log": PackRow(
        "default",
        (
            "session_start",
            "user_prompt_submit",
            "pre_tool_use",
            "post_tool_use",
            "post_tool_use_failure",
            "stop",
            "subagent_stop",
            "pre_compact",
            "session_end",
        ),
        ("none",),
        "open",
    ),
    "local-audit-log": PackRow(
        "opt-in",
        (
            "session_start",
            "user_prompt_submit",
            "post_tool_use",
            "post_tool_use_failure",
            "session_end",
        ),
        ("none",),
        "open",
    ),
    # OpenCode has no transcript to re-read and no post-compaction start (§C.1.2).
    "precompact-checkpoint": PackRow(
        "opt-in", ("pre_compact", "session_start"), ("context", "none"), "open", ("claude_code",)
    ),
}


def _audit_ids() -> list[str]:
    return sorted(
        hook_id
        for hook_id, path in engine_hook_paths().items()
        if path.is_relative_to(ENGINE_HOOKS / "audit")
    )


def test_audit_hooks_match_pack_table() -> None:
    assert _audit_ids() == sorted(AUDIT_PACK)
    for hook_id, row in AUDIT_PACK.items():
        hook = engine_hook(hook_id)
        fm = hook.frontmatter
        shipped = PackRow(
            fm.tier, tuple(fm.events), tuple(fm.decisions), fm.on_error, tuple(fm.supports)
        )
        assert (fm.id, shipped) == (hook_id, row)
        assert not hook.body.strip()  # infrastructure: no advisory anywhere (§C.4.1)


def test_audit_hooks_validate_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _validate.run(argparse.Namespace(repo_root=str(tmp_path))) == 0

    captured = capsys.readouterr()
    shipped = [str(engine_hook_paths()[hook_id]) for hook_id in AUDIT_PACK]
    assert not [line for line in captured.out.splitlines() if line.startswith("FAIL")]
    assert not [line for line in captured.err.splitlines() if any(p in line for p in shipped)]


@pytest.mark.parametrize("hook_id", sorted(AUDIT_PACK))
def test_handlers_declare_config_schema_and_no_input_mutation(hook_id: str) -> None:
    fm = engine_hook(hook_id).frontmatter
    bound = {event: fm.handler_for(event) for event in fm.events}

    for event, handler in bound.items():
        assert handler.builtin is not None
        declaration = load_builtin(handler.builtin)

        assert declaration.mutates_input is False
        assert set(handler.config) <= set(declaration.config_schema)
        assert all(declaration.config_schema[k].accepts(v) for k, v in handler.config.items())
        assert event in {e.value for e in declaration.events}


def test_routes_sink_everywhere_and_async_on_post_tool_use_only(tmp_path: Path) -> None:
    sink, audit = resolve_engine_hooks(["guard-decision-log", "local-audit-log"], tmp_path)

    assert {member_route(sink, event) for event in sink.events} == {"sink"}
    assert {event: member_route(audit, event) for event in audit.events} == {
        "session_start": "sync",
        "user_prompt_submit": "sync",
        "post_tool_use": "async",
        "post_tool_use_failure": "sync",
        "session_end": "sync",
    }


def test_guardrails_audit_domain_feeds_local_audit_log() -> None:
    """``[guardrails.audit] retain_days`` reaches the handler's config (§B.3, ``replace``)."""
    declaration = load_builtin("activity_log")

    assert declaration.config_domain == "audit"
    assert declaration.config_schema["retain_days"].policy == "replace"
    assert load_builtin("decision_log").config_schema == {}


@pytest.mark.parametrize("handler", ["activity_log", "precompact_checkpoint:reinject"])
def test_pii_key_is_an_extend_list_off_in_the_engine(handler: str) -> None:
    """Only an overlay turns PII on, and no later layer can drop its detectors (§A.6)."""
    declaration = load_builtin(handler)

    assert (declaration.config_schema["pii"].kind, declaration.config_schema["pii"].policy) == (
        "list",
        "extend",
    )
