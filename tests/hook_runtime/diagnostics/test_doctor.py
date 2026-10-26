"""``playbook-hook doctor``: environment checks, exit codes, read-only (specs/prK-lifecycle-hooks.md §D.9).

The guard-decision-log summary rows (specs/prK-hook-pack.md §E.5) read decision
lines written straight into the fixture's state root.

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

from coding_agent_playbook.hook_runtime.cli import main as cli_main
from coding_agent_playbook.hook_runtime.config.pin import INTERPRETER_PIN, write_machine_pins
from coding_agent_playbook.hook_runtime.diagnostics._doctor_checks import PROBE
from coding_agent_playbook.hook_runtime.diagnostics._doctor_ignored import ignored_call_checks
from coding_agent_playbook.hook_runtime.diagnostics.doctor import (
    Check,
    build_parser,
    exit_code,
    main,
    run_doctor,
)
from coding_agent_playbook.hook_runtime.dispatch.escape import WRAPPER_PREFIXES_VAR
from coding_agent_playbook.hook_runtime.state.audit_log import GuardDecisionRecord, append_decision
from coding_agent_playbook.hook_runtime.state.store import StateStore
from coding_agent_playbook.security.trust import HandlerApproval, sha256_of_json
from tests.engine_version import ENGINE_VERSION
from tests.hook_runtime.fakes import FakeClock, FakeProc, FakeTrustStore
from tests.hook_runtime.guard_repo import GuardRepo, hook_record

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps

_PROBE_OK = json.dumps({"version": [3, 13], "isolated": 1, "engine": ENGINE_VERSION}).encode()


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
        tools={"ruff": [str(python)]}, engine_version=ENGINE_VERSION, git_dir=repo.repo.git_dir
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
            json.dumps({"version": [3, 8], "isolated": 1, "engine": ENGINE_VERSION}).encode(),
            0,
            "broken",
            ">= 3.12",
        ),
        (
            json.dumps({"version": [3, 13], "isolated": 0, "engine": ENGINE_VERSION}).encode(),
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


def _wrapper_check(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps], value: str
) -> tuple[Check, int]:
    repo, python = _healthy(tmp_path)
    deps = _deps(runtime_deps, python, env={WRAPPER_PREFIXES_VAR: value}, home=str(tmp_path))
    checks = run_doctor(str(repo.root), deps=deps)
    (check,) = [c for c in checks if c.name == "wrappers"]
    return check, exit_code(checks)


def test_no_wrapper_declaration_no_wrapper_row(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, python = _healthy(tmp_path)

    names = [c.name for c in run_doctor(str(repo.root), deps=_deps(runtime_deps, python))]

    assert "wrappers" not in names


def test_declared_wrappers_are_listed(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    check, code = _wrapper_check(tmp_path, runtime_deps, "proxy, proxy run")

    assert check == Check(
        "wrappers", "ok", f"{WRAPPER_PREFIXES_VAR} adds wrapper prefixes: 'proxy', 'proxy run'"
    )
    assert code == 0


def test_a_wrapper_hiding_a_guarded_command_is_a_warning(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    check, code = _wrapper_check(tmp_path, runtime_deps, "proxy,git push,sudo")

    assert check.severity == "warning"
    assert check.detail == (
        f"{WRAPPER_PREFIXES_VAR}: ignored 'git push' (it would hide 'git' from every guard), "
        "'sudo' (it would hide 'sudo' from every guard); kept 'proxy'"
    )
    assert code == 0  # a warning is healthy


def test_a_wrapper_set_in_a_settings_env_is_a_warning(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    user_settings = tmp_path / ".claude" / "settings.json"
    user_settings.parent.mkdir()
    user_settings.write_text(json.dumps({"env": {WRAPPER_PREFIXES_VAR: "proxy"}}), "utf-8")

    check, _ = _wrapper_check(tmp_path, runtime_deps, "proxy")

    assert check.severity == "warning"
    assert check.detail == (
        f"{WRAPPER_PREFIXES_VAR} is set in a settings file env and is ignored; "
        "export it in the shell that launches the agent"
    )


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


# --- the guard-decision-log summary (specs/prK-hook-pack.md §E.5) ---------------------


def _decision(hook_id: str, decision: str, ts: str) -> GuardDecisionRecord:
    return {
        "v": 1,
        "ts": ts,
        "harness": "claude_code",
        "session_id": "s",
        "event": "pre_tool_use",
        "hook_id": hook_id,
        "rule_id": None,
        "decision": decision,
        "effective": decision,
        "tool_name": "Bash",
        "tool_class": "shell",
        "unattended": False,
        "degraded": False,
        "escape": None,
        "canary": False,
        "latency_ms": 1,
    }


def test_doctor_reports_decision_log_summary_per_guard(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, python = _healthy(tmp_path)
    recent, old = "2026-10-13T09:00:00.000Z", "2026-08-01T09:00:00.000Z"  # clock: 2026-10-14
    for hook_id, decision, ts in [
        ("destructive-command-guard", "deny", recent),
        ("exfil-channel-guard", "ask", recent),
        ("exfil-channel-guard", "ask", recent),
        ("exfil-channel-guard", "override", recent),
        ("exfil-channel-guard", "degraded", recent),
        ("exfil-channel-guard", "deny", old),  # outside --since 30
    ]:
        append_decision(repo.state_root, _decision(hook_id, decision, ts))

    checks = run_doctor(str(repo.root), deps=_deps(runtime_deps, python))
    wide = run_doctor(str(repo.root), deps=_deps(runtime_deps, python), since_days=90)

    rows = {c.name: (c.severity, c.detail) for c in checks if c.name.startswith("decision-log")}
    assert rows == {
        "decision-log:destructive-command-guard": (
            "ok",
            "deny 1, ask 0, override 0 (n/a), degraded 0 (last 30 days)",
        ),
        "decision-log:exfil-channel-guard": (
            "ok",
            "deny 0, ask 2, override 1 (50%), degraded 1 (last 30 days)",
        ),
    }
    assert exit_code(checks) == 0  # informational: a busy guard is not a broken install
    assert any("deny 1, ask 2" in c.detail for c in wide if c.name.endswith("exfil-channel-guard"))


def test_doctor_without_a_decision_log_adds_no_rows(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, python = _healthy(tmp_path)

    checks = run_doctor(str(repo.root), deps=_deps(runtime_deps, python))

    assert not [c for c in checks if c.name.startswith("decision-log")]


# --- ignored hook calls (specs/prU-core-python-skills.md D79) --------------------------


def _ignored(reason: str, ts: str, event: str = "pre_tool_use") -> GuardDecisionRecord:
    record = _decision("playbook-dispatcher", "ignored", ts)
    record["rule_id"], record["effective"], record["event"] = reason, "none", event
    record["tool_name"] = record["tool_class"] = None
    return record


def _user_root(tmp_path: Path) -> Path:
    root = tmp_path / "state" / "coding-agent-playbook" / "playbook-hooks"
    root.mkdir(parents=True, mode=0o700)
    return root


def test_doctor_reports_ignored_calls_most_recent_first_and_flags_misconfiguration(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo, python = _healthy(tmp_path)
    for reason, ts in [
        ("event_mismatch", "2026-10-10T09:00:00.000Z"),
        ("claude_project_dir_unset", "2026-10-11T09:00:00.000Z"),
        ("claude_project_dir_unset", "2026-10-12T09:00:00.000Z"),
        ("missing_session_id", "2026-10-09T09:00:00.000Z"),
        ("timestamp", "2026-08-01T09:00:00.000Z"),  # outside --since 30
    ]:
        append_decision(repo.state_root, _ignored(reason, ts))
    append_decision(
        _user_root(tmp_path), _ignored("not_a_repo", "2026-10-13T09:00:00.000Z", "stop")
    )
    deps = _deps(runtime_deps, python, env={"XDG_STATE_HOME": str(tmp_path / "state")})

    checks = run_doctor(str(repo.root), deps=deps)

    rows = [(c.name, c.severity, c.detail) for c in checks if c.name.startswith("ignored:")]
    assert [(name, severity) for name, severity, _ in rows] == [
        ("ignored:not_a_repo", "ok"),
        ("ignored:claude_project_dir_unset", "warning"),
        ("ignored:event_mismatch", "ok"),
        ("ignored:missing_session_id", "warning"),
    ]
    details = {name: detail for name, _, detail in rows}
    assert details["ignored:claude_project_dir_unset"].startswith(
        "2 calls, last 2026-10-12T09:00:00.000Z (claude_code: pre_tool_use)"
    )
    assert "likely a misconfigured real session" in details["ignored:claude_project_dir_unset"]
    assert "likely a misconfigured real session" in details["ignored:missing_session_id"]
    assert "misconfigured" not in details["ignored:event_mismatch"]
    assert "outside any git repository" in details["ignored:not_a_repo"]
    assert not [c for c in checks if c.name == "decision-log:playbook-dispatcher"]
    assert exit_code(checks) == 0  # a warning: the install itself is healthy


def test_doctor_reads_ignored_calls_from_an_injected_state_store(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    store = StateStore(tmp_path / "injected", clock=FakeClock())
    store.root.mkdir(mode=0o700)
    append_decision(store.root, _ignored("timestamp", "2026-10-13T09:00:00.000Z"))
    deps = runtime_deps(state=store, env={"XDG_STATE_HOME": str(tmp_path / "state")})

    checks = ignored_call_checks(None, deps, since_days=30)

    assert [(c.name, c.severity) for c in checks] == [("ignored:timestamp", "ok")]


def test_doctor_outside_git_still_reports_user_level_ignored_calls(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    append_decision(_user_root(tmp_path), _ignored("not_a_repo", "2026-10-13T09:00:00.000Z"))
    plain = tmp_path / "plain"
    plain.mkdir()

    checks = run_doctor(
        str(plain), deps=runtime_deps(env={"XDG_STATE_HOME": str(tmp_path / "state")})
    )

    assert [(c.name, c.severity) for c in checks] == [
        ("repo", "broken"),
        ("ignored:not_a_repo", "ok"),
    ]


def test_build_parser_names_the_subcommand_and_its_defaults() -> None:
    # The docs site's CLI page renders this parser (sphinx-argparse).
    parser = build_parser()

    ns = parser.parse_args([])
    assert parser.prog == "playbook-hook doctor"
    assert (ns.repo, ns.repin, ns.format) == (os.curdir, None, "text")
