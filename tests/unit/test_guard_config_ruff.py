"""Sync-time ruff tables of the §E.3 post-edit pipeline (specs/prK-hook-pack.md §E.3, OQ-37).

``guard_config.json`` gets only the repo's own ruff selection (machine-
independent); the pinned ruff's rule set is probed at sync, through the
injected ``ProcPort`` (``FakeRuff``), into ``machine.json`` ``tools.ruff.drop``.
No test spawns ruff.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook._guard_config_ruff import (
    RuffSelection,
    RuleCache,
    RuleProbe,
    probe_ruff_rules,
    read_project_ruff_selection,
    ruff_candidate_codes,
    ruff_drop_codes,
    ruff_table,
)
from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.guard_config import (
    GuardConfigInputs,
    render_guard_config,
    serialize_guard_config,
)
from coding_agent_playbook.hook_policy import ResolvedHandler
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hook_runtime.state import StateStore
from coding_agent_playbook.sync._machine_local import SyncHookDeps, write_pins
from tests.fakes import FakePinWriter
from tests.hook_runtime.fakes import FakeRuff
from tests.hook_samples import resolved_hook

if TYPE_CHECKING:
    from pathlib import Path

#: ``ruff rule --all --output-format json`` rows (the parts read), ruff 0.17 shape.
RULES_017: list[dict[str, Any]] = [
    {"code": "B006", "preview": False, "status": {"Stable": {"since": "0.0.1"}}},
    {"code": "UP045", "preview": False, "status": {"Stable": {"since": "0.12.0"}}},
    {"code": "DOC201", "preview": True, "status": {"Preview": {"since": "0.5.0"}}},
    {"code": "UP038", "preview": False, "status": {"Removed": {"since": "0.13.0"}}},
    {"code": None, "name": "invalid-syntax"},
]
#: An older ruff: no ``status`` key, and UP045 did not exist yet.
RULES_OLD: list[dict[str, Any]] = [{"code": "B006", "preview": False}]
CANDIDATES = ["B006", "DOC201", "UP038", "UP045", "ZZZ999"]


def _program(tmp_path: Path, name: str = "ruff", body: bytes = b"#!/bin/sh\n") -> str:
    path = tmp_path / name
    path.write_bytes(body)
    path.chmod(0o755)
    return str(path)


# --- the project's selection -------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        (
            "pyproject.toml",
            '[tool.ruff.lint]\nselect = ["E", "I", "UP"]\nextend-select = ["B"]\n'
            'ignore = ["E501"]\nextend-ignore = ["UP007"]\n',
            RuffSelection(("B", "E", "I", "UP"), ("E501", "UP007"), default_select=False),
        ),
        (
            "pyproject.toml",
            '[tool.ruff]\nselect = ["F", "I"]\n',  # the deprecated top-level keys
            RuffSelection(("F", "I"), (), default_select=False),
        ),
        (
            "ruff.toml",
            '[lint]\nselect = ["ALL"]\nignore = ["D"]\n',
            RuffSelection(("ALL",), ("D",), False),
        ),
        ("pyproject.toml", '[project]\nname = "x"\n', RuffSelection()),  # not a ruff config
        ("ruff.toml", 'line-length = 100\n[lint]\nextend-select = ["I"]\n', RuffSelection(("I",))),
        ("pyproject.toml", "[tool.ruff\n", RuffSelection()),  # malformed: ruff's defaults
    ],
    ids=[
        "pyproject-lint",
        "pyproject-legacy",
        "ruff-toml",
        "no-tool-ruff",
        "defaults+extend",
        "bad",
    ],
)
def test_project_select_from_pyproject_ruff_toml_and_defaults(
    tmp_path: Path, name: str, text: str, expected: RuffSelection
) -> None:
    (tmp_path / name).write_text(text, encoding="utf-8")

    assert read_project_ruff_selection(tmp_path) == expected


def test_dot_ruff_toml_wins_over_ruff_toml_over_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E"]\n', "utf-8")
    (tmp_path / "ruff.toml").write_text('[lint]\nselect = ["F"]\n', "utf-8")
    assert read_project_ruff_selection(tmp_path).select == ("F",)

    (tmp_path / ".ruff.toml").write_text('[lint]\nselect = ["I"]\n', "utf-8")
    assert read_project_ruff_selection(tmp_path).select == ("I",)


@pytest.mark.parametrize(
    ("select", "ignore", "safe", "safe_ignore"),
    [
        (("B", "E", "F", "I", "UP", "W"), ("E501",), ["I", "UP"], []),
        (("E", "F"), (), [], []),
        (("ALL",), ("I",), ["UP"], []),
        (("I", "UP006", "UP007"), (), ["I", "UP006", "UP007"], []),
        (("I", "UP"), ("UP007",), ["I", "UP"], ["UP007"]),
        (("INP", "F"), (), [], []),  # INP is flake8-no-pep420, not isort
    ],
)
def test_safe_fix_select_is_I_UP_intersect_project(
    select: tuple[str, ...], ignore: tuple[str, ...], safe: list[str], safe_ignore: list[str]
) -> None:
    table = ruff_table(RuffSelection(select, ignore, default_select=False))

    assert table["safe_fix_select"] == safe
    assert table["safe_fix_ignore"] == safe_ignore
    assert table["project_select"] == list(select)


def test_default_selection_fixes_nothing() -> None:
    """Ruff's default selection changed in 0.17; the committed table cannot name it."""
    table = ruff_table(RuffSelection())

    assert table == {
        "default_select": True,
        "project_select": [],
        "project_ignore": [],
        "safe_fix_select": [],
        "safe_fix_ignore": [],
    }


