"""Docs-consistency guard: SPEC.md v0.20 documents the hook adapters, CLI and runtime (prK §J).

Track K11 applies the §J SPEC amendment rows; ``test_docs_lifecycle_hooks_spec``
covers the model, config and architecture rows, and this module the rest: the
adapter contract (§10), the CLI and the ``playbook-hook`` runtime (§12), the
pre-commit ids (§13), the lockfile (§14.4), tests (§16), security (§17) and the
new metrics (§21). Every name a test requires comes from the landed code (the
``Adapter`` members, ``cli.parser._SUBCOMMANDS`` and the argparse flags, ``CI_STEPS``,
the ``playbook-hook`` usage, ``STOP_STAGE_ORDER``, ``.pre-commit-hooks.yaml``,
the starter template, the OpenCode floor, the metric families), so a command,
flag, step, hook id or metric that lands without documentation fails here.
Prose-only: the tests read markdown and introspect constants, never run engine
behaviour.
"""

from __future__ import annotations

import argparse
import re
import typing
from pathlib import Path

import pytest
import yaml

from coding_agent_playbook.adapters._claude_hooks import CLAUDE_HEARTBEAT_LINE
from coding_agent_playbook.adapters._harness_hooks import HOOKS_SIDECAR
from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter
from coding_agent_playbook.adapters.shared_skills_adapter import SharedSkillsAdapter
from coding_agent_playbook.cli.parser import _SUBCOMMANDS, build_parser
from coding_agent_playbook.commands._sync_hooks import HOOKS_NOTICE
from coding_agent_playbook.commands._validate_context import config_less_notes
from coding_agent_playbook.commands.init import _render_fresh_pre_commit
from coding_agent_playbook.commands.twins._ci_commit_convention import PR_TITLE_ENV
from coding_agent_playbook.commands.twins.ci import CI_STEPS
from coding_agent_playbook.hook_registrations import (
    LAUNCHER_PATH,
    OPENCODE_SHIM_PATH,
    STRICT_LAUNCH_FLAG,
    claude_command,
)
from coding_agent_playbook.hook_runtime._doctor_opencode import OPENCODE_MIN_VERSION
from coding_agent_playbook.hook_runtime.cli import ASYNC_FLAG, USAGE
from coding_agent_playbook.hook_runtime.stop.stages import STOP_STAGE_ORDER
from coding_agent_playbook.lockfile.model import ProvenanceKind
from coding_agent_playbook.metrics_gate.policy import METRIC_FAMILIES, OPT_IN_METRICS
from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section, _spec_text

_ROOT = Path(__file__).resolve().parents[2]
_BUILTIN_ADAPTERS = (
    ClaudeCodeAdapter,
    AgentsMdAdapter,
    OpenCodeAdapter,
    AgentHarnessAdapter,
    ContinueAdapter,
    SharedSkillsAdapter,
)
#: The §12 subcommands added by PR K: each documents every flag its parser declares.
_NEW_SUBCOMMANDS = (
    "ci",
    "gate-scan",
    "scan-secrets",
    "scan-sinks",
    "check-deps",
    "check-commit-trailers",
    "check-notebooks",
)
_RUNNER_SUBCOMMANDS = sorted(set(re.findall(r"playbook-hook (\w+|--version)", USAGE)))


def _cli_section(name: str) -> str:
    """The SPEC's ``### 12.N `playbook <name>``` section, up to the next heading of its level."""
    text = _spec_text()
    match = re.search(rf"^### 12\.\d+ `playbook {re.escape(name)}`", text, re.MULTILINE)
    assert match is not None, f"SPEC §12 has no '### 12.N `playbook {name}`' heading"
    ends = [text.find(mark, match.end()) for mark in ("\n### ", "\n## ")]
    return text[match.start() : min(end for end in ends if end > 0)]


def _subcommand_flags(name: str) -> list[str]:
    """Every ``--flag`` the ``playbook <name>`` parser declares, ``--help`` aside."""
    parser = build_parser()
    group = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    options = (opt for action in group.choices[name]._actions for opt in action.option_strings)
    return [opt for opt in options if opt.startswith("--") and opt != "--help"]


def _listing_of(member: str) -> str:
    """How the §10.1 code block spells an ``Adapter`` member: a ``def`` or a class attribute."""
    return f"def {member}(" if callable(getattr(Adapter, member)) else f"{member}: ClassVar"


