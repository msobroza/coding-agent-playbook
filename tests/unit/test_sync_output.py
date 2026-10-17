"""Unit tests for the ``playbook sync`` output-policy glue (``commands/_sync_output.py``)."""

from __future__ import annotations

import os
import shlex
import unicodedata
from pathlib import Path

import pytest

from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.commands._sync_output import (
    file_drift,
    gitignore_drift,
    report_kept_leftovers,
    report_staged_output,
    shared_outputs,
    staged_generated_paths,
    untrack_command,
    update_gitignore,
    warn_tracked_output,
    without_shared,
)
from coding_agent_playbook.gitignore import BLOCK_START, ignore_entries
from tests.fakes import FakeGitClient


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


# --- shared outputs (specs/prK-lifecycle-hooks.md §C.0): co-owned, never "generated" ---


def test_shared_outputs_come_from_the_adapter_classes() -> None:
    adapters = {"claude_code": ClaudeCodeAdapter(), "agents_md": AgentsMdAdapter()}

    assert shared_outputs(adapters) == frozenset({".claude/settings.json"})
    assert shared_outputs({"agents_md": AgentsMdAdapter()}) == frozenset()


def test_shared_outputs_excluded_from_ignore_entries_and_tracked_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    agents = tmp_path / "AGENTS.md"
    git = FakeGitClient(tracked={".claude/settings.json"})

    owned = without_shared([settings, agents], tmp_path, frozenset({".claude/settings.json"}))

    assert owned == [agents]
    assert "/.claude/settings.json" not in ignore_entries(owned, tmp_path)
    assert warn_tracked_output(tmp_path, owned, git) == []
    assert capsys.readouterr().err == ""


def _scratch_pair(tmp_path: Path, mode: int) -> tuple[Path, Path, Path]:
    scratch, repo = tmp_path / "scratch", tmp_path / "repo"
    for root in (scratch, repo):
        (root / "s").mkdir(parents=True)
        (root / "s" / "run.sh").write_bytes(b"#!/bin/sh\n")
    (scratch / "s" / "run.sh").chmod(0o755)
    (repo / "s" / "run.sh").chmod(mode)
    return scratch, repo, scratch / "s" / "run.sh"


@pytest.mark.skipif(os.name != "posix", reason="exec bits are POSIX-only")
def test_file_drift_reports_a_lost_exec_bit(tmp_path: Path) -> None:
    scratch, repo, rendered = _scratch_pair(tmp_path, 0o644)

    [line] = file_drift([rendered], scratch, repo)

    assert line.splitlines()[:2] == ["  s/run.sh", "    Mode differs: generated as executable."]


@pytest.mark.skipif(os.name != "posix", reason="exec bits are POSIX-only")
def test_file_drift_is_clean_when_the_exec_bit_matches(tmp_path: Path) -> None:
    scratch, repo, rendered = _scratch_pair(tmp_path, 0o755)

    assert file_drift([rendered], scratch, repo) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_file_drift_names_what_write_mode_stops_on(tmp_path: Path) -> None:
    """A missing output names the blocker write mode stops on and never removes:
    a dangling dir link, a link to a file where a dir goes, a dangling file link
    whose target dir is missing. A dangling file link the write creates the
    target of, or one at a shared (atomically replaced) output, is no blocker."""
    scratch, repo = tmp_path / "scratch", tmp_path / "repo"
    names = ("dangling/x.md", "to-file/y.md", "AGENTS.md", "CLAUDE.md")
    rendered = [scratch / name for name in names]
    for path in rendered:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("r\n", encoding="utf-8")
    (repo / "dangling").symlink_to("../gone", target_is_directory=True)
    (repo / "to-file").symlink_to("README.md")
    (repo / "AGENTS.md").symlink_to("gone/AGENTS.md")
    (repo / "CLAUDE.md").symlink_to("docs/CLAUDE.md")

    dir_link, to_file, file_link, creatable = file_drift(rendered, scratch, repo)

    assert "dangling is a dangling symbolic link: its target ../gone does not exist" in dir_link
    assert "to-file is a symbolic link to README.md, which is not a directory" in to_file
    assert "Re-point or remove the link, then run 'playbook sync'." in to_file
    assert "AGENTS.md is a dangling symbolic link: its target gone/AGENTS.md" in file_link
    assert creatable.endswith("Missing on disk; run 'playbook sync' to create.")
    shared = file_drift(rendered[2:3], scratch, repo, shared=frozenset({"AGENTS.md"}))
    assert shared[0].endswith("Missing on disk; run 'playbook sync' to create.")


def test_file_drift_keeps_the_swap_hint_inside_a_rendered_skill_dir(tmp_path: Path) -> None:
    """Inside ``<root>/<id>/`` the skill writer displaces what is in the way when it
    is its own unchanged output (§10.8), so the hint says that, not "move it"."""
    scratch, repo = tmp_path / "scratch", tmp_path / "repo"
    skill = scratch / "skills" / "demo"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("s\n", encoding="utf-8")
    (skill / "scripts" / "run.sh").write_text("x\n", encoding="utf-8")
    (repo / "skills" / "demo").mkdir(parents=True)
    (repo / "skills" / "demo" / "scripts").write_text("old file\n", encoding="utf-8")

    [hint] = file_drift([skill / "scripts" / "run.sh"], scratch, repo)

    assert "skills/demo/scripts is in the way. 'playbook sync' replaces it only" in hint
