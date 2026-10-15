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
from coding_agent_playbook.commands._sync_hook_local import RuntimePinWriter, handler_approval
from coding_agent_playbook.commands._sync_render import render_artifacts
from coding_agent_playbook.hook_runtime._external import approval_of
from coding_agent_playbook.hook_runtime.config import GuardConfig, parse_guard_config
from coding_agent_playbook.orchestrator import SyncContext
from coding_agent_playbook.security.trust import TrustStore
from tests.cli.hook_repo import GUARD_CONFIG, SCRIPT, hook_deps, make_hook_repo, never_ask
from tests.fakes import FakeGitClient, FakePinWriter

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
        "guard-generated-outputs",
        "control-plane-guard",
        "validate-then-sync-on-canonical-edit",
        "resync-on-detector-input-change",
        "eval-task-authoring-lint",
    }
    assert all(handler_approval(hook) is None for hook in builtins)
