"""Fixtures of the guard_config writer tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An empty repository: each repo input the writer reads is absent, so it keeps its default."""
    root = tmp_path / "repo"
    root.mkdir()
    return root
