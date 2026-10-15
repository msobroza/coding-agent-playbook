"""The sync-level ``guard_config.json`` and copied hook scripts (specs/prK-lifecycle-hooks.md §C.0, §D.8).

The file is committed and byte-compared by ``sync --check`` on every machine,
so its bytes depend only on the resolved hooks and the committed policy: no
absolute path, no ``sys.prefix``, no ``$HOME`` (§D.8.3). The runtime reads it
back through ``hook_runtime.config``, so the schema is pinned against that parser.
"""

from __future__ import annotations

import dataclasses
import json
import os
import stat
import sys
from typing import TYPE_CHECKING, Any

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
    DetectInputs,
    GuardConfigInputs,
    ProtectInputs,
    RepoLayout,
    adapter_output_dirs,
    applicability_rows,
    copy_hook_scripts,
    precommit_hook_ids,
    protected_rows,
    render_guard_config,
    repo_layout,
    resource_root_ids,
    serialize_guard_config,
    write_guard_config,
)
from coding_agent_playbook.hook_policy import resolve_effective_hooks
from coding_agent_playbook.hook_registrations import resolved_deadlines_ms
from coding_agent_playbook.hook_runtime.config import (
    GUARD_CONFIG_REL,
    GuardConfig,
    parse_guard_config,
)
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.handlers._control_plane_paths import CONTROL_PLANE
from coding_agent_playbook.hook_runtime.handlers._control_plane_text import (
    playbook_precommit_ids,
)
from coding_agent_playbook.hooks_config import (
    GuardrailsConfig,
    HooksConfig,
    SecretsGuardrails,
)
from coding_agent_playbook.lockfile import LockEntry, Provenance
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS
from coding_agent_playbook.types import Prompt, PromptFrontmatter, Rule, RuleFrontmatter
from tests.hook_samples import resolved_from_disk, resolved_hook, sample_hook

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.detector import Facts
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


def test_control_plane_rows_are_engine_constants(tmp_path: Path) -> None:
    """Rendered from the runtime's own constants; no input changes them (overlays: extra_paths)."""
    bare = render_guard_config(_inputs([]))["control_plane"]
    other = render_guard_config(_inputs(_two_hooks(tmp_path), ProtectInputs()))["control_plane"]

    assert bare == {key: list(rows) for key, rows in CONTROL_PLANE.items()}
    assert other == bare
    assert ".claude/settings.json" in bare["settings"]
    assert bare["toml_deny"] == ["hooks", "guardrails"]


_PRECOMMIT = """\
repos:
  - repo: local
    hooks:
      - id: playbook-sync-check
      - id: "coding-agent-playbook-sync"
      - id: ruff
#     - id: playbook-switched-off
"""


def test_precommit_ids_use_the_runtime_regex(tmp_path: Path) -> None:
    (tmp_path / ".pre-commit-config.yaml").write_text(_PRECOMMIT, encoding="utf-8")

    ids = precommit_hook_ids(tmp_path)
    rendered = render_guard_config(dataclasses.replace(_inputs([]), precommit_ids=ids))

    assert ids == playbook_precommit_ids(_PRECOMMIT)
    assert rendered["precommit"] == {
        "playbook_hook_ids": ["coding-agent-playbook-sync", "playbook-sync-check"]
    }
    assert precommit_hook_ids(tmp_path / "no-such-repo") == []


def test_runtime_reads_the_control_plane_tables_back() -> None:
    inputs = dataclasses.replace(_inputs([]), precommit_ids=["playbook-sync-check"])

    parsed = parse_guard_config(serialize_guard_config(render_guard_config(inputs)))

    assert isinstance(parsed, GuardConfig), parsed
    assert parsed.tables["precommit"] == {"playbook_hook_ids": ["playbook-sync-check"]}
    assert parsed.tables["control_plane"]["mcp"] == [".mcp.json"]


# --- K5 step 3: facts, applicability, eval, auto_sync (§E.0.5) -------------------------

_ML_RULE = Rule(
    RuleFrontmatter(
        id="ml-serialization-security",
        name="ML serialization",
        description="Never unpickle untrusted data.",
        scope="always",
        applies_if={"any_ml_stack": ["torch"]},
    ),
    "Use safetensors.\n",
    "Use safetensors.\n",
    False,
    None,
    "coding_agent_playbook",
)


def _prompt(prompt_id: str, applies_if: dict[str, Any] | None = None) -> Prompt:
    frontmatter = PromptFrontmatter(
        id=prompt_id, name=prompt_id, description="d", slash=prompt_id, applies_if=applies_if or {}
    )
    return Prompt(frontmatter, "Body.\n", "Body.\n", False, None, "<repo-local>")


