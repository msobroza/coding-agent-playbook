"""The envelope and the hook records of the compiled ``guard_config.json`` (specs/prK-lifecycle-hooks.md §D.8.2).

The keys the runtime parses itself (the schema and engine versions, the §D.4
deadlines, ``logging``, ``shell``, the path classes, the secret path globs), and
every on hook as ``ResolvedHook.to_json()``: an external hook's argv names its
script copy repo-relatively, so the file stays machine-independent.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.tables.hooks import (
    GuardrailsConfig,
    HooksConfig,
    SecretsGuardrails,
)
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hooks.guard_config.compile import (
    SYNC_OUTPUT_LOCATIONS,
    GuardConfigRequest,
    compile_guard_config,
    serialize_guard_config,
)
from coding_agent_playbook.hooks.registrations.plan import resolved_deadlines_ms
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS
from coding_agent_playbook.sync._hook_scripts import copy_hook_scripts
from tests.hook_runtime.handlers.pack_repo import resolve_engine_hooks
from tests.hook_samples import resolved_from_disk, resolved_hook
from tests.hooks.guard_config.compile_kit import compiled_document, request_for, two_hooks

if TYPE_CHECKING:
    from pathlib import Path


# --- the envelope and the hook records -------------------------------------------------


def test_envelope_and_k3_tables_present(repo: Path, tmp_path: Path) -> None:
    extra = SecretsGuardrails(extra_globs=("*.vault",))
    request = GuardConfigRequest(
        repo_root=repo,
        hooks=two_hooks(tmp_path),
        hooks_config=HooksConfig(
            enabled=True,
            unattended_ask="warn",
            wrapper_prefixes=("proxy",),
            allow_code_from=("<repo-local>",),
            state_ttl_days=3,
        ),
        guardrails=GuardrailsConfig(secrets=extra),
        engine_version="0.2.0",
        generated=(".continue/rules/", "AGENTS.md"),
    )

    cfg = compiled_document(request)

    assert cfg["schema_version"] == 1
    assert cfg["engine_version"] == "0.2.0"
    assert cfg["unattended_ask"] == "warn"
    assert cfg["logging"] == {"decisions": False, "audit": False, "audit_mode": ""}
    assert cfg["shell"]["wrapper_prefixes"] == ["proxy"]
    assert "uv run" in cfg["shell"]["runner_wrappers"]
    assert cfg["secret_path_globs"] == [*SECRET_PATH_GLOBS, "*.vault"]
    assert cfg["allow_code_from"] == ["<repo-local>"]
    assert cfg["state_ttl_days"] == 3
    classes = cfg["path_classes"]
    assert {"canonical", "control_plane", "generated", "py", "test"} <= set(classes)
    assert classes["generated"] == sorted([".continue/rules/", "AGENTS.md", *SYNC_OUTPUT_LOCATIONS])
    assert classes["control_plane"] == [
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".coding-agent-playbook.toml",
        ".coding-agent-playbook.local.toml",
        ".coding-agent-playbook.lock",
        ".coding-agent-playbook/hooks/",
    ]


def test_hooks_are_resolvedhook_to_json(repo: Path, tmp_path: Path) -> None:
    hooks = two_hooks(tmp_path)

    cfg = compiled_document(request_for(repo, hooks))

    assert cfg["hooks"] == {hook.id: hook.to_json() for hook in hooks}


def test_deadlines_match_registration_formula(repo: Path, tmp_path: Path) -> None:
    hooks = two_hooks(tmp_path)

    cfg = compiled_document(request_for(repo, hooks))

    assert cfg["deadlines_ms"] == resolved_deadlines_ms(hooks)
    assert cfg["deadlines_ms"]["pre_tool_use"] == 2000


def test_runtime_parses_the_compiled_config(repo: Path, tmp_path: Path) -> None:
    hooks = two_hooks(tmp_path)

    parsed = parse_guard_config(compile_guard_config(request_for(repo, hooks)).data)

    assert isinstance(parsed, GuardConfig), parsed
    assert sorted(parsed.hooks) == ["guard-ext", "guard-y"]


@pytest.mark.skipif(os.name != "posix", reason="exec bits are POSIX-only")
def test_external_argv_repo_relative_and_scripts_copied_with_exec_bit(
    repo: Path, tmp_path: Path
) -> None:
    hook = resolved_from_disk(tmp_path / "src", "guard-ext")
    builtin = resolved_hook("guard-y")
    out = tmp_path / "out"

    copies = copy_hook_scripts([builtin, hook], out)

    argv = compiled_document(request_for(repo, [hook]))["hooks"]["guard-ext"]["handlers"]
    assert argv["pre_tool_use"]["argv"] == [
        "sh",
        ".coding-agent-playbook/hooks/scripts/guard-ext/check.sh",
        "--fast",
    ]
    [copy] = copies
    assert copy.hook is hook
    root = out / ".coding-agent-playbook" / "hooks" / "scripts" / "guard-ext"
    assert copy.paths == (root / "check.sh", root / "lib" / "data.txt")
    assert (root / "check.sh").read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert (root / "check.sh").stat().st_mode & stat.S_IXUSR
    assert not (root / "lib" / "data.txt").stat().st_mode & 0o111


@pytest.mark.catalog
def test_logging_block_follows_hook_enablement(repo: Path, tmp_path: Path) -> None:
    """guard-decision-log switches the decision log on; local-audit-log the async audit route."""
    sink = resolve_engine_hooks(["guard-decision-log"], tmp_path)
    both = resolve_engine_hooks(["guard-decision-log", "local-audit-log"], tmp_path)

    documents = [compiled_document(request_for(repo, hooks)) for hooks in ([], sink, both)]

    assert [cfg["logging"] for cfg in documents] == [
        {"decisions": False, "audit": False, "audit_mode": ""},
        {"decisions": True, "audit": False, "audit_mode": ""},
        {"decisions": True, "audit": True, "audit_mode": "async"},
    ]
    assert documents[1]["deadlines_ms"] == {}  # the sink adds to no §D.4 deadline
    assert "post_tool_use" not in documents[2]["deadlines_ms"]  # nor does an async member
    runtime = parse_guard_config(serialize_guard_config(documents[2]))
    assert isinstance(runtime, GuardConfig)
    assert (runtime.logging.decisions, runtime.logging.audit_mode) == (True, "async")
