"""Member rule files inside a layer's skill directories (prU D5, ADR 0005).

A rule at ``<layer>/skills/<dir>/rules/**/<id>.md[.j2]`` is a member of the
skill that ``<dir>/SKILL.md`` declares: the directory sets membership, so the
file needs no ``skill:`` key. Only a directory holding ``SKILL.md`` (or
``SKILL.md.j2``) counts, as for :func:`catalog.source._iter_skills`; a
``rules/`` directory without one contributes nothing here (R4 reports it).
Split out of ``catalog/source.py`` for its file-size budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.rule import RuleLoadError
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.skills.naming import skill_id_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

#: ``SKILL.md`` names a skill directory may hold, in lookup order.
SKILL_MD_NAMES = ("SKILL.md", "SKILL.md.j2")


def iter_skill_rule_files(
    skills_root: Path, iter_md_files: Callable[[Path], Iterator[Path]]
) -> Iterator[tuple[str | RuleLoadError, Path]]:
    """Yield ``(home skill id, rule path)`` for each rule file under ``skills_root/*/rules/``.

    When the skill's ``SKILL.md`` cannot be parsed, the first item is instead a
    :class:`RuleLoadError` naming the rule file, so ``collect_rules`` can report
    it without raising (``list_skills`` fails on that ``SKILL.md`` itself).

    Skill directories come in sorted order and ``iter_md_files`` (the source's
    own walker, which skips dot directories) orders the files inside each, so
    the result is deterministic. The id is the one the merge files the skill
    under (``skills.naming.skill_id_of``), not the directory name.

    Example::

        >>> list(iter_skill_rule_files(Path("playbook/skills"), _iter_md_files))  # doctest: +SKIP
        [('python-coding', PosixPath('playbook/skills/python-coding/rules/x.md'))]
    """
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        rules_dir = skill_dir / "rules"
        skill_md = find_skill_md(skill_dir)
        if skill_md is None or not rules_dir.is_dir():
            continue
        home = _declared_skill_id(skill_md)
        for path in iter_md_files(rules_dir):
            yield (_home_error(home, path) if isinstance(home, Exception) else home), path


def find_skill_md(skill_dir: Path) -> Path | None:
    """Return ``SKILL.md`` or ``SKILL.md.j2`` inside ``skill_dir`` if it exists.

    Example: ``find_skill_md(Path("catalog/core/skills/python-coding")).name`` -> ``"SKILL.md"``.
    """
    for name in SKILL_MD_NAMES:
        candidate = skill_dir / name
        if candidate.is_file():
            return candidate
    return None


def _declared_skill_id(skill_md: Path) -> str | ValueError:
    """The id the skill at ``skill_md`` merges under, or why its frontmatter cannot be read."""
    try:
        frontmatter, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    except (ValueError, yaml.YAMLError) as exc:
        return ValueError(f"{skill_md.name}: {exc}")
    return skill_id_of(Skill(frontmatter, body, None, None, ""))


def _home_error(problem: ValueError, rule_path: Path) -> RuleLoadError:
    return RuleLoadError(rule_path, f"its skill's {problem} (the rule has no skill to join)")
