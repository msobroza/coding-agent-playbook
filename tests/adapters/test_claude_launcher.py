"""The committed Claude Code launcher, run for real under ``/bin/sh`` (specs/prK-lifecycle-hooks.md §C.2.7).

The pin is a fake interpreter: an executable shell script standing in for
``<py> -I -m coding_agent_playbook.hook_runtime`` that records its argv and exits
with a chosen code. ``git`` (used only by the registration command's fallback
when ``CLAUDE_PROJECT_DIR`` is unset) is a fake on ``PATH`` that walks up to the
nearest ``.git``. Nothing real runs besides ``sh`` and ``date``. POSIX-only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.claude_settings import LAUNCHER_TOKEN
from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hook_registrations import (
    LAUNCHER_PATH,
    claude_command,
    render_claude_launcher,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh launcher")

_RUNTIME_ARGV = ["-I", "-m", "coding_agent_playbook.hook_runtime"]
_SYSTEM_PATH = "/usr/bin:/bin"
_FAKE_GIT = """\
#!/bin/sh
echo "$@" >> "{log}"
[ "$1 $2" = "rev-parse --show-toplevel" ] || exit 2
d=$PWD
while [ "$d" != / ]; do
  if [ -e "$d/.git" ]; then echo "$d"; exit 0; fi
  d=$(dirname "$d")
