"""The rule files of the ``agent_harness`` adapter and their manifest entries (prU D22).

Every rule file is the same shape: ``description``-only frontmatter, the
sentinel as the first body line, then the rendered body. Where it goes depends
on the rule:

- an always-rule: ``rules/<priority:02d>-<id>.md`` (the adapter places it);
- a member rule whose skill this render emits: ``skills/<skill>/rules/<id>.md``,
  the same ``rules/`` directory as the source (prU D5, ADR 0005);
- any other scoped rule: the root ``references/<id>.md``.

The manifest entry records the un-rendered body and every field the harness
file cannot carry, plus ``section``. A rule placed by location records no
``skill`` (the path names it, as the source directory does), so a lossless
import can put it back in ``playbook/skills/<skill>/rules/`` without writing a
``skill:`` line its author never wrote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness import emitter, manifest
from coding_agent_playbook.artifacts.member_reference import skill_member_path
from coding_agent_playbook.generated_output.output_io import write_output_text
from coding_agent_playbook.rendering.formats import with_sentinel_body

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule


def split_members(
    scoped_rules: Sequence[Rule], emitted_skill_ids: Collection[str]
) -> tuple[list[Rule], list[Rule]]:
    """``(members of an emitted skill, every other scoped rule)``, order kept.

    Example: ``members, root = split_members(scoped, {"python-coding"})``.
    """
    members = [r for r in scoped_rules if r.frontmatter.skill in emitted_skill_ids]
    others = [r for r in scoped_rules if r.frontmatter.skill not in emitted_skill_ids]
    return members, others


def member_rule_path(repo_root: Path, rule: Rule) -> Path:
    """``<root>/skills/<skill>/rules/<id>.md`` for a member rule (its ``skill`` is set).

    Raises ``ValueError`` naming the rule when ``skill`` is None: only a member
    rule (from :func:`split_members`) has a skill directory to go to.

    Example: ``member_rule_path(root, typing_rule)`` -> ``root/"skills/python-coding/rules/python-typing.md"``.
    """
    skill_id = rule.frontmatter.skill
    if skill_id is None:
        raise ValueError(
            f"rule {rule.frontmatter.id!r} has no 'skill'; only a member rule "
            "(skill: <skill-id>) is emitted under skills/<skill>/rules/"
        )
    return repo_root / skill_member_path(skill_id, rule.frontmatter.id)


def write_rule_file(
    target: Path,
    rule: Rule,
    repo_root: Path,
    entries: list[manifest.ManifestEntry],
    *,
    record_manifest: bool = True,
) -> Path:
    """Write ``rule`` at ``target`` and, when ``record_manifest``, append its manifest entry.

    A hook advisory passes ``record_manifest=False``: presentation only, so a
    lossless import never turns it into a ``Rule`` (§C.6).

    Example: ``write_rule_file(root / "references" / "x.md", rule, root, entries)``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = emitter.frontmatter_block({"description": rule.frontmatter.description})
    write_output_text(target, with_sentinel_body(frontmatter, rule.body))
    if record_manifest:
        path = target.relative_to(repo_root).as_posix()
        entries.append(_rule_entry(rule, path, by_location=_placed_by_location(rule, path)))
    return target


def _placed_by_location(rule: Rule, path: str) -> bool:
    """Whether ``path`` is the rule's home skill's ``rules/`` and the skill came from there."""
    skill_id = rule.frontmatter.skill
    if not rule.skill_from_location or skill_id is None:
        return False
    return path == skill_member_path(skill_id, rule.frontmatter.id)


def _rule_entry(rule: Rule, path: str, *, by_location: bool) -> manifest.ManifestEntry:
    fm = rule.frontmatter
    return manifest.ManifestEntry(
        kind="rule",
        path=path,
        id=fm.id,
        # The harness rule file emits ``description`` only: ``name`` and the
        # un-rendered source body are the sidecar's, so the lossless importer
        # recovers them independently of the leaf.
        name=fm.name,
        body=rule.template_body,
        is_templated=rule.is_templated,
        scope=fm.scope,
        priority=fm.priority,
        globs=list(fm.globs),
        applies_if=dict(fm.applies_if),
        tags=list(fm.tags),
        version=fm.version,
        lint_codes=dict(fm.lint_codes),
        skill=None if by_location else fm.skill,
        section=fm.section,
    )
