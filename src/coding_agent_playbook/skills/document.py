"""Every string the skill composition adds (specs/prS-skills-context.md section 6.4.4).

A skill with member rules (ADR 0001) is emitted with text the engine generates:
a composed description (capability sentence, a "Covers ..." clause naming the
active members, then "Use when ..."), a ``## Rules`` index appended to the
authored body, one ``rules/<rule-id>.md`` file per member (ADR 0005), and the
``## Where guidance lives`` section of the always-loaded files. One module
renders all of it, so the skill roots and the two composite files cannot drift.

The authoring data lives in the skill's catalog-only ``playbook:`` block
(``use_when``, ``files``), which the emitted frontmatter never carries (E1).
Members are taken in the order given: ``compose_skills`` sorts them by
``(priority, id)``, so the highest-priority members come first everywhere.

A skill that declares ``playbook.sections`` (prU D17) is composed differently:
its Covers clause names its active sections, never truncated, and its body
gets the sectioned navigation of ``skills._rules_index``; a sectionless skill
renders exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.artifacts.member_reference import RULES_DIR, member_reference_path
from coding_agent_playbook.skills._rules_index import (
    HOW_TO_USE_BLOCK,
    RULES_HEADING,
    RULES_LEAD,
    active_sections,
    one_line,
    references_section,
    section_label,
    sectioned_navigation,
)
from coding_agent_playbook.skills.capabilities import CAPABILITIES_KEY
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.skills.playbook_block import PLAYBOOK_BLOCK_KEY, playbook_block
from coding_agent_playbook.skills.sections import skill_sections

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.artifacts.member_reference import MemberReference
    from coding_agent_playbook.artifacts.skill import Skill

#: The composed description's ceiling (D4), held by construction (D21).
DESCRIPTION_MAX_CHARS: Final = 300

#: Frontmatter keys only the engine reads, never written to an emitted ``SKILL.md``.
_ENGINE_OWNED_KEYS: Final = frozenset({PLAYBOOK_BLOCK_KEY, CAPABILITIES_KEY})

_SENTENCE_ENDINGS: Final = (".", "!", "?")

_WHERE_HEADING: Final = "## Where guidance lives"
_WHERE_LEAD: Final = (
    "Detailed conventions live in skills. Before you edit one of these files, load its "
    "skill and open the rules its index lists."
)
_WHERE_LINT_LINE: Final = (
    f"Lint feedback names a rule id; that rule's file in the skill's {RULES_DIR}/ has the fix."
)
#: The separator that ends every section of the composite files (rendering/formats.py rule sections).
_SECTION_END: Final = "---"


class DescriptionOverflowError(ValueError):
    """A composed description over :data:`DESCRIPTION_MAX_CHARS` even with one Covers name.

    Carries the shortest text the fallback could emit (``text``) and its
    ``length``. ``playbook validate``'s V11 rules it out before a sync writes.

    Example::

        except DescriptionOverflowError as exc:
            print(exc.length, exc.text)
    """

    def __init__(self, text: str, *, sectioned: bool = False) -> None:
        self.text = text
        self.length = len(text)
        covers, names = (
            ("with the Covers clause naming its sections", "the section titles")
            if sectioned
            else ("even when the Covers clause names one member", "the member names")
        )
        super().__init__(
            f"the composed description is {self.length} chars, over the "
            f"{DESCRIPTION_MAX_CHARS}-char limit {covers}: "
            f"{text!r}; shorten 'description', 'playbook.use_when' or {names}"
        )


@dataclass(frozen=True)
class SkillCatalogBlock:
    """A skill's ``playbook:`` block: the ``Use when`` condition and the Where phrase.

    Example: ``SkillCatalogBlock(use_when="editing Python code", files="Any Python file")``.
    """

    use_when: str | None
    files: str | None


@dataclass(frozen=True)
class WhereEntry:
    """One line of ``## Where guidance lives``: a file-kind phrase and its skill.

    Example: ``WhereEntry("python-testing", "Test files and conftest.py")``.
    """

    skill_id: str
    files: str


def skill_catalog_block(skill: Skill) -> SkillCatalogBlock:
    """The ``playbook`` block of ``skill``; absent or malformed keys read as ``None``.

    Validation reports a malformed block (V7-V10); here a non-mapping block, a
    non-string value and a blank one all read as absent, and values are stripped.

    Example: ``skill_catalog_block(python_coding).files`` -> ``"Any Python file"``.
    """
    block = playbook_block(skill)
    return SkillCatalogBlock(
        use_when=_catalog_phrase(block.get("use_when")),
        files=_catalog_phrase(block.get("files")),
    )


def covers_clause(member_names: Sequence[str], shown: int) -> str:
    """``Covers <a>, <b>.`` naming the first ``shown`` names; ``and N more`` for the rest (D21).

    A trailing ``.`` of each name is dropped, so the clause ends with exactly one.

    Example: ``covers_clause(["Typing", "Docstrings", "Idioms"], 1)`` ->
    ``"Covers Typing and 2 more."``
    """
    if not 1 <= shown <= len(member_names):
        raise ValueError(
            f"covers_clause names 1 to {len(member_names)} of {list(member_names)!r}, "
            f"got shown={shown}"
        )
    listed = ", ".join(_label(name) for name in member_names[:shown])
    hidden = len(member_names) - shown
    return f"Covers {listed}." if hidden == 0 else f"Covers {listed} and {hidden} more."


def compose_description(description: str, member_names: Sequence[str], use_when: str | None) -> str:
    """The emitted description: capability sentence, Covers clause, then ``Use when ...``.

    Lists every member when the result fits :data:`DESCRIPTION_MAX_CHARS`;
    otherwise the most members that fit, in the order given (highest priority
    first), then ``and N more``. Raises :class:`DescriptionOverflowError` (a
    ``ValueError`` carrying the text and its length) when even one name does
    not fit, which validate's V11 rules out before any sync writes.

    Example::

        compose_description("Python conventions.", ["Docstrings"], "editing a module")
        # 'Python conventions. Covers Docstrings. Use when editing a module.'
    """
    shown = covered_member_count(description, member_names, use_when)
    if shown == 0:
        raise DescriptionOverflowError(
            _joined(description, covers_clause(member_names, 1), use_when)
        )
    return _joined(description, covers_clause(member_names, shown), use_when)


def covered_member_count(
    description: str, member_names: Sequence[str], use_when: str | None
) -> int:
    """How many names :func:`compose_description` lists; ``0`` when even one does not fit.

    ``playbook validate`` warns (W3) when this is below ``len(member_names)``, so
    the warning and the composed text cannot disagree on where truncation starts.

    Example: ``covered_member_count("X.", ["Typing", "Idioms"], None)`` -> ``2``.
    """
    _require_members(member_names)
    for shown in range(len(member_names), 0, -1):
        text = _joined(description, covers_clause(member_names, shown), use_when)
        if len(text) <= DESCRIPTION_MAX_CHARS:
            return shown
    return 0


def worst_case_description(
    description: str, member_names: Sequence[str], use_when: str | None
) -> str:
    """The longest text a one-name Covers fallback can emit, tail included (V11, E7).

    Over every member name after the merge: ``<description> Covers <longest name>
    and <N-1> more. Use when <use_when>.``, the tail absent when ``N == 1``. A
    real composition of ``M <= N`` active members never emits a longer
    fallback, so when this fits, :func:`compose_description` cannot raise.

    Example: ``worst_case_description("X.", ["Typing", "Error handling"], None)`` ->
    ``"X. Covers Error handling and 1 more."``
    """
    _require_members(member_names)
    longest = max(member_names, key=lambda name: len(_label(name)))
    # covers_clause names only the first entry; the others only count toward the tail.
    covers = covers_clause([longest, *member_names[1:]], 1)
    return _joined(description, covers, use_when)


def emitted_frontmatter(skill: Skill) -> dict[str, Any]:
    """Authored frontmatter minus the engine-owned keys; ``description`` composed when members exist.

    The engine-owned keys are ``playbook`` and a framework skill's
    ``capabilities`` tags (D77). A skill without members keeps every other key
    and value as authored. Always a new mapping.

    Example: ``"capabilities" in emitted_frontmatter(brainstorming)`` -> ``False``.
    """
    emitted = {
        key: value for key, value in skill.frontmatter.items() if key not in _ENGINE_OWNED_KEYS
    }
    if not skill.member_references:
        return emitted
    description = str(skill.frontmatter.get("description") or "")
    use_when = skill_catalog_block(skill).use_when
    sections = skill_sections(skill)
    if sections:
        titles = [s.title for s in active_sections(skill.member_references, sections)]
        emitted["description"] = compose_sectioned_description(description, titles, use_when)
    else:
        names = [member.name for member in skill.member_references]
        emitted["description"] = compose_description(description, names, use_when)
    return emitted


def sectioned_description(
    description: str, section_titles: Sequence[str], use_when: str | None
) -> str:
    """A sectioned skill's description: Covers names every title given, never truncated (D17).

    Titles are labelled by D46.7 (``"Test Structure"`` -> ``"test structure"``,
    ``"FastAPI wiring"`` kept); no titles, no Covers clause. Its length is not
    checked here: V11 measures it over every declared section, and
    :func:`compose_sectioned_description` refuses an overflow.

    Example::

        sectioned_description("Test conventions.", ["Mocking", "FastAPI wiring"], "editing tests")
        # 'Test conventions. Covers mocking, FastAPI wiring. Use when editing tests.'
    """
    labels = [section_label(_label(title)) for title in section_titles]
    covers = f"Covers {', '.join(labels)}." if labels else ""
    return _joined(description, covers, use_when)


def compose_sectioned_description(
    description: str, section_titles: Sequence[str], use_when: str | None
) -> str:
    """:func:`sectioned_description`, or :class:`DescriptionOverflowError` over the limit.

    Example: ``compose_sectioned_description("X.", ["Mocking"], None)`` -> ``"X. Covers mocking."``.
    """
    text = sectioned_description(description, section_titles, use_when)
    if len(text) > DESCRIPTION_MAX_CHARS:
        raise DescriptionOverflowError(text, sectioned=True)
    return text


def emitted_body(skill: Skill) -> str:
    """Authored body, plus the generated navigation when members exist.

    A skill that declares sections gets the "How to use this skill" paragraph,
    the index grouped by section and its listed references (``skills._rules_index``);
    any other skill the flat ``## Rules`` index, then its listed references if any.

    Example: ``emitted_body(python_coding).endswith("Typing: Prefer ...\\n")`` -> ``True``.
    """
    if not skill.member_references:
        return skill.body
    sections = skill_sections(skill)
    if sections:
        generated = sectioned_navigation(skill.member_references, sections, skill.listed_references)
    else:
        parts = (rules_index(skill.member_references), references_section(skill.listed_references))
        generated = "\n".join(part for part in parts if part)
    authored = skill.body.rstrip()
    return f"{authored}\n\n{generated}" if authored else generated


def strip_rules_index(body: str) -> str:
    """``body`` without the trailing navigation :func:`emitted_body` appended.

    The inverse an importer needs when only the emitted ``SKILL.md`` is left (no
    sidecar keeps the authored body): the navigation is recognised by its fixed
    opening, the "How to use this skill" paragraph of a sectioned skill or the
    ``## Rules`` heading and lead line of a sectionless one, and everything from
    it to the end is dropped, so the next sync appends it exactly once again. A
    body without the navigation is returned unchanged.

    Example: ``strip_rules_index(emitted_body(skill))`` -> ``skill.body.rstrip() + "\n"``.
    """
    for marker in (HOW_TO_USE_BLOCK, f"{RULES_HEADING}\n\n{RULES_LEAD}\n"):
        if body.startswith(marker):
            return ""
        cut = body.rfind(f"\n\n{marker}")
        if cut != -1:
            return body[:cut] + "\n"
    return body


def rules_index(members: Sequence[MemberReference]) -> str:
    """The flat ``## Rules`` section of a sectionless skill: one line per member, in order.

    Each line is ``- [<rule-id>](rules/<rule-id>.md) — <name>: <description>``:
    the link text is the rule id because lint feedback names rule ids (D16).
    ``""`` without members.

    Example: ``rules_index(members).splitlines()[0]`` -> ``"## Rules"``.
    """
    if not members:
        return ""
    lines = [_index_line(member) for member in members]
    return "\n".join([RULES_HEADING, "", RULES_LEAD, "", *lines, ""])


def render_member_reference(rule_id: str, globs: Sequence[str], body: str) -> str:
    """The text of ``rules/<rule_id>.md``: one italic rule line, a blank line, the body.

    The body is the rule's rendered body unchanged, minus the blank lines that
    separate it from its frontmatter; the file ends with one newline. The globs
    line is advisory, as the ``*Applies to: ...*`` line of a rule section is.

    Example: ``render_member_reference("pytest", [], "# T\\n")`` -> ``"*Rule `pytest`.*\\n\\n# T\\n"``.
    """
    rule_body = body.strip("\n")
    return f"{_rule_line(rule_id, globs)}\n\n{rule_body}\n"


def where_entry(skill: Skill) -> WhereEntry | None:
    """``(skill id, playbook.files)`` for a skill with members and a ``files`` phrase, else None.

    Example: ``where_entry(python_coding)`` -> ``WhereEntry("python-coding", "Any Python file")``.
    """
    files = skill_catalog_block(skill).files
    if not skill.member_references or files is None:
        return None
    return WhereEntry(skill_id=skill_id_of(skill), files=files)


def where_guidance_section(entries: Sequence[WhereEntry]) -> str:
    """The ``## Where guidance lives`` section, sorted by skill id; ``""`` without entries.

    It ends with the ``---`` separator of a rule section, so it stacks like one
    in ``AGENTS.md`` and the Claude Code rules file (E10).

    Example: ``where_guidance_section([WhereEntry("ml-data", "Model code")])``.
    """
    if not entries:
        return ""
    ordered = sorted(entries, key=lambda entry: entry.skill_id)
    lines = [f"- {entry.files}: skill `{entry.skill_id}`" for entry in ordered]
    return "\n".join(
        [_WHERE_HEADING, "", _WHERE_LEAD, "", *lines, "", _WHERE_LINT_LINE, "", _SECTION_END, ""]
    )


def _index_line(member: MemberReference) -> str:
    link = f"[{member.rule_id}]({member_reference_path(member.rule_id)})"
    return f"- {link} — {one_line(member.name)}: {one_line(member.description)}"


def _rule_line(rule_id: str, globs: Sequence[str]) -> str:
    """``*Rule `<id>`; applies to `<glob>`, ...*`` or, without globs, ``*Rule `<id>`.*``."""
    if not globs:
        return f"*Rule `{rule_id}`.*"
    applies_to = ", ".join(f"`{glob}`" for glob in globs)
    return f"*Rule `{rule_id}`; applies to {applies_to}.*"


def _require_members(member_names: Sequence[str]) -> None:
    """Refuse an empty member list: a skill without members keeps its authored text."""
    if not member_names:
        raise ValueError(
            f"a Covers clause needs at least one member name, got {list(member_names)!r}"
        )


def _joined(description: str, covers: str, use_when: str | None) -> str:
    """``<description>. <covers> Use when <use_when>.``, skipping a blank part."""
    parts = [_sentence(description), covers]
    if use_when is not None and use_when.strip():
        parts.append(_sentence(f"Use when {use_when}"))
    return " ".join(part for part in parts if part)


def _sentence(text: str) -> str:
    """``text`` on one line, ending with ``.`` unless it already ends a sentence."""
    flat = one_line(text)
    if not flat or flat.endswith(_SENTENCE_ENDINGS):
        return flat
    return f"{flat}."


def _label(name: str) -> str:
    """A member name as the Covers clause shows it: one line, no trailing ``.``."""
    return one_line(name).removesuffix(".")


def _catalog_phrase(value: object) -> str | None:
    """A ``playbook`` value as a stripped string, or ``None`` when absent, blank or not a string."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