def test_section_10_1_documents_every_adapter_hook_method() -> None:
    abc = _spec_section("### 10.1 Adapter ABC", "### 10.2 Continue adapter")
    block = abc[: abc.index("```\n", abc.index("```python") + 1)]
    members = [name for name in vars(Adapter) if not name.startswith("_")]
    missing = [name for name in members if _listing_of(name) not in block]
    assert not missing, f"SPEC §10.1 code block lacks Adapter members {missing}"
    assert "hooks_config: HooksConfig | None = None" in block


def test_section_10_1_drops_stale_finalize_sentence() -> None:
    abc = _spec_section("### 10.1 Adapter ABC", "### 10.2 Continue adapter")
    assert "only ClaudeCodeAdapter overrides `finalize()`" not in _spec_text()
    overriding = [cls.__name__ for cls in _BUILTIN_ADAPTERS if "finalize" in vars(cls)]
    assert [name for name in overriding if f"`{name}`" not in abc] == []


def test_section_10_3_2_documents_the_claude_settings_merge() -> None:
    claude = _spec_section("#### 10.3.2 Hooks", "### 10.4 AGENTS.md adapter")
    for token in (LAUNCHER_PATH, CLAUDE_HEARTBEAT_LINE, STRICT_LAUNCH_FLAG, "settings.local.json"):
        assert token in claude
    assert claude_command("pre_tool_use") in claude
    assert "[output] commit = false" in claude and "[output] commit = true" in claude


def test_section_10_4_documents_the_guardrails_section() -> None:
    agents = _spec_section("### 10.4 AGENTS.md adapter", "### 10.5 Adapter registration")
    assert "## Guardrails" in agents


def test_section_10_6_states_opencode_floor() -> None:
    opencode = _spec_section("### 10.6 OpenCode adapter", "### 10.7 Agent Harness adapter")
    floor = ".".join(str(part) for part in OPENCODE_MIN_VERSION)
    assert f"≥ {floor}" in opencode
    assert OPENCODE_SHIM_PATH in opencode
    assert "agent: plan" in _spec_section("#### 10.6.1", "#### 10.6.2")


def test_section_10_6_2_is_no_longer_out_of_scope() -> None:
    assert "Hook gap (out of scope for v1)" not in _spec_text()
    shim = _spec_section("#### 10.6.2", "#### 10.6.3")
    assert OPENCODE_SHIM_PATH in shim
    assert "setup()" in shim  # the inert V2 stub (OQ-11)


def test_section_10_7_documents_the_hook_sidecar() -> None:
    harness = _spec_section("#### 10.7.2", "### 10.8")
    assert f"{HOOKS_SIDECAR}/<id>/" in harness
    assert "rules/30-guardrail-<id>.md" in harness


@pytest.mark.parametrize("name", _SUBCOMMANDS)
def test_section_12_documents_every_cli_subcommand(name: str) -> None:
    assert _cli_section(name)


@pytest.mark.parametrize("name", _NEW_SUBCOMMANDS)
def test_section_12_documents_every_new_subcommand_flag(name: str) -> None:
    section = _cli_section(name)
    missing = [flag for flag in _subcommand_flags(name) if f"`{flag}" not in section]
    assert not missing, f"SPEC §12 `playbook {name}` lacks flags {missing}"


def test_section_12_1_and_12_2_document_the_hooks_opt_in() -> None:
    assert "--no-hooks" in _cli_section("init")
    assert HOOKS_NOTICE in _cli_section("sync")


def test_section_12_4_documents_the_hooks_block() -> None:
    check = _cli_section("check")
    assert "=== Hooks ===" in check
    assert "managed entry edited: .claude/settings.json#/hooks/PreToolUse" in check


@pytest.mark.parametrize("rule", [f"H{n}" for n in range(1, 22)])
def test_section_12_6_documents_config_less_validate_and_every_h_rule(rule: str) -> None:
    validate = _cli_section("validate")
    assert f"| {rule} |" in validate
    assert config_less_notes(Path("/repo"))[0] in validate
    assert "playbook sync aborted; no files were written." in validate


def test_section_12_7_renders_hook_ids() -> None:
    assert "--format hook_claude_settings" in _cli_section("render")


def test_section_12_11_lists_every_ci_step() -> None:
    ci = _cli_section("ci")
    missing = [step.name for step in CI_STEPS if f"| `{step.name}` |" not in ci]
    assert not missing, f"SPEC §12.11 lacks CI_STEPS rows {missing}"


