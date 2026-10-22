"""Shared readers for the tests of a core skill's references (prU D47, D49).

Each ``tests/core_skills/<skill_snake>/test_references.py`` checks its skill's
``playbook.references`` entries and the rule ids its references name; these
helpers read the SKILL.md block, the rules a skill ships or plans, and the
"<skill>'s <id>, <id> and <id>" pointers into other skills.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._attributions import MAPPING_SPECS_DIR
from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

#: Another skill's rules, named "python-architecture's arch-unit-of-work and ...".
_CROSS_SKILL_RE: Final = re.compile(
    r"\b([a-z][a-z0-9-]*)'s `?([a-z0-9-]+`?(?:(?:, | and )`?[a-z0-9-]+`?)*)"
)
_LIST_SEPARATOR_RE: Final = re.compile(r", | and ")
#: A backticked rule-id-shaped token: ``design-strategy`` in backticks.
_BACKTICKED_ID_RE: Final = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")
#: A mapping spec's rule-table row: ``| `rules/<id>.md[.j2]` | ...``.
_SPEC_RULE_PATH_RE: Final = re.compile(r"^\| `rules/([a-z0-9-]+)\.md(?:\.j2)?` \|", re.MULTILINE)


def references_block(skill_root: Path) -> list[dict[str, Any]]:
    """The SKILL.md ``playbook.references`` entries under ``references/``, as YAML gives them.

    Example entries (``examples/<app>``) share the list but are left out.
    """
    frontmatter, _ = split_frontmatter((skill_root / "SKILL.md").read_text(encoding="utf-8"))
    entries = frontmatter["playbook"].get("references", [])
    assert isinstance(entries, list), entries
    return [entry for entry in entries if str(entry["path"]).startswith("references/")]


def reference_text(skill_root: Path, path: str) -> str:
    """The text of one of a skill's files, ``path`` relative to its root."""
    return (skill_root / path).read_text(encoding="utf-8")


def shipped_rule_ids(skill_root: Path) -> set[str]:
    """Every rule id a skill ships: its rule file names without their suffixes."""
    return {path.name.split(".")[0] for path in (skill_root / "rules").iterdir()}


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
    return planned | shipped_rule_ids(root)


def backticked_ids(text: str) -> set[str]:
    """Every rule-id-shaped token ``text`` writes in backticks."""
    return set(_BACKTICKED_ID_RE.findall(text))


def names_a_rule(text: str, rule_ids: set[str]) -> bool:
    """True when ``text`` names one of ``rule_ids`` in backticks, or another skill's rule."""
    return bool(backticked_ids(text) & rule_ids or cross_skill_mentions(text))