def test_facts_carry_dependency_names_and_presence_flags() -> None:
    facts: Facts = {
        "dependencies": {"torch": ">=2", "fastapi": ""},
        "dev_dependencies": {"pytest": ">=8"},
        "ml_stack": {"torch": ">=2"},
        "has_dockerfile": True,
        "has_ci": False,
        "python_version": "3.12",
    }
    inputs = dataclasses.replace(_inputs([]), detect=DetectInputs(facts=facts))

    rendered = render_guard_config(inputs)["facts"]

    assert rendered == {
        "dependencies": ["fastapi", "torch"],
        "dev_dependencies": ["pytest"],
        "has_ci": False,
        "has_dockerfile": True,
        "has_notebooks": False,
    }


def test_applicability_rows_cover_rules_prompts_and_skipped_hooks(tmp_path: Path) -> None:
    linked = sample_hook(
        "coding_agent_playbook", id="ml-guard", linked_rule=_ML_RULE.frontmatter.id
    )
    gated = sample_hook(id="nb-guard", applies_if={"has_notebooks": True})
    opt_in = sample_hook(id="later", tier="opt-in", applies_if={"has_notebooks": True})
    always = sample_hook(id="guard-x")
    hooks = [linked, gated, opt_in, always]
    view = resolve_effective_hooks(
        hooks,
        [_ML_RULE],
        HooksConfig(enabled=True),
        GuardrailsConfig(),
        {},
        tmp_path,
        adapters_enabled=["claude_code"],
    )
    rows = applicability_rows(
        rules=[_ML_RULE],
        prompts=[_prompt("security-review", {"any_ml_stack": ["torch"]}), _prompt("explain")],
        hooks=hooks,
        view=view,
        facts={},
        repo_root=tmp_path,
    )

    table = render_guard_config(
        dataclasses.replace(_inputs([]), detect=DetectInputs(applicability=rows))
    )["applicability"]

    torch = [{"any_ml_stack": ["torch"]}]
    assert table == [
        {
            "kind": "hook",
            "id": "guard-x",
            "applies_if": [],
            "source": "<repo-local>",
            "active": True,
        },
        {
            "kind": "hook",
            "id": "ml-guard",
            "applies_if": torch,
            "source": "coding_agent_playbook",
            "active": False,
        },
        {
            "kind": "hook",
            "id": "nb-guard",
            "applies_if": [{"has_notebooks": True}],
            "source": "<repo-local>",
            "active": False,
        },
        {
            "kind": "prompt",
            "id": "explain",
            "applies_if": [],
            "source": "<repo-local>",
            "active": True,
        },
        {
            "kind": "prompt",
            "id": "security-review",
            "applies_if": torch,
            "source": "<repo-local>",
            "active": False,
        },
        {
            "kind": "rule",
            "id": "ml-serialization-security",
            "applies_if": torch,
            "source": "coding_agent_playbook",
            "active": False,
        },
    ]  # the opt-in hook is off by tier: new facts can never turn it on


def test_eval_fixture_globs_default() -> None:
    rendered = render_guard_config(_inputs([]))

    assert rendered["eval"] == {"fixture_globs": ["**/eval_tasks/*/setup/**"]}
    assert rendered["path_classes"]["eval_fixture"] == rendered["eval"]["fixture_globs"]


def test_auto_sync_rendered_from_hooks_table() -> None:
    on = dataclasses.replace(_inputs([]), hooks_config=HooksConfig(enabled=True, auto_sync=True))

    assert render_guard_config(_inputs([]))["auto_sync"] is False
    assert render_guard_config(on)["auto_sync"] is True
    parsed = parse_guard_config(serialize_guard_config(render_guard_config(on)))
    assert isinstance(parsed, GuardConfig) and parsed.tables["auto_sync"] is True


# --- K6: the stop_gate table and the stop deadline (prK-hook-pack.md §E.0.5, §D.4) ------


def _stop_hooks(config: dict[str, Any] | None = None) -> list[ResolvedHook]:
    return [
        resolved_hook("stop-ci-parity-gate", events=("stop",), config=config or {}),
        resolved_hook(
            "coverage-diff-gate", events=("stop",), timeout=60.0, config={"stage": "coverage"}
        ),
        resolved_hook(
            "stop-drift-and-orphan-gate", events=("stop",), timeout=5.0, config={"stage": "drift"}
        ),
    ]


