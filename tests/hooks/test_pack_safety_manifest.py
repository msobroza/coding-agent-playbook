"""The safety pack as shipped so far (specs/prK-hook-pack.md §E.0.6, §E.4, Track K8).

Every ``resources/hooks/safety/<id>/HOOK.md`` matches its §E.0.6 row (tier,
events, decisions, ``on_error``), passes the H1-H21 contract in a config-less
``playbook validate`` with no warning, and binds builtins that declare their
config keys (a ``regex`` key screened like an overlay's) and never mutate tool
input. stop-diff-sweep names the ``secrets`` stage the coordinator plans.
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


#: K8 ships the rest of §E.4 in its later steps; each adds its row here.
SAFETY_PACK: dict[str, PackRow] = {
    "secrets-path-guard": PackRow(
        "default", ("pre_tool_use",), ("deny", "ask", "context", "none"), "ask"
    ),
    "secret-content-guard": PackRow("default", ("pre_tool_use",), ("deny", "ask", "none"), "ask"),
    "stop-diff-sweep": PackRow("default", ("stop",), ("deny", "none"), "open"),
    "destructive-command-guard": PackRow(
        "default", ("pre_tool_use",), ("deny", "ask", "none"), "ask"
    ),
    "git-commit-push-policy-guard": PackRow(
        "default", ("pre_tool_use",), ("deny", "ask", "none"), "ask"
    ),
    "command-convention-guard": PackRow(
        "opt-in", ("pre_tool_use",), ("deny", "context", "none"), "open"
    ),
}


def _safety_ids() -> list[str]:
    return sorted(
        hook_id
        for hook_id, path in engine_hook_paths().items()
        if path.is_relative_to(ENGINE_HOOKS / "safety")
    )


def test_safety_hooks_match_pack_table() -> None:
    assert _safety_ids() == sorted(SAFETY_PACK)
    for hook_id, row in SAFETY_PACK.items():
        fm = engine_hook(hook_id).frontmatter
        shipped = PackRow(fm.tier, tuple(fm.events), tuple(fm.decisions), fm.on_error)
        assert (fm.id, shipped) == (hook_id, row)
        assert fm.supports == ["claude_code", "opencode"]


def test_safety_hooks_validate_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _validate.run(argparse.Namespace(repo_root=str(tmp_path))) == 0

    captured = capsys.readouterr()
    shipped = [str(engine_hook_paths()[hook_id]) for hook_id in SAFETY_PACK]
    assert not [line for line in captured.out.splitlines() if line.startswith("FAIL")]
    assert not [line for line in captured.err.splitlines() if any(p in line for p in shipped)]


@pytest.mark.parametrize("hook_id", sorted(SAFETY_PACK))
def test_handlers_declare_config_schema_and_no_input_mutation(hook_id: str) -> None:
    fm = engine_hook(hook_id).frontmatter
    assert fm.handler is not None and fm.handler.builtin is not None

    declaration = load_builtin(fm.handler.builtin)

    assert declaration.mutates_input is False
    assert set(fm.handler.config) <= set(declaration.config_schema)
    assert all(declaration.config_schema[k].accepts(v) for k, v in fm.handler.config.items())
    assert set(fm.events) <= {e.value for e in declaration.events}


def test_stop_diff_sweep_names_a_planned_stage() -> None:
    fm = engine_hook("stop-diff-sweep").frontmatter

    assert fm.handler is not None and fm.handler.config["stage"] == "secrets"
    assert "secrets" in STOP_STAGE_ORDER and "secrets" in STAGE_FACTORIES


def test_guardrails_domains_feed_the_secret_hooks() -> None:
    """``[guardrails.secrets]`` and ``[guardrails.stop_sweep]`` reach the hooks' config (§B.3)."""
    assert load_builtin("secret_path_guard").config_domain == "secrets"
    assert load_builtin("stop_secret_sweep").config_domain == "stop_sweep"
    assert load_builtin("secret_content_guard").config_domain is None


def test_guardrails_git_domain_feeds_destructive_command_guard() -> None:
    """``[guardrails.git] protected_branches`` extends the guard's own list (§B.3)."""
    declaration = load_builtin("destructive_command_guard")

    assert declaration.config_domain == "git"
    assert declaration.config_schema["protected_branches"].policy == "extend"


@pytest.mark.parametrize(
    ("builtin", "argv0s"),
    [
        ("destructive_command_guard", {"rm", "git", "mkfs*", "curl", "dd"}),
        ("git_policy_guard", {"git", "gh", "export"}),
    ],
)
def test_bash_guards_declare_their_prefilter_argv0s(builtin: str, argv0s: set[str]) -> None:
    declared = load_builtin(builtin).argv0s

    assert declared is not None and argv0s <= declared
    assert load_builtin("command_convention_guard").argv0s is None  # rows are data: no prefilter
