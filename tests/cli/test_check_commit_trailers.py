"""``playbook check-commit-trailers``: the trailer rows' commit-msg and CI twin (specs/prK-hook-pack.md §E.4).

The command runs in-process against a fixture repository whose committed config
sets ``[hooks.git-commit-push-policy-guard]`` rows (``[hooks]`` itself is off:
the twin applies the rows whatever the agent hooks do). Range mode commits for
real under ``hermetic_git_env`` (through ``real_git``). Exit codes: 0 nothing
broken (always, with no rows), 1 a ``CP4xx`` row broken, 2 unreadable input.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable

CONFIG: Final = """\
schema_version = 1
adapters_enabled = ["claude_code"]
overlays_enabled = []

[project]
name = "consumer"
kind = "python-library"

[engine]
version = "0.1.0a0"
{tables}"""
ROWS: Final = """
[hooks]
enabled = false

[hooks.git-commit-push-policy-guard]
forbid_trailers = ["Co-Authored-By"]
required_trailers = { Refs = "^[A-Z]+-\\\\d+$" }
"""
GOOD: Final = "feat: add parser\n\nRefs: AB-12\n"
COAUTHORED: Final = "feat: add parser\n\nRefs: AB-12\nCo-Authored-By: Bot <bot@x.test>\n"


def _repo(tmp_path: Path, tables: str = ROWS) -> Path:
    root = Path(os.path.realpath(tmp_path)) / "consumer"
    root.mkdir()
    (root / ".coding-agent-playbook.toml").write_text(CONFIG.format(tables=tables), "utf-8")
    return root


def _check(root: Path, *args: str) -> int:
    return main(["check-commit-trailers", *args, "--repo-root", str(root)])


def _msgfile(root: Path, text: str) -> str:
    path = root / "COMMIT_EDITMSG"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_msgfile_forbidden_trailer_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)

    code = _check(root, _msgfile(root, COAUTHORED))

    path = root / "COMMIT_EDITMSG"
    assert code == 1
    assert capsys.readouterr().out.splitlines() == [
        f"{path}: CP401 forbidden trailer Co-Authored-By"
    ]


def test_clean_message_exits_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)

    assert _check(root, _msgfile(root, GOOD)) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("tables", ["", "\n[hooks]\nenabled = true\n"])
def test_empty_rows_exit_0(tmp_path: Path, tables: str) -> None:
    root = _repo(tmp_path, tables)

    assert _check(root, _msgfile(root, COAUTHORED)) == 0


def test_no_config_exits_0(tmp_path: Path) -> None:
    root = Path(os.path.realpath(tmp_path))

    assert _check(root, _msgfile(root, COAUTHORED)) == 0


def test_reports_only_cp4xx_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    nonconventional = "Added stuff!!\n\nwip, no ticket\n"

    assert _check(root, _msgfile(root, nonconventional)) == 1

    lines = capsys.readouterr().out.splitlines()
    assert [line.split(": ", 1)[1] for line in lines] == ["CP403 missing required trailer Refs"]


def test_msgfile_and_range_are_exclusive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)

    assert _check(root) == 2
    assert _check(root, "msg", "--range", "A..B") == 2
    assert "not both" in capsys.readouterr().err


def test_unreadable_msgfile_exits_2(tmp_path: Path) -> None:
    assert _check(_repo(tmp_path), str(tmp_path / "missing")) == 2


def test_range_mode_checks_each_commit(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    real_git("init", "-q", "-b", "main", cwd=root)
    real_git("add", "-A", cwd=root)
    real_git("commit", "-q", "-m", "chore: init\n\nRefs: AB-1", cwd=root)
    base = real_git("rev-parse", "HEAD", cwd=root)
    for message in (GOOD, COAUTHORED):
        real_git("commit", "-q", "--allow-empty", "-m", message, cwd=root)
    bad = real_git("rev-parse", "HEAD", cwd=root)

    code = _check(root, "--range", f"{base}..HEAD")

    assert code == 1
    assert capsys.readouterr().out.splitlines() == [
        f"{bad[:12]}: CP401 forbidden trailer Co-Authored-By"
    ]
