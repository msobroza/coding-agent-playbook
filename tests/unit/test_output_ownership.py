"""Tests for what a sync records as its own output (SPEC §12.2, §14.4).

The lockfile is the ownership record the stale-output sweep deletes from, so
these pin that it never claims a file the engine did not generate: a user file
found in a copied skill dir (``source_backed_skill_outputs``) or a symlink's
target (``owned_lock_entries``).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from coding_agent_playbook.lockfile import compute_hash
from coding_agent_playbook.output_ownership import (
    owned_lock_entries,
    repo_relative_path,
    source_backed_skill_outputs,
)
from coding_agent_playbook.types import Skill


def _write(root: Path, rel: str, content: str = "generated\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _skill(source: Path, *, scripts: bool = True, references: bool = True) -> Skill:
    return Skill(
        frontmatter={"id": "foo"},
        body="Body\n",
        scripts_dir=source / "scripts" if scripts else None,
        references_dir=source / "references" if references else None,
        source_package="<repo-local>",
    )


# --- source_backed_skill_outputs ------------------------------------------------


def test_keeps_skill_md_and_the_copies_its_sources_back(tmp_path: Path) -> None:
    source = tmp_path / "src"
    _write(source, "scripts/run.sh")
    _write(source, "references/deep/notes.md")
    out = tmp_path / ".claude" / "skills" / "foo"
    reported = [out / "SKILL.md", out / "scripts" / "run.sh", out / "references/deep/notes.md"]
    assert source_backed_skill_outputs(_skill(source), reported) == reported


def test_drops_files_the_skill_sources_do_not_back(tmp_path: Path) -> None:
    # copytree leaves user-added and since-dropped files in place, and the
    # adapter reports them; neither is engine output.
    source = tmp_path / "src"
    _write(source, "references/notes.md")
    out = tmp_path / ".claude" / "skills" / "foo"
    reported = [
        out / "SKILL.md",
        out / "references" / "notes.md",
        out / "references" / "my-team-notes.md",
        out / "scripts" / "node_modules" / "x.js",
    ]
    assert source_backed_skill_outputs(_skill(source, scripts=False), reported) == reported[:2]


def test_keeps_paths_with_no_native_skill_dir(tmp_path: Path) -> None:
    # A degraded skill (Continue prompt) reports no SKILL.md: nothing to check.
    reported = [tmp_path / ".continue" / "prompts" / "foo.md"]
    assert source_backed_skill_outputs(_skill(tmp_path / "src"), reported) == reported


def test_a_reference_named_skill_md_does_not_anchor_a_nested_skill_dir(tmp_path: Path) -> None:
    source = tmp_path / "src"
    _write(source, "references/sub/SKILL.md")
    # Anchored at the nested dir, the user file below would look backed by this.
    _write(source, "references/mine.md")
    out = tmp_path / ".claude" / "skills" / "foo"
    nested = out / "references" / "sub"
    reported = [out / "SKILL.md", nested / "SKILL.md", nested / "references" / "mine.md"]
    assert source_backed_skill_outputs(_skill(source), reported) == reported[:2]


# --- owned_lock_entries ---------------------------------------------------------


def test_records_logical_repo_relative_paths_sorted_and_deduplicated(tmp_path: Path) -> None:
    b = _write(tmp_path, "b.md", "b\n")
    a = _write(tmp_path, ".claude/a.md", "a\n")
    entries = owned_lock_entries([b, a, b], tmp_path)
    assert [(e.path, e.sha256, e.bytes) for e in entries] == [
        (".claude/a.md", compute_hash(b"a\n"), 2),
        ("b.md", compute_hash(b"b\n"), 2),
    ]


def test_never_records_a_symlink_or_its_target(tmp_path: Path) -> None:
    target = _write(tmp_path, "docs/guide.md", "user-authored\n")
    link = tmp_path / ".claude" / "skills" / "foo" / "references" / "guide.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    assert owned_lock_entries([link], tmp_path) == []


def test_never_records_a_path_through_a_symlinked_directory(tmp_path: Path) -> None:
    _write(tmp_path, "team-skills/foo/SKILL.md")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").symlink_to(tmp_path / "team-skills", target_is_directory=True)
    assert owned_lock_entries([tmp_path / ".claude/skills/foo/SKILL.md"], tmp_path) == []


def test_skips_paths_outside_the_repo_and_missing_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = _write(tmp_path, "outside.md")
    assert owned_lock_entries([outside, repo / "missing.md"], repo) == []


def test_matches_resolved_paths_when_the_repo_root_is_a_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    written = _write(real, "AGENTS.md")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    assert [e.path for e in owned_lock_entries([written, alias / "AGENTS.md"], alias)] == [
        "AGENTS.md"
    ]


# --- repo_relative_path ---------------------------------------------------------


def test_repo_relative_path(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    assert repo_relative_path(tmp_path / ".claude/x.md", tmp_path, root) == PurePosixPath(
        ".claude/x.md"
    )
    assert repo_relative_path(tmp_path / ".." / "x.md", tmp_path, root) is None
    assert repo_relative_path(Path("/elsewhere/x.md"), tmp_path, root) is None
    assert repo_relative_path(tmp_path, tmp_path, root) is None
