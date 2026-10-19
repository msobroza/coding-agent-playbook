"""The pinned ruff's rule set, probed at sync (specs/prK-hook-pack.md §E.3, OQ-37).

The probe asks the pinned ruff through the injected ``ProcPort`` (``FakeRuff``)
and lands in ``machine.json`` ``tools.ruff.drop``; ``guard_config.json`` never
depends on it (``test_tables_ruff``). The last test pins which ruff
``write_pins`` names, the program the probe asks. No test spawns ruff.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.hook_runtime.state.store import StateStore
from coding_agent_playbook.hooks.guard_config.ruff_probe import (
    RuleCache,
    RuleProbe,
    probe_ruff_rules,
    ruff_candidate_codes,
    ruff_drop_codes,
    ruff_probe_codes,
)
from coding_agent_playbook.hooks.resolution.resolved import ResolvedHandler
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


def test_probe_codes_add_the_quality_family(tmp_path: Path) -> None:
    """The pinned ruff is asked about every code D1 may add: the hooks' lint codes and the
    committed quality family (§F.2.2, its defaults without one), each once, sorted."""
    (tmp_path / CONFIG_FILENAME).write_text(
        '[metrics.ruff_violations]\nfamilies = { quality = ["PLR1702", "C901", "B006"] }\n',
        encoding="utf-8",
    )
    handler = ResolvedHandler("builtin", name="x", config={"lint_codes": ["B006", "ANN001"]})
    lint = _with_handler(resolved_hook("lint-x", events=("post_tool_use",)), handler)
    bare = tmp_path / "bare"
    bare.mkdir()

    assert ruff_probe_codes([lint], tmp_path) == ["ANN001", "B006", "C901", "PLR1702"]
    assert ruff_probe_codes([], bare) == ["C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915"]


# --- the program the pins name -----------------------------------------------------------


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
