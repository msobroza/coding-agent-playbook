"""Something in the way of sync output: named with exit 1, never a traceback (SPEC §12.2).

Regressions: a regular file (or a link to one) where an output directory goes
(``.claude/commands``, ``.continue``) made write-mode ``playbook sync`` crash
with a ``FileExistsError`` / ``NotADirectoryError`` traceback from ``mkdir``,
a directory where an output file goes (``AGENTS.md/``) with an
``IsADirectoryError`` one, a socket there with ``OSError`` [Errno 102], and a
FIFO there made it hang forever in ``open()``. ``--check`` claimed sync would
replace each of them (or create the file), which only the native skill writer
does, and only inside a skill directory (§10.8) — not ``agent_harness``. Write
mode now stops naming the entry and leaves it alone; ``--check`` says the same.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.sync import pipeline as _sync
from tests.cli.hook_repo import SETTINGS, hook_deps, make_hook_repo
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

#: The whole-test alarm catches a sync that blocks forever, not a slow one: a test
#: here runs its syncs in about 4 s alone but took over 60 s (the former alarm)
#: under a loaded ``pytest -n`` run, with every sync still making progress.
_HANG_GUARD_S = 300


@pytest.fixture(autouse=True)
def _fail_instead_of_hanging() -> Iterator[None]:
    """A FIFO at an output path made sync block forever in ``open()``: fail instead."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _timeout(signum: int, frame: object) -> None:
        raise TimeoutError(f"playbook sync still running after {_HANG_GUARD_S} s (a FIFO?)")

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(_HANG_GUARD_S)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _file_at_commands(repo: Path) -> None:
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").write_text("mine\n", encoding="utf-8")


def _link_to_a_file_at_commands(repo: Path) -> None:
    (repo / "NOTES.md").write_text("mine\n", encoding="utf-8")
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").symlink_to("../NOTES.md")


def _file_at_continue(repo: Path) -> None:
    (repo / ".continue").write_text("mine\n", encoding="utf-8")


def _directory_at_agents_md(repo: Path) -> None:
    (repo / "AGENTS.md").mkdir()
    (repo / "AGENTS.md" / "mine.txt").write_text("mine\n", encoding="utf-8")


def _fifo_at_agents_md(repo: Path) -> None:
    os.mkfifo(repo / "AGENTS.md")


def _socket_at_agents_md(repo: Path) -> None:
    cwd = os.getcwd()
    os.chdir(repo)  # bind a short relative name: AF_UNIX paths are capped near 104 bytes
    try:
        with socket.socket(socket.AF_UNIX) as sock:
            sock.bind("AGENTS.md")  # the socket file outlives the closed socket
    finally:
        os.chdir(cwd)


_MOVE = "Move or rename it (sync never deletes it)"
_CASES = {
    "file-at-commands": (
        _file_at_commands,
        ".claude/commands is not a directory, but sync writes generated files inside it",
        _MOVE,
    ),
    "link-to-a-file-at-commands": (
        _link_to_a_file_at_commands,
        ".claude/commands is a symbolic link to ../NOTES.md, which is not a directory, "
        "but sync writes generated files inside it",
        "Re-point or remove the link",
    ),
    "file-at-continue": (
        _file_at_continue,
        ".continue is not a directory, but sync writes generated files inside it",
        _MOVE,
    ),
    "directory-at-agents-md": (
        _directory_at_agents_md,
        "AGENTS.md is a directory, but sync writes a generated file at that path",
        _MOVE,
    ),
    "fifo-at-agents-md": (
        _fifo_at_agents_md,
        "AGENTS.md is a FIFO, not a regular file, but sync writes a generated file at that path",
        _MOVE,
    ),
    "socket-at-agents-md": (
        _socket_at_agents_md,
        "AGENTS.md is a socket, not a regular file, but sync writes a generated file at that path",
        _MOVE,
    ),
}

_POSIX_ONLY = ("link", "fifo", "socket")
_skip_on_windows = pytest.mark.skipif(sys.platform == "win32", reason="POSIX links, FIFOs, sockets")
_PARAMS = [
    pytest.param(name, marks=_skip_on_windows if any(k in name for k in _POSIX_ONLY) else ())
    for name in _CASES
]
_PLANTED = (".claude/commands", ".continue", "AGENTS.md", "AGENTS.md/mine.txt", "NOTES.md")


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    (tmp_path / "repo").mkdir()
    return make_synthetic_repo(tmp_path / "repo", rules=[("style-guide", "Use spaces.\n")])


def _entry(path: Path) -> tuple[str, bytes | None]:
    """What is at ``path``, never opening a FIFO or socket: its type and, for a file or link, its bytes."""
    mode = path.lstat().st_mode
    if stat.S_ISREG(mode):
        return "file", path.read_bytes()
    if stat.S_ISLNK(mode):
        return "link", os.fsencode(os.readlink(path))
    return stat.filemode(mode)[0], None


def _planted(repo: Path) -> tuple[str, ...]:
    """Which of the entries a case may plant exist now (before any sync writes)."""
    return tuple(name for name in _PLANTED if os.path.lexists(repo / name))


def _tree(repo: Path, names: tuple[str, ...]) -> dict[str, tuple[str, bytes | None]]:
    """The user's planted entries ``names``, as they are now."""
    return {name: _entry(repo / name) for name in names}


