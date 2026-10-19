"""Machine-local hook effects of ``playbook sync`` (specs/prK-lifecycle-hooks.md §B.4, §C.2.7, §D.8.3).

Write mode only, after the lockfile is saved: the per-worktree interpreter pin
(first writer wins) and ``machine.json``, and the trust-on-first-use prompt for
repo- or overlay-controlled handlers, which runs only when stdin and stdout are
TTYs. ``--check`` and ``--check-staged`` never pin and never prompt.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands._sync_hook_local import (
    RuntimePinWriter,
    approve_pending,
    execution_digest,
    handler_approval,
    project_python,
    write_pins,
)
from coding_agent_playbook.commands._sync_render import render_artifacts
from coding_agent_playbook.hook_registrations import stop_gate_table
from coding_agent_playbook.hook_runtime._external import approval_of
from coding_agent_playbook.hook_runtime.config import GuardConfig, parse_guard_config
from coding_agent_playbook.hook_runtime.stop.coordinator import GatePolicy
from coding_agent_playbook.security.trust import TrustStore
from coding_agent_playbook.validation.context import SyncContext
from tests.cli.hook_repo import GUARD_CONFIG, SCRIPT, hook_deps, make_hook_repo, never_ask
from tests.fakes import FakeGitClient, FakePinWriter
from tests.hook_runtime.handlers.pack_repo import resolve_engine_hooks

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

pytestmark = pytest.mark.usefixtures("sample_hook_handlers")


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory) -> Path:
    return make_hook_repo(tmp_path / "repo", make_synthetic_repo)


def test_pin_written_in_write_mode_only_first_writer_wins_never_in_check(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pins = FakePinWriter(pinned="/first/venv/bin/python", interpreter="/second/bin/python")
    deps = hook_deps(tmp_path / "state", pins=pins, which={"ruff": "/v/bin/ruff"}.get)

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=deps) == 0
    assert pins.calls == [("ensure_interpreter_pin", repo), ("write_machine_pins", repo)]
    assert pins.pinned == "/first/venv/bin/python"
    assert pins.tools == {"ruff": ["/v/bin/ruff"]}

    pins.calls.clear()
    assert _sync.execute(repo, git=FakeGitClient(), check=True, hook_deps=deps) == 0
    staged = FakeGitClient(staged=["AGENTS.md"])
    assert _sync.execute(repo, git=staged, check_staged=True, hook_deps=deps) == 1
    assert pins.calls == []
    assert "Pinned" not in capsys.readouterr().out


def test_stop_stage_tools_join_the_pin_list(repo: Path, tmp_path: Path) -> None:
    """The Stop stage runner resolves a stage's logical tool only through machine.json."""
    pins = FakePinWriter()
    which = {"ruff": "/v/bin/ruff", "python3": "/usr/bin/python3"}.get
    deps = hook_deps(tmp_path / "state", pins=pins, which=which)

    write_pins(repo, deps, engine_version="0.2.0", stage_tools=["project_python", "ruff"])

    assert pins.tools == {"ruff": ["/v/bin/ruff"], "project_python": ["/usr/bin/python3"]}


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX venv layout")
def test_machine_json_pins_cz_and_project_python_when_present(repo: Path, tmp_path: Path) -> None:
    """prK §F.4.1/§F.1.2: cz comes from the project venv first (commitizen in the dev extras)."""
    venv_cz = repo / ".venv" / "bin" / "cz"
    venv_cz.parent.mkdir(parents=True)
    venv_cz.write_bytes(b"#!/bin/sh\n")
    venv_cz.chmod(0o755)
    pins = FakePinWriter()
    which = {"cz": "/usr/local/bin/cz", "python3": "/usr/bin/python3"}.get
    deps = hook_deps(tmp_path / "state", pins=pins, which=which)

    write_pins(repo, deps, engine_version="0.2.0", stage_tools=["project_python"])

    assert pins.tools == {"cz": [str(venv_cz)], "project_python": ["/usr/bin/python3"]}


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX venv layout")
def test_project_python_prefers_the_repo_venv_unresolved(repo: Path) -> None:
    venv_python = repo / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(sys.executable)  # a venv's python is a symlink: keep it

    assert project_python(repo, {"python3": "/usr/bin/python3"}.get) == str(venv_python)
    nothing: dict[str, str] = {}
    assert project_python(repo / "missing", nothing.get) is None


@pytest.mark.skipif(sys.platform == "win32", reason="the first writer is /bin/sh")
def test_real_pin_lands_under_the_git_dir_and_keeps_the_first_writer(
    repo: Path, tmp_path: Path
) -> None:
    (repo / ".git").mkdir()  # find_repo only needs the layout; no git binary runs
    deps = hook_deps(tmp_path / "state", pins=RuntimePinWriter())

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=deps) == 0

    pin = repo / ".git" / "playbook-hooks" / "interpreter"
    assert pin.read_text(encoding="utf-8") == f"{sys.executable}\n"
    assert (repo / ".git" / "playbook-hooks" / "machine.json").is_file()
    pin.write_text("/bin/sh\n", encoding="utf-8")  # an executable first writer

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=deps) == 0
    assert pin.read_text(encoding="utf-8") == "/bin/sh\n"


def test_non_git_repo_warns_no_pin(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pins = FakePinWriter(git=False)

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=hook_deps(tmp_path, pins=pins)) == 0

    err = capsys.readouterr().err
    assert "warning: hooks are git-only" in err
    assert "no interpreter pin was written" in err
    assert pins.calls == [("ensure_interpreter_pin", repo)]


