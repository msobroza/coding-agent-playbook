"""``playbook-hook doctor``'s OpenCode checks (specs/prK-lifecycle-hooks.md §D.9, §C.3.7, QC-14).

``opencode --version`` runs only through ``FakeProc`` (no real OpenCode binary
ever runs); the shim is the real rendered template in a fixture worktree,
vouched for by a lockfile entry exactly as sync writes it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.hook_runtime.config.schema import LOCKFILE_REL
from coding_agent_playbook.hook_runtime.diagnostics._doctor_opencode import (
    DISABLE_PROJECT_CONFIG,
    OPENCODE_MIN_VERSION,
    VERSION_PROBE_TIMEOUT_S,
    opencode_checks,
    parse_opencode_version,
    read_shim_reg,
)
from coding_agent_playbook.hook_runtime.diagnostics.doctor import Check, exit_code, run_doctor
from coding_agent_playbook.hook_runtime.harness.opencode import OPENCODE_SHIM_REL
from coding_agent_playbook.hooks.registrations.opencode import (
    OPENCODE_SHIM_PATH,
    render_opencode_shim,
)
from tests.hook_runtime.fakes import FakeProc
from tests.hook_runtime.guard_repo import GuardRepo, hook_record

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.proc import ProcResult
    from coding_agent_playbook.hooks.registrations.opencode import OpenCodeRegEntry

_OPENCODE = "/opt/bin/opencode"
_REG: dict[str, OpenCodeRegEntry] = {
    "pre_tool_use": {"timeout_ms": 7000, "tools": ["apply_patch", "bash", "edit", "write"]},
    "post_tool_use": {"timeout_ms": 12000, "tools": "*"},
    "session_start": {"timeout_ms": 4000},
}


def _repo(tmp_path: Path, *, shim: bool = True) -> GuardRepo:
    """A synced worktree; with ``shim``, the rendered shim plus its lockfile entry."""
    repo = GuardRepo.create(tmp_path)
    repo.install(hook_record("guard-a"))
    if shim:
        data = render_opencode_shim(_REG).encode("utf-8")
        path = repo.root / OPENCODE_SHIM_PATH
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        _lock_shim(repo, hashlib.sha256(data).hexdigest(), len(data))
    return repo


def _lock_shim(repo: GuardRepo, sha256: str, size: int) -> None:
    with (repo.root / LOCKFILE_REL).open("a", encoding="utf-8") as lock:
        lock.write(
            f'\n[[entries]]\npath = "{OPENCODE_SHIM_PATH}"\nsha256 = "{sha256}"\n'
            f'bytes = {size}\nkind = "runtime"\nadapter = "opencode"\n'
        )


def _deps(
    runtime_deps: Callable[..., RuntimeDeps],
    version: bytes | None = b"1.19.0\n",
    *,
    env: dict[str, str] | None = None,
    **script: Any,
) -> RuntimeDeps:
    """Deps whose PATH has ``opencode`` (printing ``version``) unless ``version`` is None."""
    proc = FakeProc(programs={} if version is None else {"opencode": _OPENCODE})
    proc.script(["opencode", "--version"], stdout=version or b"", **script)
    return runtime_deps(proc=proc, env=env or {})


def _by_name(checks: list[Check]) -> dict[str, Check]:
    return {check.name: check for check in checks}


@dataclass
class FakeVanishedProc(FakeProc):
    """``opencode`` is on PATH, but the binary is gone by the time it runs."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        raise FileNotFoundError(argv[0])


