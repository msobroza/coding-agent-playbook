"""The guard twins' shared run skeleton (``commands/twins/_runner.py``, specs/prT-package-layout.md B.9).

``run_twin`` resolves the repo root, runs a twin's scan, prints its output and
returns its exit code; an expected error becomes one ``error:`` line on stderr
and exit 2 (specs/prK-hook-pack.md §E.4).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands.twins._runner import TWIN_ERRORS, TwinOutcome, run_twin
from coding_agent_playbook.hook_runtime.git import GitError

if TYPE_CHECKING:
    from collections.abc import Callable


def test_prints_the_output_and_returns_the_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    code = run_twin(None, lambda root: TwinOutcome(1, "a.py:1: finding\nscan: 1 blocking"))

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "a.py:1: finding\nscan: 1 blocking\n"
    assert captured.err == ""


def test_empty_output_prints_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_twin(None, lambda root: TwinOutcome(0, "")) == 0
    assert capsys.readouterr().out == ""


def _recording(seen: list[Path]) -> Callable[[Path], TwinOutcome]:
    def scan(root: Path) -> TwinOutcome:
        seen.append(root)
        return TwinOutcome(0, "")

    return scan


def test_scan_receives_the_resolved_repo_root(tmp_path: Path) -> None:
    seen: list[Path] = []
    (tmp_path / "sub").mkdir()

    run_twin(str(tmp_path / "sub" / ".."), _recording(seen))

    assert seen == [Path(os.path.realpath(tmp_path))]


def test_without_a_repo_root_the_scan_receives_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []
    monkeypatch.chdir(tmp_path)

    run_twin(None, _recording(seen))

    assert seen == [Path(os.path.realpath(tmp_path))]


@pytest.mark.parametrize("error", [GitError("git diff failed"), ValueError("git diff failed")])
def test_a_twin_error_is_one_error_line_and_exit_2(
    error: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    def scan(root: Path) -> TwinOutcome:
        raise error

    code = run_twin(None, scan)

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == "error: git diff failed\n"


def test_an_error_outside_errors_propagates() -> None:
    def scan(root: Path) -> TwinOutcome:
        raise OSError("disk gone")

    with pytest.raises(OSError, match="disk gone"):
        run_twin(None, scan)


def test_errors_widens_what_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    def scan(root: Path) -> TwinOutcome:
        raise FileNotFoundError("COMMIT_EDITMSG: no such file")

    assert run_twin(None, scan, errors=(*TWIN_ERRORS, OSError)) == 2
    assert capsys.readouterr().err == "error: COMMIT_EDITMSG: no such file\n"
