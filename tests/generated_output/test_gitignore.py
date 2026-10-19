"""Unit tests for the managed ``.gitignore`` block (``coding_agent_playbook.generated_output.gitignore``)."""

from __future__ import annotations

import os
import shutil
import subprocess
import unicodedata
from pathlib import Path, PurePosixPath

import pytest

from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.generated_output.gitignore import (
    BLOCK_END,
    BLOCK_START,
    LOCKFILE_ENTRY,
    LOCKFILE_NAME,
    apply_managed_block,
    block_is_current,
    entry_matches,
    escape_path,
    ignore_entries,
    relative_posix_paths,
    remove_managed_block,
    render_block,
)

ENTRIES = ["/AGENTS.md", "/.claude/CLAUDE.md"]
BLOCK = f"{BLOCK_START}\n/.claude/CLAUDE.md\n/AGENTS.md\n{BLOCK_END}\n"


def _paths(root: Path, *rels: str) -> list[Path]:
    return [root / rel for rel in rels]


# --------------------------------------------------------------------------- #
# relative_posix_paths / ignore_entries
# --------------------------------------------------------------------------- #


def test_lockfile_name_matches_state_source() -> None:
    assert LOCKFILE_NAME == FileSystemStateSource._LOCKFILE_FILENAME
    assert f"/{LOCKFILE_NAME}" == LOCKFILE_ENTRY


def test_relative_posix_paths_sorts_dedupes_and_skips_outside(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere.md"
    paths = [*_paths(tmp_path, "b.md", "a/x.md", "b.md"), outside, tmp_path]
    assert relative_posix_paths(paths, tmp_path) == ["a/x.md", "b.md"]


def test_relative_posix_paths_accepts_relative_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert relative_posix_paths([Path("AGENTS.md")], Path(".")) == ["AGENTS.md"]


def test_ignore_entries_one_root_anchored_entry_per_file_plus_lockfile(tmp_path: Path) -> None:
    written = _paths(tmp_path, "AGENTS.md", ".claude/CLAUDE.md", ".continue/rules/50-x.md")
    assert ignore_entries(written, tmp_path) == [
        "/.claude/CLAUDE.md",
        LOCKFILE_ENTRY,
        "/.continue/rules/50-x.md",
        "/AGENTS.md",
    ]


def test_ignore_entries_always_includes_lockfile(tmp_path: Path) -> None:
    assert ignore_entries([], tmp_path) == [LOCKFILE_ENTRY]


def test_ignore_entries_collapses_claude_skill_dir(tmp_path: Path) -> None:
    written = _paths(
        tmp_path,
        ".claude/skills/review/SKILL.md",
        ".claude/skills/review/scripts/run.sh",
        ".claude/skills/review/references/deep/notes.md",
    )
    assert ignore_entries(written, tmp_path) == ["/.claude/skills/review/", LOCKFILE_ENTRY]


def test_ignore_entries_collapses_skill_dirs_under_any_root(tmp_path: Path) -> None:
    """Skill roots are detected generically — no hardcoded adapter paths."""
    written = _paths(
        tmp_path,
        "shared_skills/x/SKILL.md",
        "shared_skills/x/scripts/a.py",
        ".opencode/skills/y/SKILL.md",
        "shared_skills/README.md",
    )
    assert ignore_entries(written, tmp_path) == [
        LOCKFILE_ENTRY,
        "/.opencode/skills/y/",
        "/shared_skills/README.md",
        "/shared_skills/x/",
    ]


def test_ignore_entries_collapses_to_shallowest_nested_skill_dir(tmp_path: Path) -> None:
    written = _paths(tmp_path, "s/outer/SKILL.md", "s/outer/inner/SKILL.md", "s/outer/inner/a.md")
    assert ignore_entries(written, tmp_path) == [LOCKFILE_ENTRY, "/s/outer/"]


def test_ignore_entries_does_not_collapse_root_level_skill_md(tmp_path: Path) -> None:
    written = _paths(tmp_path, "SKILL.md", "AGENTS.md")
    assert ignore_entries(written, tmp_path) == [LOCKFILE_ENTRY, "/AGENTS.md", "/SKILL.md"]


def test_ignore_entries_needs_a_written_skill_md_to_collapse(tmp_path: Path) -> None:
    """A SKILL.md on disk but not written by this sync does not collapse."""
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "SKILL.md").write_text("user file\n")
    assert ignore_entries(_paths(tmp_path, "d/a.md"), tmp_path) == [LOCKFILE_ENTRY, "/d/a.md"]


