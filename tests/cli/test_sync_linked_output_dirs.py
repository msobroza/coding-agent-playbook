"""Output directories reached through a symlink: one that dangles, one that leaves the repo.

Regressions (SPEC §4.2 steps 8-9, §12.2, §14.4):

- A dangling ``.claude/commands -> ../tools/cc`` made write-mode ``playbook
  sync`` crash with a ``FileExistsError`` traceback from ``mkdir``, and
  ``--check`` claimed sync would replace the link. Both now name the link and
  its missing target, exit 1, and leave the link alone.
- An output dir linked out of the repo (``.claude/skills -> /abs/dir``) put an
  absolute, machine-specific path in ``.coding-agent-playbook.lock``. The
  lockfile never owns output there (step 9 already released such an entry when
  read), so it now gets no entry at all.

``test_absolute_entry_from_an_older_sync_is_dropped`` pins behaviour that
predates the fix: such an entry is released on the next sync, never deleted.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.lockfile import LockEntry
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from tests.cli.hook_repo import SETTINGS, hook_deps, make_hook_repo
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")

_SKILL = "demo"


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    (tmp_path / "repo").mkdir()
    return make_synthetic_repo(tmp_path / "repo", rules=[("style-guide", "Use spaces.\n")])


def _dangle_commands_dir(repo: Path) -> Path:
    """``.claude/commands -> ../tools/cc`` with no ``tools/`` in the repo."""
    (repo / ".claude").mkdir(exist_ok=True)
    link = repo / ".claude" / "commands"
    link.symlink_to("../tools/cc", target_is_directory=True)
    return link


def _add_skill(repo: Path) -> None:
    skill_dir = repo / "playbook" / "skills" / _SKILL
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {_SKILL}\nname: {_SKILL}\ndescription: A demo skill\n---\nDo it.\n"
    )


def _lock_paths(repo: Path) -> list[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return [entry.path for entry in lockfile.entries]


def test_write_mode_names_a_dangling_output_dir_link_instead_of_a_traceback(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    link = _dangle_commands_dir(repo)

    assert _sync.execute(repo, git=FakeGitClient()) == 1

    err = capsys.readouterr().err
    assert "error: .claude/commands is a dangling symbolic link" in err
    assert "../tools/cc does not exist" in err
    assert "re-run 'playbook sync'" in err
    assert link.is_symlink()  # neither replaced nor followed
    assert not (repo / "tools").exists()


def test_check_names_a_dangling_output_dir_link_and_promises_no_replacement(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _dangle_commands_dir(repo)

    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1

    out = capsys.readouterr().out
    assert ".claude/commands is a dangling symbolic link" in out
    assert "replaces it only" not in out  # write mode never replaces a link


@pytest.mark.usefixtures("sample_hook_handlers")
def test_a_dangling_link_at_settings_json_is_replaced_and_check_says_so(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """The co-owned ``.claude/settings.json`` is written by atomic replace, so a
    dangling link there is no blocker: ``--check`` must not say sync stops on it."""
    repo = make_hook_repo(tmp_path / "repo", make_synthetic_repo)
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / SETTINGS).symlink_to("../gone/s.json")
    deps = hook_deps(tmp_path / "state")

    assert _sync.execute(repo, check=True, git=FakeGitClient(), hook_deps=deps) == 1
    out = capsys.readouterr().out
    assert f"  {SETTINGS}\n    Missing on disk; run 'playbook sync' to create." in out

    assert _sync.execute(repo, git=FakeGitClient(), hook_deps=deps) == 0
    assert not (repo / SETTINGS).is_symlink()


def test_an_unreadable_link_target_keeps_its_own_error(repo: Path, tmp_path: Path) -> None:
    """A live link into a directory nobody may search is no dangling link: the
    original error propagates, never one raised from the dangling-link handler."""
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    locked = tmp_path / "locked"
    (locked / "cc").mkdir(parents=True)
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").symlink_to(locked / "cc", target_is_directory=True)
    locked.chmod(0)
    try:
        with pytest.raises(OSError) as raised:
            _sync.execute(repo, git=FakeGitClient())
    finally:
        locked.chmod(0o755)

    frames = [str(entry.path) for entry in raised.traceback]
    assert not [frame for frame in frames if "_output_blockers" in frame or "_symlinks" in frame]


def test_output_linked_out_of_the_repo_gets_no_lockfile_entry(repo: Path, tmp_path: Path) -> None:
    _add_skill(repo)
    outside = tmp_path / "shared-skills"
    outside.mkdir()
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "skills").symlink_to(outside, target_is_directory=True)

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    assert (outside / _SKILL / "SKILL.md").is_file()  # still written through the link
    paths = _lock_paths(repo)
    assert f".opencode/skills/{_SKILL}/SKILL.md" in paths  # the in-repo root stays owned
    assert not [path for path in paths if path.startswith("/")], paths
    assert str(tmp_path) not in (repo / ".coding-agent-playbook.lock").read_text()


def test_absolute_entry_from_an_older_sync_is_dropped(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "shared" / "SKILL.md"
    outside.parent.mkdir()
    outside.write_text("old\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert lockfile is not None
    lockfile.entries.append(LockEntry(path=outside.as_posix(), sha256="0" * 64, bytes=4))
    state.save_lockfile(lockfile)

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    assert outside.as_posix() not in _lock_paths(repo)
    assert outside.read_text() == "old\n"  # released, never deleted
