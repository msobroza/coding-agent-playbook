"""Reading one core skill's references and their ``playbook.references`` entries (prU D47, D49).

Each ``tests/core_skills/<skill_snake>/test_references.py`` pins its own mapping
(paths, gates, routed rule ids) and reads the skill through these helpers, so the
reading lives in one place:

    >>> from tests._catalog import core_skill_root
    >>> root = core_skill_root("python-coding")
    >>> "python-async" in skill_rule_ids(root)
    True
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, NotRequired, TypedDict

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter

if TYPE_CHECKING:
    from pathlib import Path

#: D49: an engine-written decision guide is at most 120 lines.
INTERNAL_GUIDE_MAX_LINES: Final = 120


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