# --- the pinned ruff's rule set ----------------------------------------------------------


def test_rule_all_drops_unknown_and_preview_codes(tmp_path: Path) -> None:
    ruff = FakeRuff(rules=RULES_017)

    probe = probe_ruff_rules([_program(tmp_path)], CANDIDATES, proc=ruff)

    assert probe.complete
    assert ruff_drop_codes(CANDIDATES, probe) == ["DOC201", "UP038", "ZZZ999"]
    assert ruff.kinds() == ["rule-all"]
    assert ruff.calls[0].argv[1:] == ("rule", "--all", "--output-format", "json")


def test_per_code_fallback_when_rule_all_json_unsupported(tmp_path: Path) -> None:
    """OQ-37: one ``ruff rule <code>`` per code, at sync only."""
    old = FakeRuff(rules=RULES_OLD, rule_all=False)

    probe = probe_ruff_rules([_program(tmp_path)], ["B006", "UP045"], proc=old)

    assert not probe.complete
    assert probe.statuses == {"B006": "stable", "UP045": "unknown"}
    assert ruff_drop_codes(["B006", "UP045"], probe) == ["UP045"]
    assert old.kinds() == ["rule-all", "rule", "rule"]
    assert [c.argv[1:3] for c in old.calls[1:]] == [("rule", "B006"), ("rule", "UP045")]


def test_probe_cached_per_ruff_signature(tmp_path: Path) -> None:
    program = _program(tmp_path)
    cache = RuleCache(StateStore(tmp_path / "state"))
    first, second = FakeRuff(rules=RULES_017), FakeRuff(rules=RULES_017)

    probe_ruff_rules([program], CANDIDATES, proc=first, cache=cache)
    cached = probe_ruff_rules([program], ["B006", "NEW001"], proc=second, cache=cache)
    _program(tmp_path, body=b"#!/bin/sh\n# upgraded\n")  # a new ruff: a new signature
    probe_ruff_rules([program], ["B006"], proc=second, cache=cache)

    assert first.kinds() == ["rule-all"]
    assert cached.status("NEW001") == "unknown"  # a complete listing answers every code
    assert second.kinds() == ["rule-all"]  # only the upgraded ruff was asked again


def test_per_code_answers_are_cached_and_extended(tmp_path: Path) -> None:
    program, cache = _program(tmp_path), RuleCache(StateStore(tmp_path / "state"))
    ruff = FakeRuff(rules=RULES_OLD, rule_all=False)

    probe_ruff_rules([program], ["B006"], proc=ruff, cache=cache)
    probe = probe_ruff_rules([program], ["B006", "UP045"], proc=ruff, cache=cache)

    assert [c.argv[1:3] for c in ruff.calls if ruff.kind(c.argv[1:]) == "rule"] == [
        ("rule", "B006"),
        ("rule", "UP045"),  # B006 came from the cache
    ]
    assert probe.statuses == {"B006": "stable", "UP045": "unknown"}


