"""End-to-end tests for ``playbook sync`` (PR 10 Task 2 + Task 3).

Builds a synthetic consumer repo, runs sync programmatically, and asserts
adapter outputs landed in the expected places plus the lockfile carries
the right entries. The stale-output tests at the bottom pin the lockfile-driven
sweep (SPEC §12.2/§12.3/§14.4): outputs an earlier sync generated and this one
no longer produces are removed when unmodified, kept with a warning when edited,
and reported as drift by ``sync --check`` until the next sync removes them; a
file sync never generated (a user file in a copied skill dir, a symlink's
target) is never recorded or removed, and ``--check`` agrees with sync on it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.lockfile import LOCKFILE_SCHEMA_VERSION, Lockfile
from coding_agent_playbook.sources.filesystem import FileSystemStateSource

if TYPE_CHECKING:
    from pathlib import Path

    from tests.conftest import SyntheticRepoBuilder


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
    # Schema 2: an ownership record the stale-output sweep may delete from.
    assert lockfile.schema_version == LOCKFILE_SCHEMA_VERSION == 2
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


# --- stale outputs: lockfile-driven sweep (SPEC §12.2 / §12.3 / §14.4) ---------


def _write_repo_skill(
    repo: Path,
    skill_id: str,
    *,
    scripts: dict[str, str] | None = None,
    references: dict[str, str] | None = None,
) -> Path:
    """Write ``playbook/skills/<skill_id>/`` (``SKILL.md`` + optional side files)."""
    skill_dir = repo / "playbook" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nid: {skill_id}\nname: {skill_id}\ndescription: A repo-local skill\n---\n"
        f"Do the {skill_id} thing.\n",
        encoding="utf-8",
    )
    for subdir, files in (("scripts", scripts), ("references", references)):
        for name, content in (files or {}).items():
            target = skill_dir / subdir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return skill_dir


def _synced_repo_with_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, skill_id: str
) -> Path:
    """A synced repo whose repo-local ``skill_id`` ships a script and a reference."""
    repo: Path = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    _write_repo_skill(
        repo,
        skill_id,
        scripts={"run.sh": "#!/bin/sh\necho run\n"},
        references={"notes.md": "Notes.\n"},
    )
    assert _sync.run(_ns(repo)) == 0
    return repo


def _lockfile(repo: Path) -> Lockfile:
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return lockfile


def _locked_paths(repo: Path) -> set[str]:
    return {entry.path for entry in _lockfile(repo).entries}


_STALE = (
    "Stale: generated by an earlier sync but no longer produced. Run 'playbook sync' to remove it."
)


def _stale_rels(out: str) -> list[str]:
    """The paths ``sync --check`` reported as stale, in report order."""
    lines = out.splitlines()
    return [lines[i - 1].strip() for i, line in enumerate(lines) if line.strip() == _STALE]


def test_sync_removes_a_deleted_repo_local_skill_dir(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "gone")
    skill_out = repo / ".claude" / "skills" / "gone"
    assert (skill_out / "scripts" / "run.sh").is_file()
    assert (skill_out / "references" / "notes.md").is_file()

    shutil.rmtree(repo / "playbook" / "skills" / "gone")
    assert _sync.run(_ns(repo)) == 0

    assert not skill_out.exists()
    assert not (repo / ".continue" / "prompts" / "gone.md").exists()
    assert not any(path.startswith(".claude/skills/gone/") for path in _locked_paths(repo))


def test_sync_leaves_a_never_generated_skill_dir_untouched(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "gone")
    hand_made = repo / ".claude" / "skills" / "hand-made" / "SKILL.md"
    hand_made.parent.mkdir(parents=True)
    hand_made.write_text("---\nname: hand-made\n---\nMine.\n", encoding="utf-8")

    shutil.rmtree(repo / "playbook" / "skills" / "gone")
    assert _sync.run(_ns(repo)) == 0

    assert hand_made.read_text(encoding="utf-8") == "---\nname: hand-made\n---\nMine.\n"
    assert not (repo / ".claude" / "skills" / "gone").exists()


def test_sync_summary_counts_sweep_removals(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "gone")
    before = _locked_paths(repo)
    shutil.rmtree(repo / "playbook" / "skills" / "gone")
    capsys.readouterr()

    assert _sync.run(_ns(repo)) == 0

    dropped = before - _locked_paths(repo)
    assert dropped == {
        ".claude/skills/gone/SKILL.md",
        ".claude/skills/gone/scripts/run.sh",
        ".claude/skills/gone/references/notes.md",
        ".continue/prompts/gone.md",
    }
    assert f", {len(dropped)} removed" in capsys.readouterr().out


def test_sync_check_reports_stale_outputs_until_sync_removes_them(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "gone")
    shutil.rmtree(repo / "playbook" / "skills" / "gone")
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1
    out = capsys.readouterr().out
    assert "Drift detected" in out
    # Each stale file is reported exactly once, sorted.
    assert _stale_rels(out) == [
        ".claude/skills/gone/SKILL.md",
        ".claude/skills/gone/references/notes.md",
        ".claude/skills/gone/scripts/run.sh",
        ".continue/prompts/gone.md",
    ]
    # --check renders into a scratch copy: the real repo is untouched.
    assert (repo / ".claude" / "skills" / "gone" / "SKILL.md").is_file()

    assert _sync.run(_ns(repo)) == 0
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


def test_sync_keeps_a_user_edited_stale_file_with_a_warning(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "gone")
    edited = repo / ".claude" / "skills" / "gone" / "references" / "notes.md"
    edited.write_text("My own notes now.\n", encoding="utf-8")
    shutil.rmtree(repo / "playbook" / "skills" / "gone")
    capsys.readouterr()

    # Sync would keep the edited file, so --check does not call it stale.
    assert _sync.run(_ns(repo, check=True)) == 1
    stale = _stale_rels(capsys.readouterr().out)
    assert ".claude/skills/gone/references/notes.md" not in stale
    assert ".claude/skills/gone/SKILL.md" in stale

    assert _sync.run(_ns(repo)) == 0

    assert edited.read_text(encoding="utf-8") == "My own notes now.\n"
    assert not (repo / ".claude" / "skills" / "gone" / "SKILL.md").exists()
    err = capsys.readouterr().err
    warnings = [line for line in err.splitlines() if line.startswith("warning:")]
    assert len(warnings) == 1
    assert ".claude/skills/gone/references/notes.md" in warnings[0]
    assert "kept" in warnings[0]
    # The kept file is no longer engine output, so it is not perpetual drift.
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


def test_disabling_an_adapter_removes_its_unmodified_outputs(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    repo: Path = make_synthetic_repo(
        tmp_path,
        rules=[("x", "Body\n")],
        prompts=[("refactor", {"slash": "refactor", "body": "Refactor.\n"})],
    )
    assert _sync.run(_ns(repo)) == 0
    assert (repo / ".claude" / "commands" / "refactor.md").is_file()
    config = repo / ".coding-agent-playbook.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace('"claude_code", ', ""), encoding="utf-8"
    )

    assert _sync.run(_ns(repo)) == 0

    assert not (repo / ".claude").exists()
    assert (repo / ".continue" / "prompts" / "refactor.md").is_file()


@pytest.mark.parametrize("check", [False, True])
def test_sync_refuses_to_overwrite_an_unreadable_lockfile(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoBuilder,
    capsys: pytest.CaptureFixture[str],
    check: bool,
) -> None:
    # A committed lockfile is a natural merge-conflict target. Regenerating it
    # would drop the stale entries it records, so their outputs would never be
    # removed: sync stops with an actionable error and writes nothing.
    repo: Path = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    lock = repo / ".coding-agent-playbook.lock"
    lock.write_text("<<<<<<< HEAD\n", encoding="utf-8")

    assert _sync.run(_ns(repo, check=check)) == 2

    err = capsys.readouterr().err
    assert err.startswith("error: cannot read the previous lockfile")
    assert "git checkout --theirs .coding-agent-playbook.lock" in err
    assert lock.read_text(encoding="utf-8") == "<<<<<<< HEAD\n"
    assert not (repo / "AGENTS.md").exists()


def test_sync_skips_malformed_lockfile_entries(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    # Valid TOML with a badly typed entry must not crash every later sync.
    repo: Path = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    assert _sync.run(_ns(repo)) == 0
    with (repo / ".coding-agent-playbook.lock").open("a", encoding="utf-8") as lock:
        lock.write('\n[[entries]]\npath = 5\nsha256 = "x"\nbytes = 1\n')
        lock.write('\n[[entries]]\npath = "a\\u0000b"\nsha256 = "x"\nbytes = 1\n')

    assert _sync.run(_ns(repo)) == 0
    assert _sync.run(_ns(repo, check=True)) == 0


def test_sync_removes_a_file_dropped_from_a_still_shipped_references_dir(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    repo: Path = make_synthetic_repo(tmp_path)
    skill_dir = _write_repo_skill(
        repo, "kept", references={"keep.md": "Keep.\n", "drop.md": "Drop.\n"}
    )
    assert _sync.run(_ns(repo)) == 0
    (skill_dir / "references" / "drop.md").unlink()

    assert _sync.run(_ns(repo)) == 0

    assert not (repo / ".claude" / "skills" / "kept" / "references" / "drop.md").exists()


def test_a_user_file_in_a_generated_skill_dir_is_never_recorded_or_removed(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    # The adapter reports every file under a copied references/ dir, but only
    # the skill's own sources are engine output: a file the user added there
    # must survive an ordinary re-sync and the later removal of the skill.
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "foo")
    mine = repo / ".claude" / "skills" / "foo" / "references" / "my-team-notes.md"
    mine.write_text("Hand-written team notes.\n", encoding="utf-8")
    assert _sync.run(_ns(repo)) == 0
    assert ".claude/skills/foo/references/my-team-notes.md" not in _locked_paths(repo)

    shutil.rmtree(repo / "playbook" / "skills" / "foo")
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 1
    assert ".claude/skills/foo/references/my-team-notes.md" not in _stale_rels(
        capsys.readouterr().out
    )
    assert _sync.run(_ns(repo)) == 0

    assert mine.read_text(encoding="utf-8") == "Hand-written team notes.\n"
    assert not (repo / ".claude" / "skills" / "foo" / "SKILL.md").exists()
    assert "warning:" not in capsys.readouterr().err


def test_a_symlink_in_a_generated_dir_never_puts_its_target_in_the_lockfile(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "foo")
    guide = repo / "docs" / "guide.md"
    guide.parent.mkdir()
    guide.write_text("# Architecture guide (user-authored)\n", encoding="utf-8")
    link = repo / ".claude" / "skills" / "foo" / "references" / "guide.md"
    link.symlink_to(os.path.relpath(guide, link.parent))
    assert _sync.run(_ns(repo)) == 0
    assert "docs/guide.md" not in _locked_paths(repo)

    shutil.rmtree(repo / "playbook" / "skills" / "foo")
    assert _sync.run(_ns(repo)) == 0

    assert guide.read_text(encoding="utf-8") == "# Architecture guide (user-authored)\n"
    assert _sync.run(_ns(repo, check=True)) == 0


def test_check_and_sync_agree_on_a_symlinked_stale_entry(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    # The scratch copy dereferences symlinks; --check must still report only
    # what a real sync removes, and sync never deletes or follows a symlink.
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "gone")
    elsewhere = repo / "shared" / "run.sh"
    elsewhere.parent.mkdir()
    script = repo / ".claude" / "skills" / "gone" / "scripts" / "run.sh"
    shutil.copy(script, elsewhere)
    script.unlink()
    script.symlink_to(os.path.relpath(elsewhere, script.parent))
    shutil.rmtree(repo / "playbook" / "skills" / "gone")
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1
    stale = _stale_rels(capsys.readouterr().out)
    assert ".claude/skills/gone/SKILL.md" in stale
    assert ".claude/skills/gone/scripts/run.sh" not in stale

    assert _sync.run(_ns(repo)) == 0
    assert script.is_symlink()
    assert elsewhere.is_file()
    capsys.readouterr()
    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out


def test_a_pre_ownership_lockfile_never_deletes_and_warns(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    # Schema 1 lockfiles (before this fix) adopted user files found inside a
    # copied skill dir. The first sync after upgrading must not delete them.
    repo = _synced_repo_with_skill(tmp_path, make_synthetic_repo, "foo")
    mine = repo / ".claude" / "skills" / "foo" / "references" / "my-notes.md"
    mine.write_text("MINE\n", encoding="utf-8")
    lock = repo / ".coding-agent-playbook.lock"
    legacy = lock.read_text(encoding="utf-8").replace("schema_version = 2", "schema_version = 1")
    digest = hashlib.sha256(b"MINE\n").hexdigest()
    lock.write_text(
        legacy
        + "\n[[entries]]\n"
        + 'path = ".claude/skills/foo/references/my-notes.md"\n'
        + f'sha256 = "{digest}"\nbytes = 5\n',
        encoding="utf-8",
    )
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 0, capsys.readouterr().out
    assert _sync.run(_ns(repo)) == 0

    assert mine.read_text(encoding="utf-8") == "MINE\n"
    warnings = [
        line for line in capsys.readouterr().err.splitlines() if line.startswith("warning:")
    ]
    assert len(warnings) == 1
    assert (
        ".claude/skills/foo/references/my-notes.md is listed by a lockfile from an older"
        in (warnings[0])
    )
    # The rewritten lockfile is an ownership record that no longer adopts it.
    assert _lockfile(repo).schema_version == LOCKFILE_SCHEMA_VERSION
    assert ".claude/skills/foo/references/my-notes.md" not in _locked_paths(repo)


def test_sync_prunes_directories_adapter_cleanup_emptied(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    # agent_harness writes prompts/<slash>/; once cleanup_stale removes its last
    # file, the empty dir would trip validate-harness's routing-file check.
    config = (
        'schema_version = 1\nadapters_enabled = ["claude_code", "agent_harness"]\n'
        'overlays_enabled = []\n[project]\nname = "synthetic"\nkind = "python-library"\n'
        '[engine]\nversion = "0.1.0a0"\n'
    )
    repo: Path = make_synthetic_repo(
        tmp_path,
        config_text=config,
        rules=[("x", "Body\n")],
        prompts=[("zzmine", {"slash": "zzmine", "body": "Do it.\n"})],
    )
    assert _sync.run(_ns(repo)) == 0
    assert (repo / "prompts" / "zzmine").is_dir()
    (repo / "playbook" / "prompts" / "zzmine.md").unlink()

    assert _sync.run(_ns(repo)) == 0

    assert not (repo / "prompts" / "zzmine").exists()
    assert not (repo / ".claude" / "commands" / "zzmine.md").exists()
    # Pruning stops at the first non-empty parent (the engine's own prompts).
    assert (repo / "prompts" / "PROMPTS.md").is_file()


def test_sync_check_tolerates_a_dangling_symlink(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> None:
    repo: Path = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    assert _sync.run(_ns(repo)) == 0
    (repo / "docs").mkdir()
    (repo / "docs" / "broken.md").symlink_to("missing.md")
    assert _sync.run(_ns(repo, check=True)) == 0


def _synced_repo_with_edited_command(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder
) -> Path:
    repo: Path = make_synthetic_repo(
        tmp_path,
        rules=[("x", "Body\n")],
        prompts=[("zzmine", {"slash": "zzmine", "body": "Do it.\n"})],
    )
    assert _sync.run(_ns(repo)) == 0
    command = repo / ".claude" / "commands" / "zzmine.md"
    command.write_text(command.read_text(encoding="utf-8") + "My edit.\n", encoding="utf-8")
    return repo


def test_an_edited_sentinel_output_of_an_enabled_adapter_is_still_deleted(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    # The edited-file guarantee is the sweep's (pass 2). Pass 1, the adapter's
    # own cleanup_stale, deletes a stale sentinel-tagged file whatever its
    # content, and --check says so.
    repo = _synced_repo_with_edited_command(tmp_path, make_synthetic_repo)
    (repo / "playbook" / "prompts" / "zzmine.md").unlink()
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1
    assert ".claude/commands/zzmine.md" in _stale_rels(capsys.readouterr().out)
    assert _sync.run(_ns(repo)) == 0

    assert not (repo / ".claude" / "commands" / "zzmine.md").exists()
    assert "warning:" not in capsys.readouterr().err


def test_the_same_edit_is_kept_with_a_warning_when_its_adapter_is_disabled(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoBuilder, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _synced_repo_with_edited_command(tmp_path, make_synthetic_repo)
    config = repo / ".coding-agent-playbook.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace('"claude_code", ', ""), encoding="utf-8"
    )
    capsys.readouterr()

    assert _sync.run(_ns(repo, check=True)) == 1
    assert ".claude/commands/zzmine.md" not in _stale_rels(capsys.readouterr().out)
    assert _sync.run(_ns(repo)) == 0

    assert (
        (repo / ".claude" / "commands" / "zzmine.md")
        .read_text(encoding="utf-8")
        .endswith("My edit.\n")
    )
    err = capsys.readouterr().err
    assert "warning: .claude/commands/zzmine.md was generated by an earlier sync" in err
