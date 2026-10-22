"""Shared readers for the tests that pin a core skill's references (prU D47, D49).

Each ``tests/core_skills/<skill_snake>/test_references.py`` checks one skill's
``playbook.references`` entries and the rule ids its references name. The parsing
lives here once, keyed by skill id, so a fix to the cross-skill parser or the D49
cap reaches every skill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._attributions import MAPPING_SPECS_DIR
from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from collections.abc import Mapping

#: D49: an engine-written decision guide is at most 120 lines.
INTERNAL_GUIDE_MAX_LINES: Final = 120
#: Another skill's rules, named "python-coding's python-early-return and ...".
_CROSS_SKILL_RE: Final = re.compile(
    r"\b([a-z][a-z0-9-]*)'s ([a-z0-9-]+(?:(?:, | and )[a-z0-9-]+)*)"
)
_LIST_SEPARATOR_RE: Final = re.compile(r", | and ")
#: A mapping spec's rule-table row: ``| `rules/<id>.md[.j2]` | ...``.
_SPEC_RULE_PATH_RE: Final = re.compile(r"^\| `rules/([a-z0-9-]+)\.md(?:\.j2)?` \|", re.MULTILINE)


@dataclass(frozen=True)
class ReferenceEntry:
    """One ``playbook.references`` entry of a SKILL.md: its path, open-when line and gate."""

    path: str
    open_when: str
    applies_if: Mapping[str, object] | None


def references_block(skill: str) -> list[ReferenceEntry]:
    """``skill``'s SKILL.md ``playbook.references`` entries, in their listed order.

    Example: ``references_block("python-tooling")[0].path`` -> ``"references/check-failures.md"``.
    """
    text = (core_skill_root(skill) / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, _ = split_frontmatter(text)
    entries = frontmatter["playbook"].get("references", [])
    assert isinstance(entries, list), entries
    return [
        ReferenceEntry(
            path=str(entry["path"]),
            open_when=str(entry["open_when"]),
            applies_if=entry.get("applies_if"),
        )
        for entry in entries
    ]


def reference_text(skill: str, path: str) -> str:
    """The text of one of ``skill``'s files.

    Example: ``reference_text("python-tooling", "references/check-failures.md")``.
    """
    return (core_skill_root(skill) / path).read_text(encoding="utf-8")


def shipped_rule_ids(skill: str) -> set[str]:
    """Every rule id ``skill`` ships: its rule file names without their suffixes.

    Empty while the skill has no ``rules/`` directory (its lane has not landed).
    """
    rules_dir = core_skill_root(skill) / "rules"
    if not rules_dir.is_dir():
        return set()
    return {path.name.split(".")[0] for path in rules_dir.iterdir()}


def cross_skill_mentions(text: str) -> set[tuple[str, str]]:
    """``(skill, rule id)`` for each "<skill>'s <id>, <id> and <id>" naming a mapped skill.

    >>> sorted(cross_skill_mentions("python-coding's a-b and c-d"))
    [('python-coding', 'a-b'), ('python-coding', 'c-d')]
    """
    mentions: set[tuple[str, str]] = set()
    for match in _CROSS_SKILL_RE.finditer(text):
        skill, ids = match.groups()
        if (MAPPING_SPECS_DIR / f"mapping-{skill}.md").is_file():
            mentions.update((skill, rule_id) for rule_id in _LIST_SEPARATOR_RE.split(ids))
    return mentions


def known_rule_ids(skill: str) -> set[str]:
    """The rules ``skill`` ships, or its mapping spec plans while its lane has not landed."""
    spec = (MAPPING_SPECS_DIR / f"mapping-{skill}.md").read_text(encoding="utf-8")
    return set(_SPEC_RULE_PATH_RE.findall(spec)) | shipped_rule_ids(skill)
