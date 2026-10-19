"""What stops a write of sync output (``commands/_output_blockers.py``, SPEC §12.2).

Regressions: a dangling ``.claude/commands -> ../tools/cc``, a file (or a link
to one) at ``.claude/commands`` or ``.continue``, a directory at ``AGENTS.md``
and a socket there each made write-mode ``playbook sync`` crash with a
traceback; a FIFO there made it hang.
"""

from __future__ import annotations

import errno
import os
import socket
import sys
from pathlib import Path

import pytest

from coding_agent_playbook.commands._output_blockers import (
    OutputBlocker,
    blocker_in,
    report_blocker,
    write_blocker,
)
from coding_agent_playbook.generated_output.output_io import NotRegularFileError

needs_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".claude").mkdir(parents=True)
    (root / "README.md").write_text("r\n", encoding="utf-8")
    return root


def _failed(code: int, path: Path, other: str | os.PathLike[str] | None = None) -> OSError:
    return OSError(code, os.strerror(code), str(path), None, other)


@needs_symlinks
def test_mkdir_through_a_dangling_link_names_the_link(repo: Path) -> None:
    link = repo / ".claude" / "commands"
    link.symlink_to("../tools/cc", target_is_directory=True)

    found = blocker_in(_failed(errno.EEXIST, link), repo)

    assert found is not None
    assert (found.path, found.shown) == (link, ".claude/commands")
    assert found.problem == (
        ".claude/commands is a dangling symbolic link: its target ../tools/cc does not exist"
    )
    assert found.remedy == "Create the link's target, or re-point or remove the link"
    assert blocker_in(_failed(errno.ENOENT, link / "x.md"), repo) == found


def test_mkdir_over_a_file_names_the_file(repo: Path) -> None:
    commands = repo / ".claude" / "commands"
    commands.write_text("mine\n", encoding="utf-8")

    found = blocker_in(_failed(errno.EEXIST, commands), repo)

    assert found is not None
    assert found.path == commands
    assert found.problem == (
        ".claude/commands is not a directory, but sync writes generated files inside it"
    )
    assert found.remedy == "Move or rename it (sync never deletes it)"


def test_a_file_on_the_way_names_the_file(repo: Path) -> None:
    (repo / ".continue").write_text("mine\n", encoding="utf-8")

    found = blocker_in(_failed(errno.ENOTDIR, repo / ".continue" / "rules"), repo)

    assert found is not None
    assert found.problem.startswith(".continue is not a directory")


@needs_symlinks
def test_a_link_to_a_file_asks_to_re_point_the_link(repo: Path) -> None:
    commands = repo / ".claude" / "commands"
    commands.symlink_to("../README.md")

    found = blocker_in(_failed(errno.EEXIST, commands), repo)

    assert found is not None
    assert found.problem == (
        ".claude/commands is a symbolic link to ../README.md, which is not a directory, "
        "but sync writes generated files inside it"
    )
    assert found.remedy == "Re-point or remove the link"


def test_writing_over_a_directory_names_the_directory(repo: Path) -> None:
    (repo / "AGENTS.md").mkdir()

    found = blocker_in(_failed(errno.EISDIR, repo / "AGENTS.md"), repo)

    assert found is not None
    assert (
        found.problem == "AGENTS.md is a directory, but sync writes a generated file at that path"
    )


@needs_symlinks
def test_a_link_to_a_directory_at_a_file_path_asks_to_re_point_the_link(repo: Path) -> None:
    (repo / "docs").mkdir()
    (repo / "AGENTS.md").symlink_to("docs", target_is_directory=True)

    failed = blocker_in(_failed(errno.EISDIR, repo / "AGENTS.md"), repo)
    predicted = write_blocker(repo / "AGENTS.md", repo)

    assert failed is not None
    assert failed.problem == (
        "AGENTS.md is a symbolic link to docs, which is a directory, "
        "but sync writes a generated file at that path"
    )
    assert failed.remedy == "Re-point or remove the link"
    assert predicted == failed


@needs_symlinks
def test_a_fifo_refused_by_the_output_writer_is_named(repo: Path) -> None:
    os.mkfifo(repo / "AGENTS.md")
    refused = NotRegularFileError(errno.ENXIO, "not a regular file", str(repo / "AGENTS.md"))

    failed = blocker_in(refused, repo)
    predicted = write_blocker(repo / "AGENTS.md", repo)

    assert failed is not None
    assert failed.problem == (
        "AGENTS.md is a FIFO, not a regular file, but sync writes a generated file at that path"
    )
    assert failed.remedy == "Move or rename it (sync never deletes it)"
    assert predicted == failed


@needs_symlinks
def test_a_raw_socket_error_is_named_and_a_link_to_a_fifo_asks_to_re_point_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    sock = socket.socket(socket.AF_UNIX)
    sock.bind("AGENTS.md")  # a short relative name: AF_UNIX paths are capped
    os.mkfifo(repo / "pipe")
    (repo / "CLAUDE.md").symlink_to("pipe")
    try:
        on_socket = blocker_in(_failed(errno.EOPNOTSUPP, repo / "AGENTS.md"), repo)
        linked = write_blocker(repo / "CLAUDE.md", repo)
    finally:
        sock.close()

    assert on_socket is not None
    assert on_socket.problem.startswith("AGENTS.md is a socket, not a regular file")
    assert linked is not None
    assert linked.problem == (
        "CLAUDE.md is a symbolic link to pipe, which is a FIFO, not a regular file, "
        "but sync writes a generated file at that path"
    )
    assert linked.remedy == "Re-point or remove the link"