done
exit 128
"""


def _executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    """A worktree root with a ``.git`` dir and the rendered launcher at its committed path."""
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    launcher = root / LAUNCHER_PATH
    launcher.parent.mkdir(parents=True)
    launcher.write_text(render_claude_launcher(), encoding="utf-8")
    return root


def _pin(tmp_path: Path, state: Path, code: int = 0) -> Path:
    """Pin a fake interpreter under ``state``; it records its argv in ``tmp_path/argv``."""
    record = tmp_path / "argv"
    fake = _executable(
        tmp_path / "fake-python", f'#!/bin/sh\nprintf "%s\\n" "$@" > "{record}"\nexit {code}\n'
    )
    state.mkdir(parents=True, exist_ok=True)
    (state / "interpreter").write_text(f"{fake}\n", encoding="utf-8")
    return record


def _env(**extra: str) -> dict[str, str]:
    return {"PATH": _SYSTEM_PATH, "HOME": os.environ.get("HOME", "/"), **extra}


def _launch(
    root: Path, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", str(root / LAUNCHER_PATH), *args],
        cwd=cwd or root,
        env=_env() if env is None else env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _dispatch(event: str) -> list[str]:
    return ["dispatch", event, "--harness", "claude_code"]


# --- the rendered bytes ---------------------------------------------------------------


def test_line1_sentinel_and_no_shebang() -> None:
    text = render_claude_launcher()
    lines = text.splitlines()

    assert lines[0] == sentinel_line("hash")
    assert not text.startswith("#!")
    assert "@@" not in text
    assert text.endswith("exit 0\n")
    assert f"root=${{0%{LAUNCHER_TOKEN}}}" in lines
    assert LAUNCHER_TOKEN.lstrip("/") == LAUNCHER_PATH


def test_render_is_deterministic() -> None:
    assert render_claude_launcher() == render_claude_launcher()


# --- the exit-code contract (K-7) -------------------------------------------------------


@pytest.mark.parametrize(
    ("dispatcher_code", "launcher_code", "logged"),
    [(0, 0, False), (10, 2, False), (2, 0, True), (1, 0, True)],
    ids=["dispatcher0_exit0", "dispatcher10_exit2", "raw2_exit0_logs", "dispatcher1_exit0_logs"],
)
def test_exit_mapping(
    tmp_path: Path, dispatcher_code: int, launcher_code: int, logged: bool
) -> None:
    root = _repo(tmp_path)
    state = root / ".git" / "playbook-hooks"
    record = _pin(tmp_path, state, dispatcher_code)

    result = _launch(root, *_dispatch("pre_tool_use"))

    assert result.returncode == launcher_code
    assert result.stdout == ""
    assert record.read_text(encoding="utf-8").split() == [
        *_RUNTIME_ARGV,
        *_dispatch("pre_tool_use"),
    ]
    log = state / "launcher.log"
    assert log.exists() == logged
    if logged:
        stamp, event, why = log.read_text(encoding="utf-8").strip().split(" ", 2)
        assert stamp.isdigit()
        assert (event, why) == ("pre_tool_use", f"dispatcher exited {dispatcher_code}")


def test_missing_pin_exit0_session_start_json_only(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    quiet = _launch(root, *_dispatch("pre_tool_use"))
    notice = _launch(root, *_dispatch("session_start"))

    assert (quiet.returncode, quiet.stdout) == (0, "")
    assert notice.returncode == 0
    payload = json.loads(notice.stdout)
    assert "INACTIVE (no interpreter pin)" in payload["systemMessage"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "AGENTS.md Guardrails" in payload["hookSpecificOutput"]["additionalContext"]


def test_non_executable_pin_counts_as_missing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    state = root / ".git" / "playbook-hooks"
    state.mkdir()
    (state / "interpreter").write_text(f"{tmp_path / 'absent-python'}\n", encoding="utf-8")

    result = _launch(root, *_dispatch("session_start"))

    assert result.returncode == 0
    assert "no interpreter pin" in json.loads(result.stdout)["systemMessage"]


def test_dispatcher_crash_on_session_start_reports_inactive(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _pin(tmp_path, root / ".git" / "playbook-hooks", 1)

    result = _launch(root, *_dispatch("session_start"))

    assert result.returncode == 0
    assert "INACTIVE (dispatcher exited 1)" in json.loads(result.stdout)["systemMessage"]


def test_strict_launch_missing_pin_exits_1(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    result = _launch(root, "--strict-launch", *_dispatch("user_prompt_submit"))

    assert (result.returncode, result.stdout) == (1, "")


def test_strict_launch_passes_through_success_and_strips_its_flag(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    record = _pin(tmp_path, root / ".git" / "playbook-hooks", 0)

    result = _launch(root, "--strict-launch", *_dispatch("user_prompt_submit"))

    assert result.returncode == 0
    assert record.read_text(encoding="utf-8").split() == [
        *_RUNTIME_ARGV,
        *_dispatch("user_prompt_submit"),
    ]


def test_strict_launch_crash_exits_1(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _pin(tmp_path, root / ".git" / "playbook-hooks", 3)

    assert _launch(root, "--strict-launch", *_dispatch("user_prompt_submit")).returncode == 1


# --- finding the per-worktree pin -------------------------------------------------------


@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_linked_worktree_gitdir_file(tmp_path: Path, relative: bool) -> None:
    root = _repo(tmp_path, "linked")
    (root / ".git").rmdir()
    worktree_git = tmp_path / "main" / ".git" / "worktrees" / "linked"
    worktree_git.mkdir(parents=True)
    target = "../main/.git/worktrees/linked" if relative else str(worktree_git)
    (root / ".git").write_text(f"gitdir: {target}\n", encoding="utf-8")
    record = _pin(tmp_path, worktree_git / "playbook-hooks", 0)

    result = _launch(root, *_dispatch("stop"))

    assert result.returncode == 0
    assert record.exists()


def test_root_derived_from_dollar0(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    record = _pin(tmp_path, root / ".git" / "playbook-hooks", 0)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = _launch(
        root,
        *_dispatch("stop"),
        cwd=elsewhere,
        env=_env(CLAUDE_PROJECT_DIR=str(elsewhere)),
    )

    assert result.returncode == 0
    assert record.exists()


def test_root_falls_back_to_project_dir_off_the_committed_path(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    record = _pin(tmp_path, root / ".git" / "playbook-hooks", 0)
    stray = tmp_path / "stray-launch.sh"
    stray.write_text(render_claude_launcher(), encoding="utf-8")

    result = subprocess.run(
        ["/bin/sh", str(stray), *_dispatch("stop")],
        cwd=tmp_path,
        env=_env(CLAUDE_PROJECT_DIR=str(root)),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert record.exists()


# --- the registration command (§C.2.1) ---------------------------------------------------


@pytest.mark.parametrize(
    ("project_dir_set", "subdir", "git_runs"),
    [(True, False, False), (False, False, True), (False, True, True)],
    ids=["project_dir_set", "unset_at_root", "unset_in_subdir"],
)
def test_registration_command_project_dir_set_unset_and_subdir_cwd(
    tmp_path: Path, project_dir_set: bool, subdir: bool, git_runs: bool
) -> None:
    root = _repo(tmp_path)
    record = _pin(tmp_path, root / ".git" / "playbook-hooks", 0)
    git_log = tmp_path / "git.log"
    fake_bin = tmp_path / "bin"
    _executable(fake_bin / "git", _FAKE_GIT.format(log=git_log))
    cwd = root / "src" / "pkg" if subdir else root
    cwd.mkdir(parents=True, exist_ok=True)
    extra = {"CLAUDE_PROJECT_DIR": str(root)} if project_dir_set else {}
    if project_dir_set:
        cwd = tmp_path  # the project dir alone locates the launcher

    result = subprocess.run(
        ["/bin/sh", "-c", claude_command("stop")],
        cwd=cwd,
        env={**_env(**extra), "PATH": f"{fake_bin}:{_SYSTEM_PATH}"},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert record.read_text(encoding="utf-8").split() == [*_RUNTIME_ARGV, *_dispatch("stop")]
    assert git_log.exists() == git_runs
