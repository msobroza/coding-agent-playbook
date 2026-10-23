"""How an ``includes_rules`` list becomes prompt text (specs/prS-skills-context.md §7.4.2).

``includes_rules`` is the one declaration of the rules a prompt needs; no
prompt body places rule text itself (D15). It reaches the model two ways:

- :func:`skill_pointer_block` builds the ``## Before you start`` block of a
  Claude Code or OpenCode command: one step per owning skill naming the
  rule files to read, so the model loads them on demand.
  :func:`insert_pointer_block` places it before the body's first ``##`` section.
- :func:`includes_rules_appendix` builds the ``## Reference rules`` appendix,
  every included rule's text inline, for Continue prompts, the agent_harness
  prompt leaf and the eval runner (D22), which have no skill to point at.

Stdlib only, and ``RuleRegistry`` is imported for type checking only:
``rendering.rule_registry`` (which defines it) imports this module, so a
runtime import back would be a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.rendering.rule_registry import RuleRegistry


@dataclass(frozen=True)
class SkillReference:
    """Where an active scoped rule is delivered: its owning skill and its file inside it.

    Example: ``SkillReference("python-coding", "rules/python-typing.md")``.
    """

    skill_id: str
    path: str


class SkillReferenceIndex(Protocol):
    """Which skill rule file holds an included rule; ``RuleRegistryImpl`` implements it."""

    def reference_for(self, rule_id: str) -> SkillReference | None:
        """The rule file of an active scoped rule; ``None`` if unknown, filtered out or always."""
        ...


BEFORE_YOU_START: Final = "## Before you start"
CLOSING_STEP: Final = (
    "For each file in scope, also load any other listed skill whose description matches it."
)


def skill_pointer_block(
    includes_rules: Sequence[str], references: SkillReferenceIndex | None
) -> str:
    """The ``## Before you start`` block of a Claude Code or OpenCode command, or ``""`` (D15).

    One numbered step per owning skill, in the order its first rule appears in
    ``includes_rules``, listing only the rule files of rules that are active
    here; then the closing step. ``""`` when no included rule resolves to a
    rule file (or ``references`` is ``None``): the prompt then gets no block.

    Example::

        skill_pointer_block(["python-typing", "pytest"], registry)
        # "## Before you start\\n\\n1. Load skill `python-coding` and read its rule …"
    """
    grouped = references_by_skill(includes_rules, references)
    if not grouped:
        return ""
    steps = [load_step(n, skill, paths) for n, (skill, paths) in enumerate(grouped.items(), 1)]
    steps.append(f"{len(steps) + 1}. {CLOSING_STEP}")
    return f"{BEFORE_YOU_START}\n\n" + "\n".join(steps) + "\n"


def references_by_skill(
    includes_rules: Sequence[str], references: SkillReferenceIndex | None
) -> dict[str, list[str]]:
    """``{skill id: [rule file path, ...]}`` in first-appearance order, each id once.

    Example: ``references_by_skill(["pytest"], registry)`` ->
    ``{"python-testing": ["rules/pytest.md"]}``.
    """
    grouped: dict[str, list[str]] = {}
    if references is None:
        return grouped
    for rule_id in dict.fromkeys(includes_rules):
        found = references.reference_for(rule_id)
        if found is not None:
            grouped.setdefault(found.skill_id, []).append(found.path)
    return grouped


def load_step(number: int, skill_id: str, paths: Sequence[str]) -> str:
    """One numbered load step: the skill, then its rule file or files (prU D5).

    Example: ``load_step(2, "python-testing", ["rules/pytest.md"])`` ->
    ``"2. Load skill `python-testing` and read its rule `rules/pytest.md`."``
    """
    noun = "rule" if len(paths) == 1 else "rules"
    listed = ", ".join(f"`{path}`" for path in paths)
    return f"{number}. Load skill `{skill_id}` and read its {noun} {listed}."


def insert_pointer_block(body: str, block: str) -> str:
    """``body`` with ``block`` before its first level-2 heading outside a code fence.

    Without such a heading the block follows the leading ``# `` title line, or
    opens the body when it has no title. An empty ``block`` returns ``body``
    unchanged, so prompts without active member rules render byte-identically.
    Every shipped prompt opens with a title and a role paragraph, so the role
    stays first and the load steps come before the task instructions (P3-2).

    Example::

        insert_pointer_block("# Review\\n\\nRole.\\n\\n## Tone\\n", block)
        # "# Review\\n\\nRole.\\n\\n## Before you start\\n…\\n\\n## Tone\\n"
    """
    if not block:
        return body
    lines = body.splitlines(keepends=True)
    section = _first_section_line(lines)
    if section is not None:
        return "".join(lines[:section]) + block + "\n" + "".join(lines[section:])
    title = _title_line(lines)
    split = 0 if title is None else title + 1
    head, rest = "".join(lines[:split]).rstrip("\n"), "".join(lines[split:])
    opening = f"{head}\n\n" if head else ""
    gap = "" if not rest or rest.startswith("\n") else "\n"
    return f"{opening}{block}{gap}{rest}"


def _first_section_line(lines: Sequence[str]) -> int | None:
    """Index of the first ``## `` line outside a code fence (a ``` line toggles one)."""
    in_fence = False
    for index, line in enumerate(lines):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            return index
    return None


def _title_line(lines: Sequence[str]) -> int | None:
    """Index of the leading ``# `` title: the first non-blank line, when it is one."""
    for index, line in enumerate(lines):
        if line.strip():
            return index if line.startswith("# ") else None
    return None


def includes_rules_appendix(includes_rules: Sequence[str], registry: RuleRegistry | None) -> str:
    """The ``## Reference rules`` appendix of a prompt: each included rule's text, or ``""``.

    Every id in ``includes_rules`` is rendered through ``registry``, in order
    and once (an id listed twice keeps its first place); a rule that renders
    ``""`` (filtered out by ``applies_if``, or unknown) is skipped. ``""`` when
    there is nothing to list: no ids, no registry, or every fragment empty.

    The registry is asked with an empty context: it merges its stored detector
    facts beneath the caller's, so a templated rule renders without the caller
    knowing them.

    Example::

        includes_rules_appendix(["python-typing"], registry)
        # "\\n## Reference rules\\n\\n### Python typing\\n\\n<the rule text>\\n"
    """
    if not includes_rules or registry is None:
        return ""
    fragments: list[str] = []
    for rule_id in dict.fromkeys(includes_rules):
        fragment = registry.render_for_inclusion(rule_id, {})
        if fragment:
            fragments.append(fragment.rstrip("\n"))
    if not fragments:
        return ""
    return "\n## Reference rules\n\n" + "\n\n".join(fragments) + "\n"
