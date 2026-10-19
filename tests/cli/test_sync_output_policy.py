"""``playbook sync`` under the ``[output] commit`` policy (SPEC §12.2/§12.3).

Covers the managed ``.gitignore`` block in write mode, its drift in ``--check``,
the tracked-output warning, and the ``--check-staged`` guard. Git is always the
injected :class:`~tests.fakes.FakeGitClient` except in the two guarded
end-to-end tests at the bottom, which build a throwaway repo with real git.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.generated_output.gitignore import BLOCK_END, BLOCK_START
from coding_agent_playbook.sync import pipeline as _sync
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_COMMIT_TRUE_CONFIG = _DEFAULT_CONFIG + "\n[output]\ncommit = true\n"
_SKILL = "demo-skill"


def _add_skill(repo: Path) -> None:
    skill_dir = repo / "playbook" / "skills" / _SKILL
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {_SKILL}\nname: {_SKILL}\ndescription: A demo skill\n---\nDo the thing.\n"
    )
    (skill_dir / "scripts" / "run.sh").write_text("#!/bin/sh\necho hi\n")


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    built = make_synthetic_repo(
        tmp_path,
        rules=[("style-guide", "Use spaces.\n")],
        # Not an engine prompt id: overriding one (``refactor``) without its
        # eval_tasks fails validate, so sync would refuse to write (prK §P P8).
        prompts=[("tidy-up", {"slash": "tidy-up", "body": "Tidy up.\n"})],
    )
    _add_skill(built)
    return built


def _gitignore(repo: Path) -> str:
    return (repo / ".gitignore").read_text()


def _set_commit_true(repo: Path) -> None:
    (repo / ".coding-agent-playbook.toml").write_text(_COMMIT_TRUE_CONFIG)


# --------------------------------------------------------------------------- #
# Write mode: managed block
# --------------------------------------------------------------------------- #


def test_write_mode_writes_managed_block_by_default(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    text = _gitignore(repo)
    assert text.startswith(BLOCK_START)
    assert text.rstrip("\n").endswith(BLOCK_END)
    for entry in (
        "/AGENTS.md",
        "/.claude/CLAUDE.md",
        "/.claude/rules/coding-agent-playbook.md",
        "/.claude/commands/tidy-up.md",
        "/.continue/rules/50-style-guide.md",
        "/.opencode/command/tidy-up.md",
        "/.coding-agent-playbook.lock",
        f"/.claude/skills/{_SKILL}/",
    ):
        assert f"\n{entry}\n" in text
    assert "SKILL.md" not in text  # collapsed into the skill directory entry
    assert "Updated the managed block in .gitignore" in capsys.readouterr().out


def test_write_mode_is_idempotent(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    first = (repo / ".gitignore").read_bytes()
    capsys.readouterr()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert (repo / ".gitignore").read_bytes() == first
    assert "managed block" not in capsys.readouterr().out


def test_write_mode_preserves_user_gitignore_lines(repo: Path) -> None:
    (repo / ".gitignore").write_text("*.pyc\n.venv/\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _gitignore(repo).startswith(f"*.pyc\n.venv/\n\n{BLOCK_START}\n")


def test_gitignore_is_never_in_the_lockfile(repo: Path) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    paths = {entry.path for entry in lockfile.entries}
    assert ".gitignore" not in paths
    assert "AGENTS.md" in paths


def test_commit_true_removes_the_block(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / ".gitignore").write_text("*.pyc\n")
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    _set_commit_true(repo)
    capsys.readouterr()
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert _gitignore(repo) == "*.pyc\n"
    assert "Removed the managed block from .gitignore" in capsys.readouterr().out


def test_commit_true_never_creates_gitignore(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = make_synthetic_repo(tmp_path, config_text=_COMMIT_TRUE_CONFIG, rules=[("x", "B\n")])
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    assert not (repo / ".gitignore").exists()


def test_write_mode_malformed_block_fails_without_clobbering(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = f"*.pyc\n{BLOCK_START}\n/AGENTS.md\n"
    (repo / ".gitignore").write_text(broken)
    assert _sync.execute(repo, git=FakeGitClient()) == 1
    assert _gitignore(repo) == broken
    err = capsys.readouterr().err
    assert "error:" in err
    assert ".gitignore:2:" in err


# --------------------------------------------------------------------------- #
# --check: managed block drift
# --------------------------------------------------------------------------- #


def test_check_passes_with_current_block(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    capsys.readouterr()
    assert _sync.execute(repo, check=True) == 0
    assert "No drift" in capsys.readouterr().out


def test_check_reports_missing_block_without_writing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / ".gitignore").unlink()
    capsys.readouterr()
    assert _sync.execute(repo, check=True) == 1
    out = capsys.readouterr().out
    assert "Drift detected" in out
    assert ".gitignore" in out
    assert "missing or stale" in out
    assert not (repo / ".gitignore").exists()


def test_check_reports_stale_block(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    stale = _gitignore(repo).replace("/AGENTS.md\n", "")
    (repo / ".gitignore").write_text(stale)
    capsys.readouterr()
    assert _sync.execute(repo, check=True) == 1
    assert "missing or stale" in capsys.readouterr().out
    assert _gitignore(repo) == stale


def test_check_reports_malformed_block(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    (repo / ".gitignore").write_text(f"{BLOCK_END}\n")
    capsys.readouterr()
    assert _sync.execute(repo, check=True) == 1
    assert "Malformed managed block" in capsys.readouterr().out


def test_check_ignores_block_when_commit_true(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_commit_true(repo)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    capsys.readouterr()
    assert _sync.execute(repo, check=True) == 0
    assert not (repo / ".gitignore").exists()


# --------------------------------------------------------------------------- #
# Tracked-output warning
# --------------------------------------------------------------------------- #


def test_warns_about_tracked_generated_output(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    git = FakeGitClient(tracked={"AGENTS.md", ".coding-agent-playbook.lock", "src/app.py"})
    assert _sync.execute(repo, git=git) == 0
    err = capsys.readouterr().err
    assert "generated output is still tracked" in err
    assert "  AGENTS.md\n" in err
    assert "git rm -r --cached -- .coding-agent-playbook.lock AGENTS.md" in err
    assert "src/app.py" not in err
    asked = git.calls[0][1]
    assert ".coding-agent-playbook.lock" in asked
    assert f".claude/skills/{_SKILL}/SKILL.md" in asked


def test_no_warning_when_nothing_tracked(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sync.execute(repo, git=FakeGitClient(tracked=set())) == 0
    assert capsys.readouterr().err == ""


def test_no_warning_outside_a_git_repo(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _sync.execute(repo, git=FakeGitClient(tracked=None)) == 0
    assert capsys.readouterr().err == ""


def test_commit_true_never_asks_git(repo: Path) -> None:
    _set_commit_true(repo)
    git = FakeGitClient(tracked={"AGENTS.md"})
    assert _sync.execute(repo, git=git) == 0
    assert git.calls == []


# --------------------------------------------------------------------------- #
# --check-staged
# --------------------------------------------------------------------------- #


def test_check_staged_passes_for_source_only_commit(repo: Path) -> None:
    git = FakeGitClient(staged=["src/app.py", "playbook/rules/style-guide.md", ".gitignore"])
    assert _sync.execute(repo, check_staged=True, git=git) == 0


def test_check_staged_fails_listing_generated_paths(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    staged = [
        "AGENTS.md",
        f".claude/skills/{_SKILL}/scripts/run.sh",
        ".coding-agent-playbook.lock",
        "src/app.py",
    ]
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=staged)) == 1
    out = capsys.readouterr().out
    assert "Generated output is staged" in out
    for path in staged[:3]:
        assert f"  {path}\n" in out
    assert "src/app.py" not in out
    assert "git rm -r --cached -- AGENTS.md" in out


def test_check_staged_never_writes(repo: Path) -> None:
    git = FakeGitClient(staged=["AGENTS.md"])
    assert _sync.execute(repo, check_staged=True, git=git) == 1
    assert not (repo / "AGENTS.md").exists()
    assert not (repo / ".gitignore").exists()
    assert not (repo / ".coding-agent-playbook.lock").exists()


def test_check_staged_is_noop_when_commit_true(repo: Path) -> None:
    _set_commit_true(repo)
    git = FakeGitClient(staged=["AGENTS.md"])
    assert _sync.execute(repo, check_staged=True, git=git) == 0
    assert git.calls == []


@pytest.mark.parametrize("staged", [None, []])
def test_check_staged_passes_outside_repo_or_when_nothing_staged(
    repo: Path, staged: list[str] | None
) -> None:
    assert _sync.execute(repo, check_staged=True, git=FakeGitClient(staged=staged)) == 0


def test_execute_rejects_both_check_modes(repo: Path) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        _sync.execute(repo, check=True, check_staged=True, git=FakeGitClient())


def test_cli_parses_check_staged_and_rejects_both_modes() -> None:
    parser = build_parser()
    args = parser.parse_args(["sync", "--check-staged"])
    assert args.check_staged is True
    assert args.check is False
    with pytest.raises(SystemExit):
        parser.parse_args(["sync", "--check", "--check-staged"])


@pytest.mark.usefixtures("hermetic_git_env")
def test_run_check_staged_outside_a_repo_exits_zero(repo: Path) -> None:
    """``run()`` wires the real client; outside a git repo the guard is silent."""
    args = argparse.Namespace(repo_root=str(repo), check=False, check_staged=True)
    assert sync_cmd.run(args) == 0


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
def test_e2e_generated_output_is_ignored_and_guarded(repo: Path) -> None:
    _git(repo, "init", "-q")
    assert _sync.execute(repo) == 0
    _git(repo, "add", "-A")
    staged = _git(repo, "diff", "--cached", "--name-only").split()
    assert ".gitignore" in staged
    assert "AGENTS.md" not in staged
    assert not any(path.startswith(".claude/") for path in staged)
    assert _sync.execute(repo, check_staged=True) == 0
    _git(repo, "add", "-f", "AGENTS.md")
    assert _sync.execute(repo, check_staged=True) == 1


@needs_git
@pytest.mark.usefixtures("hermetic_git_env")
def test_e2e_warns_when_legacy_output_is_still_tracked(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    _set_commit_true(repo)
    _git(repo, "init", "-q")
    assert _sync.execute(repo) == 0
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", "legacy: output committed")
    (repo / ".coding-agent-playbook.toml").write_text(_DEFAULT_CONFIG)
    capsys.readouterr()
    assert _sync.execute(repo) == 0
    err = capsys.readouterr().err
    assert "  AGENTS.md\n" in err
    assert "git rm -r --cached --" in err
    assert "AGENTS.md" in _git(repo, "ls-files")  # warning only: git state untouched
