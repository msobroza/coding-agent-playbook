"""Tests for the shared native Agent-Skills writer (SPEC §6.3, §10.8)."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.adapters import _skill_writer
from coding_agent_playbook.adapters._skill_writer import (
    SKILL_FILENAME,
    SkillWriter,
    agent_skill_issues,
    ensure_path_safe_skill_id,
    has_declared_id,
    is_engine_owned_skill_dir,
    render_skill_md,
    skill_id_of,
)
from coding_agent_playbook.lockfile import LockEntry, Lockfile
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from coding_agent_playbook.types import Skill, split_frontmatter

_ROOTS = (Path(".claude") / "skills", Path(".opencode") / "skills", Path("shared_skills"))

needs_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


def _make_skill(
    *,
    skill_id: str | None = "demo-skill",
    description: str | None = "A demo skill",
    body: str = "# Demo skill\n\nDo the thing.\n",
    scripts_dir: Path | None = None,
    references_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Skill:
    frontmatter: dict[str, Any] = {"name": "Demo skill"}
    if skill_id is not None:
        frontmatter["id"] = skill_id
    if description is not None:
        frontmatter["description"] = description
    frontmatter.update(extra or {})
    return Skill(
        frontmatter=frontmatter,
        body=body,
        scripts_dir=scripts_dir,
        references_dir=references_dir,
        source_package="test",
    )


def _seed_tree(root: Path, files: dict[str, bytes]) -> Path:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return root


def _tree_bytes(top: Path) -> dict[str, bytes]:
    return {
        path.relative_to(top).as_posix(): path.read_bytes()
        for path in sorted(top.rglob("*"))
        if path.is_file()
    }


# --- id helpers ------------------------------------------------------------


def test_skill_id_of_reads_id_and_falls_back_to_skill() -> None:
    assert skill_id_of(_make_skill(skill_id="query-db")) == "query-db"
    assert skill_id_of(_make_skill(skill_id=None)) == "skill"


def test_has_declared_id() -> None:
    assert has_declared_id(_make_skill(skill_id="query-db"))
    assert not has_declared_id(_make_skill(skill_id=None))


@pytest.mark.parametrize("skill_id", ["demo", "query-database", "My_Skill", "v2.0"])
def test_ensure_path_safe_skill_id_accepts_single_segment(skill_id: str) -> None:
    assert ensure_path_safe_skill_id(skill_id) == skill_id


@pytest.mark.parametrize(
    "skill_id", ["", ".", "..", "../escape", "a/b", "a\\b", "/abs", "C:evil", "a\x00b"]
)
def test_ensure_path_safe_skill_id_rejects_unsafe_ids(skill_id: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        ensure_path_safe_skill_id(skill_id)
    assert repr(skill_id) in str(excinfo.value)


# --- SKILL.md rendering ----------------------------------------------------


def test_render_skill_md_sets_name_to_id_and_keeps_other_keys() -> None:
    skill = _make_skill(skill_id="demo", extra={"allowed-tools": ["Read"]})
    frontmatter, _body = split_frontmatter(render_skill_md(skill))
    assert frontmatter["name"] == "demo"  # authored display name replaced
    assert frontmatter["id"] == "demo"
    assert frontmatter["description"] == "A demo skill"
    assert frontmatter["allowed-tools"] == ["Read"]
    assert next(iter(frontmatter)) == "name"


def test_render_skill_md_keeps_frontmatter_on_line_one_and_sentinel_first_body_line() -> None:
    text = render_skill_md(_make_skill(body="# Body\n\nDo it.\n"))
    lines = text.splitlines()
    closing = lines.index("---", 1)
    assert lines[0] == "---"
    assert SENTINEL not in "\n".join(lines[:closing])
    assert lines[closing + 1] == f"<!-- {SENTINEL} -->"
    assert text.endswith("# Body\n\nDo it.\n")


def test_render_skill_md_rejects_unsafe_id() -> None:
    with pytest.raises(ValueError, match=r"'\.\./x'"):
        render_skill_md(_make_skill(skill_id="../x"))


# --- Agent Skills standard checks -----------------------------------------


def test_agent_skill_issues_empty_for_valid_skill() -> None:
    assert agent_skill_issues(_make_skill(skill_id="query-database")) == []


@pytest.mark.parametrize("skill_id", ["My_Skill", "Upper", "double--hyphen", "-lead", "trail-"])
def test_agent_skill_issues_flags_bad_name_pattern(skill_id: str) -> None:
    [issue] = agent_skill_issues(_make_skill(skill_id=skill_id))
    assert repr(skill_id) in issue
    assert "Agent Skills name" in issue


def test_agent_skill_issues_flags_missing_id() -> None:
    """Id-less skills merge under 'skill' and silently collide (review finding)."""
    [issue] = agent_skill_issues(_make_skill(skill_id=None))
    assert "no 'id'" in issue
    assert "'skill'" in issue


@pytest.mark.parametrize("raw_id", [123, True, None, ["a"]])
def test_agent_skill_issues_flags_non_string_id(raw_id: object) -> None:
    skill = _make_skill(skill_id=None, extra={"id": raw_id})
    [issue] = agent_skill_issues(skill)
    assert "must be a string" in issue
    assert repr(raw_id) in issue


def test_agent_skill_issues_flags_overlong_name() -> None:
    [issue] = agent_skill_issues(_make_skill(skill_id="a" * 65))
    assert "65 chars" in issue


@pytest.mark.parametrize("description", [None, "", "   "])
def test_agent_skill_issues_flags_missing_description(description: str | None) -> None:
    [issue] = agent_skill_issues(_make_skill(description=description))
    assert "description" in issue


def test_agent_skill_issues_flags_overlong_description() -> None:
    [issue] = agent_skill_issues(_make_skill(description="x" * 1025))
    assert "1025 chars" in issue


# --- write -----------------------------------------------------------------


def test_skills_root_is_repo_relative(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    assert writer.skills_root(tmp_path) == tmp_path / "shared_skills"


def test_write_creates_skill_md_and_returns_it(tmp_path: Path) -> None:
    written = SkillWriter(Path("shared_skills")).write(_make_skill(skill_id="demo"), tmp_path)
    skill_md = tmp_path / "shared_skills" / "demo" / SKILL_FILENAME
    assert written == [skill_md]
    assert skill_md.read_text(encoding="utf-8") == render_skill_md(_make_skill(skill_id="demo"))


def test_write_copies_scripts_and_references_byte_for_byte(tmp_path: Path) -> None:
    scripts = _seed_tree(
        tmp_path / "src" / "scripts", {"run.sh": b"#!/bin/sh\n", "n/x.bin": b"\xff\x00"}
    )
    (scripts / "run.sh").chmod(0o755)
    refs = _seed_tree(tmp_path / "src" / "references", {"guide.md": b"# Guide\n"})
    skill = _make_skill(skill_id="demo", scripts_dir=scripts, references_dir=refs)

    written = SkillWriter(Path("shared_skills")).write(skill, tmp_path / "repo")

    skill_dir = tmp_path / "repo" / "shared_skills" / "demo"
    assert set(written) == {path for path in skill_dir.rglob("*") if path.is_file()}
    assert _tree_bytes(skill_dir / "scripts") == _tree_bytes(scripts)
    assert _tree_bytes(skill_dir / "references") == _tree_bytes(refs)
    assert not any(path.is_symlink() for path in skill_dir.rglob("*"))
    if sys.platform != "win32":
        assert os.stat(skill_dir / "scripts" / "run.sh").st_mode & stat.S_IXUSR


def test_write_is_byte_identical_across_roots(tmp_path: Path) -> None:
    scripts = _seed_tree(tmp_path / "src" / "scripts", {"helper.py": b"print('hi')\n"})
    skill = _make_skill(skill_id="demo", scripts_dir=scripts)
    repo = tmp_path / "repo"
    for root in _ROOTS:
        SkillWriter(root).write(skill, repo)
    trees = [_tree_bytes(repo / root / "demo") for root in _ROOTS]
    assert trees[0] == trees[1] == trees[2]
    assert set(trees[0]) == {"SKILL.md", "scripts/helper.py"}


@pytest.mark.parametrize("skill_id", ["../escape", "nested/dir", "/abs"])
def test_write_rejects_path_traversal_and_writes_nothing(tmp_path: Path, skill_id: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError, match="not path-safe"):
        SkillWriter(Path("shared_skills")).write(_make_skill(skill_id=skill_id), repo)
    assert list(tmp_path.rglob("SKILL.md")) == []


@needs_symlinks
def test_write_refuses_symlinked_skill_dir_escaping_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "repo" / "shared_skills"
    root.mkdir(parents=True)
    (root / "demo").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="outside the skills root"):
        SkillWriter(Path("shared_skills")).write(_make_skill(skill_id="demo"), tmp_path / "repo")
    assert list(outside.iterdir()) == []


@needs_symlinks
def test_write_refuses_escaping_intermediate_dir(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    scripts = _seed_tree(tmp_path / "src" / "scripts", {"deep/x.py": b"x\n"})
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="demo"), tmp_path / "repo")  # engine-owned dir
    skill_dir = tmp_path / "repo" / "shared_skills" / "demo"
    (skill_dir / "scripts").symlink_to(outside, target_is_directory=True)
    skill = _make_skill(skill_id="demo", scripts_dir=scripts)
    with pytest.raises(ValueError, match="refusing to write"):
        writer.write(skill, tmp_path / "repo")
    assert list(outside.iterdir()) == []


@needs_symlinks
def test_write_replaces_symlinked_script_instead_of_writing_through(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me\n", encoding="utf-8")
    scripts = _seed_tree(tmp_path / "src" / "scripts", {"run.sh": b"#!/bin/sh\n"})
    skill = _make_skill(skill_id="demo", scripts_dir=scripts)
    writer = SkillWriter(Path("shared_skills"))
    writer.write(skill, tmp_path / "repo")
    script = tmp_path / "repo" / "shared_skills" / "demo" / "scripts" / "run.sh"
    script.unlink()
    script.symlink_to(victim)

    writer.write(skill, tmp_path / "repo")

    assert victim.read_text(encoding="utf-8") == "keep me\n"
    assert not script.is_symlink()
    assert script.read_bytes() == b"#!/bin/sh\n"


@needs_symlinks
def test_write_skips_dir_whose_skill_md_is_a_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A symlinked SKILL.md is not engine-owned: the dir is left untouched."""
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me\n", encoding="utf-8")
    skill_dir = tmp_path / "repo" / "shared_skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / SKILL_FILENAME).symlink_to(victim)

    written = SkillWriter(Path("shared_skills")).write(
        _make_skill(skill_id="demo"), tmp_path / "repo"
    )

    assert written == []
    assert victim.read_text(encoding="utf-8") == "keep me\n"
    assert (skill_dir / SKILL_FILENAME).is_symlink()
    assert "not playbook-managed" in capsys.readouterr().err


