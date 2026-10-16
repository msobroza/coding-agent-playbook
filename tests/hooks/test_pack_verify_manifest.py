"""The verify pack as shipped (specs/prK-hook-pack.md §E.0.6, §E.2, Track K6).

Every ``content/core/hooks/verify/<id>/HOOK.md`` matches its §E.0.6 row (tier,
events, decisions, ``on_error``), passes the H1-H21 contract in a config-less
``playbook validate`` with no warning, and binds builtins that declare their
config keys and never mutate tool input. A Stop-stage hook names its stage in
``handler.config.stage`` and the coordinator has a factory for it.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, NamedTuple

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.handlers.stop_ci_parity_gate import STAGE_FACTORIES
from coding_agent_playbook.hook_runtime.registry import load_builtin
from coding_agent_playbook.hook_runtime.stop.stages import STOP_STAGE_ORDER
from tests.hooks.pack_repo import ENGINE_HOOKS, engine_hook, engine_hook_paths

if TYPE_CHECKING:
    from pathlib import Path


class PackRow(NamedTuple):
    """One §E.0.6 row: what the shipped ``HOOK.md`` must declare."""

    tier: str
    events: tuple[str, ...]
    decisions: tuple[str, ...]
    on_error: str


VERIFY_PACK: dict[str, PackRow] = {
    "stop-ci-parity-gate": PackRow("default", ("stop",), ("deny", "none"), "open"),
    # §E.2 + §F.2.2: the stage plus its post-edit companion (the quality bucket).
    "clean-code-metrics-nonregression": PackRow(
        "default", ("stop", "post_tool_use"), ("deny", "context", "none"), "open"
    ),
    # §F.3.2: the docstrings stage plus its post-edit bucket.
    "docstring-nonregression": PackRow(
        "default", ("stop", "post_tool_use"), ("deny", "context", "none"), "open"
    ),
    "block-precommit-bypass": PackRow("default", ("pre_tool_use",), ("deny", "ask", "none"), "ask"),
    "gate-weakening-guard": PackRow(
        "default", ("stop", "pre_tool_use"), ("deny", "ask", "none"), "ask"
    ),
    # Promoted to default: warn-only (context), ~115 ms per Stop with a source diff.
    "tests-with-source-nudge": PackRow("default", ("stop",), ("deny", "none"), "open"),
    "subagent-stop-verify": PackRow("opt-in", ("subagent_stop",), ("deny", "none"), "open"),
    "prompt-output-contract-on-stop": PackRow("opt-in", ("stop",), ("deny", "none"), "open"),
    # §F.1.2: the trust-gated coverage stage (execution, opt-in).
    "coverage-diff-gate": PackRow("opt-in", ("stop",), ("deny", "none"), "open"),
}
#: Claude only: OpenCode has no subagent event and no final message text (§E.2 Portability).
CLAUDE_ONLY = frozenset({"subagent-stop-verify", "prompt-output-contract-on-stop"})


def _verify_ids() -> list[str]:
    return sorted(
        hook_id
        for hook_id, path in engine_hook_paths().items()
        if path.is_relative_to(ENGINE_HOOKS / "verify")
    )


def test_verify_hooks_match_pack_table() -> None:
    assert _verify_ids() == sorted(VERIFY_PACK)
    for hook_id, row in VERIFY_PACK.items():
        fm = engine_hook(hook_id).frontmatter
        shipped = PackRow(fm.tier, tuple(fm.events), tuple(fm.decisions), fm.on_error)
        assert (fm.id, shipped) == (hook_id, row)
        expected = ["claude_code"] if hook_id in CLAUDE_ONLY else ["claude_code", "opencode"]
        assert fm.supports == expected


def test_verify_hooks_validate_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _validate.run(argparse.Namespace(repo_root=str(tmp_path))) == 0

    captured = capsys.readouterr()
    shipped = [str(engine_hook_paths()[hook_id]) for hook_id in VERIFY_PACK]
    assert not [line for line in captured.out.splitlines() if line.startswith("FAIL")]
    assert not [line for line in captured.err.splitlines() if any(p in line for p in shipped)]


@pytest.mark.parametrize("hook_id", sorted(VERIFY_PACK))
def test_handlers_declare_config_schema_and_no_input_mutation(hook_id: str) -> None:
    fm = engine_hook(hook_id).frontmatter
    single = fm.handler
    handlers = fm.handlers or {event: single for event in fm.events if single is not None}
    assert set(handlers) == set(fm.events)
    for event, handler in handlers.items():
        assert handler.builtin is not None
        declaration = load_builtin(handler.builtin)
        assert declaration.mutates_input is False
        assert set(handler.config) <= set(declaration.config_schema)
        assert all(declaration.config_schema[k].accepts(v) for k, v in handler.config.items())
        assert event in {e.value for e in declaration.events}


@pytest.mark.parametrize(
    ("hook_id", "stage"),
    [
        ("clean-code-metrics-nonregression", "quality-metrics"),
        ("docstring-nonregression", "docstrings"),
        ("gate-weakening-guard", "gate-integrity"),
        ("tests-with-source-nudge", "tests-nudge"),
        ("prompt-output-contract-on-stop", "output-contract"),
        ("coverage-diff-gate", "coverage"),
    ],
)
def test_stage_hooks_name_a_planned_stage(hook_id: str, stage: str) -> None:
    fm = engine_hook(hook_id).frontmatter
    handler = (fm.handlers or {}).get("stop") or fm.handler

    assert handler is not None and handler.config["stage"] == stage
    assert stage in STOP_STAGE_ORDER and stage in STAGE_FACTORIES