@pytest.mark.parametrize("code", [errno.EACCES, errno.ENOSPC, errno.EROFS])
def test_an_errno_no_blocker_causes_is_never_blamed_on_one(repo: Path, code: int) -> None:
    (repo / ".continue").write_text("mine\n", encoding="utf-8")
    assert blocker_in(_failed(code, repo / ".continue" / "rules"), repo) is None


def test_an_existing_file_explains_only_a_failed_mkdir(repo: Path) -> None:
    """EEXIST is ``mkdir``'s; ENOENT/EISDIR on an existing file at the path is no blocker."""
    readme = repo / "README.md"
    assert blocker_in(_failed(errno.ENOENT, readme), repo) is None
    assert blocker_in(_failed(errno.EISDIR, readme), repo) is None


def test_errors_naming_no_usable_path_inside_the_repo_have_no_blocker(
    repo: Path, tmp_path: Path
) -> None:
    (tmp_path / "outside").write_text("x\n", encoding="utf-8")
    commands = repo / ".claude" / "commands"
    commands.write_text("mine\n", encoding="utf-8")

    assert blocker_in(OSError(errno.EEXIST, "File exists"), repo) is None  # no filename
    assert blocker_in(FileExistsError(errno.EEXIST, "x", os.fsencode(commands)), repo) is None
    assert blocker_in(_failed(errno.EEXIST, tmp_path / "outside" / "x"), repo) is None
    assert blocker_in(_failed(errno.EEXIST, repo, None), repo) is None  # the root itself
    # a PathLike filename2 is read too
    assert blocker_in(_failed(errno.EEXIST, tmp_path / "elsewhere", commands), repo) is not None


@needs_symlinks
def test_nothing_at_or_above_the_repo_root_counts(tmp_path: Path) -> None:
    (tmp_path / "gone").symlink_to(tmp_path / "missing", target_is_directory=True)
    found = blocker_in(_failed(errno.ENOENT, tmp_path / "gone" / "x.md"), tmp_path / "gone")
    assert found is None


def test_a_relative_spelling_of_the_repo_root_is_mapped(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / ".continue").write_text("mine\n", encoding="utf-8")
    monkeypatch.chdir(repo.parent)

    found = blocker_in(_failed(errno.ENOTDIR, Path("repo/.continue/rules")), Path("repo"))

    assert found is not None
    assert found.path == Path.cwd() / "repo" / ".continue"


@needs_symlinks
def test_check_predicts_a_blocker_on_the_way_or_a_directory_at_the_file(repo: Path) -> None:
    (repo / ".continue").write_text("mine\n", encoding="utf-8")
    (repo / ".claude" / "commands").symlink_to("../tools/cc", target_is_directory=True)
    (repo / "AGENTS.md").mkdir()

    on_way = write_blocker(repo / ".continue" / "rules" / "x.md", repo)
    dangling = write_blocker(repo / ".claude" / "commands" / "x.md", repo)
    directory = write_blocker(repo / "AGENTS.md", repo)

    assert on_way is not None and on_way.path == repo / ".continue"
    assert dangling is not None and dangling.path == repo / ".claude" / "commands"
    assert directory is not None and directory.path == repo / "AGENTS.md"
    assert write_blocker(repo / "README.md", repo) is None
    assert write_blocker(repo / "docs" / "new.md", repo) is None  # sync creates docs/


@needs_symlinks
def test_check_calls_a_dangling_file_link_a_blocker_only_when_the_write_fails(repo: Path) -> None:
    (repo / "docs").mkdir()
    (repo / "AGENTS.md").symlink_to("gone/AGENTS.md")
    (repo / "CLAUDE.md").symlink_to("docs/CLAUDE.md")  # the write creates docs/CLAUDE.md
    (repo / "LOOP.md").symlink_to("LOOP.md")

    assert write_blocker(repo / "AGENTS.md", repo) is not None
    assert write_blocker(repo / "CLAUDE.md", repo) is None
    assert write_blocker(repo / "LOOP.md", repo) is not None
    # an atomic os.replace (the co-owned .claude/settings.json) replaces the link
    assert write_blocker(repo / "AGENTS.md", repo, replaces_path=True) is None


@needs_symlinks
def test_a_dangling_link_says_whether_it_loops_or_reaches_another_dangling_link(
    repo: Path,
) -> None:
    (repo / "loop").symlink_to("loop")
    (repo / "hop").symlink_to("missing", target_is_directory=True)
    (repo / "first").symlink_to("hop", target_is_directory=True)

    loop = blocker_in(_failed(errno.ELOOP, repo / "loop" / "x.md"), repo)
    chain = blocker_in(_failed(errno.EEXIST, repo / "first"), repo)

    assert loop is not None
    assert (
        loop.problem == "loop is a dangling symbolic link: its target loop is a symbolic link loop"
    )
    assert chain is not None
    assert chain.problem.endswith("its target hop is itself a dangling symbolic link")


def _blocker(repo: Path) -> OutputBlocker:
    return OutputBlocker(repo / "AGENTS.md", "AGENTS.md", "is a directory, but …", "Move it")


def test_write_mode_report_goes_to_stderr(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert report_blocker(_blocker(repo), check=False) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "error: AGENTS.md is a directory, but …",
        "error: playbook sync stopped before finishing.",
        "error: Move it, then re-run 'playbook sync'.",
    ]


def test_check_report_goes_to_stdout(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert report_blocker(_blocker(repo), check=True) == 1
    # "Cannot verify <path>: …", the shape every check-mode refusal shares (the
    # stop gate's sync_check_findings reads the path from it)
    assert capsys.readouterr().out.splitlines() == [
        "Cannot verify AGENTS.md: it is a directory, but ….",
        "Move it, then re-run 'playbook sync --check'.",
    ]