def test_ignore_entries_skips_paths_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    written = [repo / "AGENTS.md", tmp_path / "other" / "x.md"]
    assert ignore_entries(written, repo) == [LOCKFILE_ENTRY, "/AGENTS.md"]


def test_ignore_entries_escapes_names(tmp_path: Path) -> None:
    written = _paths(tmp_path, "we*ird?.md", "#hash.md", "!bang.md", "sk ill/SKILL.md")
    assert ignore_entries(written, tmp_path) == [
        LOCKFILE_ENTRY,
        "/\\!bang.md",
        "/\\#hash.md",
        "/sk ill/",
        "/we\\*ird\\?.md",
    ]


_NFD = unicodedata.normalize("NFD", "café")
_NFC = unicodedata.normalize("NFC", "café")


def test_ignore_entries_emit_nfc_and_as_written_forms_for_decomposed_names(
    tmp_path: Path,
) -> None:
    """Regression: git on macOS reports NFC paths and never normalises patterns,
    so an NFD-written file needs an NFC entry (plus its own form for Linux)."""
    written = _paths(tmp_path, f".claude/commands/{_NFD}.md", f"skills/{_NFD}/SKILL.md")
    assert ignore_entries(written, tmp_path) == sorted(
        [
            LOCKFILE_ENTRY,
            f"/.claude/commands/{_NFC}.md",
            f"/.claude/commands/{_NFD}.md",
            f"/skills/{_NFC}/",
            f"/skills/{_NFD}/",
        ]
    )


def test_ignore_entries_single_entry_for_precomposed_names(tmp_path: Path) -> None:
    assert ignore_entries(_paths(tmp_path, f"{_NFC}.md"), tmp_path) == [
        LOCKFILE_ENTRY,
        f"/{_NFC}.md",
    ]


# --------------------------------------------------------------------------- #
# escape_path / entry_matches
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("plain/name.md", "plain/name.md"),
        ("a*b", "a\\*b"),
        ("a?b", "a\\?b"),
        ("b[1]", "b\\[1]"),
        ("!x", "\\!x"),
        ("#y", "\\#y"),
        ("back\\slash", "back\\\\slash"),
        ("trail ", "trail\\ "),
        (" lead", "\\ lead"),
        ("mid dle", "mid dle"),
        ("  ", "\\ \\ "),
        ("dir /f", "dir\\ /f"),
    ],
)
def test_escape_path(raw: str, escaped: str) -> None:
    assert escape_path(PurePosixPath(raw)) == escaped


def test_escape_path_normalises_to_nfc() -> None:
    assert escape_path(PurePosixPath(f"d/{_NFD}*.md")) == f"d/{_NFC}\\*.md"


def test_escape_path_rejects_newline() -> None:
    with pytest.raises(ValueError, match="newline"):
        escape_path(PurePosixPath("bad\nname"))


@pytest.mark.parametrize(
    ("rel", "entry", "expected"),
    [
        ("AGENTS.md", "/AGENTS.md", True),
        ("AGENTS.md.bak", "/AGENTS.md", False),
        ("sub/AGENTS.md", "/AGENTS.md", False),
        (".claude/skills/s/SKILL.md", "/.claude/skills/s/", True),
        (".claude/skills/s/scripts/run.sh", "/.claude/skills/s/", True),
        (".claude/skills/s2/SKILL.md", "/.claude/skills/s/", False),
        ("we*ird.md", "/we\\*ird.md", True),
        ("weXird.md", "/we\\*ird.md", False),
        ("sp ", "/sp\\ ", True),
        (f"{_NFC}.md", f"/{_NFD}.md", True),
        (f"{_NFD}.md", f"/{_NFC}.md", True),
        (f"s/{_NFC}/a.md", f"/s/{_NFD}/", True),
    ],
)
def test_entry_matches(rel: str, entry: str, expected: bool) -> None:
    assert entry_matches(rel, entry) is expected


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.usefixtures("hermetic_git_env")
def test_escaped_entries_match_literally_in_real_git(tmp_path: Path) -> None:
    """Ground truth: git itself ignores exactly the escaped names, nothing else."""
    names = ["we*ird", "weXird", "sp ", "sp", "a!b", "#y", "b[1]", "b1", "q?", "qq"]
    for name in names:
        (tmp_path / name).write_text("z")
    targets = ["we*ird", "sp ", "a!b", "#y", "b[1]", "q?"]
    entries = ignore_entries([tmp_path / name for name in targets], tmp_path)
    apply_managed_block(tmp_path / ".gitignore", entries)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--others", "--ignored", "--exclude-standard"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert sorted(proc.stdout.decode().split("\0")[:-1]) == sorted(targets)


