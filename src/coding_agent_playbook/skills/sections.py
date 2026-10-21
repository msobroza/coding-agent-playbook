"""The sections a skill declares for its member rules (prU D17, D47, ADR 0005).

A skill's catalog-only ``playbook:`` block may hold an ordered ``sections:``
list. Each entry is a mapping with exactly ``id``, ``title``, ``impact``,
``summary`` and ``open_when``; each member rule names its entry in
``section:``, and its priority lies in the band of that section's impact
(CRITICAL 20-39, HIGH 40-59, MEDIUM 60-79, LOW 80-99). One module defines the
shape, so the parser here and ``playbook validate`` (``validation._sections``)
cannot disagree: :func:`section_entry_problems` is what both read.

A malformed ``sections:`` value reads as no sections at all, so rendering never
half-applies a broken list; ``playbook validate`` reports why it is malformed.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.skills.document import PLAYBOOK_BLOCK_KEY

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.artifacts.skill import Skill

#: The ``playbook:`` key that holds a skill's ordered sections.
SECTIONS_KEY: Final = "sections"
#: The keys every section entry declares, all required (D17, D47's ``open_when``).
SECTION_KEYS: Final = ("id", "title", "impact", "summary", "open_when")
#: A section title becomes an index heading and part of the Covers clause.
SECTION_TITLE_MAX_CHARS: Final = 40
#: Lowercase words joined by single hyphens, as rule ``section:`` values are.
_KEBAB_CASE: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class Impact(StrEnum):
    """A section's impact, declared from most to least important (D17).

    Example: ``Impact("HIGH").band`` -> ``range(40, 60)``.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def band(self) -> range:
        """The priorities a member of a section of this impact may take."""
        return IMPACT_BANDS[self]

    @property
    def rank(self) -> int:
        """0 for CRITICAL up to 3 for LOW: sections are declared in rank order."""
        return list(Impact).index(self)


#: Priority = impact band + rank within the section (D17).
IMPACT_BANDS: Final[Mapping[Impact, range]] = {
    Impact.CRITICAL: range(20, 40),
    Impact.HIGH: range(40, 60),
    Impact.MEDIUM: range(60, 80),
    Impact.LOW: range(80, 100),
}


@dataclass(frozen=True)
class SkillSection:
    """One entry of a skill's ``playbook.sections`` list.

    Example::

        SkillSection("mocking", "Mocking", Impact.CRITICAL, "Fakes at the boundary.",
                     "Replacing a collaborator in a test.")
    """

    id: str
    title: str
    impact: Impact
    summary: str
    open_when: str


def declared_sections_value(skill: Skill) -> object | None:
    """The raw ``playbook.sections`` value, or ``None`` when the skill declares none.

    Example: ``declared_sections_value(skill)`` -> ``[{"id": "mocking", ...}]``.
    """
    block = skill.frontmatter.get(PLAYBOOK_BLOCK_KEY)
    if not isinstance(block, Mapping):
        return None
    return block.get(SECTIONS_KEY)


def skill_sections(skill: Skill) -> tuple[SkillSection, ...]:
    """The sections ``skill`` declares, in order; ``()`` when none or when malformed.

    Example: ``[s.id for s in skill_sections(python_testing)]`` -> ``["mocking", "fixtures"]``.
    """
    value = declared_sections_value(skill)
    if not isinstance(value, list) or not value:
        return ()
    if any(section_entry_problems(entry) for entry in value):
        return ()
    sections = tuple(_section(entry) for entry in value)
    if duplicate_section_ids(section.id for section in sections):
        return ()
    return sections


def duplicate_section_ids(section_ids: Iterable[str]) -> list[str]:
    """The ids declared more than once, sorted; ``[]`` when every id is unique.

    Example: ``duplicate_section_ids(["mocking", "fixtures", "mocking"])`` -> ``["mocking"]``.
    """
    counts = Counter(section_ids)
    return sorted(section_id for section_id, count in counts.items() if count > 1)


def section_entry_problems(entry: object) -> list[str]:
    """Why ``entry`` is no well-formed section, one phrase per problem; ``[]`` when it is.

    Each phrase names the offending value and the expected shape. Order and
    uniqueness across entries are list-level checks, left to the caller.

    Example: ``section_entry_problems({"id": "Mocking", ...})`` ->
    ``["'id' 'Mocking' must be kebab-case, e.g. 'error-handling'"]``.
    """
    if not isinstance(entry, Mapping):
        return [
            f"must be a mapping with keys {', '.join(SECTION_KEYS)}, "
            f"got {type(entry).__name__} {entry!r}"
        ]
    problems = [
        f"has unknown key {key!r}; allowed keys: {', '.join(SECTION_KEYS)}"
        for key in sorted(str(key) for key in entry if key not in SECTION_KEYS)
    ]
    for key in SECTION_KEYS:
        problem = _value_problem(key, entry.get(key))
        if problem is not None:
            problems.append(problem)
    return problems


def _value_problem(key: str, value: object) -> str | None:
    """Why one section value is malformed, or ``None``."""
    if value is None:
        return f"is missing {key!r}"
    if not isinstance(value, str) or not value.strip():
        return f"{key!r} must be a non-empty string, got {type(value).__name__} {value!r}"
    if "\n" in value.strip():
        return f"{key!r} must be one line, got {value!r}"
    if key == "id" and not _KEBAB_CASE.fullmatch(value):
        return f"'id' {value!r} must be kebab-case, e.g. 'error-handling'"
    if key == "title" and len(value.strip()) > SECTION_TITLE_MAX_CHARS:
        return (
            f"'title' {value!r} is {len(value.strip())} chars; keep it to at most "
            f"{SECTION_TITLE_MAX_CHARS}"
        )
    if key == "impact" and value not in Impact.__members__:
        return f"'impact' {value!r} must be one of {', '.join(Impact)}"
    return None


def _section(entry: Mapping[str, str]) -> SkillSection:
    """One well-formed entry (``section_entry_problems`` is empty) as a :class:`SkillSection`."""
    return SkillSection(
        id=entry["id"],
        title=entry["title"].strip(),
        impact=Impact(entry["impact"]),
        summary=entry["summary"].strip(),
        open_when=entry["open_when"].strip(),
    )