@needs_symlinks
def test_write_skips_symlinked_skill_dir_inside_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="real"), tmp_path)
    alias = tmp_path / "shared_skills" / "alias"
    alias.symlink_to(tmp_path / "shared_skills" / "real", target_is_directory=True)
    before = _tree_bytes(tmp_path / "shared_skills" / "real")

    assert writer.write(_make_skill(skill_id="alias"), tmp_path) == []

    assert alias.is_symlink()
    assert _tree_bytes(tmp_path / "shared_skills" / "real") == before
    assert str(alias) in capsys.readouterr().err


# --- ownership + cleanup ---------------------------------------------------


def test_is_engine_owned_skill_dir(tmp_path: Path) -> None:
    writer = SkillWriter(Path("s"))
    writer.write(_make_skill(skill_id="ours"), tmp_path)
    user_dir = _seed_tree(tmp_path / "s" / "theirs", {"SKILL.md": b"---\nname: theirs\n---\nx\n"})
    no_md = _seed_tree(tmp_path / "s" / "bare", {"helper.md": f"# {SENTINEL}\n".encode()})
    assert is_engine_owned_skill_dir(tmp_path / "s" / "ours")
    assert not is_engine_owned_skill_dir(user_dir)
    assert not is_engine_owned_skill_dir(no_md)
    assert not is_engine_owned_skill_dir(tmp_path / "s" / "missing")


