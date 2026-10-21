"""``playbook validate`` over the ``rules/`` layout of every layer (prU D21, D5, ADR 0005).

Deterministic checks over every layer's rule files and skill directories,
each finding naming the file, the offending value and the fix:

- R1: a rule inside ``skills/x/rules/`` that declares ``skill: y`` (y != x).
- R2: a rule's file name minus ``.md``/``.md.j2`` is its id, for every rule in
  a skill's ``rules/`` (all layers) and every engine-layer always rule, which
  may carry a two-digit priority prefix (``10-python-house-style.md``). Overlay
  and local-layer ``<layer>/rules/`` files keep free names. An engine scoped
  rule still in ``<engine>/rules/`` is left to R5 (L0-07, D36), which rejects
  it outright with a move hint naming ``<id>.md``; once it sits in a skill, R2
  checks its name, so every engine-layer rule ends up covered.
- R3: two files of one layer with one id (the later silently wins the merge);
  one id in two layers is an override.
- R4: a ``skills/<dir>/rules/`` whose ``<dir>`` has no ``SKILL.md`` or whose
  ``SKILL.md`` has no ``playbook:`` block (discovery would skip it silently).
- R6: an always rule inside a skill's ``rules/`` gets a move hint (instead of
  V3's "remove 'skill'", which ``validation._skills`` skips for it). It is that
  file's only finding: R1's and R2's hints would contradict the move.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Final

import yaml

from coding_agent_playbook.catalog._skill_rules import find_skill_md, read_skill_md
from coding_agent_playbook.catalog.source import FileSystemArtifactSource, engine_package_of
from coding_agent_playbook.skills.document import PLAYBOOK_BLOCK_KEY
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.validation.findings import ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.catalog.source import ArtifactSource


#: R2: an always rule's file may carry a two-digit priority prefix (``10-python-house-style``).
_PRIORITY_PREFIX: Final = re.compile(r"\d{2}-")
_SUFFIXES: Final = (".md.j2", ".md")


def check_rule_layout(rules: Sequence[Rule], source: ArtifactSource) -> list[ValidationError]:
    """One error per rule file or skill directory that breaks the layout rules R1-R4, R6.

    ``rules`` is every layer's well-formed rule before the merge
    (``ctx.rule_definitions``, i.e. ``source.collect_rules()[0]``).

    Example::

        errors = check_rule_layout(ctx.rule_definitions, ctx.artifact_source)
    """
    engine = engine_package_of(source)
    per_file = [
        ValidationError(path=str(path), message=message)
        for rule in rules
        if (path := rule.source_path) is not None
        for message in _file_problems(rule, path, engine)
    ]
    return [*per_file, *_duplicate_id_errors(rules), *_skill_rules_dir_errors(source)]


def _where(rule: Rule) -> str:
    return str(rule.source_path or rule.frontmatter.id)


def _file_problems(rule: Rule, path: Path, engine: str) -> list[str]:
    """R6 alone when it applies (its move makes R1 and R2 moot), else R1 and R2."""
    move = _always_in_skill_problem(rule, path)
    if move:
        return move
    return [*_foreign_skill_problem(rule, path), *_file_name_problem(rule, path, engine)]


def _foreign_skill_problem(rule: Rule, path: Path) -> list[str]:
    """R1: an in-skill rule's ``skill:`` names another skill than its directory's."""
    home, declared = rule.home_skill, rule.frontmatter.skill
    if home is None or rule.skill_from_location or declared == home:
        return []
    target = _layer_root(path) / "skills" / str(declared) / "rules" / path.name
    return [
        f"declares 'skill: {declared}' but lies in the rules/ directory of skill {home!r}, "
        f"which sets its membership; remove the 'skill:' line, or move the file to {target}"
    ]


def _file_name_problem(rule: Rule, path: Path, engine: str) -> list[str]:
    """R2: an in-skill or engine-layer rule's file name minus its suffix is its id.

    An engine scoped rule still under ``<engine>/rules/`` is left alone: R5
    (L0-07, D36) rejects it with a hint that already names ``<id>.md``.
    """
    if not _name_is_checked(rule, engine):
        return []
    name, rule_id = path.name, rule.frontmatter.id
    suffix = next((s for s in _SUFFIXES if name.endswith(s)), "")
    stem = name.removesuffix(suffix)
    always = rule.frontmatter.scope == "always"
    if stem == rule_id or (always and _PRIORITY_PREFIX.fullmatch(stem.removesuffix(rule_id))):
        return []
    problem = (
        f"file name {name!r} does not match rule id {rule_id!r}; rename the file to "
        f"{rule_id}{suffix}"
    )
    if always:
        problem += (
            f" (an always rule may keep a two-digit priority prefix, e.g. 10-{rule_id}{suffix})"
        )
    return [problem]


def _name_is_checked(rule: Rule, engine: str) -> bool:
    """R2's scope: every in-skill rule; an engine ``rules/`` rule once R5 cannot claim it."""
    if rule.home_skill is not None:
        return True
    return rule.source_package == engine and rule.frontmatter.scope == "always"


