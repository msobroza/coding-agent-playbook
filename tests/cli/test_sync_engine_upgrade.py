"""One ``playbook sync`` after an engine upgrade clears the version warnings (issue #283).

``[engine] version`` is what ``playbook init`` wrote once, under the engine
installed then; it is informational. Sync stamps the engine that rendered, the
installed one, into the lockfile, ``guard_config.json`` and ``machine.json``, so
the session briefing and ``playbook-hook doctor`` stop asking for a sync that
cannot clear them.
"""

from __future__ import annotations

import json
import re
import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.config.pin import (
    INTERPRETER_PIN,
    read_machine_pins,
    write_machine_pins,
)
from coding_agent_playbook.hook_runtime.diagnostics.doctor import run_doctor
from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateArgs, run
from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME
from coding_agent_playbook.lockfile.model import Lockfile
from coding_agent_playbook.sync import pipeline as _sync
from coding_agent_playbook.sync._machine_local import RuntimePinWriter
from tests.cli.hook_repo import GUARD_CONFIG, hook_deps, make_hook_repo
from tests.engine_version import ENGINE_VERSION
from tests.fakes import FakeGitClient
from tests.hook_payloads import PROJECT_DIR, load_hook_payload
from tests.hook_runtime.fakes import FakeClock, FakeGit, FakeProc, FakeTrustStore

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = [pytest.mark.usefixtures("sample_hook_handlers"), pytest.mark.catalog]

#: The engine that ran ``playbook init`` (and the last sync) before the upgrade.
OLD_ENGINE = "0.0.1"
_ENGINE_LINE = re.compile(r'^version = "[^"]*"$', re.M)


def _upgraded_repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    """A hook repo whose config, lockfile and ``machine.json`` :data:`OLD_ENGINE` wrote."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo, external=False)
    config = repo / ".coding-agent-playbook.toml"
    text = config.read_text(encoding="utf-8")
    config.write_text(_ENGINE_LINE.sub(f'version = "{OLD_ENGINE}"', text), encoding="utf-8")
    lockfile = f'schema_version = 2\nengine_version = "{OLD_ENGINE}"\nrendered_at = "2026-01-01T00:00:00Z"\n'
    (repo / ".coding-agent-playbook.lock").write_text(lockfile, encoding="utf-8")
    (repo / ".git").mkdir()
    write_machine_pins(tools={}, engine_version=OLD_ENGINE, git_dir=str(repo / ".git"))
    return repo


def _runtime_deps(**overrides: Any) -> RuntimeDeps:
    git = FakeGit(
        symbolic_refs={"HEAD": "feature/upgrade", "refs/remotes/origin/HEAD": "origin/main"},
        config={"user.name": "Dev Eloper", "user.email": "dev@corp.invalid"},
    )
    fields: dict[str, Any] = {
        "env": {},
        "proc": FakeProc(),
        "clock": FakeClock(),
        "trust": FakeTrustStore(),
        "git": git,
        "home": "/home/dev",
        "platform": "linux",
        **overrides,
    }
    return RuntimeDeps(**fields)


def _briefing(repo: Path) -> list[str]:
    case = load_hook_payload("claude_code", "session_start", "ssb_startup_clean")
    payload = case.raw.decode("utf-8").replace(PROJECT_DIR, str(repo)).encode("utf-8")
    args = SimulateArgs(event=EventName.SESSION_START, repo=str(repo))
    report = run(args, payload, deps=_runtime_deps())
    return [line for text in report.trace.combined.context for line in text.splitlines()]


def _doctor_pin(repo: Path) -> tuple[str, str]:
    pin = (repo / ".git" / STATE_DIR_NAME / INTERPRETER_PIN).read_text(encoding="utf-8").strip()
    facts = {"version": [3, 13], "isolated": 1, "engine": ENGINE_VERSION}
    proc = FakeProc()
    proc.script([pin, "-I", "-c"], stdout=json.dumps(facts).encode())
    checks = {check.name: check for check in run_doctor(str(repo), deps=_runtime_deps(proc=proc))}
    return checks["pin"].severity, checks["pin"].detail


def test_one_sync_after_an_upgrade_stamps_the_installed_engine_everywhere(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _upgraded_repo(tmp_path, make_synthetic_repo)
    deps = hook_deps(tmp_path / "state", pins=RuntimePinWriter())

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=deps) == 0

    lock = Lockfile.from_dict(tomllib.loads((repo / ".coding-agent-playbook.lock").read_text()))
    guard_config = json.loads((repo / GUARD_CONFIG).read_text(encoding="utf-8"))
    pins = read_machine_pins(git_dir=str(repo / ".git"))
    assert pins is not None
    assert (lock.engine_version, guard_config["engine_version"], pins.engine_version) == (
        ENGINE_VERSION,
        ENGINE_VERSION,
        ENGINE_VERSION,
    )
    assert f'version = "{OLD_ENGINE}"' in (repo / ".coding-agent-playbook.toml").read_text()
    briefing = _briefing(repo)
    assert briefing[0].startswith("PLAYBOOK-GUARDS: OK"), briefing
    assert not [line for line in briefing if line.startswith("Engine ")], briefing
    assert not [line for line in briefing if "machine.json" in line], briefing
    severity, detail = _doctor_pin(repo)
    assert "differs" not in detail
    assert severity == "ok", detail