def test_cleanup_missing_root_returns_empty(tmp_path: Path) -> None:
    assert SkillWriter(Path("shared_skills")).cleanup(set(), tmp_path) == []


def test_cleanup_removes_stale_engine_owned_skill_dir(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    scripts = _seed_tree(tmp_path / "src" / "scripts", {"a.py": b"a\n"})
    stale_paths = writer.write(_make_skill(skill_id="old", scripts_dir=scripts), tmp_path)
    current = writer.write(_make_skill(skill_id="new"), tmp_path)

    deleted = writer.cleanup({p.resolve() for p in current}, tmp_path)

    assert sorted(deleted) == sorted(stale_paths)
    assert not (tmp_path / "shared_skills" / "old").exists()
    assert (tmp_path / "shared_skills" / "new" / SKILL_FILENAME).is_file()


def test_cleanup_removes_stale_files_inside_current_skill(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"keep.py": b"k\n", "old/gone.py": b"g\n"})
    writer.write(_make_skill(skill_id="demo", scripts_dir=v1), tmp_path)
    v2 = _seed_tree(tmp_path / "v2", {"keep.py": b"k2\n"})
    current = writer.write(_make_skill(skill_id="demo", scripts_dir=v2), tmp_path)

    deleted = writer.cleanup({p.resolve() for p in current}, tmp_path)

    scripts_out = tmp_path / "shared_skills" / "demo" / "scripts"
    assert deleted == [scripts_out / "old" / "gone.py"]
    assert not (scripts_out / "old").exists()  # emptied dir pruned
    assert (scripts_out / "keep.py").read_bytes() == b"k2\n"