def test_unanswered_code_is_dropped_and_asked_again(tmp_path: Path) -> None:
    ruff = FakeRuff(rules=RULES_OLD, rule_all=False, timeouts={"rule"})

    probe = probe_ruff_rules([_program(tmp_path)], ["B006"], proc=ruff)

    assert probe.status("B006") is None
    assert ruff_drop_codes(["B006"], probe) == ["B006"]
    assert RuleProbe(False, {}).covers(["B006"]) is False


def test_candidate_codes_come_from_builtin_lint_codes_config() -> None:
    lint = resolved_hook("lint-x", events=("post_tool_use",))
    handler = ResolvedHandler("builtin", name="x", config={"lint_codes": ["B006", "ANN001"]})
    warn = ResolvedHandler("builtin", name="y", config={"lint_codes": {"warn": ["B006"]}})
    hooks = [
        _with_handler(lint, handler),
        _with_handler(resolved_hook("lint-y", events=("post_tool_use",)), warn),
        resolved_hook("guard-z"),
    ]

    assert ruff_candidate_codes(hooks) == ["ANN001", "B006"]


def _with_handler(hook: Any, handler: ResolvedHandler) -> Any:
    import dataclasses

    return dataclasses.replace(hook, handlers={"post_tool_use": handler})


# --- machine independence ----------------------------------------------------------------


def test_guard_config_ruff_tables_machine_independent(tmp_path: Path) -> None:
    """Two ruff versions: identical guard_config.json bytes, different machine.json drops."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F", "I", "UP"]\n', encoding="utf-8"
    )
    configs: list[bytes] = []
    drops: list[dict[str, list[str]]] = []
    for rules in (RULES_017, RULES_OLD):
        venv_ruff = tmp_path / ".venv" / "bin" / "ruff"
        venv_ruff.parent.mkdir(parents=True, exist_ok=True)
        venv_ruff.write_bytes(repr(rules).encode())
        venv_ruff.chmod(0o755)
        pins = FakePinWriter()
        deps = SyncHookDeps(
            pins=pins, which=lambda _: None, proc=FakeRuff(rules=rules), rule_cache=lambda _: None
        )
        write_pins(tmp_path, deps, engine_version="0.2.0", ruff_codes=["B006", "UP045"])
        inputs = GuardConfigInputs(
            hooks=[],
            hooks_config=HooksConfig(enabled=True),
            guardrails=GuardrailsConfig(),
            engine_version="0.2.0",
            ruff=read_project_ruff_selection(tmp_path),
        )
        configs.append(serialize_guard_config(render_guard_config(inputs)))
        drops.append(pins.drops)

    assert configs[0] == configs[1]
    assert b'"safe_fix_select":["I","UP"]' in configs[0]
    assert drops == [{}, {"ruff": ["UP045"]}]


def test_runtime_reads_the_ruff_table_back() -> None:
    inputs = GuardConfigInputs(
        hooks=[],
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        ruff=RuffSelection(("E", "I", "UP"), ("UP007",), default_select=False),
    )

    parsed = parse_guard_config(serialize_guard_config(render_guard_config(inputs)))

    assert isinstance(parsed, GuardConfig)
    assert parsed.tables["ruff"]["safe_fix_select"] == ["I", "UP"]
    assert parsed.tables["ruff"]["safe_fix_ignore"] == ["UP007"]


def test_write_pins_prefers_the_project_venv_ruff(tmp_path: Path) -> None:
    venv_ruff = tmp_path / ".venv" / "bin" / "ruff"
    venv_ruff.parent.mkdir(parents=True)
    venv_ruff.write_bytes(b"#!/bin/sh\n")
    venv_ruff.chmod(0o755)
    pins = FakePinWriter()
    deps = SyncHookDeps(pins=pins, which={"ruff": "/usr/bin/ruff", "cz": "/usr/bin/cz"}.get)

    write_pins(tmp_path, deps, engine_version="0.2.0")

    assert pins.tools == {"ruff": [str(venv_ruff)], "cz": ["/usr/bin/cz"]}
    assert pins.drops == {}  # no hook asked for extra codes: ruff was never spawned
