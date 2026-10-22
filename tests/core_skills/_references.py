"""Reading one core skill's references and their ``playbook.references`` entries (prU D47, D49).

Each ``tests/core_skills/<skill_snake>/test_references.py`` pins its own mapping
(paths, gates, routed rule ids) and reads the skill through these helpers, so the
reading lives in one place, along with the "<skill>'s <id>, <id> and <id>"
pointers a reference makes into other skills:

    >>> from tests._catalog import core_skill_root
    >>> root = core_skill_root("python-coding")
    >>> "python-async" in skill_rule_ids(root)
    True
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final, NotRequired, TypedDict

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._attributions import MAPPING_SPECS_DIR
from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

#: D49: an engine-written decision guide is at most 120 lines.
INTERNAL_GUIDE_MAX_LINES: Final = 120
#: Another skill's rules, named "python-architecture's arch-unit-of-work and ...".
_CROSS_SKILL_RE: Final = re.compile(
    r"\b([a-z][a-z0-9-]*)'s `?([a-z0-9-]+`?(?:(?:, | and )`?[a-z0-9-]+`?)*)"
)
_LIST_SEPARATOR_RE: Final = re.compile(r", | and ")
#: A backticked rule-id-shaped token: ``design-strategy`` in backticks.
_BACKTICKED_ID_RE: Final = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")
#: A mapping spec's rule-table row: ``| `rules/<id>.md[.j2]` | ...``.
_SPEC_RULE_PATH_RE: Final = re.compile(r"^\| `rules/([a-z0-9-]+)\.md(?:\.j2)?` \|", re.MULTILINE)


class ReferenceEntry(TypedDict):
    """One ``playbook.references`` entry: ``{"path": "references/x.md", "open_when": "..."}``."""

    path: str
    open_when: str
    applies_if: NotRequired[dict[str, list[str]]]


def skill_md_parts(skill_root: Path) -> tuple[dict[str, Any], str]:
    """The skill's SKILL.md split into its frontmatter mapping and its body."""
    return split_frontmatter((skill_root / "SKILL.md").read_text(encoding="utf-8"))


def references_block(skill_root: Path) -> list[ReferenceEntry]:
    """The SKILL.md ``playbook.references`` entries under ``references/``, as YAML gives them.

    Entries for ``examples/`` share the list but are no references, so they are left out.
    """
    frontmatter, _ = skill_md_parts(skill_root)
    entries = frontmatter["playbook"].get("references", [])
    assert isinstance(entries, list), entries
    return [entry for entry in entries if str(entry["path"]).startswith("references/")]


def reference_text(skill_root: Path, path: str) -> str:
    """The text of one of the skill's files: ``reference_text(root, "references/x.md")``."""
    return (skill_root / path).read_text(encoding="utf-8")


def skill_rule_ids(skill_root: Path) -> set[str]:
    """Every rule id of the skill: the rule file names without their suffixes."""
    return {path.name.split(".")[0] for path in (skill_root / "rules").iterdir()}


def guide_line_count(skill_root: Path, path: str) -> int:
    """The number of lines of a guide, to hold against ``INTERNAL_GUIDE_MAX_LINES``."""
    return reference_text(skill_root, path).count("\n")


def cross_skill_mentions(text: str) -> set[tuple[str, str]]:
    """``(skill, rule id)`` for each "<skill>'s <id>, <id> and <id>" naming a mapped skill.

    >>> sorted(cross_skill_mentions("python-architecture's a-b and `c-d`"))
    [('python-architecture', 'a-b'), ('python-architecture', 'c-d')]
    """
    mentions: set[tuple[str, str]] = set()
    for match in _CROSS_SKILL_RE.finditer(text):
        skill, ids = match.groups()
        if (MAPPING_SPECS_DIR / f"mapping-{skill}.md").is_file():
            mentions.update(
                (skill, rule_id.strip("`")) for rule_id in _LIST_SEPARATOR_RE.split(ids)
            )
    return mentions


def known_rule_ids(skill: str) -> set[str]:
    """The rules ``skill`` ships, or its mapping spec plans while its lane has not landed."""
    spec = (MAPPING_SPECS_DIR / f"mapping-{skill}.md").read_text(encoding="utf-8")
    planned = set(_SPEC_RULE_PATH_RE.findall(spec))
    root = core_skill_root(skill)
    if not (root / "rules").is_dir():
        return planned
    return planned | skill_rule_ids(root)


def backticked_ids(text: str) -> set[str]:
    """Every rule-id-shaped token ``text`` writes in backticks."""
    return set(_BACKTICKED_ID_RE.findall(text))


def names_a_rule(text: str, rule_ids: set[str]) -> bool:
    """True when ``text`` names one of ``rule_ids`` in backticks, or another skill's rule."""
    return bool(backticked_ids(text) & rule_ids or cross_skill_mentions(text))
