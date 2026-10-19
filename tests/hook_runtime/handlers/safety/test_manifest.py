"""The safety pack as shipped (specs/prK-hook-pack.md §E.0.6, §E.4, §E.5, Tracks K8-K9).

Every ``catalog/core/hooks/safety/<id>/HOOK.md`` matches its §E.0.6 row (tier,
events, decisions, ``on_error``, ``supports``), passes the H1-H21 contract in a
config-less ``playbook validate`` with no warning, and binds builtins (one per
event for the hooks with companions) that declare their config keys (a
``regex`` key screened like an overlay's) and never mutate tool input.
stop-diff-sweep names the ``secrets`` stage the coordinator plans. The §E.5
overlay-tier mechanisms that live here ship inert: ``tier: overlay``, no
``on_error: deny`` (H10: ``deny`` is an overlay's to set) and ``mode: off``.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, NamedTuple

import pytest

from coding_agent_playbook.commands import validate as _validate
from coding_agent_playbook.hook_runtime.dispatch.registry import load_builtin
from coding_agent_playbook.hook_runtime.handlers.stop_ci_parity_gate import STAGE_FACTORIES
from coding_agent_playbook.hook_runtime.stop.stages import STOP_STAGE_ORDER
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
    supports: tuple[str, ...] = ("claude_code", "opencode")


#: The nine §E.4 rows plus §F.4.2 (taint-escalation's marker and the exfil snapshot are companions).
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
    "dependency-allowlist-guard": PackRow(
        "default", ("pre_tool_use",), ("deny", "ask", "none"), "ask"
    ),
    "exfil-channel-guard": PackRow(
        "default", ("pre_tool_use", "session_start"), ("deny", "ask", "none"), "ask"
    ),
    "taint-escalation": PackRow(
        "opt-in", ("pre_tool_use", "post_tool_use", "session_start"), ("ask", "none"), "ask"
    ),
    # §F.4.2: commitizen on commits and pushes; never asks (a convention is no judgment call).
    "commit-message-convention": PackRow("default", ("pre_tool_use",), ("deny", "none"), "open"),
}


#: The §E.5 overlay-tier mechanisms under ``safety/`` (Track K9): inert until an
#: overlay promotes them. pii-prompt-guard is Claude-only (QC-2); the two
#: ``pre_tool_use`` guards keep ``on_error: ask`` (a guard's default) and ship ``mode: off``.
OVERLAY_PACK: dict[str, PackRow] = {
    "pii-prompt-guard": PackRow(
        "overlay", ("user_prompt_submit",), ("deny", "none"), "open", ("claude_code",)
    ),
    "network-egress-guard": PackRow("overlay", ("pre_tool_use",), ("deny", "ask", "none"), "ask"),
    "sensitive-data-read-guard": PackRow(
        "overlay", ("pre_tool_use",), ("ask", "deny", "none"), "ask"
    ),
}
SHIPPED: dict[str, PackRow] = SAFETY_PACK | OVERLAY_PACK


def _safety_ids() -> list[str]:
    return sorted(
        hook_id
        for hook_id, path in engine_hook_paths().items()
        if path.is_relative_to(ENGINE_HOOKS / "safety")
    )


def test_safety_hooks_match_pack_table() -> None:
    assert _safety_ids() == sorted(SHIPPED)
    for hook_id, row in SHIPPED.items():
        fm = engine_hook(hook_id).frontmatter
        shipped = PackRow(
            fm.tier, tuple(fm.events), tuple(fm.decisions), fm.on_error, tuple(fm.supports)
        )
        assert (fm.id, shipped) == (hook_id, row)


def test_safety_hooks_validate_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _validate.run(argparse.Namespace(repo_root=str(tmp_path))) == 0

    captured = capsys.readouterr()
    shipped = [str(engine_hook_paths()[hook_id]) for hook_id in SHIPPED]
    assert not [line for line in captured.out.splitlines() if line.startswith("FAIL")]
    assert not [line for line in captured.err.splitlines() if any(p in line for p in shipped)]


@pytest.mark.parametrize("hook_id", sorted(SHIPPED))
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


def test_stop_diff_sweep_names_a_planned_stage() -> None:
    fm = engine_hook("stop-diff-sweep").frontmatter

    assert fm.handler is not None and fm.handler.config["stage"] == "secrets"
    assert "secrets" in STOP_STAGE_ORDER and "secrets" in STAGE_FACTORIES


def test_guardrails_domains_feed_the_secret_hooks() -> None:
    """``[guardrails.secrets]`` and ``[guardrails.stop_sweep]`` reach the hooks' config (§B.3)."""
    assert load_builtin("secret_path_guard").config_domain == "secrets"
    assert load_builtin("stop_secret_sweep").config_domain == "stop_sweep"
    assert load_builtin("secret_content_guard").config_domain is None


def test_guardrails_dependencies_domain_feeds_the_dependency_guard() -> None:
    """``[guardrails.dependencies]`` mode (strictest) and allowlist (relax) reach the guard (§B.3)."""
    declaration = load_builtin("dependency_guard")

    assert declaration.config_domain == "dependencies"
    assert declaration.config_schema["mode"].policy == "strictest"
    assert declaration.config_schema["index_mode"].order == ("ask", "deny")
    assert declaration.config_schema["allowlist"].policy == "relax"
    assert load_builtin("exfil_guard").config_schema["allowed_hosts"].policy == "relax"


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
        ("exfil_guard", {"git", "gh", "curl", "wget", "scp", "rsync", "sftp"}),
    ],
)
def test_bash_guards_declare_their_prefilter_argv0s(builtin: str, argv0s: set[str]) -> None:
    declared = load_builtin(builtin).argv0s

    assert declared is not None and argv0s <= declared
    assert load_builtin("command_convention_guard").argv0s is None  # rows are data: no prefilter
    # Runner launchers hide the install from the effective argv0 (``uvx ruff`` runs ``ruff``),
    # and taint escalates on any outbound client: neither can be prefiltered by argv0.
    assert load_builtin("dependency_guard").argv0s is None
    assert load_builtin("taint_escalation").argv0s is None


@pytest.mark.parametrize("hook_id", sorted(OVERLAY_PACK))
def test_overlay_mechanisms_ship_inert(hook_id: str) -> None:
    fm = engine_hook(hook_id).frontmatter

    assert (fm.tier, fm.enabled, fm.mandatory, fm.on_error != "deny") == (
        "overlay",
        True,
        False,
        True,
    )
    config = fm.handler_for(fm.events[0]).config
    assert config.get("mode", "off") == "off"
    assert not any(config.get(key) for key in ("allowed_hosts", "deny_globs", "detectors"))
