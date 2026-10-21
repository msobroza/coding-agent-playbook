"""``playbook validate`` over member rules and ``playbook:`` blocks (prS §6.4.12, §6.6).

A scoped rule is a member rule of one skill (ADR 0001, ADR 0005): of the skill
whose ``skills/<skill>/rules/`` directory holds it, or, for a rule from another
layer, of the skill it names in ``skill:``. The loader fills ``skill`` from the
location (``Rule.home_skill``), so every check below reads ``skill`` alone. The
engine writes a member as one of the skill's rule files. Two checks guard that
composition before ``playbook sync`` writes anything:

- :func:`check_skill_membership`, per rule: a skill is required on a scoped
  rule (V1, with V2's hint when the rule overrides one that named a skill) and
  forbidden on an always rule (V3), must be a skill id string (V4) naming a
  skill that exists after the layer merge (V5) and declares a ``playbook:``
  block (V14, E6); a member rule's own id must be a skill-safe file name (V6,
  E14).
- :func:`check_rule_skills`, per skill with a ``playbook:`` block: the block's
  shape (V7-V10, E15), the worst-case composed description within 300 chars
  (V11, E7), no authored ``## Rules`` heading (V13; V12 was retired by prU D5:
  members render to ``rules/``, so a hand-written ``references/`` file cannot
  collide with one); warnings for a block without members, in its ``rules/``
  directory or naming it (W1),
  members without ``files`` (W2) and a truncated Covers clause (W3).

Every check runs over the merged sets and ignores ``applies_if``, so overlay
authors and consumers see the same findings whatever the detector facts.
V11 measures with ``skills.document.worst_case_description``, the bound sync's
``compose_description`` holds, so a skill that validates cannot make sync raise.

The user-facing text is documented, not only coded: SPEC §12.6 lists every check
with a sample line, and MIGRATION.md quotes V1 (:data:`SCOPED_RULE_NEEDS_SKILL_MESSAGE`,
``{known}`` filled for core) verbatim, which ``tests/unit/test_docs_migration_skills.py``
pins. Change a message here and update both docs in the same change.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypeGuard

from coding_agent_playbook.artifacts.member_reference import member_reference_path
from coding_agent_playbook.skills.document import (
    DESCRIPTION_MAX_CHARS,
    PLAYBOOK_BLOCK_KEY,
    covered_member_count,
    covers_clause,
    skill_catalog_block,
    worst_case_description,
)
from coding_agent_playbook.skills.membership import is_rule_skill, member_rules_of
from coding_agent_playbook.skills.naming import (
    AGENT_SKILL_NAME_MAX_CHARS,
    AGENT_SKILL_NAME_PATTERN,
    skill_id_of,
)
from coding_agent_playbook.validation.findings import (
    ValidationError,
    ValidationFindings,
    skill_label,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

_NAME_SHAPE: Final = f"{AGENT_SKILL_NAME_PATTERN.pattern} (1-{AGENT_SKILL_NAME_MAX_CHARS} chars)"
#: The phrase keys V9 checks; ``sections`` and ``references`` are lists that
#: ``validation._sections`` and ``validation._skill_references`` check (prU D17, D47).
_PHRASE_KEYS: Final = ("files", "use_when")
_BLOCK_KEYS: Final = (*_PHRASE_KEYS, "sections", "references")
#: ``playbook.files`` becomes one line of ``## Where guidance lives`` (prS §6.4.2).
_FILES_MAX_CHARS: Final = 80
_PHRASE_SHAPES: Final = {
    "files": (
        f"keep it to one line of at most {_FILES_MAX_CHARS} chars without a trailing period "
        "(it becomes one line of 'Where guidance lives')"
    ),
    "use_when": (
        "keep it to one non-empty line (the engine writes it as 'Use when <use_when>.' in "
        "the composed description)"
    ),
}
# E15: the engine adds the prefix, so an authored one would read "Use when Use when".
_USE_WHEN_PREFIX: Final = re.compile(r"use when\b", re.IGNORECASE)
_RULES_HEADING: Final = "## Rules"
#: V1's message; MIGRATION.md quotes it with ``{known}`` filled for core, and a docs
#: test imports it so the quote cannot drift (prS §6.4.12).
SCOPED_RULE_NEEDS_SKILL_MESSAGE: Final = (
    "scope 'scoped' needs a skill: put the file in that skill's rules/ directory "
    "(skills/<skill-id>/rules/), or add 'skill: <skill-id>' when the skill comes from "
    "another layer; known skills: {known}"
)


def check_skill_membership(
    resolved_rules: Sequence[Rule], skills: Sequence[Skill], *, all_rules: Sequence[Rule]
) -> list[ValidationError]:
    """One error per way a rule's ``skill`` breaks D2 (required/forbidden/shape/exists), E14 or V14.

    ``resolved_rules`` and ``skills`` are the merged sets (``ctx.rules_resolved``,
    ``ctx.skills_resolved``); ``all_rules`` is every layer's definition
    (``ctx.rule_definitions``, loaded tolerantly so validate never raises on a
    malformed rule file), read only for V2's hint. An always
    rule without ``skill`` passes here.

    Example::

        errors = check_skill_membership(
            ctx.rules_resolved, ctx.skills_resolved, all_rules=ctx.rule_definitions
        )
    """
    skills_by_id = {skill_id_of(skill): skill for skill in skills}
    return [
        ValidationError(path=str(rule.source_path or rule.frontmatter.id), message=message)
        for rule in resolved_rules
        for message in _rule_membership_problems(rule, skills_by_id, all_rules)
    ]


def check_rule_skills(
    resolved_rules: Sequence[Rule], skills: Sequence[Skill]
) -> ValidationFindings:
    """Errors and warnings for skills with a ``playbook:`` block (V7-V13, W1-W3).

    Members are every merged rule naming the skill, ``applies_if`` ignored (E7).

    Example::

        findings = check_rule_skills(ctx.rules_resolved, ctx.skills_resolved)
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    for skill in skills:
        if not is_rule_skill(skill):
            continue
        members = member_rules_of(skill_id_of(skill), resolved_rules)
        label = skill_label(skill)
        errors.extend(ValidationError(label, m) for m in _rule_skill_errors(skill, members))
        warnings.extend(ValidationError(label, m) for m in _rule_skill_warnings(skill, members))
    return ValidationFindings(errors, warnings)


