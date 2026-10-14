"""Regression: output an earlier sync left behind never becomes committable.

``cleanup_stale`` never deletes inside a skill directory (and never runs for a
disabled adapter). Before the fix those files fell out of the managed
``.gitignore`` block, showed up as untracked, and the ``--check-staged`` guard
let them through. Now the previous lockfile owns them: pristine + untracked
leftovers are deleted, everything else stays ignored — and a file the engine
never wrote is never deleted, even inside an engine-owned skill dir.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.lockfile import compute_hash
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_SKILL = "demo"
_SKILL_OUT = f".claude/skills/{_SKILL}"
# Native skill roots under the default fixture config (claude_code + opencode).
_SKILL_ROOTS = (".claude/skills", ".opencode/skills")
_HARNESS_CONFIG = _DEFAULT_CONFIG.replace(
    'adapters_enabled = ["continue", "claude_code", "opencode"]',
    'adapters_enabled = ["claude_code", "agent_harness"]',
)


def _add_skill(repo: Path) -> None:
    skill_dir = repo / "playbook" / "skills" / _SKILL
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {_SKILL}\nname: {_SKILL}\ndescription: A demo skill\n---\nDo it.\n"
    )
    (skill_dir / "scripts" / "run.sh").write_text("#!/bin/sh\necho hi\n")


def _remove_skill_source(repo: Path) -> None:
    shutil.rmtree(repo / "playbook" / "skills" / _SKILL)


def _commit_output(repo: Path) -> None:
    config = repo / ".coding-agent-playbook.toml"
    config.write_text(config.read_text() + "\n[output]\ncommit = true\n")


def _lock_paths(repo: Path) -> set[str]:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return {entry.path for entry in lockfile.entries}


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    built = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])
    _add_skill(built)
    return built


def test_removed_skill_pristine_leftovers_are_deleted(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / _SKILL_OUT / "scripts" / "run.sh").is_file()
    _remove_skill_source(repo)
    capsys.readouterr()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    for root in _SKILL_ROOTS:  # files deleted, empty dirs pruned up to the skills root
        assert not (repo / root).exists(), root
    assert f"/{_SKILL_OUT}/" not in (repo / ".gitignore").read_text()
    assert not any(path.startswith(_SKILL_OUT) for path in _lock_paths(repo))
    # 2 roots x (SKILL.md + run.sh) as orphans, plus Continue's degraded prompt
    # that cleanup_stale removed itself (sentinel on line 1).
    assert "5 removed" in capsys.readouterr().out


def test_modified_leftover_stays_ignored_and_owned(repo: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    script = repo / _SKILL_OUT / "scripts" / "run.sh"
    script.write_text("#!/bin/sh\necho edited by hand\n")
    _remove_skill_source(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert script.read_text() == "#!/bin/sh\necho edited by hand\n"  # never deleted
    assert not (repo / _SKILL_OUT / "SKILL.md").exists()  # pristine sibling deleted
    assert f"\n/{_SKILL_OUT}/scripts/run.sh\n" in (repo / ".gitignore").read_text()
    assert f"{_SKILL_OUT}/scripts/run.sh" in _lock_paths(repo)  # carried forward
    # Steady state: the next sync and --check agree and keep owning it.
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert f"{_SKILL_OUT}/scripts/run.sh" in _lock_paths(repo)
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_kept_leftover_is_released_once_deleted(repo: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    script = repo / _SKILL_OUT / "scripts" / "run.sh"
    script.write_text("edited\n")
    _remove_skill_source(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    script.unlink()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert "run.sh" not in (repo / ".gitignore").read_text()
    assert not any("run.sh" in path for path in _lock_paths(repo))


def test_tracked_leftover_is_kept_and_reported(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    _remove_skill_source(repo)
    git = FakeGitClient(tracked={f"{_SKILL_OUT}/SKILL.md"})
    capsys.readouterr()
    assert _sync.execute(repo, git=git) == 0
    assert (repo / _SKILL_OUT / "SKILL.md").is_file()  # tracked: never deleted
    assert not (repo / _SKILL_OUT / "scripts" / "run.sh").exists()
    assert f"  {_SKILL_OUT}/SKILL.md\n" in capsys.readouterr().err


def test_user_file_dropped_into_engine_owned_skill_dir_survives_removal(repo: Path) -> None:
    """The skill dir is engine-owned (sentinel ``SKILL.md``), but a file the engine
    never wrote is not in the lockfile: it is a user file and is never deleted."""
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    notes = repo / _SKILL_OUT / "notes.md"
    notes.write_text("mine\n")
    _remove_skill_source(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert notes.read_text() == "mine\n"
    assert sorted(p.name for p in (repo / _SKILL_OUT).iterdir()) == ["notes.md"]
    assert "notes.md" not in (repo / ".gitignore").read_text()  # the user's, not ours
    assert not any(path.startswith(_SKILL_OUT) for path in _lock_paths(repo))
    assert not (repo / ".opencode" / "skills").exists()  # untouched root still pruned


def test_stale_script_of_a_live_skill_pristine_deleted_edited_kept(repo: Path) -> None:
    """A script dropped from a skill that still exists: the pristine copy goes, an
    edited copy stays owned (lockfile + the collapsed skill-dir block entry)."""
    source_scripts = repo / "playbook" / "skills" / _SKILL / "scripts"
    (source_scripts / "old.sh").write_text("old\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (source_scripts / "old.sh").unlink()
    edited = repo / _SKILL_OUT / "scripts" / "old.sh"
    edited.write_text("edited by hand\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert edited.read_text() == "edited by hand\n"
    assert not (repo / ".opencode" / "skills" / _SKILL / "scripts" / "old.sh").exists()
    assert f"{_SKILL_OUT}/scripts/old.sh" in _lock_paths(repo)
    assert f"\n/{_SKILL_OUT}/\n" in (repo / ".gitignore").read_text()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_without_a_previous_lockfile_nothing_in_skill_dirs_is_deleted(repo: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / ".coding-agent-playbook.lock").unlink()
    _remove_skill_source(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    for root in _SKILL_ROOTS:
        assert (repo / root / _SKILL / "scripts" / "run.sh").is_file(), root


def test_commit_true_settles_skill_leftovers_with_the_same_policy(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``[output] commit = true``: pristine untracked leftovers are deleted, a tracked
    (committed) one is kept and listed on stderr, a user file is never touched."""
    config = repo / ".coding-agent-playbook.toml"
    config.write_text(config.read_text() + "\n[output]\ncommit = true\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    notes = repo / _SKILL_OUT / "notes.md"
    notes.write_text("mine\n")
    _remove_skill_source(repo)
    git = FakeGitClient(tracked={f"{_SKILL_OUT}/SKILL.md"})
    capsys.readouterr()
    assert _sync.execute(repo, git=git) == 0
    assert (repo / _SKILL_OUT / "SKILL.md").is_file()  # tracked: kept
    assert notes.read_text() == "mine\n"  # user file: never deleted
    assert not (repo / _SKILL_OUT / "scripts").exists()  # pristine + untracked: deleted
    assert not (repo / ".opencode" / "skills").exists()
    assert f"{_SKILL_OUT}/SKILL.md" in _lock_paths(repo)  # still owned
    err = capsys.readouterr().err
    assert f"  {_SKILL_OUT}/SKILL.md\n" in err
    assert "notes.md" not in err
    assert not (repo / ".gitignore").exists()
    assert _sync.execute(repo, check=True, git=git) == 0


def test_git_failing_inside_a_work_tree_keeps_committed_leftovers(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: with git unavailable (PATH, 'dubious ownership', timeout) the tracked
    check read as "nothing tracked" and committed leftovers were deleted. Inside a work
    tree an unknown answer keeps everything (fail closed) and lists it."""
    _commit_output(repo)
    (repo / ".git").mkdir()  # a work tree git cannot answer about
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    _remove_skill_source(repo)
    capsys.readouterr()
    assert _sync.execute(repo, git=FakeGitClient(tracked=None)) == 0
    captured = capsys.readouterr()
    for rel in ("SKILL.md", "scripts/run.sh"):
        assert (repo / _SKILL_OUT / rel).is_file(), rel
        assert f"  {_SKILL_OUT}/{rel}\n" in captured.err, rel
        assert f"{_SKILL_OUT}/{rel}" in _lock_paths(repo), rel


def test_tampered_lockfile_never_deletes_git_internals_or_user_files(repo: Path) -> None:
    """Regression: under ``commit = true`` the lockfile is committed (merged), and its
    entries were a deletion authority with no allowlist — ``.git/HEAD`` included."""
    _commit_output(repo)
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('app')\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    lock = repo / ".coding-agent-playbook.lock"
    extra = ""
    for rel in (".git/HEAD", "src/app.py"):
        content = (repo / rel).read_bytes()
        extra += f'\n[[entries]]\npath = "{rel}"\nsha256 = "{compute_hash(content)}"\n'
        extra += f"bytes = {len(content)}\n"
    lock.write_text(lock.read_text() + extra)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / ".git" / "HEAD").read_text() == "ref: refs/heads/main\n"
    assert (repo / "src" / "app.py").is_file()
    assert not {".git/HEAD", "src/app.py"} & _lock_paths(repo)  # released, not owned


def test_swap_never_displaces_an_edited_committed_leftover(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: a file/folder swap rmtree'd ``scripts/lib/`` holding a user-edited
    (and committed) file because it was merely *listed* in the lockfile."""
    _commit_output(repo)
    lib = repo / "playbook" / "skills" / _SKILL / "scripts" / "lib"
    lib.mkdir()
    (lib / "a.py").write_text("a\n")
    git = FakeGitClient()
    assert _sync.execute(repo, git=git) == 0
    edited = repo / _SKILL_OUT / "scripts" / "lib" / "a.py"
    edited.write_text("a\n# my important local edits\n")
    shutil.rmtree(lib)
    lib.write_text("now a file\n")
    capsys.readouterr()
    assert _sync.execute(repo, git=git) == 0
    assert edited.read_text() == "a\n# my important local edits\n"
    assert f"not writing {repo / _SKILL_OUT / 'scripts' / 'lib'}" in capsys.readouterr().err
    # The pristine copy in the other root was displaced (and counted as removed).
    assert (repo / ".opencode" / "skills" / _SKILL / "scripts" / "lib").read_text() == (
        "now a file\n"
    )


def test_swap_displacing_pristine_output_counts_as_removed(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lib = repo / "playbook" / "skills" / _SKILL / "scripts" / "lib"
    lib.mkdir()
    (lib / "a.py").write_text("a\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    shutil.rmtree(lib)
    lib.write_text("now a file\n")
    capsys.readouterr()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert ", 2 removed" in capsys.readouterr().out  # lib/a.py in both skill roots
    for root in _SKILL_ROOTS:
        assert (repo / root / _SKILL / "scripts" / "lib").read_text() == "now a file\n"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_symlinked_skills_root_target_survives_removing_the_last_skill(repo: Path) -> None:
    """Regression (SPEC §12.3 layout ``.claude/skills -> ../.agents/skills``): pruning
    followed the lockfile's resolved paths, removed ``.agents/skills`` and ``.agents``,
    and every later sync crashed on the dangling link."""
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / ".agents" / "skills" / _SKILL / "SKILL.md").is_file()
    _remove_skill_source(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / ".agents" / "skills").is_dir()
    assert not (repo / ".agents" / "skills" / _SKILL).exists()
    assert (repo / ".claude" / "skills").is_symlink()
    _add_skill(repo)  # adding a skill afterwards must neither crash nor drift
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / ".agents" / "skills" / _SKILL / "SKILL.md").is_file()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_harness_removed_skill_settles_through_the_leftover_policy(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the harness ``cleanup_stale`` deleted a removed skill's user-edited
    script and left an empty ``skills/`` tree that HARNESS.md then indexed, so
    ``--check`` failed forever. Skill dirs are the leftover policy's alone."""
    repo = make_synthetic_repo(tmp_path, config_text=_HARNESS_CONFIG, rules=[("r", "B\n")])
    _add_skill(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    edited = repo / "skills" / _SKILL / "scripts" / "run.sh"
    edited.write_text("edited\n")
    _remove_skill_source(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert edited.read_text() == "edited\n"
    assert not (repo / "skills" / _SKILL / "SKILL.md").exists()  # pristine: deleted
    assert f"skills/{_SKILL}/scripts/run.sh" in _lock_paths(repo)
    capsys.readouterr()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0
    edited.unlink()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert not (repo / "skills").exists()  # emptied harness root pruned
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_harness_case_only_rename_converges(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (case-insensitive FS): harness cleanup compared spellings, deleted the
    freshly written ``skills/demo/SKILL.md`` under its old ``Demo`` spelling, and re-did
    it on every sync."""
    probe = tmp_path / "CaseProbe"
    probe.mkdir()
    insensitive = (tmp_path / "caseprobe").exists()
    probe.rmdir()
    if not insensitive:
        pytest.skip("needs a case-insensitive filesystem")
    repo = make_synthetic_repo(tmp_path, config_text=_HARNESS_CONFIG, rules=[("r", "B\n")])
    skill_md = repo / "playbook" / "skills" / "Demo" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\nid: Demo\nname: Demo\ndescription: d\n---\nDo it.\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    skill_md.write_text(skill_md.read_text().replace("id: Demo", "id: demo"))
    for _ in range(2):
        capsys.readouterr()
        assert _sync.execute(repo, git=FakeGitClient()) == 0
        assert ", 0 removed" in capsys.readouterr().out
        assert (repo / "skills" / "demo" / "SKILL.md").is_file()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_disabled_adapter_output_is_deleted(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_HARNESS_CONFIG, rules=[("r", "B\n")])
    _add_skill(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / "HARNESS.md").is_file()
    harness_paths = {p for p in _lock_paths(repo) if not p.startswith((".claude/", "AGENTS"))}
    assert harness_paths
    (repo / ".coding-agent-playbook.toml").write_text(_DEFAULT_CONFIG)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    for rel in harness_paths:
        assert not (repo / rel).exists(), rel
    assert not (repo / "skills").exists()
    gitignore = (repo / ".gitignore").read_text()
    assert "/HARNESS.md" not in gitignore
    assert not harness_paths & _lock_paths(repo)


def test_missing_adapter_keeps_its_previous_output(
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An enabled adapter missing from this environment (e.g. pre-commit's
    hook venv) must not get its output deleted or un-ignored."""
    repo = make_synthetic_repo(tmp_path, config_text=_HARNESS_CONFIG, rules=[("r", "B\n")])
    _add_skill(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    before = _lock_paths(repo)
    missing = _HARNESS_CONFIG.replace('"agent_harness"', '"agent_harness", "not_installed_x"')
    (repo / ".coding-agent-playbook.toml").write_text(missing.replace('"claude_code", ', ""))
    capsys.readouterr()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert f"{_SKILL_OUT}/SKILL.md" in _lock_paths(repo)
    assert (repo / _SKILL_OUT / "SKILL.md").is_file()
    assert f"/{_SKILL_OUT}/" in (repo / ".gitignore").read_text()
    assert before <= _lock_paths(repo)
    assert "not_installed_x" in capsys.readouterr().err


def test_check_reports_block_drift_until_leftovers_are_settled(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    _remove_skill_source(repo)
    capsys.readouterr()
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 1
    assert "missing or stale" in capsys.readouterr().out
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _sync.execute(repo, check=True, git=FakeGitClient()) == 0


def test_check_staged_flags_leftovers_before_resync(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    _remove_skill_source(repo)
    staged = [f"{_SKILL_OUT}/SKILL.md", f"{_SKILL_OUT}/scripts/run.sh", "src/a.py"]
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=staged)) == 1
    out = capsys.readouterr().out
    assert f"  {_SKILL_OUT}/scripts/run.sh\n" in out
    assert "src/a.py" not in out


def test_check_staged_flags_kept_modified_leftover(repo: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / _SKILL_OUT / "scripts" / "run.sh").write_text("edited\n")
    _remove_skill_source(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    staged = [f"{_SKILL_OUT}/scripts/run.sh"]
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=staged)) == 1


def test_lockfile_entries_outside_the_repo_are_never_deleted(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "keep.md"
    outside.write_text("x")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    lock = repo / ".coding-agent-playbook.lock"
    digest = compute_hash(b"x")
    lock.write_text(
        lock.read_text()
        + f'\n[[entries]]\npath = "{outside}"\nsha256 = "{digest}"\nbytes = 1\n'
        + f'\n[[entries]]\npath = ".gitignore"\nsha256 = "{digest}"\nbytes = 1\n'
    )
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert outside.read_text() == "x"
    assert (repo / ".gitignore").is_file()


def test_unreadable_lockfile_is_ignored_with_a_warning(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / ".coding-agent-playbook.lock").write_text("not = [valid toml")
    capsys.readouterr()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert "ignoring unreadable .coding-agent-playbook.lock" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# End-to-end with real git (cheap, guarded)
# --------------------------------------------------------------------------- #

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, timeout=10
    )
    return proc.stdout


@needs_git
@pytest.mark.usefixtures("hermetic_git_env")
def test_e2e_removed_skill_output_is_never_staged(repo: Path) -> None:
    _git(repo, "init", "-q")
    assert _sync.execute(repo) == 0
    (repo / _SKILL_OUT / "scripts" / "run.sh").write_text("edited\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", "sources")
    _remove_skill_source(repo)
    assert _sync.execute(repo) == 0
    _git(repo, "add", "-A")
    staged = _git(repo, "diff", "--cached", "--name-only").split()
    assert not any(path.startswith(".claude/") for path in staged)
    assert _sync.execute(repo, check_staged=True) == 0
    _git(repo, "add", "-f", f"{_SKILL_OUT}/scripts/run.sh")
    assert _sync.execute(repo, check_staged=True) == 1


@needs_git
@pytest.mark.usefixtures("hermetic_git_env")
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_e2e_skill_taken_over_through_a_symlink_is_never_deleted(repo: Path) -> None:
    """Regression: the user moved a generated skill into ``my-skills/``, linked it back
    and committed it; the old lockfile entries resolved through the link (and git's
    ``ls-files`` cannot see through it), so sync deleted the committed files."""
    _git(repo, "init", "-q")
    assert _sync.execute(repo) == 0
    (repo / "my-skills").mkdir()
    (repo / _SKILL_OUT).rename(repo / "my-skills" / _SKILL)
    (repo / _SKILL_OUT).symlink_to(f"../../my-skills/{_SKILL}", target_is_directory=True)
    _remove_skill_source(repo)
    _git(repo, "add", "my-skills")
    _git(repo, "commit", "-q", "--no-verify", "-m", "take the skill over")
    assert _sync.execute(repo) == 0
    assert (repo / "my-skills" / _SKILL / "SKILL.md").is_file()
    assert (repo / "my-skills" / _SKILL / "scripts" / "run.sh").is_file()
    assert " D " not in _git(repo, "status", "--porcelain")
    assert "my-skills" not in (repo / ".gitignore").read_text()


@needs_git
@pytest.mark.usefixtures("hermetic_git_env")
def test_e2e_tracked_leftover_after_a_case_only_dir_rename_is_kept(repo: Path) -> None:
    """Regression (case-insensitive FS, ``commit = true``): after the engine renamed
    ``Demo/`` to ``demo/`` the index still says ``Demo/...``; a case-sensitive pathspec
    judged the committed leftover untracked, and sync deleted it."""
    probe = repo / "CaseProbe"
    probe.mkdir()
    insensitive = (repo / "caseprobe").exists()
    probe.rmdir()
    if not insensitive:
        pytest.skip("needs a case-insensitive filesystem")
    _commit_output(repo)
    _git(repo, "init", "-q")
    source = repo / "playbook" / "skills" / "Demo"
    (repo / "playbook" / "skills" / _SKILL).rename(source)
    skill_md = source / "SKILL.md"
    skill_md.write_text(skill_md.read_text().replace(f"id: {_SKILL}", "id: Demo"))
    (source / "scripts" / "old.sh").write_text("old\n")
    assert _sync.execute(repo) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", "committed output")
    skill_md.write_text(skill_md.read_text().replace("id: Demo", "id: demo"))
    assert _sync.execute(repo) == 0  # renames .claude/skills/Demo -> demo
    (source / "scripts" / "old.sh").unlink()
    assert _sync.execute(repo) == 0
    assert (repo / ".claude" / "skills" / "demo" / "scripts" / "old.sh").is_file()
    status = _git(repo, "status", "--porcelain").splitlines()
    assert not [line for line in status if line.startswith(" D .claude/")], status
