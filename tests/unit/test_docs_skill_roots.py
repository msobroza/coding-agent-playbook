"""Docs-consistency guard: the shared skill root and the ``playbook init`` default (SPEC v0.21).

The ``shared_skills`` adapter writes ``.agents/skills/<id>/`` and keeps the pre-v0.21
``shared_skills/`` as a retired location; ``playbook init`` leaves ``continue`` opt-in
and no longer offers ``codex`` (specs/prS-skills-context.md section 5). Prose-only:
these tests read markdown, never engine behaviour, except that every documented init
default must equal the code's ``DEFAULT_ADAPTERS``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from coding_agent_playbook.commands._init_adapters import DEFAULT_ADAPTERS
from tests._docs import user_docs
from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section
from tests.unit.test_docs_readme_hooks import _section

_ROOT = Path(__file__).resolve().parents[2]
_INIT_DEFAULT_MARKER = "# the init default"
_ADAPTERS_LINE = re.compile(
    r"^\s*(adapters_enabled = \[[^\]]*\])\s*" + re.escape(_INIT_DEFAULT_MARKER)
)
_SKILL_ROOTS = (".claude/skills/<id>/", ".opencode/skills/<id>/", ".agents/skills/<id>/")


def _marked_init_defaults(text: str) -> list[list[str]]:
    """Every ``adapters_enabled = [...]`` line marked ``# the init default``, parsed."""
    found: list[list[str]] = []
    for line in text.splitlines():
        match = _ADAPTERS_LINE.match(line)
        if match is not None:
            found.append(tomllib.loads(match.group(1))["adapters_enabled"])
    return found


def test_spec_10_8_names_the_shared_root_and_its_retired_location() -> None:
    section = _spec_section("### 10.8 Shared-skills adapter", "## 11. Overlay system")
    assert "`.agents/skills/<id>/`" in section
    assert "`shared_skills/`" in section
    assert "Retired location" in section
    assert "No loose file in a skill root" in section
    assert 'retired_output_locations = ("shared_skills/",)' in section


def test_documented_init_default_matches_the_code() -> None:
    spec = (_ROOT / "SPEC.md").read_text(encoding="utf-8")
    documented = [*_marked_init_defaults(spec), *_marked_init_defaults(user_docs())]
    assert len(documented) >= 3, documented  # SPEC §11.5, docs config + superpowers
    assert all(adapters == list(DEFAULT_ADAPTERS) for adapters in documented), documented


def test_readme_skills_section_names_every_native_root() -> None:
    section = _section("## Skills: one source, every Agent-Skills root")
    for root in _SKILL_ROOTS:
        assert root in section, root


def test_readme_promises_no_report_for_an_edited_untracked_leftover() -> None:
    """Regression (PR #68 review): under ``commit = false`` sync keeps an edited,
    untracked ``shared_skills/`` copy without a notice (spec P1-8: no new notice),
    so the README must say which kept files are reported, as MIGRATION does."""
    section = _section("## Skills: one source, every Agent-Skills root")
    bullet = next(item for item in section.split("\n- ") if "`shared_skills/`" in item)
    prose = " ".join(bullet.split())  # undo the markdown line wrapping
    assert "keeps, and reports" not in prose
    assert "under `commit = true` every kept file" in prose
    assert "untracked copy stays owned and gitignored without a notice" in prose


def test_spec_init_transcript_offers_no_codex_choice() -> None:
    section = _spec_section("### 12.1 `playbook init`", "### 12.2")
    assert "Codex CLI (AGENTS.md only)" not in section
    assert "◯ Continue (opt-in)" in section
