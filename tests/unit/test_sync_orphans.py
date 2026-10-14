"""Unit tests for lockfile-based orphan ownership (``commands/_sync_orphans.py``)."""

from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path

import pytest

from coding_agent_playbook.commands._output_locations import OutputLocations
from coding_agent_playbook.commands._sync_orphans import (
    OrphanPlan,
    delete_orphans,
    entry_paths,
    find_orphans,
    plan_orphans,
)
from coding_agent_playbook.lockfile import LockEntry, Lockfile, compute_hash
from tests.fakes import FakeGitClient


def _entry(repo: Path, rel: str, content: bytes | None = None) -> LockEntry:
    """A lock entry for ``rel``; writes ``content`` to disk when given."""
    payload = b"generated\n" if content is None else content
    if content is not None:
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return LockEntry(path=rel, sha256=compute_hash(payload), bytes=len(payload))


def _lock(*entries: LockEntry) -> Lockfile:
    return Lockfile(schema_version=1, engine_version="0", rendered_at="", entries=list(entries))


def test_find_orphans_without_previous_lockfile(tmp_path: Path) -> None:
    assert find_orphans(None, [tmp_path / "AGENTS.md"], tmp_path) == []


def test_find_orphans_lists_unrewritten_on_disk_entries(tmp_path: Path) -> None:
    kept = _entry(tmp_path, "AGENTS.md", b"a")
    stale = _entry(tmp_path, ".claude/skills/s/SKILL.md", b"s")
    gone = _entry(tmp_path, "gone.md")  # in the lockfile, not on disk
    previous = _lock(kept, stale, gone)
    assert find_orphans(previous, [tmp_path / "AGENTS.md"], tmp_path) == [stale]