def test_cleanup_preserves_user_authored_skill_dirs(tmp_path: Path) -> None:
    user_dir = _seed_tree(
        tmp_path / "shared_skills" / "mine",
        {"SKILL.md": b"---\nname: mine\ndescription: d\n---\nbody\n", "scripts/x.py": b"x\n"},
    )
    no_md = _seed_tree(tmp_path / "shared_skills" / "bare", {"note.md": f"{SENTINEL}\n".encode()})
    before = {**_tree_bytes(user_dir), **_tree_bytes(no_md)}

    deleted = SkillWriter(Path("shared_skills")).cleanup(set(), tmp_path)

    assert deleted == []
    assert {**_tree_bytes(user_dir), **_tree_bytes(no_md)} == before


def test_cleanup_tolerates_binary_files(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="ours"), tmp_path)
    stale_binary = tmp_path / "shared_skills" / "ours" / "blob.bin"
    stale_binary.write_bytes(b"\x80\x81\xff\xfe")
    user_dir = _seed_tree(tmp_path / "shared_skills" / "theirs", {"SKILL.md": b"\x80\x81\xff"})

    deleted = writer.cleanup(set(), tmp_path)

    assert stale_binary in deleted
    assert not (tmp_path / "shared_skills" / "ours").exists()
    assert (user_dir / "SKILL.md").read_bytes() == b"\x80\x81\xff"


@needs_symlinks
def test_cleanup_never_follows_or_deletes_symlinks(tmp_path: Path) -> None:
    outside = _seed_tree(tmp_path / "outside", {"precious.txt": b"p\n"})
    foreign = _seed_tree(
        tmp_path / "foreign-skill", {"SKILL.md": f"---\nname: f\n---\n{SENTINEL}\n".encode()}
    )
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="ours"), tmp_path)
    ours = tmp_path / "shared_skills" / "ours"
    (ours / "linked-dir").symlink_to(outside, target_is_directory=True)
    (ours / "linked-file").symlink_to(outside / "precious.txt")
    (tmp_path / "shared_skills" / "foreign").symlink_to(foreign, target_is_directory=True)

    deleted = writer.cleanup(set(), tmp_path)

    assert deleted == [ours / SKILL_FILENAME]
    assert (outside / "precious.txt").read_bytes() == b"p\n"
    assert (foreign / "SKILL.md").is_file()
    assert (ours / "linked-dir").is_symlink()
    assert (ours / "linked-file").is_symlink()


# --- ownership is decided before writing (review finding: data loss) --------


def _fs_is_case_insensitive(probe_dir: Path) -> bool:
    probe = probe_dir / "CaseProbe"
    probe.mkdir()
    try:
        return (probe_dir / "caseprobe").exists()
    finally:
        probe.rmdir()


def _save_lockfile(repo: Path, *rel_paths: str) -> None:
    entries = [LockEntry(path=rel, sha256="0" * 64, bytes=0) for rel in rel_paths]
    lockfile = Lockfile(schema_version=1, engine_version="0", rendered_at="t", entries=entries)
    FileSystemStateSource(repo_root=repo).save_lockfile(lockfile)


