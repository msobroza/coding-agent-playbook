"""Unit tests for the ``playbook sync`` output-policy glue (``commands/_sync_output.py``)."""

from __future__ import annotations

import shlex
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.commands._sync_output import (
    gitignore_drift,
    report_kept_leftovers,
    report_staged_output,
    staged_generated_paths,
    untrack_command,
    update_gitignore,
    warn_tracked_output,
)
from coding_agent_playbook.gitignore import BLOCK_START, ignore_entries
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    import pytest


def test_update_gitignore_applies_then_reports_no_change(tmp_path: Path) -> None:
    written = [tmp_path / "AGENTS.md"]
    assert update_gitignore(tmp_path, written, commit=False) == (
        "Updated the managed block in .gitignore"
    )
    assert "/AGENTS.md" in (tmp_path / ".gitignore").read_text()
    assert update_gitignore(tmp_path, written, commit=False) is None


def test_update_gitignore_commit_true_removes_block(tmp_path: Path) -> None:
    update_gitignore(tmp_path, [tmp_path / "AGENTS.md"], commit=False)
    assert (
        update_gitignore(tmp_path, [], commit=True) == "Removed the managed block from .gitignore"
    )
    assert update_gitignore(tmp_path, [], commit=True) is None


def test_gitignore_drift_states(tmp_path: Path) -> None:
    entries = ["/AGENTS.md"]
    assert "missing or stale" in gitignore_drift(tmp_path, entries)[0]
    update_gitignore(tmp_path, [tmp_path / "AGENTS.md"], commit=False)
    current = ["/.coding-agent-playbook.lock", "/AGENTS.md"]
    assert gitignore_drift(tmp_path, current) == []
    (tmp_path / ".gitignore").write_text(f"{BLOCK_START}\n")
    assert "Malformed managed block" in gitignore_drift(tmp_path, current)[0]


def test_warn_tracked_output_returns_tracked_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    git = FakeGitClient(tracked={"AGENTS.md"})
    assert warn_tracked_output(tmp_path, [tmp_path / "AGENTS.md"], git) == ["AGENTS.md"]
    assert "git rm -r --cached -- AGENTS.md" in capsys.readouterr().err
    assert git.calls == [("tracked_paths", (".coding-agent-playbook.lock", "AGENTS.md"))]


def test_warn_tracked_output_silent_when_git_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert warn_tracked_output(tmp_path, [], FakeGitClient(tracked=None)) == []
    assert capsys.readouterr().err == ""


def test_staged_generated_paths_matches_files_and_skill_dirs() -> None:
    entries = ["/AGENTS.md", "/.claude/skills/s/", "/x\\*.md"]
    staged = ["AGENTS.md", ".claude/skills/s/scripts/a.sh", "x*.md", "xy.md", "src/a.py"]
    assert staged_generated_paths(staged, entries) == [
        "AGENTS.md",
        ".claude/skills/s/scripts/a.sh",
        "x*.md",
    ]


def test_staged_generated_paths_matches_nfc_staged_path_to_nfd_entry(tmp_path: Path) -> None:
    """Regression: git on macOS stages precomposed (NFC) names; an NFD-written
    file must still be caught by the guard and ignored in both forms."""
    nfd = unicodedata.normalize("NFD", "café.md")
    nfc = unicodedata.normalize("NFC", "café.md")
    entries = ignore_entries([tmp_path / ".claude" / "commands" / nfd], tmp_path)
    assert f"/.claude/commands/{nfc}" in entries
    assert f"/.claude/commands/{nfd}" in entries
    staged = [f".claude/commands/{nfc}", f".claude/commands/{nfd}", "src/a.py"]
    assert staged_generated_paths(staged, entries) == staged[:2]


def test_untrack_command_shell_quotes_paths() -> None:
    assert untrack_command(["AGENTS.md", "a b.md", "x*.md"]) == (
        "git rm -r --cached -- AGENTS.md 'a b.md' 'x*.md'"
    )


def test_untrack_command_omits_dash_c_when_repo_root_is_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert untrack_command(["AGENTS.md"], tmp_path) == "git rm -r --cached -- AGENTS.md"
    assert untrack_command(["AGENTS.md"], Path(".")) == "git rm -r --cached -- AGENTS.md"


def test_untrack_command_targets_repo_root_from_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: ``--repo-root packages/foo`` from a monorepo root must not
    print paths that resolve against the monorepo's own files."""
    sub = tmp_path / "packages" / "my foo"
    sub.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    relative = Path("packages/my foo")
    assert untrack_command(["AGENTS.md"], relative) == (
        "git -C 'packages/my foo' rm -r --cached -- AGENTS.md"
    )
    assert untrack_command(["AGENTS.md"], sub) == (
        f"git -C {shlex.quote(str(sub))} rm -r --cached -- AGENTS.md"
    )


def test_report_staged_output_prints_paths_and_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    report_staged_output(["AGENTS.md"], tmp_path)
    out = capsys.readouterr().out
    assert "  AGENTS.md\n" in out
    assert "git rm -r --cached -- AGENTS.md" in out


def test_report_kept_leftovers_lists_paths_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kept = [tmp_path / ".claude" / "skills" / "s" / "SKILL.md"]
    assert report_kept_leftovers(tmp_path, kept) == [".claude/skills/s/SKILL.md"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "  .claude/skills/s/SKILL.md\n" in captured.err
    assert "no longer generates" in captured.err


def test_report_kept_leftovers_is_silent_when_nothing_is_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert report_kept_leftovers(tmp_path, []) == []
    assert capsys.readouterr().err == ""
