"""Shared builders for the rules/ layout checks R1-R6 (``validation._rule_layout``).

Minimal rule and skill files written into a layer, the resources layer of a
throwaway engine package, and the layout errors a repo yields, so
``test_rule_layout.py`` and the SPEC pin ``tests/unit/test_docs_rules_in_skills_spec.py``
build one fixture shape.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.validation._rule_layout import check_rule_layout

if TYPE_CHECKING:
    from coding_agent_playbook.validation.findings import ValidationError

_RULE = "---\nid: {id}\nname: {id}\ndescription: d\nscope: {scope}\n{extra}---\nBody\n"
_SKILL = "---\nid: {id}\nname: {id}\ndescription: d\n{block}---\nBody\n"
#: A minimal ``playbook:`` block, so the skill can take member rules.
PLAYBOOK_BLOCK = "playbook:\n  files: f\n"


def write_file(path: Path, text: str) -> Path:
    """Write ``text`` to ``path``, creating its parents; returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_skill(layer: Path, skill_id: str, *, block: str = PLAYBOOK_BLOCK) -> Path:
    """Write ``<layer>/skills/<skill_id>/SKILL.md``; returns the skill directory.

    Example: ``write_skill(repo / "playbook", "s") / "rules"`` is the skill's rules/.
    """
    skill_dir = layer / "skills" / skill_id
    write_file(skill_dir / "SKILL.md", _SKILL.format(id=skill_id, block=block))
    return skill_dir


def write_rule(
    path: Path,
    rule_id: str,
    *,
    scope: Literal["always", "scoped"] = "scoped",
    extra: str = "",
) -> Path:
    """Write a rule with ``rule_id`` at ``path``; ``extra`` adds frontmatter lines.

    Example: ``write_rule(rules_dir / "r.md", "r", extra="skill: t\\n")``.
    """
    return write_file(path, _RULE.format(id=rule_id, scope=scope, extra=extra))


def engine_resources(engine: str) -> Path:
    """The ``resources`` layer of the importable package ``engine``."""
    module = importlib.import_module(engine)
    assert module.__file__ is not None, f"package {engine!r} has no __file__"
    return Path(module.__file__).parent / "resources"


def layout_errors(repo: Path, engine: str) -> list[ValidationError]:
    """The R1-R6 findings for ``repo`` over the layers of ``engine``."""
    source = FileSystemArtifactSource(repo_root=repo, engine_package=engine)
    rules, _ = source.collect_rules()
    return check_rule_layout(rules, source)
