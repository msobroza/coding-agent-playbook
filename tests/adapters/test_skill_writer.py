"""Tests for the shared native Agent-Skills writer (SPEC §6.3, §10.8)."""

from __future__ import annotations

import contextlib
import os
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.adapters import _skill_writer
from coding_agent_playbook.adapters._prior_output import judging_leftovers_with
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
from coding_agent_playbook.commands._output_locations import OutputLocations
from coding_agent_playbook.commands._sync_orphans import LeftoverPolicy
from coding_agent_playbook.lockfile import LockEntry, Lockfile, compute_hash
from coding_agent_playbook.orchestrator import installed_output_locations
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.sources.filesystem import FileSystemStateSource
from coding_agent_playbook.types import Skill, split_frontmatter
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Iterator

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


@needs_symlinks
def test_write_skips_a_dangling_symlinked_skills_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``.claude/skills -> ../.agents/skills`` whose target is gone: warn and skip
    (regression: ``mkdir`` crashed every later sync with ``FileExistsError``)."""
    (tmp_path / ".claude").mkdir()
    root = tmp_path / ".claude" / "skills"
    root.symlink_to("../.agents/skills", target_is_directory=True)

    writer = SkillWriter(Path(".claude") / "skills")
    assert writer.write(_make_skill(skill_id="demo"), tmp_path) == []

    assert root.is_symlink()
    assert not (tmp_path / ".agents").exists()
    assert f"not writing skills under {root}" in capsys.readouterr().err
    with _skill_writer.deciding_ownership_against(tmp_path):  # check modes skip it too
        assert writer.write(_make_skill(skill_id="demo"), tmp_path / "scratch") == []


def test_write_skips_a_skills_root_that_is_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "shared_skills").write_bytes(b"not a dir\n")
    assert SkillWriter(Path("shared_skills")).write(_make_skill(skill_id="demo"), tmp_path) == []
    assert (tmp_path / "shared_skills").read_bytes() == b"not a dir\n"
    assert "dangling symlink or a file" in capsys.readouterr().err


# --- ownership (the writer never deletes) ---------------------------------


def test_is_engine_owned_skill_dir(tmp_path: Path) -> None:
    writer = SkillWriter(Path("s"))
    writer.write(_make_skill(skill_id="ours"), tmp_path)
    user_dir = _seed_tree(tmp_path / "s" / "theirs", {"SKILL.md": b"---\nname: theirs\n---\nx\n"})
    no_md = _seed_tree(tmp_path / "s" / "bare", {"helper.md": f"# {SENTINEL}\n".encode()})
    assert is_engine_owned_skill_dir(tmp_path / "s" / "ours")
    assert not is_engine_owned_skill_dir(user_dir)
    assert not is_engine_owned_skill_dir(no_md)
    assert not is_engine_owned_skill_dir(tmp_path / "s" / "missing")


def test_is_engine_owned_skill_dir_tolerates_binary_skill_md(tmp_path: Path) -> None:
    theirs = _seed_tree(tmp_path / "s" / "theirs", {"SKILL.md": b"\x80\x81\xff"})
    assert not is_engine_owned_skill_dir(theirs)


@needs_symlinks
def test_is_engine_owned_skill_dir_rejects_symlinks(tmp_path: Path) -> None:
    foreign = _seed_tree(
        tmp_path / "foreign", {"SKILL.md": f"---\nname: f\n---\n{SENTINEL}\n".encode()}
    )
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "alias").symlink_to(foreign, target_is_directory=True)
    assert not is_engine_owned_skill_dir(tmp_path / "s" / "alias")


def test_writer_never_deletes_stale_files(tmp_path: Path) -> None:
    """Superseded A-era cleanup: stale output is settled by sync's lockfile leftover
    policy (SPEC §4.2 step 9), never by the writer — rewriting a skill without a
    script leaves the old copy (and any user file) where it is."""
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"keep.py": b"k\n", "gone.py": b"g\n"})
    writer.write(_make_skill(skill_id="demo", scripts_dir=v1), tmp_path)
    user_file = tmp_path / "shared_skills" / "demo" / "notes.md"
    user_file.write_bytes(b"mine\n")
    v2 = _seed_tree(tmp_path / "v2", {"keep.py": b"k2\n"})

    written = writer.write(_make_skill(skill_id="demo", scripts_dir=v2), tmp_path)

    scripts_out = tmp_path / "shared_skills" / "demo" / "scripts"
    assert scripts_out / "gone.py" not in written
    assert (scripts_out / "gone.py").read_bytes() == b"g\n"
    assert user_file.read_bytes() == b"mine\n"
    assert not hasattr(writer, "cleanup")


# --- ownership is decided before writing (review finding: data loss) --------


def _fs_is_case_insensitive(probe_dir: Path) -> bool:
    probe = probe_dir / "CaseProbe"
    probe.mkdir()
    try:
        return (probe_dir / "caseprobe").exists()
    finally:
        probe.rmdir()


def _save_lockfile(repo: Path, *rel_paths: str) -> None:
    """Record ``rel_paths`` with their current bytes, as ``playbook sync`` would."""
    entries = []
    for rel in rel_paths:
        content = (repo / rel).read_bytes()
        entries.append(LockEntry(path=rel, sha256=compute_hash(content), bytes=len(content)))
    lockfile = Lockfile(schema_version=1, engine_version="0", rendered_at="t", entries=entries)
    FileSystemStateSource(repo_root=repo).save_lockfile(lockfile)


@contextlib.contextmanager
def _under_sync_policy(
    repo: Path, git: FakeGitClient | None = None, *, keep_all: bool = False
) -> Iterator[LeftoverPolicy]:
    """Run writes under the leftover policy write-mode ``playbook sync`` installs."""
    policy = LeftoverPolicy(
        previous=FileSystemStateSource(repo_root=repo).load_lockfile(),
        repo_root=repo,
        git=git or FakeGitClient(),
        keep_all=keep_all,
        locations=OutputLocations.declared(installed_output_locations(), repo),
    )
    with judging_leftovers_with(policy.may_delete):
        yield policy


def test_write_skips_user_authored_dir_with_colliding_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hand-written ``<root>/<id>/`` (no sentinel) keeps every file."""
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

    assert written == []
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
    proves ownership, so an upgrade takes the dir over. Its stale files are left to
    sync's lockfile leftover policy, never deleted by the writer."""
    legacy = _seed_tree(
        tmp_path / ".claude" / "skills" / "demo",
        {"SKILL.md": b"---\nid: demo\n---\nold\n", "scripts/old.py": b"o\n"},
    )
    _save_lockfile(tmp_path, ".claude/skills/demo/SKILL.md", ".claude/skills/demo/scripts/old.py")
    writer = SkillWriter(Path(".claude") / "skills")

    written = writer.write(_make_skill(skill_id="demo"), tmp_path)

    assert written == [legacy / SKILL_FILENAME]
    assert SENTINEL in (legacy / SKILL_FILENAME).read_text(encoding="utf-8")
    assert (legacy / "scripts" / "old.py").read_bytes() == b"o\n"


