"""The whole inventory of the ``mattpocock_skills`` bundled plugin, pinned (T10).

specs/prT-mattpocock-skills.md section 7.8. The other gates parametrise over the
skills present, so a lost skill directory or a stale label would pass them; this
file pins the 26 D9 ids, the scripts, the rule, the root entries, the user-invoked
set, the finished docs and every name a skill points at.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.validation.link_check import _CODE_SPAN_RE
from tests.plugins.mattpocock_skills._expectations import (
    FINAL_IDS,
    LOAD_RE,
    PLUGIN_ROOT,
    RULE_FILE_NAME,
    SKILLS_ROOT,
    USER_INVOKED_IDS,
    plugin_files,
    present_skill_ids,
    rule_files,
    split_skill,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_ROOT_ENTRIES: Final = [
    "ATTRIBUTIONS.md",
    "LICENSE",
    "README.md",
    "framework.toml",
    "rules",
    "skills",
]
_SCRIPTS: Final = [
    "diagnosing-bugs/scripts/hitl_loop_template.py",
    "wizard/scripts/wizard_template.py",
]
#: A code span whose whole text is one slash word, such as `` `/tdd` ``.
_SLASH_WORD_RE: Final = re.compile(r"/([A-Za-z0-9_-]+)")
#: The two non-label slash spans kept verbatim from upstream (section 7.8):
#: (path relative to the plugin root, span text).
_NON_LABEL_SPANS: Final = frozenset(
    {
        ("skills/improve-codebase-architecture/SKILL.md", "/tmp"),
        ("skills/throwaway-prototype/references/UI.md", "/settings"),
    }
)
#: An ask-matt router label (A.T09 test 1).
_ROUTER_LABEL_RE: Final = re.compile(r"`/([a-z0-9]+(?:-[a-z0-9]+)*)`")
_SIBLING_PATH_RE: Final = re.compile(r"\.\./([a-z0-9]+(?:-[a-z0-9]+)*)/")
_BULLET_RE: Final = re.compile(r"\n\s*- ")
_ROUTER_FILES: Final = ("SKILL.md", "references/PHASE-BOUNDARIES.md")
#: The superpowers skills each overlapping plugin skill must be named with (D33).
_SUPERPOWERS_PAIRS: Final = (
    ("tdd", "test-driven-development"),
    ("diagnosing-bugs", "systematic-debugging"),
    ("writing-for-agents", "writing-skills"),
    ("two-axis-review", "requesting-code-review", "receiving-code-review"),
    ("grilling", "brainstorming"),
)


def _rel(path: Path) -> str:
    return path.relative_to(PLUGIN_ROOT).as_posix()


def _text_files() -> list[Path]:
    """Markdown under ``skills/`` and ``rules/``: the files whose labels must be live."""
    return [
        p for p in plugin_files() if p.suffix == ".md" and _rel(p).startswith(("skills/", "rules/"))
    ]


def _readme() -> str:
    return (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")


def test_skills_are_exactly_the_26_final_ids() -> None:
    assert present_skill_ids() == sorted(FINAL_IDS)


def test_scripts_rule_and_root_entries_are_pinned() -> None:
    scripts = sorted(
        p.relative_to(SKILLS_ROOT).as_posix() for p in plugin_files() if "scripts" in p.parts
    )
    assert scripts == _SCRIPTS
    assert [p.name for p in rule_files()] == [RULE_FILE_NAME]
    assert sorted(p.name for p in PLUGIN_ROOT.iterdir()) == _ROOT_ENTRIES


def test_user_invoked_skills_are_exactly_the_15() -> None:
    marked = {i for i in present_skill_ids() if split_skill(i)[0].get("disable-model-invocation")}
    assert marked == USER_INVOKED_IDS


def test_no_placeholder_left_anywhere() -> None:
    left = [_rel(p) for p in plugin_files() if b"_Filled by" in p.read_bytes()]
    assert left == [], "a `_Filled by T0x._` placeholder survived"


def _slash_spans() -> set[tuple[str, str]]:
    """(file, span text) of every code span that is exactly `` `/<word>` ``."""
    spans: set[tuple[str, str]] = set()
    for path in _text_files():
        for match in _CODE_SPAN_RE.finditer(path.read_text(encoding="utf-8")):
            if _SLASH_WORD_RE.fullmatch(match.group(2)):
                spans.add((_rel(path), match.group(2)))
    return spans


def test_every_slash_span_names_a_final_id() -> None:
    stale = {s for s in _slash_spans() - _NON_LABEL_SPANS if s[1][1:] not in FINAL_IDS}
    assert stale == set(), "a `/label` that names no shipped skill (renamed or dropped)"


def test_the_non_label_slash_spans_still_occur() -> None:
    # Checked both ways: an exemption whose span is gone must be removed from the set.
    assert _slash_spans() >= _NON_LABEL_SPANS


def test_every_load_target_is_present() -> None:
    targets = {
        m.group(1) for p in _text_files() for m in LOAD_RE.finditer(p.read_text(encoding="utf-8"))
    }
    assert targets, "the plugin loads no skill at all: LOAD_RE is broken"
    assert targets - set(present_skill_ids()) == set()


def test_every_router_label_is_present() -> None:
    router = SKILLS_ROOT / "ask-matt"
    labels = {
        label
        for name in _ROUTER_FILES
        for label in _ROUTER_LABEL_RE.findall((router / name).read_text(encoding="utf-8"))
    }
    assert labels == set(present_skill_ids()) - {"ask-matt"}


def test_every_sibling_path_names_a_present_skill() -> None:
    owners = {
        m for p in _text_files() for m in _SIBLING_PATH_RE.findall(p.read_text(encoding="utf-8"))
    }
    assert owners - set(present_skill_ids()) == set()


@pytest.mark.parametrize("skill_id", sorted(USER_INVOKED_IDS))
def test_readme_names_each_user_invoked_skill(skill_id: str) -> None:
    assert f"`/{skill_id}`" in _readme()


def test_readme_names_the_scratch_directory() -> None:
    assert "`.scratch/`" in _readme()


@pytest.mark.parametrize("pair", _SUPERPOWERS_PAIRS, ids=lambda pair: pair[0])
def test_readme_names_each_superpowers_pair_together(pair: tuple[str, ...]) -> None:
    section = _readme().split("\n## Coexistence\n", 1)[1].split("\n## ", 1)[0]
    bullets = _BULLET_RE.split(section)  # nested bullets too, so each pair is its own item
    assert any(all(f"`{name}`" in bullet for name in pair) for bullet in bullets), pair


# --- ATTRIBUTIONS.md global sections state the finished facts (T10 fix round 1) ---


def _attributions_global(heading: str) -> str:
    """One global ``## <heading>`` section of ``ATTRIBUTIONS.md``, whitespace folded."""
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return " ".join(section.split())


def test_restructure_does_not_limit_moved_file_edits_to_links_and_glossary() -> None:
    # HTML-REPORT.md, issue-tracker-local.md, CREDITS.md and others carry
    # decision-forced rewording too, each listed in its skill's own section.
    section = _attributions_global("Restructure")
    assert "except the link and glossary edits" not in section
    assert "except the edits listed in the skill's own section" in section


def test_rendering_does_not_call_the_synced_skill_md_byte_identical() -> None:
    # Sync re-dumps the frontmatter and inserts the sentinel (see test_sync.py).
    section = _attributions_global("Rendering per adapter")
    assert "byte-identical copies of `SKILL.md`" not in section
    assert "byte-identical copies of `references/` and `scripts/`" in section
    assert "the three native roots hold the same bytes" in section


def test_frontmatter_names_exactly_the_two_changed_descriptions() -> None:
    section = _attributions_global("Frontmatter")
    assert "(expected:" not in section
    assert "Descriptions are verbatim except two" in section
    for skill_id in ("wizard", "domain-modeling"):
        assert f"{skill_id}'s" in section, skill_id
