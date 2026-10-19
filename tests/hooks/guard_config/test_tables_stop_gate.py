"""K6: the ``stop_gate`` table and the Stop deadline (specs/prK-hook-pack.md §E.0.5, §D.4).

The Stop coordinator's table, compiled through ``compile_guard_config``: its stage
records (the hooks' configs and the detected dev tools), its budget and block budget,
the verify commands and the claim patterns. Machine-independent like the rest of
``guard_config.json``.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hooks.guard_config.compile import (
    compile_guard_config,
    serialize_guard_config,
)
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs
from coding_agent_playbook.hooks.registrations.plan import resolved_deadlines_ms
from tests.hook_samples import resolved_hook
from tests.hooks.guard_config.compile_kit import compiled_document, request_for

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook


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


def _stop_gate(
    repo: Path, hooks: list[ResolvedHook], facts: dict[str, Any] | None = None
) -> dict[str, Any]:
    request = dataclasses.replace(request_for(repo, hooks), detect=DetectInputs(facts=facts or {}))
    gate: dict[str, Any] = compiled_document(request)["stop_gate"]
    return gate


def test_stop_gate_derived_from_hook_config_and_dev_tools(repo: Path) -> None:
    config = {
        "budget_s": 4.5,
        "max_blocks": 3,
        "verify_commands": ["uv run --frozen --no-sync pytest -q"],
        "claim_patterns": ["(?i)shipped it"],
    }

    gate = _stop_gate(repo, _stop_hooks(config), {"dev_tools": {"ruff"}})

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
        {  # K10: the coverage stage runs the project's pytest (STAGE_HOOK_COMMANDS)
            "name": "coverage",
            "owner": "coverage-diff-gate",
            "cost": "execution",
            "tool": "project_python",
            "args": ["-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-q"],
            "timeout_s": 60.0,
            "needs_diff": True,
            "mode": "block",
        },
    ]
    assert gate["verify_commands"] == [
        {"id": "custom-1", "argv": ["uv", "run", "--frozen", "--no-sync", "pytest", "-q"]}
    ]
    assert gate["claim_patterns"][-1] == "(?i)shipped it" and len(gate["claim_patterns"]) > 1
    parsed = parse_guard_config(compile_guard_config(request_for(repo)).data)
    assert isinstance(parsed, GuardConfig) and parsed.tables["stop_gate"]["stages"] == []


def test_opted_in_execution_stages_join_the_table_and_the_deadline(repo: Path) -> None:
    hooks = _stop_hooks({"stages": ["tests", "typecheck"]})[:1]

    gate = _stop_gate(repo, hooks)
    deadlines = compiled_document(request_for(repo, hooks))["deadlines_ms"]

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


def test_verify_commands_derived_when_absent(repo: Path) -> None:
    gate = _stop_gate(repo, _stop_hooks(), {"dev_tools": {"pytest", "mypy", "ruff"}})

    assert gate["verify_commands"] == [
        {"id": "lint", "argv": ["ruff", "check"]},
        {"id": "format", "argv": ["ruff", "format"]},
        {"id": "typecheck", "argv": ["mypy"]},
        {"id": "tests", "argv": ["pytest"]},
    ]
    assert (gate["budget_s"], gate["max_blocks"]) == (3.0, 2)
    assert _stop_gate(repo, _stop_hooks())["verify_commands"] == []


def test_stop_gate_is_machine_independent(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datas: list[bytes] = []
    for prefix, home in (("/opt/venv-a", tmp_path / "home-a"), ("/srv/venv-b", tmp_path / "b")):
        monkeypatch.setattr(sys, "prefix", prefix)
        monkeypatch.setenv("HOME", str(home))
        gate = _stop_gate(repo, _stop_hooks({"budget_s": 4.0}), {"dev_tools": {"ruff", "pytest"}})
        datas.append(serialize_guard_config(gate))

    assert datas[0] == datas[1]
    text = datas[0].decode("ascii")
    assert str(tmp_path) not in text and "/opt/" not in text and "/srv/" not in text


def test_stop_deadline_formula_includes_exec_timeouts(repo: Path) -> None:
    hooks = _stop_hooks({"budget_s": 4.0})
    coverage = {"stage": "coverage"}
    slow = [
        hooks[0],
        resolved_hook("coverage-diff-gate", events=("stop",), timeout=900.0, config=coverage),
    ]

    deadlines = compiled_document(request_for(repo, hooks))["deadlines_ms"]

    assert deadlines["stop"] == 64_000  # 1000 * (budget_s 4.0 + the coverage stage's 60 s)
    assert deadlines == resolved_deadlines_ms(hooks)
    assert resolved_deadlines_ms(slow)["stop"] == 595_000  # the engine cap