def test_write_skips_listed_sentinel_less_dir_whose_skill_md_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: the lockfile also carries kept (edited) leftovers, so "listed" alone
    would let the engine re-claim a dir the user adopted (rewrote ``SKILL.md`` without
    the sentinel) and silently overwrite their files. Only unchanged bytes prove it."""
    adopted = _seed_tree(
        tmp_path / ".claude" / "skills" / "demo",
        {"SKILL.md": b"---\nid: demo\n---\nold\n", "scripts/run.sh": b"echo 1\n"},
    )
    _save_lockfile(tmp_path, ".claude/skills/demo/SKILL.md", ".claude/skills/demo/scripts/run.sh")
    (adopted / "SKILL.md").write_bytes(b"MY OWN INSTRUCTIONS\n")
    (adopted / "scripts" / "run.sh").write_bytes(b"echo mine\n")
    before = _tree_bytes(adopted)

    written = SkillWriter(Path(".claude") / "skills").write(_make_skill(skill_id="demo"), tmp_path)

    assert written == []
    assert _tree_bytes(adopted) == before
    assert "not playbook-managed" in capsys.readouterr().err


def test_write_skips_sentinel_less_dir_when_lockfile_is_unreadable(tmp_path: Path) -> None:
    user_dir = _seed_tree(tmp_path / "shared_skills" / "demo", {"SKILL.md": b"mine\n"})
    (tmp_path / ".coding-agent-playbook.lock").write_text("not = [valid toml", encoding="utf-8")

    assert SkillWriter(Path("shared_skills")).write(_make_skill(skill_id="demo"), tmp_path) == []
    assert (user_dir / "SKILL.md").read_bytes() == b"mine\n"


# --- rewrites over changed on-disk shapes (review findings) -----------------


def _sync_like_write(writer: SkillWriter, skill: Skill, repo: Path) -> list[Path]:
    """Write ``skill`` and record it in the lockfile, as ``playbook sync`` would."""
    written = writer.write(skill, repo)
    _save_lockfile(repo, *(path.relative_to(repo).as_posix() for path in written))
    return written


def test_rewrite_handles_reference_file_becoming_a_folder(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"api": b"flat\n"})
    _sync_like_write(writer, _make_skill(skill_id="demo", references_dir=v1), tmp_path)
    v2 = _seed_tree(tmp_path / "v2", {"api/v1.md": b"nested\n"})

    with _under_sync_policy(tmp_path) as policy:
        written = writer.write(_make_skill(skill_id="demo", references_dir=v2), tmp_path)

    refs = tmp_path / "shared_skills" / "demo" / "references"
    assert (refs / "api" / "v1.md").read_bytes() == b"nested\n"
    assert refs / "api" / "v1.md" in written
    assert policy.displaced == [refs / "api"]  # counted as removed by sync


def test_rewrite_handles_reference_folder_becoming_a_file(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"api/v1.md": b"nested\n", "api/deep/x.md": b"x\n"})
    _sync_like_write(writer, _make_skill(skill_id="demo", references_dir=v1), tmp_path)
    v2 = _seed_tree(tmp_path / "v2", {"api": b"flat\n"})

    with _under_sync_policy(tmp_path) as policy:
        written = writer.write(_make_skill(skill_id="demo", references_dir=v2), tmp_path)

    api = tmp_path / "shared_skills" / "demo" / "references" / "api"
    assert api.is_file()
    assert api.read_bytes() == b"flat\n"
    assert all(path.is_file() for path in written)  # never records a directory
    assert sorted(policy.displaced) == [api / "deep" / "x.md", api / "v1.md"]


# --- a swap displaces only what the leftover policy would delete (U1) ----------


def _flip_reference_folder_to_file(
    tmp_path: Path, *, edit: bool = False
) -> tuple[SkillWriter, Skill, Path]:
    """Sync ``references/api/v1.md``; return the writer, a skill whose ``api`` is a file,
    and the old (optionally user-edited) ``v1.md``."""
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"api/v1.md": b"nested\n"})
    _sync_like_write(writer, _make_skill(skill_id="demo", references_dir=v1), tmp_path)
    old = tmp_path / "shared_skills" / "demo" / "references" / "api" / "v1.md"
    if edit:
        old.write_bytes(b"MY IMPORTANT EDITS\n")
    v2 = _seed_tree(tmp_path / "v2", {"api": b"flat\n"})
    return writer, _make_skill(skill_id="demo", references_dir=v2), old


def test_swap_never_displaces_an_edited_leftover(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    writer, skill, old = _flip_reference_folder_to_file(tmp_path, edit=True)

    with _under_sync_policy(tmp_path) as policy:
        written = writer.write(skill, tmp_path)

    assert old.read_bytes() == b"MY IMPORTANT EDITS\n"
    assert old.parent not in written
    assert policy.displaced == []
    assert f"not writing {old.parent}" in capsys.readouterr().err


def test_swap_never_displaces_a_tracked_leftover(tmp_path: Path) -> None:
    writer, skill, old = _flip_reference_folder_to_file(tmp_path)
    git = FakeGitClient(tracked={"shared_skills/demo/references/api/v1.md"})

    with _under_sync_policy(tmp_path, git):
        writer.write(skill, tmp_path)

    assert old.read_bytes() == b"nested\n"


def test_swap_with_a_missing_adapter_displaces_nothing(tmp_path: Path) -> None:
    writer, skill, old = _flip_reference_folder_to_file(tmp_path)

    with _under_sync_policy(tmp_path, keep_all=True):
        writer.write(skill, tmp_path)

    assert old.read_bytes() == b"nested\n"


def test_swap_outside_a_sync_displaces_nothing(tmp_path: Path) -> None:
    """No leftover policy installed (the writer used on its own): fail safe."""
    writer, skill, old = _flip_reference_folder_to_file(tmp_path)

    writer.write(skill, tmp_path)

    assert old.read_bytes() == b"nested\n"


def test_file_becoming_a_folder_never_displaces_an_edited_leftover(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"tool": b"#!/bin/sh\n"})
    _sync_like_write(writer, _make_skill(skill_id="demo", scripts_dir=v1), tmp_path)
    tool = tmp_path / "shared_skills" / "demo" / "scripts" / "tool"
    tool.write_bytes(b"# my important local edits\n")
    v2 = _seed_tree(tmp_path / "v2", {"tool/main.sh": b"#!/bin/sh\n"})

    with _under_sync_policy(tmp_path):
        writer.write(_make_skill(skill_id="demo", scripts_dir=v2), tmp_path)

    assert tool.read_bytes() == b"# my important local edits\n"


# --- a file/folder swap never deletes a file the engine did not write -----------


def test_folder_becoming_a_file_never_deletes_a_user_file_inside_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"api/v1.md": b"nested\n"})
    _sync_like_write(writer, _make_skill(skill_id="demo", references_dir=v1), tmp_path)
    api = tmp_path / "shared_skills" / "demo" / "references" / "api"
    (api / "mine.md").write_bytes(b"user notes\n")
    v2 = _seed_tree(tmp_path / "v2", {"api": b"flat\n", "other.md": b"o\n"})

    with _under_sync_policy(tmp_path):
        written = writer.write(_make_skill(skill_id="demo", references_dir=v2), tmp_path)

    assert (api / "mine.md").read_bytes() == b"user notes\n"
    assert (api / "v1.md").read_bytes() == b"nested\n"  # nothing partially removed
    assert api not in written
    assert api.parent / "other.md" in written  # the rest of the skill is still written
    assert f"not writing {api}" in capsys.readouterr().err


def test_file_becoming_a_folder_never_deletes_a_user_file_in_the_way(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    writer = SkillWriter(Path("shared_skills"))
    _sync_like_write(writer, _make_skill(skill_id="demo"), tmp_path)
    user_file = tmp_path / "shared_skills" / "demo" / "references"
    user_file.write_bytes(b"not ours\n")  # never in the lockfile
    v2 = _seed_tree(tmp_path / "v2", {"api.md": b"a\n"})

    with _under_sync_policy(tmp_path):
        written = writer.write(_make_skill(skill_id="demo", references_dir=v2), tmp_path)

    assert user_file.read_bytes() == b"not ours\n"
    assert written == [tmp_path / "shared_skills" / "demo" / SKILL_FILENAME]
    assert "is in the way" in capsys.readouterr().err


@needs_symlinks
def test_folder_with_a_symlink_inside_is_never_displaced(tmp_path: Path) -> None:
    writer = SkillWriter(Path("shared_skills"))
    v1 = _seed_tree(tmp_path / "v1", {"api/v1.md": b"nested\n"})
    _sync_like_write(writer, _make_skill(skill_id="demo", references_dir=v1), tmp_path)
    api = tmp_path / "shared_skills" / "demo" / "references" / "api"
    (api / "link").symlink_to(tmp_path / "v1", target_is_directory=True)
    v2 = _seed_tree(tmp_path / "v2", {"api": b"flat\n"})

    with _under_sync_policy(tmp_path):
        writer.write(_make_skill(skill_id="demo", references_dir=v2), tmp_path)

    assert (api / "link").is_symlink()
    assert (tmp_path / "v1" / "api" / "v1.md").is_file()


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


# --- case-only id renames ----------------------------------------------------


def test_case_only_id_rename_keeps_skill_on_case_insensitive_fs(tmp_path: Path) -> None:
    """Default macOS APFS / Windows: ``QueryDB`` -> ``querydb`` renames the dir in place."""
    if not _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-insensitive filesystem")
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="QueryDB"), tmp_path)

    written = writer.write(_make_skill(skill_id="querydb"), tmp_path)

    assert written == [tmp_path / "shared_skills" / "querydb" / SKILL_FILENAME]
    assert [entry.name for entry in (tmp_path / "shared_skills").iterdir()] == ["querydb"]
    text = (tmp_path / "shared_skills" / "querydb" / SKILL_FILENAME).read_text(encoding="utf-8")
    assert text.startswith("---\nname: querydb\n")


def test_case_only_id_rename_writes_a_new_dir_on_case_sensitive_fs(tmp_path: Path) -> None:
    """The old dir is a separate leftover there; sync's leftover policy removes it."""
    if _fs_is_case_insensitive(tmp_path):
        pytest.skip("needs a case-sensitive filesystem")
    writer = SkillWriter(Path("shared_skills"))
    writer.write(_make_skill(skill_id="QueryDB"), tmp_path)

    writer.write(_make_skill(skill_id="querydb"), tmp_path)

    names = sorted(entry.name for entry in (tmp_path / "shared_skills").iterdir())
    assert names == ["QueryDB", "querydb"]