def test_tofu_prompts_only_on_tty_lists_source_command_hashes(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[str] = []

    def answer_yes(prompt: str) -> str:
        asked.append(prompt)
        return "y"

    tty = hook_deps(tmp_path / "state", is_tty=lambda: True, ask=answer_yes)
    no_tty = hook_deps(tmp_path / "state")

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=no_tty) == 0
    assert "await approval" in capsys.readouterr().out

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=tty) == 0
    out = capsys.readouterr().out
    assert asked == ["Approve it? [y/N]: "]
    assert "guard-ext" in out and "<repo-local>" in out
    assert f"sh {SCRIPT} --fast" in out
    assert "(not approved) ->" in out
    store = TrustStore(tmp_path / "state" / "trust.json", repo_root=repo)
    approved = store.handler("guard-ext")
    assert approved is not None
    assert approved.launcher == "sh"
    assert approved.script_sha256 in out

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=tty) == 0  # approved: no prompt
    assert asked == ["Approve it? [y/N]: "]
    assert "await approval" not in capsys.readouterr().out


def test_declined_approval_records_nothing(repo: Path, tmp_path: Path) -> None:
    deps = hook_deps(tmp_path / "state", is_tty=lambda: True, ask=lambda prompt: "")

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=deps) == 0

    store = TrustStore(tmp_path / "state" / "trust.json", repo_root=repo)
    assert store.handler("guard-ext") is None


def test_no_prompt_in_check_modes(repo: Path, tmp_path: Path) -> None:
    deps = hook_deps(tmp_path / "state", is_tty=lambda: True, ask=never_ask)
    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=hook_deps(tmp_path / "s")) == 0

    assert _sync.execute(repo, git=FakeGitClient(), check=True, hook_deps=deps) == 0
    staged = FakeGitClient(staged=[SCRIPT])
    assert _sync.execute(repo, git=staged, check_staged=True, hook_deps=deps) == 1


def test_handler_approval_mirrors_the_runtime_record(repo: Path, tmp_path: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=hook_deps(tmp_path)) == 0
    config = parse_guard_config((repo / GUARD_CONFIG).read_bytes())
    assert isinstance(config, GuardConfig)

    resolved = render_artifacts(SyncContext.from_repo(repo)).hooks.resolved
    [hook] = [hook for hook in resolved if hook.id == "guard-ext"]
    assert handler_approval(hook) == approval_of(config.hooks["guard-ext"])
    builtins = [hook for hook in resolved if hook.id != "guard-ext"]
    assert {hook.id for hook in builtins} == {
        "guard-x",
        "block-precommit-bypass",
        "clean-code-metrics-nonregression",
        "docstring-nonregression",
        "gate-weakening-guard",
        "tests-with-source-nudge",
        "guard-generated-outputs",
        "control-plane-guard",
        "validate-then-sync-on-canonical-edit",
        "resync-on-detector-input-change",
        "eval-task-authoring-lint",
        "stop-drift-and-orphan-gate",
        "session-start-playbook-briefing",
        "stop-ci-parity-gate",
        "prompt-write-scope-guard",
        "post-edit-ruff-format",
        "error-handling-lint-feedback",
        "typing-lint-feedback",
        "toolchain-missing-hint",
        "skill-nudge",
        "secrets-path-guard",
        "secret-content-guard",
        "destructive-command-guard",
        "git-commit-push-policy-guard",
        "commit-message-convention",
        "stop-diff-sweep",
        "dependency-allowlist-guard",
        "exfil-channel-guard",
        "guard-decision-log",
    }
    assert all(handler_approval(hook) is None for hook in builtins)


# --- the Stop gate's execution stages (§B.4: execution = {stages_sha256}) ---------------------

_GATE = "stop-ci-parity-gate"


@pytest.mark.catalog
def test_execution_digest_is_the_one_the_runtime_checks(tmp_path: Path) -> None:
    hooks = resolve_engine_hooks([_GATE], tmp_path, per_hook={_GATE: {"stages": ["tests"]}})
    runtime = GatePolicy.from_table(stop_gate_table(hooks, {})).stages_sha256()

    assert execution_digest(hooks) == runtime
    assert execution_digest(resolve_engine_hooks([_GATE], tmp_path)) is None  # nothing to run


@pytest.mark.catalog
def test_execution_stages_need_an_interactive_approval(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    hooks = resolve_engine_hooks([_GATE], root, per_hook={_GATE: {"stages": ["typecheck"]}})
    asked: list[str] = []

    def answer_yes(prompt: str) -> str:
        asked.append(prompt)
        return "y"

    yes = hook_deps(tmp_path / "state", is_tty=lambda: True, ask=answer_yes)
    store = TrustStore(tmp_path / "state" / "trust.json", repo_root=root)

    assert approve_pending(hooks, root, hook_deps(tmp_path / "state")) == []
    assert "stop gate's execution stages await approval" in capsys.readouterr().out
    assert approve_pending(hooks, root, yes) == ["stop gate"]
    out = capsys.readouterr().out
    assert "typecheck: project_python -m mypy" in out
    assert store.allows_execution(execution_digest(hooks) or "")
    assert approve_pending(hooks, root, yes) == []  # approved: never asked again
    assert asked == ["Approve it? [y/N]: "]
