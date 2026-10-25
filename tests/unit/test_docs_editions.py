"""Docs guard for the editions and releases decision (spec #281, ticket 01).

The decision record that replaced per-repo prompt sets, the superseded status of ADR 0008
and the contributor guide's "Editions and releases" section are what a catalog author
reads before editing graded text. Prose-only: these tests read markdown, never engine
behaviour.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from tests._catalog import CATALOG_ROOT, REPO_ROOT

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_ADR_DIR = REPO_ROOT / "docs" / "adr"
_STATUS_LINE = re.compile(r"^status: (.+)$", re.MULTILINE)


def _adr_status(path: Path) -> str:
    """The ``status:`` value of an ADR's frontmatter.

    Example: ``_adr_status(_ADR_DIR / "0010-skill-only-...md")`` returns ``"accepted"``.
    """
    match = _STATUS_LINE.search(path.read_text(encoding="utf-8"))
    assert match, f"{path.name} has no 'status:' line in its frontmatter"
    return match.group(1).strip()


def _editions_adr() -> Path:
    """The one ADR whose file name records the editions decision.

    Example: ``_editions_adr().name[:4]`` is that ADR's number, such as ``"0012"``.
    """
    matches = sorted(_ADR_DIR.glob("*-editions*.md"))
    assert len(matches) == 1, f"expected one docs/adr/*-editions*.md, found {matches}"
    return matches[0]


def _contributor_section(heading: str) -> str:
    """The text of one ``## `` section of catalog/README.md, heading included.

    Example: ``_contributor_section("Run the gate")`` starts with ``"## Run the gate"``.
    """
    text = (CATALOG_ROOT / "README.md").read_text(encoding="utf-8")
    start = text.index(f"## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_editions_adr_is_accepted_and_supersedes_adr_0008() -> None:
    adr = _editions_adr()
    assert _adr_status(adr) == "accepted", f"{adr.name} must be accepted"
    assert "0008" in adr.read_text(encoding="utf-8"), f"{adr.name} must name ADR 0008"


def test_adr_0008_is_superseded_by_the_editions_adr() -> None:
    adr_0008 = next(_ADR_DIR.glob("0008-*.md"))
    number = _editions_adr().name[:4]
    assert _adr_status(adr_0008) == f"superseded by ADR {number}"


@pytest.mark.parametrize(
    "token",
    ["`catalog/editions/`", "`catalog/releases/`", "`feat`", "`fix`", "`!`", "current text"],
)
def test_contributor_guide_documents_editions_and_releases(token: str) -> None:
    section = _contributor_section("Editions and releases")
    assert token in section, f"'Editions and releases' must mention {token}"
