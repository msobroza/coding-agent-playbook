"""Docs-consistency guard: SPEC.md makes no Continue hook claim (prK §P5).

Continue ships no wired lifecycle-hook mechanism (the ``cn`` CLI's hook code is
unreachable in every published bundle; the IDE ``config.yaml`` has no hooks
key), and ``adapters/base.py`` has no HTTP-hook API. The SPEC must say Continue
gets guardrail text only, so no Continue hook track starts from a false premise.
The statement lives in §10.2: CONTEXT.md is the only glossary, and SPEC §3 is a
pointer to it. Prose-only: these tests read markdown, never engine behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SPEC = Path(__file__).resolve().parents[2] / "SPEC.md"

#: Refuted claims the SPEC carried before §P5.
_REFUTED_CLAIMS = (
    "supported by Claude Code and Continue CLI",
    "Continue CLI HTTP hook type",
    "supported by the adapter API",
)


def _spec_section(start_heading: str, end_heading: str) -> str:
    """The SPEC text from ``start_heading`` up to ``end_heading``."""
    text = _SPEC.read_text(encoding="utf-8")
    start = text.index(start_heading)
    return text[start : text.index(end_heading, start)]


@pytest.mark.parametrize("claim", _REFUTED_CLAIMS)
def test_spec_carries_no_refuted_hook_claim(claim: str) -> None:
    assert claim not in _SPEC.read_text(encoding="utf-8")


def test_continue_section_states_no_wired_hook_mechanism() -> None:
    section = _spec_section("### 10.2 Continue adapter", "### 10.3 Claude Code adapter")
    assert "Continue ships no wired hook mechanism" in section
    assert "guardrail text only" in section


def test_continue_adapter_section_states_no_hooks() -> None:
    section = _spec_section("### 10.2 Continue adapter", "### 10.3 Claude Code adapter")
    assert "Hooks: none — guardrail text only." in section


def test_air_gapped_section_rejects_http_hook_handlers() -> None:
    section = _spec_section("### 17.1 Air-gapped operation", "### 17.2 Dependency allowlist")
    assert "not expressible in the canonical `Hook` schema" in section