def _stop_gate(hooks: list[ResolvedHook], facts: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = dataclasses.replace(_inputs(hooks), detect=DetectInputs(facts=facts or {}))
    gate: dict[str, Any] = render_guard_config(inputs)["stop_gate"]
    return gate


def test_stop_gate_derived_from_hook_config_and_dev_tools() -> None:
    config = {
        "budget_s": 4.5,
        "max_blocks": 3,
        "verify_commands": ["uv run --frozen --no-sync pytest -q"],
        "claim_patterns": ["(?i)shipped it"],
    }

    gate = _stop_gate(_stop_hooks(config), {"dev_tools": {"ruff"}})

    assert (gate["budget_s"], gate["max_blocks"]) == (4.5, 3)
    assert gate["stages"] == [
        {
            "name": "drift",
            "owner": "stop-drift-and-orphan-gate",
            "cost": "deterministic",
            "tool": "",
            "args": [],
            "timeout_s": 5.0,
            "needs_diff": False,
            "mode": "block",
        },
        {
            "name": "lint",
            "owner": "stop-ci-parity-gate",
            "cost": "deterministic",
            "tool": "ruff",
            "args": ["check", "--output-format=json", "."],
            "timeout_s": 3.0,
            "needs_diff": True,
            "mode": "block",
        },
        {
            "name": "verify-claim",
            "owner": "stop-ci-parity-gate",
            "cost": "deterministic",
            "tool": "",
            "args": [],
            "timeout_s": 1.0,
            "needs_diff": True,
            "mode": "block",
        },
        {
            "name": "coverage",
            "owner": "coverage-diff-gate",
            "cost": "execution",
            "tool": "",
            "args": [],
            "timeout_s": 60.0,
            "needs_diff": True,
            "mode": "block",
        },
    ]
    assert gate["verify_commands"] == [
        {"id": "custom-1", "argv": ["uv", "run", "--frozen", "--no-sync", "pytest", "-q"]}
    ]
    assert gate["claim_patterns"][-1] == "(?i)shipped it" and len(gate["claim_patterns"]) > 1
    parsed = parse_guard_config(serialize_guard_config(render_guard_config(_inputs([]))))
    assert isinstance(parsed, GuardConfig) and parsed.tables["stop_gate"]["stages"] == []


def test_opted_in_execution_stages_join_the_table_and_the_deadline() -> None:
    hooks = _stop_hooks({"stages": ["tests", "typecheck"]})[:1]

    gate = _stop_gate(hooks)
    deadlines = render_guard_config(_inputs(hooks))["deadlines_ms"]

    rows = [(r["name"], r["owner"], r["cost"], r["tool"], r["args"]) for r in gate["stages"]]
    assert rows == [
        (
            "lint",
            "stop-ci-parity-gate",
            "deterministic",
            "ruff",
            ["check", "--output-format=json", "."],
        ),
        ("verify-claim", "stop-ci-parity-gate", "deterministic", "", []),
        ("typecheck", "stop-ci-parity-gate", "execution", "project_python", ["-m", "mypy"]),
        ("tests", "stop-ci-parity-gate", "execution", "project_python", ["-m", "pytest", "-q"]),
    ]
    assert deadlines["stop"] == 423_000  # 1000 * (budget_s 3.0 + typecheck 120 + tests 300)


def test_verify_commands_derived_when_absent() -> None:
    gate = _stop_gate(_stop_hooks(), {"dev_tools": {"pytest", "mypy", "ruff"}})

    assert gate["verify_commands"] == [
        {"id": "lint", "argv": ["ruff", "check"]},
        {"id": "format", "argv": ["ruff", "format"]},
        {"id": "typecheck", "argv": ["mypy"]},
        {"id": "tests", "argv": ["pytest"]},
    ]
    assert (gate["budget_s"], gate["max_blocks"]) == (3.0, 2)
    assert _stop_gate(_stop_hooks())["verify_commands"] == []


def test_stop_gate_is_machine_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rendered: list[bytes] = []
    for prefix, home in (("/opt/venv-a", tmp_path / "home-a"), ("/srv/venv-b", tmp_path / "b")):
        monkeypatch.setattr(sys, "prefix", prefix)
        monkeypatch.setenv("HOME", str(home))
        gate = _stop_gate(_stop_hooks({"budget_s": 4.0}), {"dev_tools": {"ruff", "pytest"}})
        rendered.append(serialize_guard_config(gate))

    assert rendered[0] == rendered[1]
    text = rendered[0].decode("ascii")
    assert str(tmp_path) not in text and "/opt/" not in text and "/srv/" not in text


def test_stop_deadline_formula_includes_exec_timeouts() -> None:
    hooks = _stop_hooks({"budget_s": 4.0})
    coverage = {"stage": "coverage"}
    slow = [
        hooks[0],
        resolved_hook("coverage-diff-gate", events=("stop",), timeout=900.0, config=coverage),
    ]

    deadlines = render_guard_config(_inputs(hooks))["deadlines_ms"]

    assert deadlines["stop"] == 64_000  # 1000 * (budget_s 4.0 + the coverage stage's 60 s)
    assert deadlines == resolved_deadlines_ms(hooks)
    assert resolved_deadlines_ms(slow)["stop"] == 595_000  # the engine cap


# --- the verify-pack tables (specs/prK-hook-pack.md §E.0.5, §E.2) --------------------------


def _contract_prompt(prompt_id: str, slash: str, contract: list[str]) -> Prompt:
    fm = PromptFrontmatter(
        id=prompt_id, name=prompt_id, description="d", slash=slash, output_contract=contract
    )
    return Prompt(fm, "Body\n", "Body\n", False, None, "coding_agent_playbook")


def test_prompts_table_maps_slash_to_contract() -> None:
    verdict = r"(?im)^\W*(approve|request changes)\W*$"
    prompts = [
        _contract_prompt("review", "review", [verdict]),
        _contract_prompt("explain", "explain", []),
        _contract_prompt(
            "review-overlay", "review", ["shadowed"]
        ),  # the first prompt per slash wins
    ]
    inputs = dataclasses.replace(_inputs([]), prompts=prompts)

    table = render_guard_config(inputs)["prompts"]

    assert table == {
        "review": {"id": "review", "output_contract": [verdict]},
        "explain": {"id": "explain", "output_contract": []},
    }
    parsed = parse_guard_config(serialize_guard_config(render_guard_config(inputs)))
    assert isinstance(parsed, GuardConfig) and parsed.tables["prompts"] == table
    assert render_guard_config(_inputs([]))["prompts"] == {}


def _nudge_hook(config: dict[str, Any] | None = None) -> ResolvedHook:
    hook = resolved_hook("tests-with-source-nudge", events=("stop",), config=config)
    handler = dataclasses.replace(hook.handlers["stop"], name="tests_with_source_nudge")
    return dataclasses.replace(hook, handlers={"stop": handler})


def test_tests_nudge_roots_from_src_and_testpaths(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests/unit", "integration/"]\n', "utf-8"
    )
    bare = tmp_path / "bare"
    bare.mkdir()

    layout = repo_layout(tmp_path)
    inputs = dataclasses.replace(_inputs([_nudge_hook(), resolved_hook()]), layout=layout)
    hooks = render_guard_config(inputs)["hooks"]
    consumer = dataclasses.replace(
        _inputs([_nudge_hook({"test_roots": ["checks"]})]), layout=layout
    )

    assert layout == RepoLayout(source_roots=("src",), test_roots=("tests/unit", "integration"))
    assert repo_layout(bare) == RepoLayout(source_roots=(".",), test_roots=("tests",))
    assert hooks["tests-with-source-nudge"]["handlers"]["stop"]["config"] == {
        "source_roots": ["src"],
        "test_roots": ["tests/unit", "integration"],
    }
    assert "source_roots" not in hooks["guard-x"]["handlers"]["pre_tool_use"]["config"]
    rendered = render_guard_config(consumer)["hooks"]["tests-with-source-nudge"]
    assert rendered["handlers"]["stop"]["config"]["test_roots"] == ["checks"]  # consumer wins


# --- prompt-write-scope-guard scopes (specs/prK-hook-pack.md §E.3) ----------------------


def _scoped_prompt(slash: str, scope: dict[str, Any]) -> Prompt:
    prompt = _prompt(slash)
    prompt.frontmatter.write_scope = scope
    return prompt


def test_prompt_scopes_rendered_into_the_scope_guard_config_only() -> None:
    guard = resolved_hook("prompt-write-scope-guard", config={"keep": 1})
    other = resolved_hook("guard-y")
    prompts = [
        _scoped_prompt("review", {"read_only": True}),
        _scoped_prompt("generate-tests", {"globs": ["tests/**", "**/conftest.py"]}),
        _prompt("refactor"),  # no write_scope: no row
    ]
    inputs = dataclasses.replace(_inputs([guard, other]), prompts=prompts)

    hooks = render_guard_config(inputs)["hooks"]

    assert hooks["prompt-write-scope-guard"]["handlers"]["pre_tool_use"]["config"] == {
        "keep": 1,
        "scopes": {
            "generate-tests": {"globs": ["tests/**", "**/conftest.py"]},
            "review": {"read_only": True},
        },
    }
    assert hooks["guard-y"] == other.to_json()
    assert guard.handlers["pre_tool_use"].config == {"keep": 1}  # the resolved hook is untouched


def test_runtime_reads_the_scopes_back() -> None:
    guard = resolved_hook("prompt-write-scope-guard")
    scoped = [_scoped_prompt("x", {"read_only": True})]
    inputs = dataclasses.replace(_inputs([guard]), prompts=scoped)

    parsed = parse_guard_config(serialize_guard_config(render_guard_config(inputs)))

    assert isinstance(parsed, GuardConfig)
    spec = parsed.hooks["prompt-write-scope-guard"].handlers[EventName.PRE_TOOL_USE]
    assert spec.config["scopes"] == {"x": {"read_only": True}}
