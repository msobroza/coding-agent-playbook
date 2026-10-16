"""``playbook check-notebooks``: notebook-output-hygiene's off-workstation twin (specs/prK-hook-pack.md §E.3).

The real command runs in-process on notebooks written under a temporary
repository; without PATHS it lists the tracked ones through a stateless
``SafeGit`` (``real_git`` builds the repository under ``hermetic_git_env``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable

ADVICE: Final = "Outputs may embed data rows; strip outputs before committing."
OUTPUT: Final = {"output_type": "stream", "name": "stdout", "text": ["3\n"]}


def _notebook(outputs: list[dict[str, Any]]) -> str:
    cells = [{"id": "c1", "cell_type": "code", "source": "1 + 2", "outputs": outputs}]
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


@pytest.fixture
def root(tmp_path: Path) -> Path:
    built = Path(os.path.realpath(tmp_path)) / "consumer"
    (built / "nb").mkdir(parents=True)
    (built / "nb" / "dirty.ipynb").write_text(_notebook([OUTPUT]), encoding="utf-8")
    (built / "nb" / "clean.ipynb").write_text(_notebook([]), encoding="utf-8")
    return built


def _check(root: Path, *paths: str) -> int:
    return main(["check-notebooks", *paths, "--repo-root", str(root)])


def test_notebook_with_outputs_exits_1(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _check(root, "nb/dirty.ipynb", "nb/clean.ipynb") == 1

    assert capsys.readouterr().out.splitlines() == [
        f'"nb/dirty.ipynb": cell c1 keeps outputs. {ADVICE}',
        "check-notebooks: 1 of 2 notebooks need their outputs stripped",
    ]


def test_clean_notebook_exits_0(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _check(root, "nb/clean.ipynb") == 0
    assert capsys.readouterr().out.strip() == "check-notebooks: 1 notebooks clean"


def test_invalid_notebook_exits_1_and_missing_path_exits_2(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / "nb" / "broken.ipynb").write_text("{not json", encoding="utf-8")

    assert _check(root, "nb/broken.ipynb") == 1
    assert _check(root, "nb/absent.ipynb") == 2
    captured = capsys.readouterr()
    assert '"nb/broken.ipynb": not a valid notebook' in captured.out
    assert "no such notebook: nb/absent.ipynb" in captured.err


def test_without_paths_checks_every_tracked_notebook(
    root: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    real_git("init", "-q", "-b", "main", cwd=root)
    real_git("add", "nb/dirty.ipynb", "nb/clean.ipynb", cwd=root)
    (root / "untracked.ipynb").write_text(_notebook([OUTPUT]), encoding="utf-8")

    assert _check(root) == 1
    assert capsys.readouterr().out.splitlines()[-1] == (
        "check-notebooks: 1 of 2 notebooks need their outputs stripped"
    )