def test_doctor_warns_below_opencode_floor(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    checks = opencode_checks(_repo(tmp_path).repo, _deps(runtime_deps, b"1.18.28\n"))

    version = _by_name(checks)["opencode"]
    assert version.severity == "degraded"
    assert "1.18.28 is below 1.18.29" in version.detail
    assert "silently" in version.detail
    assert exit_code(checks) == 1


def test_below_floor_without_a_shim_is_only_a_warning(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    # No OpenCode hooks in this worktree: an old OpenCode loses nothing here.
    checks = opencode_checks(_repo(tmp_path, shim=False).repo, _deps(runtime_deps, b"1.18.28\n"))

    assert [(c.name, c.severity) for c in checks] == [("opencode", "warning")]
    assert exit_code(checks) == 0


@pytest.mark.parametrize("output", [b"1.18.29\n", b"1.19.0\n", b"opencode 1.19.0\n", b"2.0.0-rc.1"])
def test_doctor_accepts_opencode_at_or_above_floor(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps], output: bytes
) -> None:
    checks = opencode_checks(_repo(tmp_path).repo, _deps(runtime_deps, output))

    assert _by_name(checks)["opencode"].severity == "ok"
    assert exit_code(checks) == 0


def test_doctor_skips_opencode_probe_when_not_on_path(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    deps = _deps(runtime_deps, None)

    checks = opencode_checks(_repo(tmp_path).repo, deps)

    assert "opencode" not in _by_name(checks)
    assert deps.proc.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("version", "script", "needle"),
    [
        (b"opencode dev build\n", {}, "cannot read a version"),
        (b"", {"timeout": True}, "timed out"),
        (b"1.19.0\n", {"returncode": 1}, "cannot read a version"),
    ],
    ids=["unparseable", "timed-out", "failed"],
)
def test_doctor_reports_unparseable_or_timed_out_opencode_version(
    tmp_path: Path,
    runtime_deps: Callable[..., RuntimeDeps],
    version: bytes,
    script: dict[str, Any],
    needle: str,
) -> None:
    checks = opencode_checks(_repo(tmp_path).repo, _deps(runtime_deps, version, **script))

    check = _by_name(checks)["opencode"]
    assert check.severity == "warning"
    assert needle in check.detail
    assert exit_code(checks) == 0


def test_vanished_opencode_binary_is_a_warning(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    deps = runtime_deps(proc=FakeVanishedProc(programs={"opencode": _OPENCODE}))

    check = _by_name(opencode_checks(_repo(tmp_path).repo, deps))["opencode"]

    assert (check.severity, "FileNotFoundError" in check.detail) == ("warning", True)


def test_doctor_version_probe_is_bounded_by_timeout(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    deps = _deps(runtime_deps)

    opencode_checks(_repo(tmp_path).repo, deps)

    (call,) = deps.proc.calls  # type: ignore[attr-defined]
    assert call.argv == (_OPENCODE, "--version")
    assert call.timeout == VERSION_PROBE_TIMEOUT_S
    assert 0 < VERSION_PROBE_TIMEOUT_S <= 30


@pytest.mark.parametrize(
    ("value", "shim", "severity"),
    [("1", True, "degraded"), ("TRUE", True, "degraded"), ("1", False, "warning")],
)
def test_doctor_reports_opencode_disable_project_config(
    tmp_path: Path,
    runtime_deps: Callable[..., RuntimeDeps],
    value: str,
    shim: bool,
    severity: str,
) -> None:
    deps = _deps(runtime_deps, None, env={DISABLE_PROJECT_CONFIG: value})

    check = _by_name(opencode_checks(_repo(tmp_path, shim=shim).repo, deps))["opencode-config"]

    assert check.severity == severity
    assert DISABLE_PROJECT_CONFIG in check.detail


@pytest.mark.parametrize("value", ["0", "false", ""])
def test_falsy_disable_project_config_is_not_reported(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps], value: str
) -> None:
    deps = _deps(runtime_deps, None, env={DISABLE_PROJECT_CONFIG: value})

    assert "opencode-config" not in _by_name(opencode_checks(_repo(tmp_path).repo, deps))


def test_doctor_lists_opencode_registrations_from_shim(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    checks = opencode_checks(_repo(tmp_path).repo, _deps(runtime_deps, None))

    shim = _by_name(checks)["opencode-shim"]
    assert shim.severity == "ok"
    assert "3 OpenCode registration(s)" in shim.detail
    assert "pre_tool_use (7000 ms: apply_patch, bash, edit, write)" in shim.detail
    assert "post_tool_use (12000 ms: every tool)" in shim.detail
    assert "session_start (4000 ms)" in shim.detail
    assert "--pure" in shim.detail  # a CLI flag doctor cannot see: documented instead


def test_doctor_flags_shim_hash_mismatch_and_never_executes_it(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _repo(tmp_path)
    path = repo.root / OPENCODE_SHIM_PATH
    tampered = path.read_text(encoding="utf-8").replace('"pre_tool_use"', '"pwned_event"')
    path.write_text(tampered, encoding="utf-8")
    deps = _deps(runtime_deps, None)

    checks = opencode_checks(repo.repo, deps)

    shim = _by_name(checks)["opencode-shim"]
    assert shim.severity == "broken"
    assert "lockfile" in shim.detail
    assert "pwned_event" not in shim.detail  # reported unread
    assert deps.proc.calls == []  # type: ignore[attr-defined]
    assert exit_code(checks) == 2


def test_missing_shim_with_a_lock_entry_is_broken(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _repo(tmp_path)
    (repo.root / OPENCODE_SHIM_PATH).unlink()

    shim = _by_name(opencode_checks(repo.repo, _deps(runtime_deps, None)))["opencode-shim"]

    assert shim.severity == "broken"
    assert "missing" in shim.detail


def test_shim_without_a_lock_entry_is_degraded_and_unread(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _repo(tmp_path, shim=False)
    path = repo.root / OPENCODE_SHIM_PATH
    path.parent.mkdir(parents=True)
    path.write_text(render_opencode_shim(_REG), encoding="utf-8")

    shim = _by_name(opencode_checks(repo.repo, _deps(runtime_deps, None)))["opencode-shim"]

    assert shim.severity == "degraded"
    assert "pre_tool_use" not in shim.detail


def test_vouched_shim_without_a_reg_line_is_broken(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _repo(tmp_path, shim=False)
    data = b"// a shim from another engine\nexport default {}\n"
    path = repo.root / OPENCODE_SHIM_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    _lock_shim(repo, hashlib.sha256(data).hexdigest(), len(data))

    shim = _by_name(opencode_checks(repo.repo, _deps(runtime_deps, None)))["opencode-shim"]

    assert (shim.severity, "no readable REG line" in shim.detail) == ("broken", True)


def test_no_shim_and_no_entry_adds_no_shim_row(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    assert opencode_checks(_repo(tmp_path, shim=False).repo, _deps(runtime_deps, None)) == []


def test_run_doctor_appends_the_opencode_checks_last(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = _repo(tmp_path)

    names = [c.name for c in run_doctor(str(repo.root), deps=_deps(runtime_deps))]

    assert names[-2:] == ["opencode", "opencode-shim"]


def test_read_shim_reg_round_trips_the_rendered_shim() -> None:
    assert read_shim_reg(render_opencode_shim(_REG)) == _REG


@pytest.mark.parametrize(
    "text",
    ["const x = 1\n", "const REG = [1]\n", "const REG = {oops\n", "// const REG = {}\n"],
)
def test_read_shim_reg_rejects_text_without_a_json_object_reg_line(text: str) -> None:
    assert read_shim_reg(text) is None


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (b"1.18.29\n", (1, 18, 29)),
        (b"opencode 1.19.0 (bun 1.2.0)\n", (1, 19, 0)),
        (b"v10.0.12", (10, 0, 12)),
        (b"1.19\n", None),
        (b"\xff\xfe", None),
    ],
)
def test_parse_opencode_version_takes_the_first_x_y_z(
    output: bytes, expected: tuple[int, int, int] | None
) -> None:
    assert parse_opencode_version(output) == expected


def test_floor_and_shim_path_are_the_engine_values() -> None:
    assert OPENCODE_MIN_VERSION == (1, 18, 29)
    assert OPENCODE_SHIM_REL == OPENCODE_SHIM_PATH


def test_warning_severity_never_changes_the_exit_code() -> None:
    assert exit_code([Check("opencode", "warning", ""), Check("pin", "ok", "")]) == 0
