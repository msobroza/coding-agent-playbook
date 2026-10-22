"""The sections a skill declares for its member rules (prU D17, D47, ADR 0005).

A skill's catalog-only ``playbook:`` block may hold an ordered ``sections:``
list. Each entry is a mapping with exactly ``id``, ``title``, ``impact``,
``summary`` and ``open_when``; each member rule names its entry in
``section:``, and its priority lies in the band of that section's impact
(CRITICAL 20-39, HIGH 40-59, MEDIUM 60-79, LOW 80-99). One module defines the
shape, so the parser here and ``playbook validate`` (``validation._sections``)
cannot disagree: :func:`section_list_problems` is what both read.

An empty ``sections: []`` declares no sections. A malformed ``sections:`` value
reads as no sections at all, so rendering never half-applies a broken list;
``playbook validate`` reports why it is malformed.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.artifacts.impact import Impact
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.skills.playbook_block import PLAYBOOK_BLOCK_KEY, playbook_block

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

#: The ``playbook:`` key that holds a skill's ordered sections.
SECTIONS_KEY: Final = "sections"
#: The ``playbook:`` key that lists a skill's references and examples (D47).
REFERENCES_KEY: Final = "references"
#: How findings name the list: ``'playbook.sections'``.
SECTIONS_FIELD: Final = f"'{PLAYBOOK_BLOCK_KEY}.{SECTIONS_KEY}'"
#: The keys every section entry declares, all required (D17, D47's ``open_when``).
SECTION_KEYS: Final = ("id", "title", "impact", "summary", "open_when")
#: A section title becomes an index heading and part of the Covers clause.
SECTION_TITLE_MAX_CHARS: Final = 40
#: Lowercase words joined by single hyphens, as rule ``section:`` values are.
_KEBAB_CASE: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


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
    """The raw ``playbook.sections`` value; ``None`` when absent or an empty list.

    Example: ``declared_sections_value(skill)`` -> ``[{"id": "mocking", ...}]``.
    """
    value = playbook_block(skill).get(SECTIONS_KEY)
    return None if isinstance(value, list) and not value else value


def skill_sections(skill: Skill) -> tuple[SkillSection, ...]:
    """The sections ``skill`` declares, in order; ``()`` when none or when malformed.

    Example: ``[s.id for s in skill_sections(python_testing)]`` -> ``["mocking", "fixtures"]``.
    """
    value = declared_sections_value(skill)
    if not isinstance(value, list) or section_list_problems(value):
        return ()
    return tuple(_section(entry) for entry in value)


def section_rank(sections: Sequence[SkillSection]) -> Callable[[str | None], int]:
    """Where a member's ``section`` id sorts among ``sections``: its declared index.

    ``None`` or an id no entry declares ranks ``len(sections)``: D42's engine-made
    "Other" section, listed last. The one place that decides what lands in Other.

    Example: ``section_rank(sections)("fixtures")`` -> ``1``;
    ``section_rank(sections)(None)`` -> ``len(sections)``.
    """
    ranks = {section.id: index for index, section in enumerate(sections)}
    other = len(ranks)

    def rank(section_id: str | None) -> int:
        return other if section_id is None else ranks.get(section_id, other)

    return rank


def section_list_problems(value: object) -> list[str]:
    """S1: why a declared ``sections`` value is no sound list; ``[]`` when it is.

    Entry problems come first; uniqueness is checked once every entry is sound.

    Example: ``section_list_problems("mocking")`` ->
    ``["'playbook.sections' must be a list of mappings with keys ..., got str 'mocking'"]``.
    """
    if not isinstance(value, list):
        return [
            f"{SECTIONS_FIELD} must be a list of mappings with keys "
            f"{', '.join(SECTION_KEYS)}, got {type(value).__name__} {value!r}"
        ]
    problems = [
        f"{_entry_label(index, entry)}: {problem}"
        for index, entry in enumerate(value, start=1)
        for problem in section_entry_problems(entry)
    ]
    if problems:
        return problems
    return [
        f"{SECTIONS_FIELD} declares section {section_id!r} more than once; ids are unique"
        for section_id in duplicate_section_ids(entry["id"] for entry in value)
    ]


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


def one_line_phrase_problem(key: str, value: object) -> str | None:
    """Why ``value`` of ``key`` is no non-empty one-line string; ``None`` when it is.

    Shared by section entries and ``playbook.references`` entries (D47's ``open_when``).

    Example: ``one_line_phrase_problem("open_when", "")`` ->
    ``"'open_when' must be a non-empty string, got str ''"``.
    """
    if value is None:
        return f"is missing {key!r}"
    if not isinstance(value, str) or not value.strip():
        return f"{key!r} must be a non-empty string, got {type(value).__name__} {value!r}"
    if "\n" in value.strip():
        return f"{key!r} must be one line, got {value!r}"
    return None


def _entry_label(index: int, entry: object) -> str:
    """``section 'mocking' (entry 1 of 'playbook.sections')``, or without the id."""
    where = f"entry {index} of {SECTIONS_FIELD}"
    section_id = entry.get("id") if isinstance(entry, Mapping) else None
    return (
        f"section {section_id!r} ({where})" if isinstance(section_id, str) else f"section {where}"
    )


def _value_problem(key: str, value: object) -> str | None:
    """Why one section value is malformed, or ``None``."""
    problem = one_line_phrase_problem(key, value)
    key_check = _KEY_CHECKS.get(key)
    if problem is not None or key_check is None:
        return problem
    return key_check(str(value))


def _id_problem(value: str) -> str | None:
    """A section id is kebab-case, as rule ``section:`` values are."""
    if _KEBAB_CASE.fullmatch(value):
        return None
    return f"'id' {value!r} must be kebab-case, e.g. 'error-handling'"


def _title_problem(value: str) -> str | None:
    """A section title fits an index heading."""
    length = len(value.strip())
    if length <= SECTION_TITLE_MAX_CHARS:
        return None
    return f"'title' {value!r} is {length} chars; keep it to at most {SECTION_TITLE_MAX_CHARS}"


def _impact_problem(value: str) -> str | None:
    """A section impact is one of :class:`Impact`."""
    if value in Impact.__members__:
        return None
    return f"'impact' {value!r} must be one of {', '.join(Impact)}"


#: The check a key adds once its value is a one-line string; summary and open_when add none.
_KEY_CHECKS: Final[Mapping[str, Callable[[str], str | None]]] = {
    "id": _id_problem,
    "title": _title_problem,
    "impact": _impact_problem,
}


def _section(entry: Mapping[str, str]) -> SkillSection:
    """One well-formed entry (``section_entry_problems`` is empty) as a :class:`SkillSection`."""
    return SkillSection(
        id=entry["id"],
        title=entry["title"].strip(),
        impact=Impact(entry["impact"]),
        summary=entry["summary"].strip(),
        open_when=entry["open_when"].strip(),
    )


def section_impacts(skills: Iterable[Skill], rules: Iterable[Rule]) -> dict[str, Impact]:
    """Each member rule's id mapped to its section's impact, for one render pass (D32).

    A rule is listed when its ``skill`` names one of ``skills`` and its
    ``section`` is one that skill declares. Always rules, members of sectionless
    skills and rules naming an undeclared section are absent: their titles stay
    as authored.

    Example: ``section_impacts([python_testing], rules)["mock-monkeypatch"]`` -> ``Impact.HIGH``.
    """
    impacts_by_skill = {
        skill_id_of(skill): {section.id: section.impact for section in skill_sections(skill)}
        for skill in skills
    }
    impacts: dict[str, Impact] = {}
    for rule in rules:
        frontmatter = rule.frontmatter
        impacts_by_section = impacts_by_skill.get(frontmatter.skill or "", {})
        impact = impacts_by_section.get(frontmatter.section or "")
        if impact is not None:
            impacts[frontmatter.id] = impact
    return impacts
