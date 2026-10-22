"""Fixtures for the design-patterns script tests: each script loaded once by path."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from tests.core_skills.design_patterns._scripts import DETECT_SMELLS, LCOM4_CLUSTERS, load_script

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture(scope="session")
def detect() -> ModuleType:
    """``detect_smells.py`` loaded as a module."""
    return load_script(DETECT_SMELLS, "design_patterns_detect_smells")


@pytest.fixture(scope="session")
def smell_model(detect: ModuleType) -> ModuleType:
    """``_smell_model.py``, as ``detect_smells.py`` imported it."""
    return sys.modules["_smell_model"]


@pytest.fixture(scope="session")
def smell_detectors(detect: ModuleType) -> ModuleType:
    """``_smell_detectors.py``, as ``detect_smells.py`` imported it."""
    return sys.modules["_smell_detectors"]


@pytest.fixture(scope="session")
def lcom4() -> ModuleType:
    """``lcom4_clusters.py`` loaded as a module."""
    return load_script(LCOM4_CLUSTERS, "design_patterns_lcom4_clusters")
