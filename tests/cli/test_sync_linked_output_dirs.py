"""Output directories reached through a symlink: one that dangles, one that leaves the repo
or a skill directory.

Regressions (SPEC §4.2 steps 8-9, §12.2, §14.4):

- A dangling ``.claude/commands -> ../tools/cc`` made write-mode ``playbook
  sync`` crash with a ``FileExistsError`` traceback from ``mkdir``, and
  ``--check`` claimed sync would replace the link. Both now name the link and
  its missing target, exit 1, and leave the link alone.
- An output dir linked out of the repo (``.claude/skills -> /abs/dir``) put an
  absolute, machine-specific path in ``.coding-agent-playbook.lock``. The
  lockfile never owns output there (step 9 already released such an entry when
  read), so it now gets no entry at all.

- A link inside a skill directory leading out of it (``.claude/skills/demo/scripts
  -> /elsewhere``), or a skill directory linked out of its skills root, stopped
  ``playbook sync`` with a ``ValueError`` traceback from the skill writer (the
  latter in ``--check`` too). The skill writer skips it with a warning instead,
  as it does every other skill-dir refusal (SPEC §10.8): the file inside the
  skill dir is named by ``--check`` until the link goes, the linked skill dir is
  skipped by every mode.

``test_absolute_entry_from_an_older_sync_is_dropped`` pins behaviour that
predates the fix: such an entry is released on the next sync, never deleted.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.lockfile.model import LockEntry
from coding_agent_playbook.sync import pipeline as _sync
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


def _add_skill(repo: Path, *, script: bool = False) -> None:
    skill_dir = repo / "playbook" / "skills" / _SKILL
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {_SKILL}\nname: {_SKILL}\ndescription: A demo skill\n---\nDo it.\n"
    )
    if script:
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "run.sh").write_text("echo hi\n")


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
    assert not [frame for frame in frames if "_output_blockers" in frame or "symlinks.py" in frame]


@pytest.mark.parametrize("dangling", [False, True], ids=["live", "dangling"])
def test_a_link_leaving_a_skill_dir_is_skipped_with_a_warning_and_named_by_check(
    repo: Path, tmp_path: Path, dangling: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_skill(repo, script=True)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    outside = tmp_path / "shared-scripts"
    if not dangling:
        outside.mkdir()
    scripts = repo / ".claude" / "skills" / _SKILL / "scripts"
    shutil.rmtree(scripts)
    scripts.symlink_to(outside, target_is_directory=True)
    capsys.readouterr()

    assert _sync.execute(repo, git=FakeGitClient()) == 0

    err = capsys.readouterr().err
    assert f"{scripts} is a symbolic link leading outside the skill directory" in err
    assert not outside.exists() or list(outside.iterdir()) == []
    assert scripts.is_symlink()
    assert (scripts.parent / "SKILL.md").is_file()  # the rest of the skill is still written
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1
    assert (
        f"  .claude/skills/{_SKILL}/scripts/run.sh\n"
        f"    Missing on disk: .claude/skills/{_SKILL}/scripts is a symbolic link leading outside "
        "the skill directory, and sync never writes through one.\n"
        "    Remove or re-point the link, then run 'playbook sync'."
    ) in capsys.readouterr().out


def test_a_skill_dir_linked_out_of_its_root_is_skipped_in_every_mode(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_skill(repo)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".claude" / "skills" / _SKILL).symlink_to(outside, target_is_directory=True)

    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert "outside the skills root" in capsys.readouterr().err
    assert list(outside.iterdir()) == []
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0  # skipped there too
    assert "outside the skills root" in capsys.readouterr().err


def test_a_looping_output_dir_link_is_named_not_a_traceback(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (Python 3.12, where ``Path.resolve()`` raises on a symlink loop): a
    looping declared output dir crashed sync before any message."""
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "commands").symlink_to("commands")
    problem = (
        ".claude/commands is a dangling symbolic link: its target commands is a symbolic link loop"
    )

    assert _sync.execute(repo, git=FakeGitClient()) == 1
    assert f"error: {problem}" in capsys.readouterr().err
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1
    assert f"    Missing on disk: {problem}." in capsys.readouterr().out


def test_looping_links_in_a_skills_root_never_crash(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (Python 3.12): a loop inside a skill dir, at the skill dir, or at a
    removed skill's dir each crashed the skill writer or the leftover policy."""
    _add_skill(repo, script=True)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    skill_dir = repo / ".claude" / "skills" / _SKILL
    shutil.rmtree(skill_dir / "scripts")
    (skill_dir / "scripts").symlink_to("scripts")

    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1
    assert _sync.execute(repo, git=FakeGitClient()) == 0  # a link inside never blocks
    assert (skill_dir / "scripts" / "run.sh").is_file()
    shutil.rmtree(skill_dir)
    skill_dir.symlink_to(_SKILL)
    assert _sync.execute(repo, git=FakeGitClient()) == 0  # the looping skill dir is skipped
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    shutil.rmtree(repo / "playbook" / "skills" / _SKILL)  # its entries now name a loop
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert skill_dir.is_symlink()
    capsys.readouterr()


def test_a_looping_opencode_plugins_dir_never_crashes_the_stale_scan(repo: Path) -> None:
    """Regression (Python 3.12): with hooks off the stale-shim check resolved
    ``.opencode/plugins/playbook-hooks.js`` and crashed on ``plugins -> plugins``."""
    (repo / ".opencode").mkdir(exist_ok=True)
    (repo / ".opencode" / "plugins").symlink_to("plugins")

    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_a_looping_skill_md_in_a_user_skill_dir_never_crashes(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (Python 3.12): judging a user's own colliding skill dir looked its
    ``SKILL.md`` up in the lockfile by resolved path, and ``SKILL.md -> SKILL.md`` crashed."""
    _add_skill(repo)
    user_dir = repo / ".claude" / "skills" / _SKILL
    user_dir.mkdir(parents=True)
    (user_dir / "notes.md").write_text("mine\n", encoding="utf-8")
    (user_dir / "SKILL.md").symlink_to("SKILL.md")

    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient()) == 0
    assert "not playbook-managed" in capsys.readouterr().err
    assert (user_dir / "SKILL.md").is_symlink()


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
