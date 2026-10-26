"""Skill directories of a layer and the member rule files inside them (prU D5, ADR 0005).

A rule at ``<layer>/skills/<dir>/rules/**/<id>.md[.j2]`` is a member of the
skill that ``<dir>/SKILL.md`` declares: the directory sets membership, so the
file needs no ``skill:`` key. Only a directory holding ``SKILL.md`` (or
``SKILL.md.j2``) counts; :func:`iter_skill_dirs` is the one walk that both
``catalog.source._iter_skills`` and :func:`iter_skill_rule_files` use, so the
two never disagree on which directories are skills. A ``rules/`` directory
without a ``SKILL.md`` contributes nothing here (R4 reports it). Split out of
``catalog/source.py`` for its file-size budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.identity import artifact_id_of
from coding_agent_playbook.artifacts.skill import Skill

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: ``SKILL.md`` names a skill directory may hold, in lookup order.
SKILL_MD_NAMES = ("SKILL.md", "SKILL.md.j2")


def iter_md_files(root: Path) -> Iterator[Path]:
    """Yield ``*.md`` and ``*.md.j2`` files under ``root`` in deterministic order.

    Example: ``list(iter_md_files(Path("playbook/rules")))`` -> ``[PosixPath('playbook/rules/x.md')]``.
    """
    # rglob builds every result from root's own parts, so the names below root are
    # path.parts[depth:]: what relative_to(root).parts gave, without walking both
    # paths' parents per file: 98 ms -> 23 ms over the 4 roots (405 files) a
    # sync's link gate lists, CPython 3.12.
    depth = len(root.parts)
    for path in sorted(root.rglob("*.md*")):
        # Skip dotted directories (.git, .venv, node_modules-of-vendored-skills,
        # etc.) for hygiene — these never legitimately contain canonical
        # artifacts, and walking them silently inflates source listings.
        if any(part.startswith(".") for part in path.parts[depth:]):
            continue
        # Note: case-sensitive on Linux/macOS APFS (lowercase .md convention).
        # Banking deployments on case-insensitive volumes may need to revisit.
        if path.name.endswith(".md") or path.name.endswith(".md.j2"):
            yield path


def find_skill_md(skill_dir: Path) -> Path | None:
    """Return ``SKILL.md`` or ``SKILL.md.j2`` inside ``skill_dir`` if it exists.

    Example: ``find_skill_md(Path("catalog/core/skills/python-coding")).name`` -> ``"SKILL.md"``.
    """
    for name in SKILL_MD_NAMES:
        candidate = skill_dir / name
        if candidate.is_file():
            return candidate
    return None


def iter_skill_dirs(skills_root: Path) -> Iterator[tuple[Path, Path]]:
    """Yield ``(skill dir, its SKILL.md)`` for each subdirectory of ``skills_root`` that is a skill.

    Example: ``next(iter_skill_dirs(Path("playbook/skills")))[1].name`` -> ``"SKILL.md"``.
    """
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill_md = find_skill_md(skill_dir)
        if skill_md is not None:
            yield skill_dir, skill_md


def read_skill_md(skill_md: Path) -> Skill:
    """The frontmatter and body of ``skill_md`` as a bare ``Skill`` (no scripts, no layer).

    The one parse that :func:`declared_skill_id` and the R4 layout check share.
    Raises ``ValueError`` or ``yaml.YAMLError`` when its frontmatter cannot be read.

    Example: ``read_skill_md(Path("catalog/core/skills/python-coding/SKILL.md")).frontmatter["id"]``
    -> ``"python-coding"``.
    """
    frontmatter, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    return Skill(frontmatter, body, None, None, "")


def declared_skill_id(skill_md: Path) -> str:
    """The id the skill at ``skill_md`` merges under (the overlay-merge key, ``artifact_id_of``).

    Raises ``ValueError`` or ``yaml.YAMLError`` when its frontmatter cannot be read.

    Example: ``declared_skill_id(Path("catalog/core/skills/python-coding/SKILL.md"))`` -> ``"python-coding"``.
    """
    return artifact_id_of(read_skill_md(skill_md))


def iter_skill_rule_files(skills_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(home skill id, rule path)`` for each rule file under ``skills_root/*/rules/``.

    Skill directories come in sorted order and :func:`iter_md_files` (which
    skips dot directories) orders the files inside each, so the result is
    deterministic. The id is the one the merge files the skill under, not the
    directory name. A skill whose ``SKILL.md`` cannot be parsed contributes no
    rule: ``list_skills`` raises on that ``SKILL.md`` itself, so it is reported.

    Example::

        >>> list(iter_skill_rule_files(Path("playbook/skills")))  # doctest: +SKIP
        [('python-coding', PosixPath('playbook/skills/python-coding/rules/x.md'))]
    """
    for skill_dir, skill_md in iter_skill_dirs(skills_root):
        rules_dir = skill_dir / "rules"
        if not rules_dir.is_dir():
            continue
        try:
            home = declared_skill_id(skill_md)
        except (ValueError, yaml.YAMLError):
            continue
        yield from ((home, path) for path in iter_md_files(rules_dir))
