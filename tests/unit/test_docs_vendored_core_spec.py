"""Docs-consistency guard: SPEC records vendored core guidance and the prU budgets (prU D-02).

ADR 0004 retired the fresh-text policy: core vendors and adapts the python-best-practices and
python-clean-architecture text, ships each source's license byte-identical in the skill's
``references/`` (D19) and maps every upstream file in ``catalog/core/ATTRIBUTIONS.md`` (D31).
D18 as amended by D54 and D59 raised the description budgets. The SPEC parts this ticket owns
(the 0.21 version line, §11.5, §16.3, §16.7 and the v0.21 changelog) must say so and must no
longer carry the old wording. The rest of the body (§5.1, §6.3) belongs to D-01's pin test.
Prose-only: these tests read markdown, never engine behaviour.
"""

from __future__ import annotations

import re

import pytest

from tests._budget_probe import (
    CORE_DESCRIPTION_MAX_CHARS,
    CORE_DESCRIPTIONS_MAX_CHARS,
    DOMINO_CORE_DESCRIPTIONS_MAX_CHARS,
    DOMINO_LISTING_MAX_CHARS,
    LISTING_MAX_CHARS,
)
from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section

#: ``(start heading, end heading)`` of every SPEC part this ticket rewrote.
_OWNED_PARTS = (
    ("- **0.21** — ", "\n- **0.20** — "),
    ("### 11.5 Bundled opt-in plugins", "### 11.6 "),
    ("### 16.3 Integration tests", "### 16.4 CI"),
    ("### 16.7 Bundled plugin tests", "\n## 17. "),
)
#: The wording the fresh-text policy and the old budgets left behind (D-02 acceptance).
_RETIRED_WORDING = re.compile(
    r"\bwritten fresh\b|\bdistilled, not vendored\b|\b2,000\b|\b6,000\b|\bfour skills\b"
)
_LICENSE_COPIES = (
    "references/LICENSE.python-best-practices",
    "references/LICENSE.python-clean-architecture",
)
#: D4's three new skills, then the four of D52/D53 and D70's authoring skill.
_NEW_SKILLS = (
    "web-application",
    "design-patterns",
    "python-architecture",
    "python-documentation",
    "domino-apps",
    "domino-jobs",
    "domino-agents",
    "playbook-creator",
)
_RETIRED_IDS = (
    "python-performance-idioms",
    "python-classes-and-protocols",
    "ml-dtypes-and-typing",
    "ml-reproducibility-and-testing",
)
_CHANGELOG_LABEL = "- **Vendored core guidance ("


def _changelog_entry() -> str:
    """The v0.21 changelog bullet this ticket adds, one line."""
    return _spec_section(_CHANGELOG_LABEL, "\n")


@pytest.mark.parametrize(("start", "end"), _OWNED_PARTS, ids=[s[:20] for s, _ in _OWNED_PARTS])
def test_owned_spec_part_drops_the_fresh_text_and_old_budget_wording(start: str, end: str) -> None:
    hits = _RETIRED_WORDING.findall(_spec_section(start, end))
    assert not hits, f"SPEC {start.strip('#- *')!r} still says {hits}"


def test_spec_bundled_plugins_section_says_core_vendors_too() -> None:
    section = _spec_section("### 11.5 Bundled opt-in plugins", "#### 11.5.1")
    for phrase in ("ADR 0004", "`catalog/core/ATTRIBUTIONS.md`", *_LICENSE_COPIES):
        assert phrase in section, f"SPEC 11.5 must name {phrase!r}"


@pytest.mark.parametrize(
    ("start", "end"),
    [("### 16.3 Integration tests", "### 16.4 CI"), ("### 16.7 Bundled plugin tests", "\n## 17. ")],
    ids=["16.3", "16.7"],
)
def test_spec_test_sections_quote_the_budget_constants(start: str, end: str) -> None:
    section = _spec_section(start, end)
    assert f"{LISTING_MAX_CHARS:,}" in section, f"SPEC {start} must quote {LISTING_MAX_CHARS:,}"


def test_spec_reference_probe_quotes_every_description_budget() -> None:
    section = _spec_section("### 16.3 Integration tests", "### 16.4 CI")
    for cap in (
        CORE_DESCRIPTION_MAX_CHARS,
        CORE_DESCRIPTIONS_MAX_CHARS,
        DOMINO_CORE_DESCRIPTIONS_MAX_CHARS,
        DOMINO_LISTING_MAX_CHARS,
    ):
        assert f"{cap:,}" in section, f"SPEC 16.3 must quote the {cap:,}-character budget"


def test_spec_reference_probe_names_the_provenance_gates() -> None:
    section = _spec_section("### 16.3 Integration tests", "### 16.4 CI")
    for gate in ("test_core_attributions.py", "test_core_license_copies.py"):
        assert gate in section, f"SPEC 16.3 must name {gate}"


@pytest.mark.parametrize(
    "phrase",
    [
        "ADR 0004",
        *_LICENSE_COPIES,
        *(f"`{skill}`" for skill in _NEW_SKILLS),
        *(f"`{rule_id}`" for rule_id in _RETIRED_IDS),
        "`rules/`",
        "sections",
        "`has_dependency`",
        f"{CORE_DESCRIPTIONS_MAX_CHARS:,}",
        f"{LISTING_MAX_CHARS:,}",
    ],
)
def test_v021_changelog_records_vendored_core(phrase: str) -> None:
    assert phrase in _changelog_entry(), f"the v0.21 changelog entry must name {phrase!r}"


def test_v021_changelog_entry_sits_in_the_v021_section() -> None:
    assert _CHANGELOG_LABEL in _spec_section("### v0.21 ", "### v0.20 ")
