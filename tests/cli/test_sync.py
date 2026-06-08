"""End-to-end tests for ``playbook sync`` (PR 10 Task 2 + Task 3).

Builds a synthetic consumer repo, runs sync programmatically, and asserts
adapter outputs landed in the expected places plus the lockfile carries
the right entries.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.lockfile import Lockfile
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from pathlib import Path


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base = {"repo_root": str(repo), "check": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_sync_writes_continue_rules_and_agents_md(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("style-guide", "Use spaces, not tabs.\n")],
        prompts=[("refactor", {"slash": "refactor", "body": "Refactor the code.\n"})],
    )
    rc = _sync.run(_ns(repo))
    assert rc == 0
    # Continue adapter must have written its rule file.
    continue_rule = repo / ".continue" / "rules" / "50-style-guide.md"
    assert continue_rule.is_file()
    # AGENTS.md is always generated.
    agents_md = repo / "AGENTS.md"
    assert agents_md.is_file()
    # Continue prompt landed under .continue/prompts.
    continue_prompt = repo / ".continue" / "prompts" / "refactor.md"
    assert continue_prompt.is_file()
    # claude code prompt slash command
    claude_command = repo / ".claude" / "commands" / "refactor.md"
    assert claude_command.is_file()
    # opencode prompt slash command
    opencode_command = repo / ".opencode" / "command" / "refactor.md"
    assert opencode_command.is_file()


def test_sync_stamps_lockfile(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("a-rule", "A rule body\n")],
    )
    rc = _sync.run(_ns(repo))
    assert rc == 0
    state = FileSystemStateSource(repo_root=repo)
    lockfile = state.load_lockfile()
    assert isinstance(lockfile, Lockfile)
    assert lockfile.schema_version == 1
    # Lockfile should reference at least the AGENTS.md and continue rule outputs.
    paths = [entry.path for entry in lockfile.entries]
    assert "AGENTS.md" in paths
    assert ".continue/rules/50-a-rule.md" in paths
    # Each entry has a sha256 + bytes count.
    for entry in lockfile.entries:
        assert entry.sha256
        assert entry.bytes > 0


def test_sync_uses_cwd_when_repo_root_not_set(tmp_path, make_synthetic_repo, monkeypatch):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    monkeypatch.chdir(repo)
    rc = _sync.run(argparse.Namespace(repo_root=None, check=False))
    assert rc == 0
    assert (repo / "AGENTS.md").is_file()


def test_sync_prints_summary_line(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    rc = _sync.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Summary:" in out
    assert "files written" in out


def test_sync_no_artifacts_still_succeeds(tmp_path, make_synthetic_repo):
    """A repo with no rules/prompts is valid; sync should succeed and the
    lockfile should be created (possibly empty)."""
    repo = make_synthetic_repo(tmp_path)
    rc = _sync.run(_ns(repo))
    assert rc == 0
    state = FileSystemStateSource(repo_root=repo)
    assert state.load_lockfile() is not None


# --- playbook sync --check (drift detection) -----------------------------------


def test_sync_check_clean_repo_returns_zero(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body of x\n")])
    # Build the on-disk artifacts first.
    assert _sync.run(_ns(repo)) == 0
    capsys.readouterr()  # clear
    rc = _sync.run(_ns(repo, check=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "No drift" in out


def test_sync_check_detects_modified_file(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Original body\n")])
    assert _sync.run(_ns(repo)) == 0
    # Mutate the rendered file so the next --check sees drift.
    agents_md = repo / "AGENTS.md"
    agents_md.write_text(agents_md.read_text() + "\nMUTATED LINE\n")
    capsys.readouterr()
    rc = _sync.run(_ns(repo, check=True))
    assert rc == 1
    out = capsys.readouterr().out
    assert "Drift detected" in out
    assert "AGENTS.md" in out


def test_sync_check_detects_missing_file(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("y", "Body y\n")])
    assert _sync.run(_ns(repo)) == 0
    # Delete a written file to simulate a drift-by-omission case.
    (repo / "AGENTS.md").unlink()
    capsys.readouterr()
    rc = _sync.run(_ns(repo, check=True))
    assert rc == 1
    out = capsys.readouterr().out
    assert "Missing" in out or "AGENTS.md" in out
