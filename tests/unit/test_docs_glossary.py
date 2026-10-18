"""Docs-consistency guard: CONTEXT.md is the project's only glossary (skills-first spec, D12).

SPEC §3 used to define the project's terms. Two glossaries drift apart, so §3 is now a
one-line pointer and ``CONTEXT.md`` at the repository root holds every definition. The
two facts only the old glossary carried now live where the spec needs them, §6.6.7 and
§10.2; ``test_docs_lifecycle_hooks_spec`` and ``test_docs_continue_hooks`` pin them. No
other part of the spec body may cite §3 for a fact, because §3 documents nothing now.
Prose-only: these tests read markdown, never engine behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section

_CONTEXT_MD = Path(__file__).resolve().parents[2] / "CONTEXT.md"

#: A citation of SPEC section 3: "§3" or "Section 3", but not "§3.1" or "§30".
_SECTION_3_CITATION = re.compile(r"(?:§|Section )3(?![0-9]|\.[0-9])")

#: Every term the spec's vocabulary note relies on; each needs a ``**Term**:`` entry.
_GLOSSARY_TERMS = (
    "Rule",
    "Always rule",
    "Scoped rule",
    "Member rule",
    "Skill",
    "Reference",
    "Prompt",
    "Hook",
    "Guardrail",
    "Skill nudge",
    "Eval task",
    "Always-loaded context",
    "Skill listing",
    "Context budget",
    "Skill root",
    "Engine",
    "Catalog",
    "Layer",
    "Core",
    "Bundled plugin",
    "Overlay",
    "Detector fact",
    "Detector",
    "Renderer",
    "Adapter",
    "Harness",
    "OpenCode plugin",
    "OpenCode agent",
    "Consumer repo",
    "Distilled content",
    "Vendored content",
)


def test_spec_glossary_is_a_pointer_to_context_md() -> None:
    section = _spec_section("## 3. Glossary", "## 4. Architecture overview")
    body = [line for line in section.splitlines()[1:] if line.strip()]
    assert len(body) == 1, f"SPEC §3 must be one non-empty line, found {len(body)}: {body}"
    assert "CONTEXT.md" in body[0], f"SPEC §3 must point at CONTEXT.md, found {body[0]!r}"


def test_spec_body_cites_no_fact_to_the_glossary_pointer() -> None:
    # A "(§3, ...)" citation sends the reader to a section that documents nothing: the
    # OpenCode plugin line of §2.3 did, until it named §6.6.7 and §10.6.2 instead. The
    # Changelog keeps history ("Section 3 (glossary)"), so only the body is read.
    body = _spec_section("## 1. Context", "*End of SPEC.md")
    stale = [line for line in body.splitlines() if _SECTION_3_CITATION.search(line)]
    assert not stale, f"SPEC §3 only points at CONTEXT.md; cite it or the owning section: {stale}"


@pytest.mark.parametrize("term", _GLOSSARY_TERMS)
def test_context_md_defines_term(term: str) -> None:
    entry = re.compile(rf"^\*\*{re.escape(term)}\*\*:", re.MULTILINE)
    text = _CONTEXT_MD.read_text(encoding="utf-8")
    assert entry.search(text), f"CONTEXT.md has no entry starting '**{term}**:'"
