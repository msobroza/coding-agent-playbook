"""Unit tests for the ``playbook sync`` output-policy glue (``sync/_output_policy.py``)."""

from __future__ import annotations

import os
import shlex
import unicodedata
from pathlib import Path

import pytest

from coding_agent_playbook.adapters.agents_md import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.generated_output.gitignore import BLOCK_START, ignore_entries
from coding_agent_playbook.sync._output_policy import (
    file_drift,
    gitignore_drift,
    native_skill_roots,
    report_kept_leftovers,
    report_staged_output,
    shared_outputs,
    staged_generated_paths,
    untrack_command,
    update_gitignore,
    warn_tracked_output,
    without_shared,
)
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


def _skill_scratch(tmp_path: Path, root: str) -> tuple[Path, Path, Path]:
    """A scratch render of ``<root>/demo/scripts/run.sh`` and the real repo beside it."""
    scratch, repo = tmp_path / "scratch", tmp_path / "repo"
    skill = scratch / root / "demo"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("s\n", encoding="utf-8")
    (skill / "scripts" / "run.sh").write_text("x\n", encoding="utf-8")
    (repo / root / "demo").mkdir(parents=True)
    return scratch, repo, skill / "scripts" / "run.sh"


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_file_drift_counts_output_written_into_a_character_device_as_delivered(
    tmp_path: Path,
) -> None:
    """``AGENTS.md -> /dev/null`` is how a repo discards a force-enabled output: write
    mode writes into it, so there is nothing to compare and nothing sync could fix."""
    scratch, repo = tmp_path / "scratch", tmp_path / "repo"
    scratch.mkdir()
    repo.mkdir()
    (scratch / "AGENTS.md").write_text("x\n", encoding="utf-8")
    (repo / "AGENTS.md").symlink_to(os.devnull)

    assert file_drift([scratch / "AGENTS.md"], scratch, repo) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_file_drift_reports_a_character_device_inside_a_native_skill_dir(tmp_path: Path) -> None:
    """The skill writer replaces a link at its destination with the real file, so
    ``scripts/run.sh -> /dev/null`` there is drift sync clears, not delivered output."""
    scratch, repo, rendered = _skill_scratch(tmp_path, ".claude/skills")
    (repo / ".claude/skills/demo/scripts").mkdir()
    (repo / ".claude/skills/demo/scripts/run.sh").symlink_to(os.devnull)

    [hint] = file_drift([rendered], scratch, repo, skill_roots=frozenset({".claude/skills"}))

    assert hint.endswith("Missing on disk; run 'playbook sync' to create.")


def test_file_drift_keeps_the_swap_hint_inside_a_native_skill_dir(tmp_path: Path) -> None:
    """Inside ``<root>/<id>/`` of a native skills root the skill writer displaces what
    is in the way when it is its own unchanged output (§10.8): the hint says that."""
    scratch, repo, rendered = _skill_scratch(tmp_path, ".claude/skills")
    (repo / ".claude/skills/demo/scripts").write_text("old file\n", encoding="utf-8")

    [hint] = file_drift([rendered], scratch, repo, skill_roots=frozenset({".claude/skills"}))

    assert ".claude/skills/demo/scripts is in the way. 'playbook sync' replaces it only" in hint


def test_file_drift_gives_agent_harness_skills_the_blocker_write_mode_stops_on(
    tmp_path: Path,
) -> None:
    """``skills/`` is ``agent_harness``'s, not a native root: it never displaces anything."""
    scratch, repo, rendered = _skill_scratch(tmp_path, "skills")
    (repo / "skills/demo/scripts").write_text("old file\n", encoding="utf-8")

    [hint] = file_drift([rendered], scratch, repo, skill_roots=frozenset({".claude/skills"}))

    assert "skills/demo/scripts is not a directory, but sync writes generated files" in hint
    assert "replaces it only" not in hint


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_file_drift_names_the_link_even_when_a_file_is_behind_it(tmp_path: Path) -> None:
    """ "Run 'playbook sync' to regenerate" would be a drift no sync clears: sync never
    writes through a link leading out of the skill dir, so the hint names the link."""
    scratch, repo, rendered = _skill_scratch(tmp_path, ".claude/skills")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "run.sh").write_text("their version\n", encoding="utf-8")
    (repo / ".claude/skills/demo/scripts").symlink_to(tmp_path / "elsewhere")

    [hint] = file_drift([rendered], scratch, repo, skill_roots=frozenset({".claude/skills"}))

    assert "is a symbolic link leading outside the skill directory" in hint
    assert "regenerate" not in hint


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_file_drift_names_a_link_leaving_a_native_skill_dir(tmp_path: Path) -> None:
    """The skill writer skips a file under such a link with a warning: name the link."""
    scratch, repo, rendered = _skill_scratch(tmp_path, ".claude/skills")
    (tmp_path / "elsewhere").mkdir()
    (repo / ".claude/skills/demo/scripts").symlink_to(tmp_path / "elsewhere")

    [hint] = file_drift([rendered], scratch, repo, skill_roots=frozenset({".claude/skills"}))

    assert hint.endswith(
        "    Missing on disk: .claude/skills/demo/scripts is a symbolic link leading outside the "
        "skill directory, and sync never writes through one.\n"
        "    Remove or re-point the link, then run 'playbook sync'."
    )


def test_native_skill_roots_are_the_skill_writer_roots_of_the_given_adapters() -> None:
    from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
    from coding_agent_playbook.adapters.continue_ import ContinueAdapter
    from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
    from coding_agent_playbook.adapters.shared_skills import (
        SHARED_SKILLS_ROOT,
        SharedSkillsAdapter,
    )
    from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter

    native = {
        "claude_code": ClaudeCodeAdapter(),
        "opencode": OpenCodeAdapter(),
        "shared_skills": SharedSkillsAdapter(),
    }
    others = {"continue": ContinueAdapter(), "agent_harness": AgentHarnessAdapter()}

    assert native_skill_roots({**native, **others}) == {
        ".claude/skills",
        ".opencode/skills",
        SHARED_SKILLS_ROOT.as_posix(),
    }
    assert native_skill_roots(others) == frozenset()


def test_native_skill_roots_read_the_public_class_attribute() -> None:
    """An out-of-tree adapter opts in by declaring ``native_skills_root``."""
    from coding_agent_playbook.adapters.continue_ import ContinueAdapter

    class _ThirdPartySkills(ContinueAdapter):
        native_skills_root = ".acme/skills"

    assert native_skill_roots({"acme": _ThirdPartySkills()}) == {".acme/skills"}