def test_write_skips_user_authored_dir_with_colliding_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hand-written ``<root>/<id>/`` (no sentinel) keeps every file, before and after cleanup."""
    user_dir = _seed_tree(
        tmp_path / "shared_skills" / "deploy",
        {
            "SKILL.md": b"---\nname: deploy\ndescription: mine\n---\nmine\n",
            "checklist.md": b"- step\n",
            "assets/template.yaml": b"k: v\n",
        },
    )
    before = _tree_bytes(user_dir)
    writer = SkillWriter(Path("shared_skills"))

    written = writer.write(_make_skill(skill_id="deploy"), tmp_path)
    deleted = writer.cleanup({p.resolve() for p in written}, tmp_path)

    assert written == []
    assert deleted == []
    assert _tree_bytes(user_dir) == before
    err = capsys.readouterr().err
    assert str(user_dir) in err
    assert "not playbook-managed" in err


def test_write_skips_plain_file_at_skill_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "shared_skills" / "demo"
    blocker.parent.mkdir(parents=True)
    blocker.write_bytes(b"not a dir\n")

    assert SkillWriter(Path("shared_skills")).write(_make_skill(skill_id="demo"), tmp_path) == []

    assert blocker.read_bytes() == b"not a dir\n"
    assert str(blocker) in capsys.readouterr().err


def test_write_claims_empty_existing_dir(tmp_path: Path) -> None:
    (tmp_path / "shared_skills" / "demo").mkdir(parents=True)
    written = SkillWriter(Path("shared_skills")).write(_make_skill(skill_id="demo"), tmp_path)
    assert written == [tmp_path / "shared_skills" / "demo" / SKILL_FILENAME]


def test_write_claims_legacy_sentinel_less_dir_listed_in_prior_lockfile(tmp_path: Path) -> None:
    """Pre-sentinel engines wrote ``.claude/skills/<id>/`` without a sentinel; the lockfile
    proves ownership, so an upgrade takes the dir over and cleans its stale files."""
    legacy = _seed_tree(
        tmp_path / ".claude" / "skills" / "demo",
        {"SKILL.md": b"---\nid: demo\n---\nold\n", "scripts/old.py": b"o\n"},
    )
    _save_lockfile(tmp_path, ".claude/skills/demo/SKILL.md", ".claude/skills/demo/scripts/old.py")
    writer = SkillWriter(Path(".claude") / "skills")

    written = writer.write(_make_skill(skill_id="demo"), tmp_path)
    deleted = writer.cleanup({p.resolve() for p in written}, tmp_path)

    assert written == [legacy / SKILL_FILENAME]
    assert SENTINEL in (legacy / SKILL_FILENAME).read_text(encoding="utf-8")
    assert deleted == [legacy / "scripts" / "old.py"]


def test_write_skips_sentinel_less_dir_when_lockfile_is_unreadable(tmp_path: Path) -> None:
    user_dir = _seed_tree(tmp_path / "shared_skills" / "demo", {"SKILL.md": b"mine\n"})
    (tmp_path / ".coding-agent-playbook.lock").write_text("not = [valid toml", encoding="utf-8")

    assert SkillWriter(Path("shared_skills")).write(_make_skill(skill_id="demo"), tmp_path) == []
    assert (user_dir / "SKILL.md").read_bytes() == b"mine\n"


# --- rewrites over changed on-disk shapes (review findings) -----------------


def test_rewrite_handles_reference_file_becoming_a_folder(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"api": b"flat\n"})
    writer.write(_make_skill(skill_id="demo", references_dir=v1), tmp_path)
    v2 = _seed_tree(tmp_path / "v2", {"api/v1.md": b"nested\n"})

    written = writer.write(_make_skill(skill_id="demo", references_dir=v2), tmp_path)
    deleted = writer.cleanup({p.resolve() for p in written}, tmp_path)

    refs = tmp_path / "shared_skills" / "demo" / "references"
    assert (refs / "api" / "v1.md").read_bytes() == b"nested\n"
    assert refs / "api" / "v1.md" in written
    assert deleted == []


def test_rewrite_handles_reference_folder_becoming_a_file(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"api/v1.md": b"nested\n"})
    writer.write(_make_skill(skill_id="demo", references_dir=v1), tmp_path)
    v2 = _seed_tree(tmp_path / "v2", {"api": b"flat\n"})

    written = writer.write(_make_skill(skill_id="demo", references_dir=v2), tmp_path)
    writer.cleanup({p.resolve() for p in written}, tmp_path)

    api = tmp_path / "shared_skills" / "demo" / "references" / "api"
    assert api.is_file()
    assert api.read_bytes() == b"flat\n"
    assert all(path.is_file() for path in written)  # never records a directory


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_rewrite_over_read_only_copy_from_earlier_sync(tmp_path: Path) -> None:
    scripts = _seed_tree(tmp_path / "src" / "scripts", {"run.sh": b"#!/bin/sh\necho 1\n"})
    (scripts / "run.sh").chmod(0o555)
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="demo", scripts_dir=scripts), tmp_path / "repo")
    (scripts / "run.sh").chmod(0o755)
    (scripts / "run.sh").write_bytes(b"#!/bin/sh\necho 2\n")
    (scripts / "run.sh").chmod(0o555)

    writer.write(_make_skill(skill_id="demo", scripts_dir=scripts), tmp_path / "repo")

    out = tmp_path / "repo" / "shared_skills" / "demo" / "scripts" / "run.sh"
    assert out.read_bytes() == b"#!/bin/sh\necho 2\n"


# --- cleanup matches written files by identity, not path spelling -----------


def test_cleanup_keeps_written_files_under_a_relative_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``playbook sync --repo-root rel`` walks relative paths while ``written_paths``
    holds resolved ones; nothing written this sync may be deleted."""
    monkeypatch.chdir(tmp_path)
    scripts = _seed_tree(tmp_path / "src" / "scripts", {"a.py": b"a\n"})
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="old"), Path("repo"))
    written = writer.write(_make_skill(skill_id="demo", scripts_dir=scripts), Path("repo"))

    deleted = writer.cleanup({p.resolve() for p in written}, Path("repo"))

    assert deleted == [Path("repo") / "shared_skills" / "old" / SKILL_FILENAME]
    assert all(path.is_file() for path in written)


