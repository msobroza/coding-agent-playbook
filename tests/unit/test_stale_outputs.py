"""Tests for the lockfile-driven stale-output sweep (SPEC §10.1, §12.2, §14.4).

``sweep_stale_outputs`` deletes files an earlier ``playbook sync`` generated
(recorded in the previous lockfile) that the current sync no longer writes. It
must only ever delete unmodified engine output inside the repo, so most tests
here pin a guard: hash mismatch, unsafe or off-limits entry paths, symlinks
(the file or any parent), file identity, malformed entries, and pre-ownership
(schema 1) lockfiles. ``prune_empty_parents`` is tested at the bottom.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.lockfile import (
    LOCKFILE_SCHEMA_VERSION,
    LockEntry,
    Lockfile,
    compute_hash,
)
from coding_agent_playbook.stale_outputs import (
    StaleSweep,
    prune_empty_parents,
    sweep_stale_outputs,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(repo: Path, rel: str, content: str = "generated\n") -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _entry(path: str, content: bytes) -> LockEntry:
    return LockEntry(path=path, sha256=compute_hash(content), bytes=len(content))


def _lock(*entries: LockEntry, schema_version: int = LOCKFILE_SCHEMA_VERSION) -> Lockfile:
    return Lockfile(
        schema_version=schema_version,
        engine_version="0.1.0a0",
        rendered_at="2026-10-14T00:00:00Z",
        entries=list(entries),
    )


def _lock_on_disk(repo: Path, *rels: str) -> Lockfile:
    """A lockfile recording each ``rel`` with the hash of its current content."""
    return _lock(*(_entry(rel, (repo / rel).read_bytes()) for rel in rels))


def test_removes_an_unmodified_stale_file(tmp_path: Path) -> None:
    stale = _write(tmp_path, "out/stale.md")
    sweep = sweep_stale_outputs(_lock_on_disk(tmp_path, "out/stale.md"), [], tmp_path)
    assert sweep == StaleSweep(removed=(tmp_path / "out/stale.md",), kept_modified=())
    assert not stale.exists()


def test_keeps_and_reports_a_user_edited_stale_file(tmp_path: Path) -> None:
    stale = _write(tmp_path, "out/stale.md")
    previous = _lock_on_disk(tmp_path, "out/stale.md")
    stale.write_text("edited by a human\n", encoding="utf-8")
    sweep = sweep_stale_outputs(previous, [], tmp_path)
    assert sweep == StaleSweep(removed=(), kept_modified=(tmp_path / "out/stale.md",))
    assert stale.read_text(encoding="utf-8") == "edited by a human\n"


def test_keeps_files_written_this_sync(tmp_path: Path) -> None:
    current = _write(tmp_path, "out/current.md")
    stale = _write(tmp_path, "out/stale.md")
    previous = _lock_on_disk(tmp_path, "out/current.md", "out/stale.md")
    sweep = sweep_stale_outputs(previous, [current], tmp_path)
    assert sweep.removed == (stale,)
    assert current.is_file()


def test_no_previous_lockfile_is_a_no_op(tmp_path: Path) -> None:
    kept = _write(tmp_path, "out/file.md")
    assert sweep_stale_outputs(None, [], tmp_path) == StaleSweep(removed=(), kept_modified=())
    assert kept.is_file()


def test_missing_files_are_skipped_silently(tmp_path: Path) -> None:
    previous = _lock(_entry("out/gone.md", b"generated\n"))
    assert sweep_stale_outputs(previous, [], tmp_path) == StaleSweep(removed=(), kept_modified=())


@pytest.mark.parametrize(
    "rel",
    [
        ".coding-agent-playbook.toml",
        ".coding-agent-playbook.local.toml",
        ".coding-agent-playbook.lock",
        "nested/.coding-agent-playbook.toml",
        # Nested, so the identity guard (which protects the root state files on
        # a case-insensitive filesystem) cannot be what keeps it.
        "nested/.Coding-Agent-Playbook.TOML",
        "out\\stale.md",
    ],
)
def test_ignores_state_files_and_non_posix_entries(tmp_path: Path, rel: str) -> None:
    target = _write(tmp_path, rel)
    sweep = sweep_stale_outputs(_lock_on_disk(tmp_path, rel), [], tmp_path)
    assert sweep == StaleSweep(removed=(), kept_modified=())
    assert target.is_file()


@pytest.mark.parametrize("rel", ["../outside/victim.md", "out/../../outside/victim.md"])
def test_ignores_entries_with_a_parent_part(tmp_path: Path, rel: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    victim = _write(tmp_path, "outside/victim.md")
    previous = _lock(_entry(rel, victim.read_bytes()))
    assert sweep_stale_outputs(previous, [], repo) == StaleSweep(removed=(), kept_modified=())
    assert victim.is_file()


@pytest.mark.parametrize(
    "rel",
    [
        ".git/HEAD",
        ".GIT/HEAD",
        "vendor/sub/.git/config",
        ".hg/hgrc",
        "playbook/rules/x.md",
        "Playbook/skills/mine/SKILL.md",
    ],
)
def test_never_sweeps_vcs_internals_or_canonical_sources(tmp_path: Path, rel: str) -> None:
    # A hand-edited, malicious or botched lockfile entry with a matching hash
    # must not delete .git internals (the checkout breaks) or the repo-local
    # canonical sources under playbook/, which sync never writes.
    target = _write(tmp_path, rel, "ref: refs/heads/main\n")
    sweep = sweep_stale_outputs(_lock_on_disk(tmp_path, rel), [], tmp_path)
    assert sweep == StaleSweep(removed=(), kept_modified=())
    assert target.is_file()


def test_ignores_absolute_entries(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    victim = _write(tmp_path, "outside/victim.md")
    previous = _lock(_entry(victim.as_posix(), victim.read_bytes()))
    assert sweep_stale_outputs(previous, [], repo) == StaleSweep(removed=(), kept_modified=())
    assert victim.is_file()


def test_ignores_entries_that_escape_through_a_symlinked_parent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    victim = _write(tmp_path, "outside/victim.md")
    (repo / "linked").symlink_to(tmp_path / "outside", target_is_directory=True)
    previous = _lock(_entry("linked/victim.md", victim.read_bytes()))
    assert sweep_stale_outputs(previous, [], repo) == StaleSweep(removed=(), kept_modified=())
    assert victim.is_file()
    assert (repo / "linked").is_symlink()


def test_ignores_entries_whose_parent_is_a_symlink_inside_the_repo(tmp_path: Path) -> None:
    # A user "ejects" a generated skill dir into a tracked dir and symlinks it
    # back. The engine never wrote the target, so the identical file there stays.
    owned = _write(tmp_path, "team-skills/mine/SKILL.md")
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "mine").symlink_to(
        tmp_path / "team-skills" / "mine", target_is_directory=True
    )
    previous = _lock(_entry(".claude/skills/mine/SKILL.md", owned.read_bytes()))
    assert sweep_stale_outputs(previous, [], tmp_path) == StaleSweep(removed=(), kept_modified=())
    assert owned.is_file()


def test_never_deletes_or_follows_a_symlink_entry(tmp_path: Path) -> None:
    target = _write(tmp_path, "real.md")
    link = tmp_path / "link.md"
    link.symlink_to(target)
    previous = _lock(_entry("link.md", target.read_bytes()))
    assert sweep_stale_outputs(previous, [], tmp_path) == StaleSweep(removed=(), kept_modified=())
    assert link.is_symlink()
    assert target.is_file()


def test_keeps_a_stale_entry_that_is_the_same_file_as_a_written_one(tmp_path: Path) -> None:
    # A hard link (or a case-only rename on a case-insensitive filesystem)
    # makes two paths name one file: deleting the stale path would delete the
    # file this sync just wrote, so identity, not path text, decides.
    written = _write(tmp_path, "out/written.md")
    alias = tmp_path / "out/alias.md"
    os.link(written, alias)
    previous = _lock_on_disk(tmp_path, "out/alias.md")
    sweep = sweep_stale_outputs(previous, [written], tmp_path)
    assert sweep == StaleSweep(removed=(), kept_modified=())
    assert alias.is_file()
    assert written.is_file()


@pytest.mark.parametrize(
    "entry",
    [
        {"path": 5, "sha256": "x", "bytes": 1},
        {"path": "out/a\x00b.md", "sha256": "x", "bytes": 1},
        {"path": "out/stale.md", "sha256": 5, "bytes": 1},
    ],
)
def test_malformed_entries_are_skipped_not_raised(tmp_path: Path, entry: dict[str, object]) -> None:
    # A valid-TOML lockfile with a badly typed entry must not crash every sync.
    stale = _write(tmp_path, "out/stale.md")
    previous = Lockfile.from_dict(
        {"schema_version": 2, "engine_version": "x", "rendered_at": "x", "entries": [entry]}
    )
    assert sweep_stale_outputs(previous, [], tmp_path) == StaleSweep(removed=(), kept_modified=())
    assert stale.is_file()


def test_a_schema_1_lockfile_is_reported_never_deleted(tmp_path: Path) -> None:
    # Schema 1 lockfiles could list user files found inside a copied skill dir
    # (and symlink targets), so an unmodified stale entry is kept and reported.
    unverified = _write(tmp_path, ".claude/skills/foo/references/mine.md")
    edited = _write(tmp_path, ".claude/skills/foo/SKILL.md")
    previous = _lock(
        *_lock_on_disk(tmp_path, ".claude/skills/foo/references/mine.md").entries,
        *_lock_on_disk(tmp_path, ".claude/skills/foo/SKILL.md").entries,
        schema_version=1,
    )
    edited.write_text("edited\n", encoding="utf-8")
    sweep = sweep_stale_outputs(previous, [], tmp_path)
    assert sweep == StaleSweep(removed=(), kept_modified=(edited,), kept_unverified=(unverified,))
    assert unverified.is_file()


def test_dry_run_reports_without_deleting_or_pruning(tmp_path: Path) -> None:
    stale = _write(tmp_path, "out/deep/stale.md")
    edited = _write(tmp_path, "out/edited.md")
    previous = _lock_on_disk(tmp_path, "out/deep/stale.md", "out/edited.md")
    edited.write_text("edited\n", encoding="utf-8")
    sweep = sweep_stale_outputs(previous, [], tmp_path, dry_run=True)
    assert sweep == StaleSweep(removed=(stale,), kept_modified=(edited,))
    assert stale.is_file()


def test_prunes_directories_the_sweep_emptied(tmp_path: Path) -> None:
    _write(tmp_path, ".claude/skills/gone/SKILL.md")
    _write(tmp_path, ".claude/skills/gone/references/notes.md")
    kept = _write(tmp_path, ".claude/skills/kept/SKILL.md")
    previous = _lock_on_disk(
        tmp_path, ".claude/skills/gone/SKILL.md", ".claude/skills/gone/references/notes.md"
    )
    sweep_stale_outputs(previous, [kept], tmp_path)
    assert not (tmp_path / ".claude/skills/gone").exists()
    assert kept.is_file()


def test_pruning_stops_at_a_non_empty_directory(tmp_path: Path) -> None:
    _write(tmp_path, ".claude/skills/mine/SKILL.md")
    user_file = _write(tmp_path, ".claude/skills/mine/my-notes.md", "hand-written\n")
    previous = _lock_on_disk(tmp_path, ".claude/skills/mine/SKILL.md")
    sweep_stale_outputs(previous, [], tmp_path)
    assert user_file.is_file()


def test_pruning_never_removes_the_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "only.md")
    sweep_stale_outputs(_lock_on_disk(repo, "only.md"), [], repo)
    assert repo.is_dir()


def test_pruning_leaves_unrelated_empty_directories(tmp_path: Path) -> None:
    (tmp_path / "already-empty").mkdir()
    _write(tmp_path, "out/stale.md")
    sweep_stale_outputs(_lock_on_disk(tmp_path, "out/stale.md"), [], tmp_path)
    assert (tmp_path / "already-empty").is_dir()


def test_results_are_sorted_by_path(tmp_path: Path) -> None:
    rels = ["b/z.md", "a/y.md", "b/a.md", "c.md"]
    for rel in rels:
        _write(tmp_path, rel)
    previous = _lock_on_disk(tmp_path, *rels)
    for rel in rels:
        (tmp_path / rel).write_text("edited\n", encoding="utf-8")
    _write(tmp_path, "z/stale.md")
    _write(tmp_path, "d/stale.md")
    previous.entries.extend(_lock_on_disk(tmp_path, "z/stale.md", "d/stale.md").entries)
    sweep = sweep_stale_outputs(previous, [], tmp_path)
    assert sweep.kept_modified == tuple(tmp_path / rel for rel in sorted(rels))
    assert sweep.removed == (tmp_path / "d/stale.md", tmp_path / "z/stale.md")


def test_repo_root_given_through_a_symlink_still_sweeps(tmp_path: Path) -> None:
    real_repo = tmp_path / "real"
    stale = _write(real_repo, "out/stale.md")
    alias_root = tmp_path / "alias"
    alias_root.symlink_to(real_repo, target_is_directory=True)
    sweep = sweep_stale_outputs(_lock_on_disk(real_repo, "out/stale.md"), [], alias_root)
    assert sweep.removed == (alias_root / "out/stale.md",)
    assert not stale.exists()


def test_entry_under_a_symlink_loop_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "loop").symlink_to(tmp_path / "loop")
    previous = _lock(_entry("loop/stale.md", b"generated\n"))
    assert sweep_stale_outputs(previous, [], tmp_path) == StaleSweep(removed=(), kept_modified=())
    assert (tmp_path / "loop").is_symlink()


_NEEDS_NON_ROOT = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root ignores file permissions"
)


@_NEEDS_NON_ROOT
def test_undeletable_stale_file_is_skipped(tmp_path: Path) -> None:
    stale = _write(tmp_path, "out/stale.md")
    previous = _lock_on_disk(tmp_path, "out/stale.md")
    stale.parent.chmod(0o555)
    try:
        sweep = sweep_stale_outputs(previous, [], tmp_path)
    finally:
        stale.parent.chmod(0o755)
    assert sweep == StaleSweep(removed=(), kept_modified=())
    assert stale.is_file()


@_NEEDS_NON_ROOT
def test_unreadable_stale_file_is_skipped(tmp_path: Path) -> None:
    stale = _write(tmp_path, "out/locked.md")
    previous = _lock_on_disk(tmp_path, "out/locked.md")
    stale.chmod(0)
    try:
        sweep = sweep_stale_outputs(previous, [], tmp_path)
    finally:
        stale.chmod(0o644)
    assert sweep == StaleSweep(removed=(), kept_modified=())
    assert stale.is_file()


# --- prune_empty_parents --------------------------------------------------------


def test_prune_removes_each_emptied_parent_up_to_the_repo_root(tmp_path: Path) -> None:
    gone = tmp_path / ".claude" / "commands" / "gone.md"
    gone.parent.mkdir(parents=True)
    prune_empty_parents(tmp_path, [gone])
    assert not (tmp_path / ".claude").exists()
    assert tmp_path.is_dir()


def test_prune_stops_at_the_first_non_empty_parent(tmp_path: Path) -> None:
    kept = _write(tmp_path, ".claude/settings.json")
    (tmp_path / ".claude" / "commands").mkdir()
    prune_empty_parents(tmp_path, [tmp_path / ".claude" / "commands" / "gone.md"])
    assert not (tmp_path / ".claude" / "commands").exists()
    assert kept.is_file()


def test_prune_ignores_paths_outside_the_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside" / "empty"
    outside.mkdir(parents=True)
    prune_empty_parents(repo, [outside / "gone.md", repo / ".." / "outside" / "empty" / "x"])
    assert outside.is_dir()


def test_prune_never_removes_a_directory_reached_through_a_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real" / "empty"
    real.mkdir(parents=True)
    (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)
    prune_empty_parents(tmp_path, [tmp_path / "linked" / "empty" / "gone.md"])
    assert real.is_dir()
    assert (tmp_path / "linked").is_symlink()