def is_skill_safe_name(value: object) -> TypeGuard[str]:
    """Whether ``value`` is an Agent Skills name: a file and directory name in every root.

    Example: ``is_skill_safe_name("python-typing")`` -> ``True``; ``"Py_Typing"`` -> ``False``.
    """
    return (
        isinstance(value, str)
        and len(value) <= AGENT_SKILL_NAME_MAX_CHARS
        and AGENT_SKILL_NAME_PATTERN.fullmatch(value) is not None
    )


def _rule_membership_problems(
    rule: Rule, skills_by_id: Mapping[str, Skill], all_rules: Sequence[Rule]
) -> list[str]:
    """V1/V2 for a scoped rule without ``skill``; the ``skill`` checks when it sets one."""
    if rule.frontmatter.skill is not None:
        return _membership_problems(rule, skills_by_id)
    if rule.frontmatter.scope != "scoped":
        return []
    message = SCOPED_RULE_NEEDS_SKILL_MESSAGE.format(known=_known_rule_skills(skills_by_id))
    return [message + _overridden_skill_hint(rule, all_rules)]


def _overridden_skill_hint(rule: Rule, all_rules: Sequence[Rule]) -> str:
    """V2: ``; the rule it overrides (<pkg>) names '<skill>'``, or ``""`` when none did.

    The merge keeps the last definition of an id, so every other definition of
    ``rule``'s id is one it overrides; the nearest one that names a skill wins.
    """
    overridden = [
        other
        for other in all_rules
        if other.frontmatter.id == rule.frontmatter.id
        and (other.source_package, other.source_path) != (rule.source_package, rule.source_path)
        and isinstance(other.frontmatter.skill, str)
    ]
    if not overridden:
        return ""
    nearest = overridden[-1]
    return f"; the rule it overrides ({nearest.source_package}) names {nearest.frontmatter.skill!r}"


