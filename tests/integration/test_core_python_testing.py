"""The python-testing skill as the reference probe emits it (prU C-python-testing-refs).

The probe has pytest, so every reference the skill gates on ``has_framework: pytest``
is written into each native skill root and listed under "References and examples"
in the mapping's order (D47, D58(2)).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

#: The mapping's references, in its order.
_GUIDES: Final = ["choosing-a-test-double.md", "async-tests.md", "reviewing-tests.md"]


def _written_references(repo: Path, root: str) -> list[str]:
    """The reference guide names ``repo``'s python-testing skill holds under ``root``."""
    references = repo / root / "python-testing" / "references"
    return sorted(p.name for p in references.iterdir() if p.suffix == ".md")


def _listed_references(repo: Path) -> list[str]:
    """The reference file names the emitted SKILL.md lists under "References and examples"."""
    skill_md = repo / ".claude" / "skills" / "python-testing" / "SKILL.md"
    listing = skill_md.read_text(encoding="utf-8").partition("## References and examples")[2]
    return re.findall(r"\[references/([a-z0-9-]+\.md)\]", listing)


def test_reference_probe_writes_every_python_testing_guide(reference_probe_repo: Path) -> None:
    for root in NATIVE_SKILL_ROOTS:
        assert _written_references(reference_probe_repo, root) == sorted(_GUIDES), root


def test_reference_probe_lists_the_guides_in_mapping_order(reference_probe_repo: Path) -> None:
    assert _listed_references(reference_probe_repo) == _GUIDES
