"""The python-testing skill as the reference probe emits it (prU C-python-testing-refs).

The probe has pytest, so every reference the skill gates on ``has_framework: pytest``
is written into each native skill root and listed under "References and examples"
in the mapping's order (D47, D58(2)).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from tests.core_skills._references import listed_references, written_references
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

#: The mapping's references, in its order.
_SKILL: Final = "python-testing"
_GUIDES: Final = ["choosing-a-test-double.md", "async-tests.md", "reviewing-tests.md"]


def test_reference_probe_writes_every_python_testing_guide(reference_probe_repo: Path) -> None:
    for root in NATIVE_SKILL_ROOTS:
        assert written_references(reference_probe_repo, root, _SKILL) == sorted(_GUIDES), root


def test_reference_probe_lists_the_guides_in_mapping_order(reference_probe_repo: Path) -> None:
    assert listed_references(reference_probe_repo, _SKILL) == _GUIDES
