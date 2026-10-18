"""Docs-consistency guard: SPEC documents scoped rules delivered as skill references (prS 6.9.1).

The skills-first release moved every scoped rule out of always-loaded context and into the
skill it names. The sections that describe each adapter's rule delivery must say so, or a
reader of §10 still expects scoped rules in ``AGENTS.md``. Each case names the SPEC section
by its heading and one phrase that carries the fact; the phrases are prose, so rewording a
sentence means editing its case here. Prose-only: these tests read markdown, never engine
behaviour.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.skill_document import render_member_reference
from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section

#: ``(start heading, end heading, phrase)``: the phrase the section between them must carry.
_DELIVERY_FACTS = (
    ("#### 6.2.5", "### 6.3 Skills", "`includes_rules` is how a prompt carries a scoped rule"),
    ("### 9.7 ", "## 10. Adapter subsystem", "| `skill_reference` |"),
    ("### 10.2 Continue adapter", "#### 10.2.1", "Rules: one file per rule, scoped ones included."),
    ("### 10.2 Continue adapter", "#### 10.2.1", "drops the `skill` key"),
    ("### 10.6 OpenCode adapter", "#### 10.6.1", "a scoped rule's `globs` gate nothing here"),
    ("### 10.8 Shared-skills adapter", "## 11. Overlay system", "**Member references.**"),
    ("### 20.10 ", "### 20.11 ", "v0.21 adds the rule field `skill`"),
)


@pytest.mark.parametrize(
    ("start", "end", "phrase"),
    _DELIVERY_FACTS,
    ids=[f"{start.strip('# ')}:{phrase[:24]}" for start, _, phrase in _DELIVERY_FACTS],
)
def test_spec_section_documents_skill_reference_delivery(start: str, end: str, phrase: str) -> None:
    assert phrase in _spec_section(start, end), f"SPEC {start.strip('# ')} must say {phrase!r}"


def test_spec_skill_reference_row_matches_the_rendered_rule_line() -> None:
    # The §9.7 row quotes the reference's first line; take its shape from the renderer, so
    # a change to the rule line fails here instead of leaving the row stale.
    row = _spec_section("| `skill_reference` |", "\n")
    with_globs = render_member_reference("<id>", ["g1", "g2"], "body").splitlines()[0]
    without_globs = render_member_reference("<id>", [], "body").splitlines()[0]
    assert f"``{with_globs}``" in row, f"§9.7 must quote {with_globs!r}"
    assert f"``{without_globs}``" in row, f"§9.7 must quote {without_globs!r}"
