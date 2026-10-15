"""``playbook-hook doctor``: environment checks, exit codes, read-only (specs/prK-lifecycle-hooks.md §D.9).

The pinned interpreter's probe runs through ``FakeProc``; everything else is
a real fixture worktree (pin file, ``machine.json``, state root, lockfile).
"""

from __future__ import annotations

import io
import json
import os
import stat
import sys
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime._doctor_checks import PROBE
from coding_agent_playbook.hook_runtime.cli import main as cli_main
from coding_agent_playbook.hook_runtime.doctor import Check, exit_code, main, run_doctor
from coding_agent_playbook.hook_runtime.pin import INTERPRETER_PIN, write_machine_pins
from coding_agent_playbook.security.trust import HandlerApproval, sha256_of_json
from tests.hook_runtime.fakes import FakeProc, FakeTrustStore
from tests.hook_runtime.guard_repo import GuardRepo, hook_record

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps

_PROBE_OK = json.dumps({"version": [3, 13], "isolated": 1, "engine": "0.1.0a0"}).encode()


def _healthy(tmp_path: Path) -> tuple[GuardRepo, str]:
    """A synced worktree: config + lock, a 0700 state root, an executable pin, machine.json."""
    repo = GuardRepo.create(tmp_path)
    repo.install(hook_record("guard-a"))
    repo.state_root.mkdir(mode=0o700)
    os.chmod(repo.state_root, 0o700)
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    (repo.state_root / INTERPRETER_PIN).write_text(f"{python}\n", encoding="utf-8")
    write_machine_pins(
        tools={"ruff": [str(python)]}, engine_version="0.1.0a0", git_dir=repo.repo.git_dir
    )
    return repo, str(python)


def _deps(
    runtime_deps: Callable[..., RuntimeDeps], python: str, stdout: bytes = _PROBE_OK, **kw: Any
) -> RuntimeDeps:
    proc = FakeProc()
    proc.script([python, "-I", "-c"], stdout=stdout)
    return runtime_deps(proc=proc, **kw)


def _severities(checks: list[Check]) -> dict[str, str]:
    return {check.name: check.severity for check in checks}