def _duplicate_id_errors(rules: Sequence[Rule]) -> list[ValidationError]:
    """R3: one error per id that two or more files of one layer define, naming every path.

    The same id in two layers is an override (SPEC §11) and is not reported.
    """
    by_layer_id: defaultdict[tuple[str, str], list[Rule]] = defaultdict(list)
    for rule in rules:
        by_layer_id[(rule.source_package, rule.frontmatter.id)].append(rule)
    return [
        ValidationError(
            path=_where(group[0]),
            message=(
                f"rule id {rule_id!r} is defined by {len(group)} files in layer {layer}: "
                f"{_and_join([_where(rule) for rule in group])}; the later one silently "
                "replaces the earlier, so give one file another id or delete it"
            ),
        )
        for (layer, rule_id), group in by_layer_id.items()
        if len(group) > 1
    ]


def _and_join(items: Sequence[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _skill_rules_dir_errors(source: ArtifactSource) -> list[ValidationError]:
    """R4: each ``skills/<dir>/rules/`` whose ``<dir>`` is no skill that takes members.

    Discovery skips such a directory (``catalog._skill_rules``), so without
    this check its rules vanish silently. Only a filesystem source has layers.
    """
    if not isinstance(source, FileSystemArtifactSource):
        return []
    return [
        ValidationError(path=str(skill_dir / "rules"), message=message)
        for _, skills_root in source.layer_roots("skills")
        for skill_dir in sorted(p for p in skills_root.iterdir() if (p / "rules").is_dir())
        for message in _skill_dir_problem(skill_dir, skills_root.parent / "rules")
    ]


def _skill_dir_problem(skill_dir: Path, layer_rules: Path) -> list[str]:
    """R4 for one directory holding ``rules/``: no ``SKILL.md``, or no ``playbook:`` block."""
    skill_md = find_skill_md(skill_dir)
    if skill_md is None:
        return [
            "a rules/ directory in a skill directory without SKILL.md is never loaded; add "
            "SKILL.md with an 'id' and a 'playbook:' block, or move its files to "
            f"{layer_rules}/ with 'skill: <skill-id>'"
        ]
    try:
        skill = read_skill_md(skill_md)
    except (ValueError, yaml.YAMLError):
        return []  # list_skills raises on this SKILL.md itself, so it is reported there
    if PLAYBOOK_BLOCK_KEY in skill.frontmatter:
        return []
    return [
        f"skill {skill_id_of(skill)!r} has a rules/ directory but its SKILL.md declares no "
        f"'{PLAYBOOK_BLOCK_KEY}:' block, so it cannot take member rules; add a "
        f"'{PLAYBOOK_BLOCK_KEY}:' block (e.g. "
        f"'{PLAYBOOK_BLOCK_KEY}: {{files: <which files this skill covers>}}') "
        f"to {skill_md}, or move the rules out"
    ]


def _always_in_skill_problem(rule: Rule, path: Path) -> list[str]:
    """R6: an always rule in a skill's ``rules/`` belongs in its layer's ``rules/``.

    Replaces V3's "remove 'skill'" for this case: the directory, not a key, made
    it a member (``validation._skills`` skips V3 for it).
    """
    home = rule.home_skill
    if home is None or rule.frontmatter.scope != "always":
        return []
    target = _layer_root(path) / "rules" / path.name
    return [
        f"always rule {rule.frontmatter.id!r} lies in the rules/ directory of skill {home!r}, "
        f"but always rules are never skill members; move it to {target}, or set "
        "'scope: scoped' to keep it in the skill"
    ]


def _layer_root(path: Path) -> Path:
    """``<layer>`` for a file under ``<layer>/skills/<dir>/rules/**``, the only place a
    rule with a ``home_skill`` comes from (``catalog._skill_rules``).

    Example: ``_layer_root(Path("playbook/skills/s/rules/a/x.md"))`` -> ``Path("playbook")``.
    """
    for parent in path.parents:
        if parent.name == "rules" and parent.parent.parent.name == "skills":
            return parent.parent.parent.parent
    raise ValueError(
        f"in-skill rule {path} is not under <layer>/skills/<dir>/rules/; "
        "a rule with a home skill must come from a skill's rules/ directory"
    )
