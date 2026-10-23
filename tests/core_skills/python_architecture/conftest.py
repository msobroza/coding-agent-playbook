"""Fixtures for the ``layer_map.py`` tests: the script loaded once, and an in-process run."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from tests.core_skills.python_architecture._scripts import LAYER_MAP, Outcome, load_script

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType


@pytest.fixture(scope="session")
def layer_map() -> ModuleType:
    """``layer_map.py`` loaded as a module."""
    return load_script(LAYER_MAP, "python_architecture_layer_map")


@pytest.fixture(scope="session")
def layer_model(layer_map: ModuleType) -> ModuleType:
    """``_layer_model.py``, as ``layer_map.py`` imported it."""
    return sys.modules["_layer_model"]


@pytest.fixture
def run_map(
    layer_map: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Outcome]:
    """Call ``main(args)`` in-process with ``tmp_path`` as the working directory."""
    monkeypatch.chdir(tmp_path)

    def run(*args: str) -> Outcome:
        try:
            code = int(layer_map.main(list(args)))
        except SystemExit as exit_:
            code = int(exit_.code or 0)
        captured = capsys.readouterr()
        return Outcome(code, captured.out, captured.err)

    return run