def _membership_problems(rule: Rule, skills_by_id: Mapping[str, Skill]) -> list[str]:
    """V3, then V4, then V6 and V5/V14 for one rule that sets ``skill``."""
    value: object = rule.frontmatter.skill
    if rule.frontmatter.scope == "always":
        return [
            f"'skill: {value}' is not allowed on an always rule (always rules stay in "
            "always-loaded context); remove 'skill', or set 'scope: scoped' to deliver the "
            "rule through that skill"
        ]
    if not is_skill_safe_name(value):
        return [
            f"skill {value!r} must be a skill id string matching {_NAME_SHAPE}, e.g. 'python-coding'"
        ]
    problems = [] if is_skill_safe_name(rule.frontmatter.id) else [_unsafe_id_problem(rule, value)]
    target_problem = _target_problem(value, skills_by_id)
    return problems if target_problem is None else [*problems, target_problem]


def _unsafe_id_problem(rule: Rule, skill_id: str) -> str:
    """V6: the member's id becomes ``rules/<id>.md`` in every skill root."""
    return (
        f"rule id {rule.frontmatter.id!r} cannot be a member of skill {skill_id!r}: its "
        f"rule file is written as {member_reference_path('<id>')}, so the id must match "
        f"{_NAME_SHAPE}"
    )


def _target_problem(skill_id: str, skills_by_id: Mapping[str, Skill]) -> str | None:
    """V5 when ``skill_id`` names no merged skill, V14 when that skill takes no members."""
    known = _known_rule_skills(skills_by_id)
    target = skills_by_id.get(skill_id)
    if target is None:
        return (
            f"skill {skill_id!r} does not exist after merging every layer; expected one of: "
            f"{known} (or enable the overlay that ships it)"
        )
    if is_rule_skill(target):
        return None
    return (
        f"skill {skill_id!r} ({target.source_package}) declares no 'playbook:' block, so it "
        f"cannot take member rules; name one that does ({known}), or add a 'playbook:' block "
        "to a skill of your own (an override of a core skill must keep one)"
    )


def _known_rule_skills(skills_by_id: Mapping[str, Skill]) -> str:
    """The sorted ids of the skills that take members, or why there are none."""
    ids = sorted(skill_id for skill_id, skill in skills_by_id.items() if is_rule_skill(skill))
    return ", ".join(ids) if ids else "none, no skill declares a 'playbook:' block"


def _rule_skill_errors(skill: Skill, members: Sequence[Rule]) -> list[str]:
    """V7-V10 on the block, V11 when the block is sound, then V13."""
    errors = _block_problems(skill.frontmatter[PLAYBOOK_BLOCK_KEY])
    if not errors and members:
        errors.extend(_overflow_problems(skill, members))
    if any(line.strip() == _RULES_HEADING for line in skill.body.splitlines()):
        errors.append(
            f"the body has its own {_RULES_HEADING!r} heading; the engine appends that "
            "section for member rules, so rename yours (e.g. '## Conventions')"
        )
    return errors


def _block_problems(block: object) -> list[str]:
    """V7 (not a mapping), V8 (unknown keys), V9 and V10 (the two phrases)."""
    if not isinstance(block, Mapping):
        return [
            f"'{PLAYBOOK_BLOCK_KEY}' must be a mapping with optional keys "
            f"{', '.join(_BLOCK_KEYS)}, got {type(block).__name__} {block!r}"
        ]
    unknown = sorted(str(key) for key in block if key not in _BLOCK_KEYS)
    problems = [
        f"'{PLAYBOOK_BLOCK_KEY}' has unknown key {key!r}; allowed keys: {', '.join(_BLOCK_KEYS)}"
        for key in unknown
    ]
    for key in _PHRASE_KEYS:
        problem = _phrase_problem(key, block.get(key))
        if problem is not None:
            problems.append(f"'{PLAYBOOK_BLOCK_KEY}.{key}' {problem}; {_PHRASE_SHAPES[key]}")
    return [*problems, *_use_when_prefix_problem(block.get("use_when"))]


def _phrase_problem(key: str, value: object) -> str | None:
    """Why a ``playbook`` phrase is not one usable line; ``None`` (absent) is fine."""
    if value is None:
        return None
    if not isinstance(value, str):
        return f"is {type(value).__name__} {value!r}"
    text = value.strip()
    if not text:
        return "is blank"
    if "\n" in text:
        return f"spans {len(text.splitlines())} lines ({text!r})"
    if key == "files" and len(text) > _FILES_MAX_CHARS:
        return f"is {len(text)} chars"
    if key == "files" and text.endswith("."):
        return f"ends with a period ({text!r})"
    return None