def test_doctor_healthy_against_canned_config_exits_0(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, python = _healthy(tmp_path)
    deps = _deps(runtime_deps, python)

    checks = run_doctor(str(repo.root), deps=deps)

    assert _severities(checks) == {
        "guard_config": "ok",
        "pin": "ok",
        "state": "ok",
        "machine.json": "ok",
        "trust": "ok",
    }
    assert exit_code(checks) == 0
    (call,) = deps.proc.calls  # type: ignore[attr-defined]
    assert call.argv == (python, "-I", "-c", PROBE)


def _break_digest(repo: GuardRepo, python: str) -> None:
    repo.write_lock("0" * 64)


def _drop_pin(repo: GuardRepo, python: str) -> None:
    (repo.state_root / INTERPRETER_PIN).unlink()


def _drop_machine(repo: GuardRepo, python: str) -> None:
    (repo.state_root / "machine.json").unlink()


def _touch_tool(repo: GuardRepo, python: str) -> None:
    with open(python, "a", encoding="utf-8") as handle:
        handle.write("# changed\n")


def _loosen_state(repo: GuardRepo, python: str) -> None:
    os.chmod(repo.state_root, 0o755)


@pytest.mark.parametrize(
    ("damage", "check", "severity", "code"),
    [
        (_break_digest, "guard_config", "broken", 2),
        (_drop_pin, "pin", "broken", 2),
        (_drop_machine, "machine.json", "degraded", 1),
        (_touch_tool, "machine.json", "degraded", 1),
        (_loosen_state, "state", "degraded", 1),
    ],
)
def test_doctor_digest_mismatch_or_missing_pin_is_degraded_or_broken(
    tmp_path: Path,
    runtime_deps: Callable[..., RuntimeDeps],
    damage: Callable[[GuardRepo, str], None],
    check: str,
    severity: str,
    code: int,
) -> None:
    repo, python = _healthy(tmp_path)
    damage(repo, python)

    checks = run_doctor(str(repo.root), deps=_deps(runtime_deps, python))

    assert _severities(checks)[check] == severity
    assert exit_code(checks) == code


@pytest.mark.parametrize(
    ("stdout", "returncode", "severity", "needle"),
    [
        (
            json.dumps({"version": [3, 8], "isolated": 1, "engine": "0.1.0a0"}).encode(),
            0,
            "broken",
            ">= 3.12",
        ),
        (
            json.dumps({"version": [3, 13], "isolated": 0, "engine": "0.1.0a0"}).encode(),
            0,
            "broken",
            "-I",
        ),
        (
            json.dumps({"version": [3, 13], "isolated": 1, "engine": "9.9"}).encode(),
            0,
            "degraded",
            "differs",
        ),
        (b"", 1, "broken", "cannot import"),
        (b"garbage", 0, "broken", "unexpected probe output"),
    ],
)
def test_pin_probe_findings(
    tmp_path: Path,
    runtime_deps: Callable[..., RuntimeDeps],
    stdout: bytes,
    returncode: int,
    severity: str,
    needle: str,
) -> None:
    repo, python = _healthy(tmp_path)
    proc = FakeProc()
    proc.script([python], stdout=stdout, returncode=returncode)

    pin = next(
        c for c in run_doctor(str(repo.root), deps=runtime_deps(proc=proc)) if c.name == "pin"
    )

    assert pin.severity == severity
    assert needle in pin.detail


def test_trust_reports_unapproved_external_handlers(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, python = _healthy(tmp_path)
    external = {
        "kind": "external",
        "argv": ["python", ".coding-agent-playbook/hooks/scripts/ext/a.py"],
    }
    repo.install(hook_record("ext", handler=external, script_sha256="ab", source_package="acme"))
    approval = HandlerApproval("acme", "python", sha256_of_json([]), "ab")

    missing = run_doctor(str(repo.root), deps=_deps(runtime_deps, python))
    approved = run_doctor(
        str(repo.root), deps=_deps(runtime_deps, python, trust=FakeTrustStore({"ext": approval}))
    )

    assert _severities(missing)["trust"] == "degraded"
    assert _severities(approved)["trust"] == "ok"


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {
        str(path): (path.stat().st_mtime_ns, stat.S_IMODE(path.stat().st_mode))
        for path in sorted(root.rglob("*"))
    }


def test_repin_overwrites_and_doctor_is_otherwise_read_only(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, python = _healthy(tmp_path)
    _loosen_state(repo, python)  # a non-0700 root must be reported, not fixed
    deps = _deps(runtime_deps, python)
    before = _snapshot(repo.root)

    run_doctor(str(repo.root), deps=deps)
    assert _snapshot(repo.root) == before

    checks = run_doctor(str(repo.root), deps=deps, repin=sys.executable)
    pinned = (repo.state_root / INTERPRETER_PIN).read_text(encoding="utf-8")

    assert pinned == f"{sys.executable}\n"
    assert checks[0] == Check("repin", "ok", f"pinned {sys.executable}")


def test_doctor_outside_git_is_broken(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    checks = run_doctor(str(tmp_path), deps=runtime_deps())

    assert [(c.name, c.severity) for c in checks] == [("repo", "broken")]


def test_main_json_format_and_cli_route(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps], capsys: pytest.CaptureFixture[str]
) -> None:
    repo, python = _healthy(tmp_path)
    out = io.StringIO()

    code = main(
        ["--repo", str(repo.root), "--format", "json"], deps=_deps(runtime_deps, python), stdout=out
    )
    routed = cli_main(["doctor", "--repo", str(repo.root)], deps=_deps(runtime_deps, python))

    report = json.loads(out.getvalue())
    assert (code, report["status"], report["exit_code"]) == (0, "healthy", 0)
    assert routed == 0
    assert "playbook-hook doctor: healthy" in capsys.readouterr().out


def test_usage_error_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--format", "yaml"]) == 2
    assert "invalid choice" in capsys.readouterr().err