# --------------------------------------------------------------------------- #
# render_block / apply_managed_block
# --------------------------------------------------------------------------- #


def test_render_block_sorts_and_dedupes() -> None:
    assert render_block(["/b", "/a", "/b"]) == f"{BLOCK_START}\n/a\n/b\n{BLOCK_END}\n"


def test_render_block_crlf() -> None:
    assert render_block(["/a"], "\r\n") == f"{BLOCK_START}\r\n/a\r\n{BLOCK_END}\r\n"


def test_apply_creates_missing_file(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    assert apply_managed_block(target, ENTRIES) is True
    assert target.read_text() == BLOCK


def test_apply_to_empty_file_writes_block_only(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("")
    assert apply_managed_block(target, ENTRIES) is True
    assert target.read_text() == BLOCK


def test_apply_appends_after_one_blank_line(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n.venv/\n")
    assert apply_managed_block(target, ENTRIES) is True
    assert target.read_text() == f"*.pyc\n.venv/\n\n{BLOCK}"


def test_apply_reuses_existing_trailing_blank_line(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n\n")
    apply_managed_block(target, ENTRIES)
    assert target.read_text() == f"*.pyc\n\n{BLOCK}"


def test_apply_handles_missing_final_newline(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc")
    apply_managed_block(target, ENTRIES)
    assert target.read_text() == f"*.pyc\n\n{BLOCK}"


def test_apply_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n")
    assert apply_managed_block(target, ENTRIES) is True
    first = target.read_bytes()
    assert apply_managed_block(target, ENTRIES) is False
    assert target.read_bytes() == first


def test_apply_replaces_block_in_place_preserving_surroundings(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(f"head\n\n{BLOCK_START}\n/old.md\n{BLOCK_END}\ntail\n")
    assert apply_managed_block(target, ENTRIES) is True
    assert target.read_text() == f"head\n\n{BLOCK}tail\n"


def test_apply_preserves_crlf_line_endings(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_bytes(b"*.pyc\r\n.venv/\r\n")
    apply_managed_block(target, ["/a"])
    expected = f"*.pyc\r\n.venv/\r\n\r\n{BLOCK_START}\r\n/a\r\n{BLOCK_END}\r\n"
    assert target.read_bytes() == expected.encode()
    assert apply_managed_block(target, ["/a"]) is False


def test_apply_replace_keeps_crlf_and_bytes_outside(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    before = b"a\r\n\xff raw\r\n"
    after = b"z\r\nno-final-newline"
    target.write_bytes(
        before + f"{BLOCK_START}\r\n/old\r\n{BLOCK_END}\r\n".encode() + after,
    )
    apply_managed_block(target, ["/new"])
    block = f"{BLOCK_START}\r\n/new\r\n{BLOCK_END}\r\n".encode()
    assert target.read_bytes() == before + block + after


def test_apply_keeps_block_without_final_newline_idempotent(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(f"x\n{BLOCK_START}\n/AGENTS.md\n{BLOCK_END}")
    assert apply_managed_block(target, ["/AGENTS.md"]) is False
    apply_managed_block(target, ["/B.md"])
    assert target.read_text() == f"x\n{BLOCK_START}\n/B.md\n{BLOCK_END}"


def test_apply_tolerates_trailing_whitespace_on_markers(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(f"{BLOCK_START}  \n/old\n{BLOCK_END}\t\n")
    apply_managed_block(target, ENTRIES)
    assert target.read_text() == BLOCK


@pytest.mark.parametrize(
    ("content", "line", "fragment"),
    [
        (f"a\n{BLOCK_START}\n/x\n", 2, "no end marker"),
        (f"a\nb\n{BLOCK_END}\n", 3, "no start marker"),
        (f"{BLOCK_END}\n{BLOCK_START}\n", 1, "precedes"),
        (f"{BLOCK_START}\n{BLOCK_END}\n{BLOCK_START}\n{BLOCK_END}\n", 3, "duplicate"),
        (f"{BLOCK_START}\n{BLOCK_END}\n{BLOCK_END}\n", 3, "duplicate"),
    ],
)
def test_apply_rejects_malformed_markers_without_clobbering(
    tmp_path: Path, content: str, line: int, fragment: str
) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(content)
    with pytest.raises(ValueError, match=fragment) as exc:
        apply_managed_block(target, ENTRIES)
    assert f"{target}:{line}:" in str(exc.value)
    assert target.read_text() == content


_BOM = "\ufeff"


def test_apply_replaces_bom_prefixed_first_line_block_keeping_the_bom(tmp_path: Path) -> None:
    """Regression: a Windows editor saving with a BOM must not make the block
    unparseable (git itself skips the BOM)."""
    target = tmp_path / ".gitignore"
    target.write_text(f"{_BOM}{BLOCK_START}\n/old.md\n{BLOCK_END}\ntail\n")
    assert apply_managed_block(target, ENTRIES) is True
    assert target.read_text() == f"{_BOM}{BLOCK}tail\n"
    assert apply_managed_block(target, ENTRIES) is False
    assert block_is_current(target, ENTRIES) is True


def test_apply_bom_only_matters_on_the_first_line(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    content = f"a\n{_BOM}{BLOCK_START}\n{BLOCK_END}\n"
    target.write_text(content)
    with pytest.raises(ValueError, match="no start marker"):
        apply_managed_block(target, ENTRIES)
    assert target.read_text() == content


def test_remove_keeps_bom_of_a_first_line_block(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(f"{_BOM}{BLOCK}*.pyc\n")
    assert remove_managed_block(target) is True
    assert target.read_text() == f"{_BOM}*.pyc\n"


def test_apply_never_touches_a_user_gitignore_tmp_file(tmp_path: Path) -> None:
    """Regression: the temp file name is unique — a user's ``.gitignore.tmp``
    is neither overwritten nor moved onto ``.gitignore``."""
    user_file = tmp_path / ".gitignore.tmp"
    user_file.write_text("MY NOTES\n")
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n")
    assert apply_managed_block(target, ENTRIES) is True
    assert user_file.read_text() == "MY NOTES\n"
    assert target.read_text() == f"*.pyc\n\n{BLOCK}"
    assert sorted(p.name for p in tmp_path.iterdir()) == [".gitignore", ".gitignore.tmp"]


def test_apply_new_file_gets_umask_default_mode(tmp_path: Path) -> None:
    umask = os.umask(0o022)
    try:
        apply_managed_block(tmp_path / ".gitignore", ENTRIES)
    finally:
        os.umask(umask)
    assert (tmp_path / ".gitignore").stat().st_mode & 0o777 == 0o644


def test_apply_leaves_no_temp_file_when_write_fails(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    with pytest.raises(UnicodeEncodeError):
        apply_managed_block(target, ["/\ud800"])  # lone surrogate cannot be encoded
    assert list(tmp_path.iterdir()) == []


def test_apply_preserves_file_mode(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("x\n")
    target.chmod(0o640)
    apply_managed_block(target, ENTRIES)
    assert target.stat().st_mode & 0o777 == 0o640
    assert not (tmp_path / ".gitignore.tmp").exists()


# --------------------------------------------------------------------------- #
# remove_managed_block / block_is_current
# --------------------------------------------------------------------------- #


def test_remove_round_trips_an_appended_block(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    original = "*.pyc\n.venv/\n"
    target.write_text(original)
    apply_managed_block(target, ENTRIES)
    assert remove_managed_block(target) is True
    assert target.read_text() == original


def test_remove_mid_file_block_keeps_surroundings(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(f"head\n\n{BLOCK}tail\n")
    assert remove_managed_block(target) is True
    assert target.read_text() == "head\n\ntail\n"


def test_remove_block_only_file_leaves_empty_file(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    apply_managed_block(target, ENTRIES)
    assert remove_managed_block(target) is True
    assert target.read_text() == ""


def test_remove_is_noop_without_file_or_block(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    assert remove_managed_block(target) is False
    assert not target.exists()
    target.write_text("*.pyc\n")
    assert remove_managed_block(target) is False
    assert target.read_text() == "*.pyc\n"


def test_remove_rejects_malformed_markers(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(f"{BLOCK_START}\n/x\n")
    with pytest.raises(ValueError, match="no end marker"):
        remove_managed_block(target)


def test_block_is_current(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    assert block_is_current(target, ENTRIES) is False  # missing file
    target.write_text("*.pyc\n")
    assert block_is_current(target, ENTRIES) is False  # no block
    apply_managed_block(target, ENTRIES)
    assert block_is_current(target, ENTRIES) is True
    assert block_is_current(target, [*ENTRIES, "/new.md"]) is False  # stale


def test_block_is_current_never_writes(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text("*.pyc\n")
    block_is_current(target, ENTRIES)
    assert target.read_text() == "*.pyc\n"


def test_block_is_current_raises_on_malformed_markers(tmp_path: Path) -> None:
    target = tmp_path / ".gitignore"
    target.write_text(f"{BLOCK_END}\n")
    with pytest.raises(ValueError, match="no start marker"):
        block_is_current(target, ENTRIES)