def _use_when_prefix_problem(value: object) -> list[str]:
    """V10 (E15): ``use_when`` holds only the condition."""
    if not isinstance(value, str) or not _USE_WHEN_PREFIX.match(value.strip()):
        return []
    return [
        f"'{PLAYBOOK_BLOCK_KEY}.use_when' starts with 'Use when'; write only the condition "
        "(the engine adds 'Use when'), e.g. 'editing a Python module'"
    ]


def _overflow_problems(skill: Skill, members: Sequence[Rule]) -> list[str]:
    """V11: even a one-name Covers clause with its ``and N-1 more`` tail is over the limit."""
    parts = _ComposedParts.of(skill, members)
    worst = parts.worst_case()
    if len(worst) <= DESCRIPTION_MAX_CHARS:
        return []
    return [
        f"the composed description cannot fit {DESCRIPTION_MAX_CHARS} chars even when the "
        f"Covers clause names one member: '{worst}' is {len(worst)} chars; shorten "
        f"{_shorten_hint(parts, _longest_member(members))}"
    ]


@dataclass(frozen=True)
class _ComposedParts:
    """What sync's ``compose_description`` gets for a skill, over every merged member."""

    description: str
    names: tuple[str, ...]
    use_when: str | None

    @classmethod
    def of(cls, skill: Skill, members: Sequence[Rule]) -> _ComposedParts:
        """The authored parts exactly as ``emitted_frontmatter`` reads them."""
        description = str(skill.frontmatter.get("description") or "")
        names = tuple(rule.frontmatter.name for rule in members)
        return cls(description, names, skill_catalog_block(skill).use_when)

    def worst_case(self) -> str:
        """V11's measure: :func:`worst_case_description` over these parts."""
        return worst_case_description(self.description, self.names, self.use_when)

    def covered(self) -> int:
        """How many names the composed description lists (:func:`covered_member_count`)."""
        return covered_member_count(self.description, self.names, self.use_when)


def _longest_member(members: Sequence[Rule]) -> Rule:
    """The member whose name ``worst_case_description`` names: the longest label, first on ties."""
    return max(members, key=lambda rule: len(covers_clause([rule.frontmatter.name], 1)))


def _shorten_hint(parts: _ComposedParts, longest: Rule) -> str:
    """``'description' (N chars), 'playbook.use_when' (M chars) or the longest member name (…)``."""
    hints = [f"'description' ({len(parts.description.strip())} chars)"]
    if parts.use_when is not None:
        hints.append(f"'{PLAYBOOK_BLOCK_KEY}.use_when' ({len(parts.use_when)} chars)")
    fm = longest.frontmatter
    return f"{', '.join(hints)} or the longest member name ({fm.id}: '{fm.name}')"


def _rule_skill_warnings(skill: Skill, members: Sequence[Rule]) -> list[str]:
    """W1 without members; otherwise W2 (no ``files``) and W3 (truncated Covers clause)."""
    if not members:
        return [
            f"declares '{PLAYBOOK_BLOCK_KEY}' but has no member rule (none in its rules/ "
            "directory, none naming it in 'skill:'); it is never written"
        ]
    block = skill.frontmatter[PLAYBOOK_BLOCK_KEY]
    warnings = []
    if isinstance(block, Mapping) and block.get("files") is None:
        warnings.append(
            f"has member rules but no '{PLAYBOOK_BLOCK_KEY}.files'; it is left out of the "
            "'Where guidance lives' section"
        )
    # W3 measures the block's phrases, so like V11 it waits until V7-V10 accept them.
    if _block_problems(block):
        return warnings
    return [*warnings, *_truncation_warning(skill, members)]


def _truncation_warning(skill: Skill, members: Sequence[Rule]) -> list[str]:
    """W3 (D21): the full member list does not fit; silent when V11 already fails."""
    parts = _ComposedParts.of(skill, members)
    if len(parts.worst_case()) > DESCRIPTION_MAX_CHARS:
        return []
    shown, total = parts.covered(), len(parts.names)
    if shown == total:
        return []
    hidden = total - shown
    return [
        f"the composed description names {shown} of {total} member rules within "
        f"{DESCRIPTION_MAX_CHARS} chars ('... and {hidden} more'); shorten member names or "
        "the authored parts to list them all"
    ]