def test_is_same_file_is_false_for_missing_paths(tmp_path: Path) -> None:
    present = tmp_path / "present.txt"
    present.write_bytes(b"x")
    assert _skill_writer._is_same_file(present, present)
    assert not _skill_writer._is_same_file(present, tmp_path / "missing.txt")


# --- check modes decide ownership against the real tree (SPEC §12.3) ---------


def test_ownership_is_decided_against_the_real_tree_when_rendering_elsewhere(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--check`` renders into an empty scratch dir; a user-owned dir in the real
    repo must be skipped there too, else the check reports false drift."""
    real, scratch = tmp_path / "real", tmp_path / "scratch"
    user_dir = _seed_tree(real / "shared_skills" / "deploy", {"SKILL.md": b"---\nname: x\n---\n"})
    writer = SkillWriter(Path("shared_skills"))

    with _skill_writer.deciding_ownership_against(real):
        assert writer.write(_make_skill(skill_id="deploy"), scratch) == []
        written = writer.write(_make_skill(skill_id="fresh"), scratch)

    assert written == [scratch / "shared_skills" / "fresh" / SKILL_FILENAME]
    assert not (scratch / "shared_skills" / "deploy").exists()
    assert str(user_dir) in capsys.readouterr().err  # names the real dir, not scratch
    # Outside the context the scratch tree decides again (nothing there to collide).
    assert writer.write(_make_skill(skill_id="deploy"), scratch) != []


def test_check_mode_ownership_honours_the_real_lockfile_legacy_claim(tmp_path: Path) -> None:
    real, scratch = tmp_path / "real", tmp_path / "scratch"
    _seed_tree(real / ".claude" / "skills" / "demo", {"SKILL.md": b"---\nid: demo\n---\nold\n"})
    _save_lockfile(real, ".claude/skills/demo/SKILL.md")
    writer = SkillWriter(Path(".claude") / "skills")

    with _skill_writer.deciding_ownership_against(real):
        written = writer.write(_make_skill(skill_id="demo"), scratch)

    assert written == [scratch / ".claude" / "skills" / "demo" / SKILL_FILENAME]
    assert b"old" in (real / ".claude" / "skills" / "demo" / SKILL_FILENAME).read_bytes()
