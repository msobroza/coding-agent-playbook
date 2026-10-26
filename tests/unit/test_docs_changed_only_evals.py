"""Docs guard for changed-only release evals (spec #329, ticket 01).

ADR 0013 amends ADR 0012: release metrics no longer score every eval sample on every
release, only the samples whose inputs digest changed plus every edition control, with
the rest carried forward. The record, the pointer from ADR 0012 and the glossary terms
are what a maintainer reads before touching ``prepare --eval``. Prose-only: these tests
read markdown, never engine behaviour.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from tests._catalog import REPO_ROOT
from tests.unit.test_docs_editions import _adr_status

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_ADR_DIR = REPO_ROOT / "docs" / "adr"
_CONTEXT_MD = REPO_ROOT / "CONTEXT.md"


def _changed_only_adr() -> Path:
    """The one ADR whose file name records the changed-only release evals decision.

    Example: ``_changed_only_adr().name[:4]`` is that ADR's number, ``"0013"``.
    """
    matches = sorted(_ADR_DIR.glob("*-release-evals-rerun-only-*.md"))
    assert len(matches) == 1, f"expected one docs/adr/*-release-evals-rerun-only-*.md: {matches}"
    return matches[0]


def _section(text: str, heading: str) -> str:
    """The body of one ``## `` section of a markdown text, heading excluded.

    Example: ``_section(adr_text, "Consequences")`` starts after ``"## Consequences"``.
    """
    start = text.index(f"\n## {heading}\n") + len(heading) + 5
    end = text.find("\n## ", start)
    return text[start : end if end != -1 else len(text)]


def _glossary_entry(term: str) -> str:
    """The ``**Term**:`` paragraph of CONTEXT.md, up to the next blank line.

    Example: ``_glossary_entry("Edition")`` starts with ``"**Edition**:"``.
    """
    text = _CONTEXT_MD.read_text(encoding="utf-8")
    match = re.search(rf"^\*\*{re.escape(term)}\*\*:.*?(?=\n\n|\Z)", text, re.M | re.S)
    assert match, f"CONTEXT.md has no entry starting '**{term}**:'"
    return match.group(0)


def test_changed_only_adr_is_number_0013_and_accepted() -> None:
    adr = _changed_only_adr()
    assert adr.name.startswith("0013-"), f"{adr.name} must be ADR 0013"
    assert _adr_status(adr) == "accepted", f"{adr.name} must be accepted"


def test_changed_only_adr_says_it_amends_adr_0012() -> None:
    text = _changed_only_adr().read_text(encoding="utf-8")
    assert "ADR 0012" in text, "ADR 0013 must name the ADR it amends"
    assert "amends" in text.lower(), "ADR 0013 must say it amends ADR 0012"


@pytest.mark.parametrize(
    "token",
    ["inputs digest", "setup digest", "edition control", "carried", "isolat", "--full"],
)
def test_changed_only_adr_decision_names(token: str) -> None:
    text = _changed_only_adr().read_text(encoding="utf-8").lower()
    decision = text.split("\n## ", 1)[0]
    assert token in decision, f"ADR 0013's decision must mention {token!r}"


@pytest.mark.parametrize("rejected", ["manifest", "maximum carry age", "harness version"], ids=str)
def test_changed_only_adr_lists_rejected_alternative(rejected: str) -> None:
    options = _section(_changed_only_adr().read_text(encoding="utf-8"), "Considered Options")
    assert rejected in options.lower(), f"Considered Options must reject {rejected!r}"


def test_changed_only_adr_has_consequences() -> None:
    consequences = _section(_changed_only_adr().read_text(encoding="utf-8"), "Consequences")
    assert consequences.count("\n- ") >= 3, "ADR 0013 must list its consequences"


def test_adr_0012_points_to_adr_0013_after_its_release_metrics_paragraph() -> None:
    text = next(_ADR_DIR.glob("0012-*.md")).read_text(encoding="utf-8")
    release_metrics = text.index("**Release metrics**")
    pointer = text.find("Amended by ADR 0013")
    assert pointer > release_metrics, "ADR 0012 must say 'Amended by ADR 0013' after it"
    assert pointer < text.index("## Considered Options"), "the pointer belongs to the decision"


@pytest.mark.parametrize("term", ["Inputs digest", "Setup digest", "Carried entry"])
def test_context_md_defines_changed_only_term(term: str) -> None:
    assert _glossary_entry(term)


def test_release_metrics_entry_no_longer_scores_every_sample() -> None:
    entry = _glossary_entry("Release metrics")
    assert "every eval sample" not in entry, f"'Release metrics' still scores all: {entry!r}"
    assert "carried entr" in entry.lower(), (
        f"'Release metrics' must mention carried entries: {entry!r}"
    )


def test_release_metrics_entry_reruns_edition_controls_not_every_pinned_sample() -> None:
    entry = _glossary_entry("Release metrics").lower()
    assert "edition control" in entry, f"'Release metrics' must name edition controls: {entry!r}"
    assert "every pinned sample" not in entry, f"only edition controls rerun: {entry!r}"
    assert "new" in entry, f"'Release metrics' must rerun new samples: {entry!r}"


def test_inputs_digest_entry_reruns_a_sample_missing_from_the_previous_file() -> None:
    entry = _glossary_entry("Inputs digest").lower()
    assert "missing" in entry, f"'Inputs digest' must rerun a missing entry: {entry!r}"


def test_carried_entry_excludes_edition_controls() -> None:
    entry = _glossary_entry("Carried entry").lower()
    assert "edition control" in entry, f"'Carried entry' must exclude edition controls: {entry!r}"