@pytest.mark.parametrize("case", _PARAMS)
def test_write_mode_names_what_is_in_the_way_and_leaves_it_alone(
    repo: Path, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    plant, problem, remedy = _CASES[case]
    plant(repo)
    planted = _planted(repo)
    before = _tree(repo, planted)

    assert _sync.execute(repo, git=FakeGitClient()) == 1

    assert capsys.readouterr().err.splitlines() == [
        f"error: {problem}",
        "error: playbook sync stopped before finishing.",
        f"error: {remedy}, then re-run 'playbook sync'.",
    ]
    assert _tree(repo, planted) == before


@pytest.mark.parametrize("case", _PARAMS)
def test_check_names_what_is_in_the_way_and_promises_no_replacement(
    repo: Path, case: str, capsys: pytest.CaptureFixture[str]
) -> None:
    plant, problem, remedy = _CASES[case]
    plant(repo)

    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1

    out = capsys.readouterr().out
    assert f"    Missing on disk: {problem}.\n    {remedy}, then run 'playbook sync'." in out
    assert "replaces it only" not in out


def _agent_harness_repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    """A synced repo with only ``agent_harness`` on and one skill with a script."""
    config = _DEFAULT_CONFIG.replace(
        'adapters_enabled = ["continue", "claude_code", "opencode"]',
        'adapters_enabled = ["agent_harness"]',
    )
    (tmp_path / "repo").mkdir()
    repo = make_synthetic_repo(tmp_path / "repo", config_text=config, rules=[("style", "S.\n")])
    source = repo / "playbook" / "skills" / "demo"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nid: demo\nname: demo\ndescription: D.\n---\nDo it.\n")
    (source / "scripts" / "run.sh").write_text("echo hi\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    return repo


def _file_at_harness_scripts(repo: Path) -> str:
    shutil.rmtree(repo / "skills" / "demo" / "scripts")
    (repo / "skills" / "demo" / "scripts").write_text("mine\n", encoding="utf-8")
    return "skills/demo/scripts is not a directory, but sync writes generated files inside it"


def _directory_at_harness_script(repo: Path) -> str:
    """Regression: ``shutil.copy2`` copied the script *into* the directory, exit 0."""
    script = repo / "skills" / "demo" / "scripts" / "run.sh"
    script.unlink()
    script.mkdir()
    (script / "mine.txt").write_text("mine\n", encoding="utf-8")
    return (
        "skills/demo/scripts/run.sh is a directory, but sync writes a generated file at that path"
    )


@pytest.mark.parametrize("plant", [_file_at_harness_scripts, _directory_at_harness_script])
def test_an_agent_harness_skill_dir_gets_the_blocker_write_mode_reports(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    plant: Callable[[Path], str],
) -> None:
    """``agent_harness`` writes ``skills/<id>/`` plainly and never displaces what is in
    the way, so ``--check`` must not promise the native skill writer's file/folder swap."""
    repo = _agent_harness_repo(tmp_path, make_synthetic_repo)
    problem = plant(repo)
    capsys.readouterr()

    assert _sync.execute(repo, git=FakeGitClient()) == 1
    assert f"error: {problem}" in capsys.readouterr().err
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1

    out = capsys.readouterr().out
    assert f"    Missing on disk: {problem}.\n" in out
    assert "replaces it only" not in out
    assert not (repo / "skills" / "demo" / "scripts" / "run.sh" / "run.sh").exists()


@_skip_on_windows
def test_a_fifo_at_gitignore_is_named_in_both_modes(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: ``.gitignore`` is read before its managed block is rewritten, and
    reading a FIFO blocks too: write mode and ``--check`` hung."""
    os.mkfifo(repo / ".gitignore")
    problem = (
        ".gitignore is a FIFO, not a regular file, but sync writes a generated file at that path"
    )

    assert _sync.execute(repo, git=FakeGitClient()) == 1
    assert f"error: {problem}" in capsys.readouterr().err
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1
    assert f"Cannot verify .gitignore: it {problem.split(' ', 1)[1]}." in capsys.readouterr().out
    assert stat.S_ISFIFO((repo / ".gitignore").lstat().st_mode)


@_skip_on_windows
@pytest.mark.usefixtures("sample_hook_handlers")
def test_a_fifo_at_claude_settings_is_named_in_both_modes(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the Claude Code merge reads ``settings.json`` first: every mode hung."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    (repo / ".claude").mkdir(exist_ok=True)
    os.mkfifo(repo / SETTINGS)
    deps = hook_deps(tmp_path / "state")
    reason = "is a FIFO, not a regular file, but sync writes a generated file at that path"

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=deps) == 1
    assert f"error: {SETTINGS} {reason}" in capsys.readouterr().err
    assert _sync.execute(repo, check=True, git=FakeGitClient(), hook_deps=deps) == 1
    assert f"Cannot verify {SETTINGS}: it {reason}." in capsys.readouterr().out


@_skip_on_windows
def test_an_agent_harness_script_linked_to_dev_null_still_syncs(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """Regression: ``shutil.copy2``'s copystat raised EACCES on ``/dev/null``."""
    repo = _agent_harness_repo(tmp_path, make_synthetic_repo)
    script = repo / "skills" / "demo" / "scripts" / "run.sh"
    script.unlink()
    script.symlink_to(os.devnull)

    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    assert script.is_symlink()


@_skip_on_windows
def test_agents_md_linked_to_dev_null_still_syncs(repo: Path) -> None:
    """A link to a character device never blocks: a known way to discard AGENTS.md."""
    (repo / "AGENTS.md").symlink_to(os.devnull)

    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / "AGENTS.md").is_symlink()
    # write mode delivered it; "Missing on disk; run 'playbook sync'" would never clear
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