@needs_symlinks
def test_cleanup_keeps_written_files_under_a_symlinked_repo_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    writer = SkillWriter(Path("shared_skills"))
    written = writer.write(_make_skill(skill_id="demo"), link)

    assert writer.cleanup({p.resolve() for p in written}, link) == []
    assert (real / "shared_skills" / "demo" / SKILL_FILENAME).is_file()


@needs_symlinks
def test_cleanup_compares_file_identity_not_path_spelling(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    [skill_md] = writer.write(_make_skill(skill_id="demo"), tmp_path)
    alias = tmp_path / "hardlink-to-skill-md"
    os.link(skill_md, alias)

    assert writer.cleanup({alias}, tmp_path) == []
    assert skill_md.is_file()


def test_case_only_id_rename_keeps_skill_on_case_insensitive_fs(tmp_path: Path) -> None:
    """Default macOS APFS / Windows: ``QueryDB`` -> ``querydb`` must not delete the skill."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem")
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="QueryDB"), tmp_path)

    written = writer.write(_make_skill(skill_id="querydb"), tmp_path)
    deleted = writer.cleanup({p.resolve() for p in written}, tmp_path)

    assert deleted == []
    assert [entry.name for entry in (tmp_path / "shared_skills").iterdir()] == ["querydb"]
    text = (tmp_path / "shared_skills" / "querydb" / SKILL_FILENAME).read_text(encoding="utf-8")
    assert text.startswith("---\nname: querydb\n")


def test_case_only_id_rename_cleans_old_dir_on_case_sensitive_fs(tmp_path: Path) -> None:
    if _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-sensitive filesystem")
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="QueryDB"), tmp_path)

    written = writer.write(_make_skill(skill_id="querydb"), tmp_path)
    deleted = writer.cleanup({p.resolve() for p in written}, tmp_path)

    assert deleted == [tmp_path / "shared_skills" / "QueryDB" / SKILL_FILENAME]
    assert [entry.name for entry in (tmp_path / "shared_skills").iterdir()] == ["querydb"]


def test_file_identities_skip_missing_paths(tmp_path: Path) -> None:
    present = tmp_path / "present.txt"
    present.write_bytes(b"x")
    missing = tmp_path / "missing.txt"

    assert _skill_writer._file_identity(missing) is None
    assert _skill_writer._file_identities([present, missing]) == {
        (present.stat().st_dev, present.stat().st_ino)
    }
    assert not _skill_writer._is_same_file(present, missing)


def test_cleanup_tolerates_written_paths_that_no_longer_exist(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    written = writer.write(_make_skill(skill_id="demo"), tmp_path)
    gone = tmp_path / "removed-by-another-adapter.md"

    assert writer.cleanup({*(p.resolve() for p in written), gone}, tmp_path) == []
