"""The sync-level ``guard_config.json`` and copied hook scripts (specs/prK-lifecycle-hooks.md §C.0, §D.8).

The file is committed and byte-compared by ``sync --check`` on every machine,
so its bytes depend only on the resolved hooks and the committed policy: no
absolute path, no ``sys.prefix``, no ``$HOME`` (§D.8.3). The runtime reads it
back through ``hook_runtime.config``, so the schema is pinned against that parser.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.guard_config import (
    GUARD_CONFIG_PATH,
    SYNC_OUTPUT_LOCATIONS,
    GuardConfigInputs,
    copy_hook_scripts,
    render_guard_config,
    serialize_guard_config,
    write_guard_config,
)
from coding_agent_playbook.hook_registrations import resolved_deadlines_ms
from coding_agent_playbook.hook_runtime.config import (
    GUARD_CONFIG_REL,
    GuardConfig,
    parse_guard_config,
)
from coding_agent_playbook.hooks_config import (
    GuardrailsConfig,
    HooksConfig,
    SecretsGuardrails,
)
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS
from tests.hook_samples import resolved_from_disk, resolved_hook

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_policy import ResolvedHook


def _inputs(hooks: list[ResolvedHook]) -> GuardConfigInputs:
    return GuardConfigInputs(
        hooks=hooks,
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        generated=(".claude/commands/", "AGENTS.md"),
    )


def _two_hooks(tmp_path: Path) -> list[ResolvedHook]:
    return [
        resolved_from_disk(tmp_path / "src", "guard-ext"),
        resolved_hook("guard-y", events=("stop",), timeout=1.5),
    ]


def test_render_is_machine_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hooks = _two_hooks(tmp_path)
    rendered: list[bytes] = []
    for prefix, home in (("/opt/venv-a", tmp_path / "home-a"), ("/srv/venv-b", tmp_path / "b")):
        monkeypatch.setattr(sys, "prefix", prefix)
        monkeypatch.setenv("HOME", str(home))
        rendered.append(serialize_guard_config(render_guard_config(_inputs(hooks))))

    assert rendered[0] == rendered[1]
    text = rendered[0].decode("ascii")
    assert str(tmp_path) not in text
    assert "/opt/" not in text and "/srv/" not in text


def test_canonical_serialization_sorted_compact_ascii_newline() -> None:
    data = {"b": 1, "a": {"z": "é", "y": [1, 2]}}

    blob = serialize_guard_config(data)

    assert blob == b'{"a":{"y":[1,2],"z":"\\u00e9"},"b":1}\n'
    assert blob == (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def test_envelope_and_k3_tables_present(tmp_path: Path) -> None:
    extra = SecretsGuardrails(extra_globs=("*.vault",))
    inputs = GuardConfigInputs(
        hooks=_two_hooks(tmp_path),
        hooks_config=HooksConfig(
            enabled=True,
            unattended_ask="warn",
            wrapper_prefixes=("rtk",),
            allow_code_from=("<repo-local>",),
            state_ttl_days=3,
        ),
        guardrails=GuardrailsConfig(secrets=extra),
        engine_version="0.2.0",
        generated=(".continue/rules/", "AGENTS.md"),
    )

    cfg = render_guard_config(inputs)

    assert cfg["schema_version"] == 1
    assert cfg["engine_version"] == "0.2.0"
    assert cfg["unattended_ask"] == "warn"
    assert cfg["logging"] == {"decisions": False, "audit": False, "audit_mode": ""}
    assert cfg["shell"]["wrapper_prefixes"] == ["rtk"]
    assert "uv run" in cfg["shell"]["runner_wrappers"]
    assert cfg["secret_path_globs"] == [*SECRET_PATH_GLOBS, "*.vault"]
    assert cfg["allow_code_from"] == ["<repo-local>"]
    assert cfg["state_ttl_days"] == 3
    classes = cfg["path_classes"]
    assert {"canonical", "control_plane", "generated", "py", "test"} <= set(classes)
    assert classes["generated"] == sorted([".continue/rules/", "AGENTS.md", *SYNC_OUTPUT_LOCATIONS])
    assert ".claude/settings.json" in classes["control_plane"]


def test_hooks_are_resolvedhook_to_json(tmp_path: Path) -> None:
    hooks = _two_hooks(tmp_path)

    cfg = render_guard_config(_inputs(hooks))

    assert cfg["hooks"] == {hook.id: hook.to_json() for hook in hooks}


def test_deadlines_match_registration_formula(tmp_path: Path) -> None:
    hooks = _two_hooks(tmp_path)

    cfg = render_guard_config(_inputs(hooks))

    assert cfg["deadlines_ms"] == resolved_deadlines_ms(hooks)
    assert cfg["deadlines_ms"]["pre_tool_use"] == 2000


def test_runtime_parses_the_rendered_config(tmp_path: Path) -> None:
    hooks = _two_hooks(tmp_path)

    parsed = parse_guard_config(serialize_guard_config(render_guard_config(_inputs(hooks))))

    assert isinstance(parsed, GuardConfig), parsed
    assert sorted(parsed.hooks) == ["guard-ext", "guard-y"]
    assert GUARD_CONFIG_PATH == GUARD_CONFIG_REL


def test_write_guard_config_writes_canonical_bytes(tmp_path: Path) -> None:
    cfg = render_guard_config(_inputs([]))

    path = write_guard_config(tmp_path, cfg)

    assert path == tmp_path / GUARD_CONFIG_PATH
    assert path.read_bytes() == serialize_guard_config(cfg)


@pytest.mark.skipif(os.name != "posix", reason="exec bits are POSIX-only")
def test_external_argv_repo_relative_and_scripts_copied_with_exec_bit(tmp_path: Path) -> None:
    hook = resolved_from_disk(tmp_path / "src", "guard-ext")
    builtin = resolved_hook("guard-y")
    out = tmp_path / "out"

    copies = copy_hook_scripts([builtin, hook], out)

    argv = render_guard_config(_inputs([hook]))["hooks"]["guard-ext"]["handlers"]
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