def test_find_orphans_skips_state_user_and_outside_paths(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("elsewhere") / "x.md"
    outside.write_text("x")
    entries = [
        _entry(tmp_path, ".gitignore", b"g"),
        _entry(tmp_path, "sub/.gitignore", b"g"),
        _entry(tmp_path, ".coding-agent-playbook.toml", b"c"),
        _entry(tmp_path, ".coding-agent-playbook.lock", b"l"),
        LockEntry(path=str(outside), sha256=compute_hash(b"x"), bytes=1),
        LockEntry(path="../escape.md", sha256="", bytes=0),
    ]
    assert find_orphans(_lock(*entries), [], tmp_path) == []


# --- "not rewritten" compares file identity, not path spelling (U3) ----------


def _fs_is_case_insensitive(probe_dir: Path) -> bool:
    probe = probe_dir / "CaseProbe"
    probe.mkdir()
    try:
        return (probe_dir / "caseprobe").exists()
    finally:
        probe.rmdir()


def test_find_orphans_case_variant_of_a_written_file_is_not_an_orphan(tmp_path: Path) -> None:
    """Case-only skill-id rename on macOS APFS / Windows: the old entry ``Demo/run.sh``
    *is* the file just written as ``demo/run.sh`` — deleting it would delete fresh output."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem")
    old = _entry(tmp_path, ".claude/skills/Demo/run.sh", b"r")
    assert find_orphans(_lock(old), [tmp_path / ".claude/skills/demo/run.sh"], tmp_path) == []


def test_find_orphans_case_variant_is_a_real_orphan_on_case_sensitive_fs(tmp_path: Path) -> None:
    if _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-sensitive filesystem")
    old = _entry(tmp_path, ".claude/skills/Demo/run.sh", b"r")
    _entry(tmp_path, ".claude/skills/demo/run.sh", b"r")
    assert find_orphans(_lock(old), [tmp_path / ".claude/skills/demo/run.sh"], tmp_path) == [old]


def test_find_orphans_matches_written_files_by_identity(tmp_path: Path) -> None:
    """A hard link is the same file under another name on every filesystem."""
    written = tmp_path / "out" / "written.md"
    _entry(tmp_path, "out/written.md", b"w")
    alias = _entry(tmp_path, "out/alias.md")
    os.link(written, tmp_path / alias.path)
    assert find_orphans(_lock(alias), [written], tmp_path) == []


def test_find_orphans_lists_one_entry_per_file(tmp_path: Path) -> None:
    """Two old entries naming one file (case variants, hard links) yield one orphan,
    so the lockfile and the managed block never carry duplicates."""
    first = _entry(tmp_path, "a.md", b"a")
    second = _entry(tmp_path, "b.md")
    os.link(tmp_path / "a.md", tmp_path / "b.md")
    assert find_orphans(_lock(first, second), [], tmp_path) == [first]


def test_find_orphans_with_relative_or_symlinked_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    written = _entry(real, "AGENTS.md", b"a")
    stale = _entry(real, "old.md", b"o")
    monkeypatch.chdir(tmp_path)
    assert find_orphans(_lock(written, stale), [Path("real/AGENTS.md")], Path("real")) == [stale]
    if sys.platform != "win32":
        (tmp_path / "link").symlink_to(real, target_is_directory=True)
        link = tmp_path / "link"
        assert find_orphans(_lock(written, stale), [link / "AGENTS.md"], link) == [stale]


def test_find_orphans_matches_written_paths_missing_on_disk_by_path(tmp_path: Path) -> None:
    """``--check`` maps scratch output onto real paths that may not exist yet."""
    gone = _entry(tmp_path, "gone.md")
    assert find_orphans(_lock(gone), [tmp_path / "gone.md"], tmp_path) == []


def _locations(repo: Path, *declared: str) -> OutputLocations:
    return OutputLocations.declared(declared or ("out/", ".claude/skills/"), repo)


def _plan(
    orphans: list[LockEntry], repo: Path, git: FakeGitClient, *, keep_all: bool = False
) -> OrphanPlan:
    return plan_orphans(orphans, repo, git, keep_all=keep_all, locations=_locations(repo))


def test_plan_orphans_deletes_only_pristine_untracked(tmp_path: Path) -> None:
    pristine = _entry(tmp_path, "out/a.md", b"a")
    modified = _entry(tmp_path, "out/b.md", b"b")
    (tmp_path / "out" / "b.md").write_bytes(b"edited")
    tracked = _entry(tmp_path, "out/c.md", b"c")
    git = FakeGitClient(tracked={"out/c.md"})
    plan = _plan([pristine, modified, tracked], tmp_path, git)
    assert plan == OrphanPlan(delete=(pristine,), keep=(modified, tracked))
    assert git.calls == [("tracked_paths", ("out/a.md", "out/b.md", "out/c.md"))]


def test_plan_orphans_outside_a_git_repo_treats_all_as_untracked(tmp_path: Path) -> None:
    pristine = _entry(tmp_path, "out/a.md", b"a")
    plan = _plan([pristine], tmp_path, FakeGitClient(tracked=None))
    assert plan.delete == (pristine,)


@pytest.mark.parametrize("git_dir_kind", ["dir", "worktree-file"])
def test_plan_orphans_keeps_all_when_git_fails_inside_a_work_tree(
    tmp_path: Path, git_dir_kind: str
) -> None:
    """Regression: git missing / timing out / 'dubious ownership' in a real repo read as
    "nothing tracked", so committed leftovers were deleted. Unknown = keep (fail closed)."""
    if git_dir_kind == "dir":
        (tmp_path / ".git").mkdir()
    else:
        (tmp_path / ".git").write_text("gitdir: /elsewhere\n")
    repo = tmp_path / "pkg"
    pristine = _entry(repo, "out/a.md", b"a")
    plan = _plan([pristine], repo, FakeGitClient(tracked=None))
    assert plan == OrphanPlan(keep=(pristine,))


def test_plan_orphans_matches_git_index_in_nfc(tmp_path: Path) -> None:
    """Regression: git on macOS reports precomposed names; a decomposed (NFD) lockfile
    path never string-matched, so a tracked leftover was deleted."""
    nfd = unicodedata.normalize("NFD", "out/café.py")
    nfc = unicodedata.normalize("NFC", nfd)
    assert nfd != nfc
    entry = _entry(tmp_path, nfd, b"print()\n")
    plan = _plan([entry], tmp_path, FakeGitClient(tracked={nfc}))
    assert plan == OrphanPlan(keep=(entry,))


def test_plan_orphans_asks_git_case_insensitively(tmp_path: Path) -> None:
    """Git pathspecs are case-sensitive even under ``core.ignorecase``; the index may
    spell a tracked leftover ``Demo/...`` after an engine case-only dir rename."""
    entry = _entry(tmp_path, ".claude/skills/demo/run.py", b"r")
    git = FakeGitClient(tracked={".claude/skills/Demo/run.py"})
    plan = _plan([entry], tmp_path, git)
    if _fs_is_case_insensitive(tmp_path):  # Demo/run.py *is* demo/run.py: tracked
        assert plan == OrphanPlan(keep=(entry,))
    else:  # a different (absent) file on a case-sensitive filesystem
        assert plan == OrphanPlan(delete=(entry,))


def test_plan_orphans_releases_entries_outside_declared_locations(tmp_path: Path) -> None:
    """Regression: a tampered/merged lockfile listing a user file with predictable bytes
    got it deleted. Outside every adapter's output location nothing is deleted or kept."""
    stray = _entry(tmp_path, "src/app.py", b"x")
    inside = _entry(tmp_path, "out/a.md", b"a")
    assert _plan([stray, inside], tmp_path, FakeGitClient()) == OrphanPlan(delete=(inside,))
    assert (tmp_path / "src" / "app.py").is_file()


def test_plan_orphans_keep_all_and_empty_never_ask_git(tmp_path: Path) -> None:
    pristine = _entry(tmp_path, "out/a.md", b"a")
    stray = _entry(tmp_path, "src/a.md", b"a")
    git = FakeGitClient()
    plan = _plan([pristine, stray], tmp_path, git, keep_all=True)
    assert plan == OrphanPlan(keep=(pristine, stray))  # a missing adapter's own output
    assert _plan([], tmp_path, git) == OrphanPlan()
    assert git.calls == []


def test_plan_orphans_unreadable_file_is_kept(tmp_path: Path) -> None:
    entry = _entry(tmp_path, "out/a.md", b"a")
    (tmp_path / "out" / "a.md").unlink()
    (tmp_path / "out" / "a.md").mkdir()  # reading a directory raises OSError
    plan = _plan([entry], tmp_path, FakeGitClient())
    assert plan.keep == (entry,)


def test_find_orphans_never_lists_git_internals(tmp_path: Path) -> None:
    """Regression: lockfile entries for ``.git/HEAD`` deleted the repository's HEAD."""
    entries = [_entry(tmp_path, ".git/HEAD", b"ref"), _entry(tmp_path, "sub/.GIT/x", b"x")]
    assert find_orphans(_lock(*entries), [], tmp_path) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_find_orphans_never_lists_a_path_reached_through_a_symlink(tmp_path: Path) -> None:
    """Regression: the user took a skill over (moved it to ``my-skills/``, linked it
    back); the old entry resolved through the link onto their committed files."""
    entry = _entry(tmp_path, ".claude/skills/demo/SKILL.md", b"s")
    (tmp_path / "my-skills").mkdir()
    (tmp_path / ".claude" / "skills" / "demo").rename(tmp_path / "my-skills" / "demo")
    (tmp_path / ".claude" / "skills" / "demo").symlink_to(
        "../../my-skills/demo", target_is_directory=True
    )
    assert find_orphans(_lock(entry), [], tmp_path) == []
    assert delete_orphans([entry], tmp_path, _locations(tmp_path)) == []
    assert (tmp_path / "my-skills" / "demo" / "SKILL.md").is_file()


def test_delete_orphans_removes_files_and_prunes_empty_dirs(tmp_path: Path) -> None:
    skill = _entry(tmp_path, ".claude/skills/s/SKILL.md", b"s")
    script = _entry(tmp_path, ".claude/skills/s/scripts/run.sh", b"r")
    (tmp_path / ".claude" / "settings.json").write_text("{}")
    deleted = delete_orphans([skill, script], tmp_path, _locations(tmp_path))
    assert deleted == [tmp_path / skill.path, tmp_path / script.path]
    assert not (tmp_path / ".claude" / "skills").exists()  # an emptied skills root goes too
    assert (tmp_path / ".claude" / "settings.json").is_file()  # non-empty parent kept
    assert tmp_path.is_dir()


def test_delete_orphans_never_prunes_above_a_declared_root(tmp_path: Path) -> None:
    skill = _entry(tmp_path, ".claude/skills/s/SKILL.md", b"s")
    delete_orphans([skill], tmp_path, _locations(tmp_path))
    assert (tmp_path / ".claude").is_dir()  # empty, but not engine output


def test_delete_orphans_never_touches_outside_or_state_paths(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("x\n")
    entries = [_entry(tmp_path, ".gitignore", b"x\n"), LockEntry("../x.md", "", 0)]
    assert delete_orphans(entries, tmp_path, _locations(tmp_path, "./", "")) == []
    assert (tmp_path / ".gitignore").is_file()


def test_delete_orphans_skips_entries_outside_declared_locations(tmp_path: Path) -> None:
    stray = _entry(tmp_path, "src/app.py", b"x")
    assert delete_orphans([stray], tmp_path, _locations(tmp_path)) == []
    assert (tmp_path / "src" / "app.py").is_file()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_delete_orphans_never_prunes_the_target_of_a_symlinked_root(tmp_path: Path) -> None:
    """Regression: with ``.claude/skills -> ../.agents/skills`` the lockfile records
    ``.agents/skills/...``; pruning removed ``.agents/skills`` and ``.agents``, leaving
    the link dangling (and every later sync crashing)."""
    (tmp_path / ".agents" / "skills").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").symlink_to("../.agents/skills", target_is_directory=True)
    entry = _entry(tmp_path, ".agents/skills/s/scripts/run.sh", b"s")
    assert delete_orphans([entry], tmp_path, _locations(tmp_path)) == [tmp_path / entry.path]
    assert (tmp_path / ".claude" / "skills").is_symlink()
    assert (tmp_path / ".agents" / "skills").is_dir()
    assert not (tmp_path / ".agents" / "skills" / "s").exists()


def test_entry_paths_maps_to_repo_root(tmp_path: Path) -> None:
    assert entry_paths([LockEntry("a/b.md", "", 0)], tmp_path) == [tmp_path / "a" / "b.md"]
