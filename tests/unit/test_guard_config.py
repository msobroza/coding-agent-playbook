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

from coding_agent_playbook import renderer
from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter
from coding_agent_playbook.commands._sync_lockfile import build_lockfile
from coding_agent_playbook.guard_config import (
    GUARD_CONFIG_PATH,
    HOOK_ARTIFACTS,
    SYNC_OUTPUT_LOCATIONS,
    GuardConfigInputs,
    ProtectInputs,
    adapter_output_dirs,
    copy_hook_scripts,
    protected_rows,
    render_guard_config,
    resource_root_ids,
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
from coding_agent_playbook.lockfile import LockEntry, Provenance
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS
from tests.hook_samples import resolved_from_disk, resolved_hook

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hook_policy import ResolvedHook


_PROTECT = ProtectInputs(
    entries=(),
    output_dirs=(".claude/commands/", "AGENTS.md"),
    packages=("coding_agent_playbook", "coding_agent_playbook.packs.superpowers"),
)


def _inputs(hooks: list[ResolvedHook], protect: ProtectInputs = _PROTECT) -> GuardConfigInputs:
    return GuardConfigInputs(
        hooks=hooks,
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        generated=(".claude/commands/", "AGENTS.md"),
        protected=protect,
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
    assert '"protected":' in text and '"sentinel":' in text
    assert "site-packages" not in text


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


# --- the §E.0.5 protect tables (Track K5 step 1) ------------------------------------------------


def _written_tree(root: Path) -> tuple[dict[Path, Provenance], list[LockEntry]]:
    """A synced tree: two whole-file outputs, a composite and a co-owned settings file."""
    files = {
        ".claude/skills/demo/SKILL.md": Provenance("skill", "demo", "<repo-local>", "claude_code"),
        ".continue/rules/10-x.md": Provenance("rule", "x", "coding_agent_playbook", "continue"),
        "AGENTS.md": Provenance("composite", adapter="agents_md"),
        ".claude/settings.json": Provenance("composite", adapter="claude_code"),
    }
    provenance: dict[Path, Provenance] = {}
    for rel, origin in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{rel}\n", encoding="utf-8")
        provenance[path.resolve()] = origin
    managed = [
        LockEntry(
            path=".claude/settings.json",
            sha256="ab" * 32,
            bytes=40,
            kind="runtime",
            artifact_id="registration:pre_tool_use",
            adapter="claude_code",
            scope="json:/hooks/PreToolUse",
        )
    ]
    return provenance, managed


def test_protected_entries_mirror_lockfile_provenance(tmp_path: Path) -> None:
    provenance, managed = _written_tree(tmp_path)
    shared = (".claude/settings.json",)

    rows = protected_rows(provenance, managed, tmp_path, shared=shared)

    lock = build_lockfile(
        list(provenance), tmp_path, "0.2.0", provenance=provenance, managed=managed, shared=shared
    )
    columns = ("path", "kind", "artifact_id", "source", "scope")
    assert [{c: row.to_json()[c] for c in columns} for row in rows] == [
        {c: getattr(entry, c) for c in columns} for entry in lock.entries
    ]


def test_scoped_entries_carry_sha256(tmp_path: Path) -> None:
    provenance, managed = _written_tree(tmp_path)

    rows = [row.to_json() for row in protected_rows(provenance, managed, tmp_path)]

    scoped = [row for row in rows if row["scope"]]
    assert scoped == [
        {
            "path": ".claude/settings.json",
            "kind": "runtime",
            "artifact_id": "registration:pre_tool_use",
            "source": "",
            "scope": "json:/hooks/PreToolUse",
            "sha256": "ab" * 32,
        }
    ]
    assert all("sha256" not in row for row in rows if not row["scope"])


def test_protected_output_dirs_match_adapter_stale_scan_dirs(tmp_path: Path) -> None:
    adapters = {
        "claude_code": ClaudeCodeAdapter(),
        "continue": ContinueAdapter(),
        "opencode": OpenCodeAdapter(),
        "agents_md": AgentsMdAdapter(),
    }

    dirs = adapter_output_dirs(adapters, tmp_path)

    scanned = {
        f"{path.relative_to(tmp_path).as_posix()}/"
        for adapter in adapters.values()
        for path in adapter._output_directories(tmp_path)
    }
    assert set(dirs) == scanned | {".claude/CLAUDE.md", "AGENTS.md"}
    assert ".claude/skills/" not in dirs  # skill output is lockfile-only (main #25)
    assert dirs == sorted(dirs)
    assert adapter_output_dirs({"continue": ContinueAdapter()}, tmp_path) == [
        ".continue/prompts/",
        ".continue/rules/",
    ]


def test_resource_roots_are_package_relative_ids() -> None:
    packages = ("coding_agent_playbook", "coding_agent_playbook.packs.superpowers")

    table = render_guard_config(_inputs([]))["protected"]

    assert resource_root_ids(packages) == [
        "pkg:coding_agent_playbook/resources",
        "pkg:coding_agent_playbook.packs.superpowers/resources",
    ]
    assert table["resource_roots"] == resource_root_ids(packages)
    assert table["hook_artifacts"] == list(HOOK_ARTIFACTS)
    assert table["hook_artifacts"] == [
        ".coding-agent-playbook/hooks/",
        ".claude/hooks/playbook/",
        ".opencode/plugins/playbook-hooks.js",
    ]
    assert table["output_dirs"] == [".claude/commands/", "AGENTS.md"]


def test_sentinel_key_is_renderer_sentinel() -> None:
    cfg = render_guard_config(_inputs([]))

    assert cfg["sentinel"] == renderer.SENTINEL


def test_runtime_reads_the_protect_tables_back(tmp_path: Path) -> None:
    provenance, managed = _written_tree(tmp_path)
    protect = ProtectInputs(entries=protected_rows(provenance, managed, tmp_path))

    parsed = parse_guard_config(serialize_guard_config(render_guard_config(_inputs([], protect))))

    assert isinstance(parsed, GuardConfig), parsed
    assert parsed.tables["sentinel"] == renderer.SENTINEL
    paths = [row["path"] for row in parsed.tables["protected"]["entries"]]
    assert paths == sorted(paths)