def test_section_12_11_passes_pr_title_only_through_env() -> None:
    ci = _cli_section("ci")
    assert f"{PR_TITLE_ENV}: ${{{{ github.event.pull_request.title }}}}" in ci
    run_lines = [line for line in ci.splitlines() if line.strip().startswith("run:")]
    assert run_lines and not [line for line in run_lines if "github.event" in line]


def test_section_12_12_points_metrics_at_section_21_5() -> None:
    assert "§21.5" in _cli_section("metrics")


@pytest.mark.parametrize("sub", _RUNNER_SUBCOMMANDS)
def test_section_12_13_documents_playbook_hook_subcommands(sub: str) -> None:
    runtime = _spec_section("### 12.13 `playbook-hook`", "### 12.14")
    assert f"playbook-hook {sub}" in runtime
    assert ASYNC_FLAG in runtime


def test_spec_documents_stop_stage_order() -> None:
    runtime = _spec_section("### 12.13 `playbook-hook`", "### 12.14")
    assert " → ".join(f"`{stage}`" for stage in STOP_STAGE_ORDER) in runtime


def _precommit_ids() -> list[str]:
    hooks = yaml.safe_load((_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    return [hook["id"] for hook in hooks]


@pytest.mark.parametrize("hook_id", _precommit_ids())
def test_section_13_1_lists_every_shipped_precommit_hook(hook_id: str) -> None:
    section = _spec_section("### 13.1 The engine's", "### 13.2 Template")
    assert f"- id: {hook_id}\n" in section


def _starter_ids() -> list[str]:
    ids: list[str] = []
    for commit in (False, True):
        rendered = _render_fresh_pre_commit(
            output_commit=commit, commit_trailers=True, commitizen=True
        )
        repos = yaml.safe_load(rendered)["repos"]
        ids.extend(hook["id"] for repo in repos for hook in repo["hooks"])
    return sorted(set(ids))


@pytest.mark.parametrize("hook_id", _starter_ids())
def test_section_13_2_lists_every_starter_hook(hook_id: str) -> None:
    section = _spec_section("### 13.2 Template", "### 13.3 Merge")
    assert hook_id in section


def test_section_14_4_documents_scoped_entries() -> None:
    lock = _spec_section("### 14.4 Lockfile", "## 15. Eval abstractions")
    for stale in ("Not populated yet", "never appear today", "No adapter writes one yet"):
        assert stale not in lock
    assert 'scope = "json:/hooks/PreToolUse"' in lock
    assert "executable = true" in lock
    assert [k for k in typing.get_args(ProvenanceKind) if f"`{k}`" not in lock] == []


@pytest.mark.parametrize("folder", ["hook_runtime", "hooks", "security"])
def test_section_16_documents_the_hook_test_layout(folder: str) -> None:
    assert (_ROOT / "tests" / folder).is_dir()
    assert f"tests/{folder}/" in _spec_section("## 16. Testing strategy", "## 17. Security")


def test_spec_drops_the_gitleaks_promise() -> None:
    assert "gitleaks" not in _spec_section("### 16.4 CI", "### 16.5")
    secrets = _spec_section("### 17.3 Secrets", "### 17.4 Audit log")
    assert "baseline includes `gitleaks`" not in secrets
    assert "`playbook-secrets`" in secrets


def test_section_17_4_names_the_audit_writer() -> None:
    assert (_ROOT / "src" / "coding_agent_playbook" / "security" / "audit.py").is_file()
    assert "security/audit.py" in _spec_section("### 17.4 Audit log", "## 18. Rollout plan")


def _metric_names() -> list[str]:
    return sorted({*OPT_IN_METRICS, *(m for members in METRIC_FAMILIES.values() for m in members)})


@pytest.mark.parametrize("metric", _metric_names())
def test_section_21_documents_new_metrics(metric: str) -> None:
    families = _spec_section("### 21.2 The check families", "### 21.3 Registry")
    assert f"\n| `{metric}`" in families  # a table row of its own (``cbo`` carries a "(≈)")


def test_section_21_documents_selection_and_flags() -> None:
    registry = _spec_section("### 21.3 Registry", "### 21.4 Aggregation")
    for name in ("resolve_metric_selection", "METRIC_FAMILIES", "OPT_IN_METRICS", *METRIC_FAMILIES):
        assert name in registry
    gate = _spec_section("### 21.5 Standalone gate", "### 21.6 Eval")
    missing = [flag for flag in _subcommand_flags("metrics") if flag not in gate]
    assert not missing, f"SPEC §21.5 lacks playbook metrics flags {missing}"
