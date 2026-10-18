"""Builders for a skill with member rules, shared by the writer, adapter and lockfile tests.

A member rule (ADR 0001) reaches its skill as a :class:`MemberReference`. These
builders make a composed skill without running ``compose_skills``, so each test
pins one seam: the writer, an adapter or the lockfile split
(specs/prS-skills-context.md 6.8.4-6.8.7).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook._member_reference import MemberReference
from coding_agent_playbook.skill_document import render_member_reference
from coding_agent_playbook.types import Skill

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

#: The ``playbook:`` block every sample member skill declares.
SAMPLE_PLAYBOOK_BLOCK: dict[str, str] = {
    "use_when": "editing Python code",
    "files": "Any Python file",
}


def sample_member_reference(
    rule_id: str = "python-typing",
    *,
    name: str = "Typing",
    description: str = "Prefer a concrete type or a Protocol to Any.",
    priority: int = 50,
    globs: Sequence[str] = ("**/*.py",),
    body: str = "# Python typing\n\nUse type hints.\n",
    source_package: str = "coding_agent_playbook",
) -> MemberReference:
    """One active member rule, its ``text`` rendered the way ``compose_skills`` renders it.

    Example: ``sample_member_reference("pytest").filename`` -> ``"pytest.md"``.
    """
    text = render_member_reference(rule_id, globs, body)
    return MemberReference(rule_id, name, description, priority, tuple(globs), text, source_package)


def sample_member_skill(
    skill_id: str = "python-coding",
    *members: MemberReference,
    references_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Skill:
    """A skill with a ``playbook:`` block and ``members`` attached, as sync writes it.

    Example: ``sample_member_skill("python-coding", sample_member_reference())``.
    """
    frontmatter: dict[str, Any] = {
        "id": skill_id,
        "name": skill_id,
        "description": "Library-agnostic Python conventions.",
        "playbook": dict(SAMPLE_PLAYBOOK_BLOCK),
        **(extra or {}),
    }
    body = "# Python coding\n\nPick the reference the task needs.\n"
    return Skill(frontmatter, body, None, references_dir, "coding_agent_playbook", tuple(members))


# --- a synthetic repo's own skill with member rules (tests/conftest.make_synthetic_repo) ---


def write_repo_member_skill(
    repo: Path,
    skill_id: str = "risk-models",
    *,
    description: str = "Conventions for the risk models.",
) -> Path:
    """Write ``playbook/skills/<skill_id>/SKILL.md`` with a ``playbook:`` block; return its dir.

    ``description`` is the authored capability sentence (one YAML plain scalar).

    Example: ``write_repo_member_skill(repo)`` -> ``repo/"playbook/skills/risk-models"``.
    """
    skill_dir = repo / "playbook" / "skills" / skill_id
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"id: {skill_id}\n"
        f"name: {skill_id}\n"
        f"description: {description}\n"
        "playbook:\n"
        "  use_when: changing a risk model\n"
        "  files: Risk model modules\n"
        "---\n"
        "# Risk models\n\nOpen the reference the change needs.\n",
        encoding="utf-8",
    )
    return skill_dir


def write_repo_member_rule(
    repo: Path,
    rule_id: str,
    *,
    skill_id: str = "risk-models",
    priority: int = 50,
    framework_gate: str | None = None,
) -> Path:
    """Write a scoped ``playbook/rules/<rule_id>.md.j2`` naming ``skill_id``; return its path.

    The body renders ``{{ project_name }}``, so a test can tell the rendered
    text from the template. ``framework_gate`` adds ``applies_if: has_framework``.

    Example: ``write_repo_member_rule(repo, "risk-click", framework_gate="click")``.
    """
    lines = [
        "---",
        f"id: {rule_id}",
        f"name: {rule_id.replace('-', ' ').capitalize()}",
        f"description: Follow the {rule_id} conventions.",
        "scope: scoped",
        f"skill: {skill_id}",
        'globs: ["src/risk/**/*.py"]',
        f"priority: {priority}",
    ]
    if framework_gate is not None:
        lines.extend(["applies_if:", "  has_framework:", f"    - {framework_gate}"])
    lines.extend(["---", f"# {rule_id}", "", "Applies in {{ project_name }}.", ""])
    target = repo / "playbook" / "rules" / f"{rule_id}.md.j2"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def skill_tree_bytes(skill_dir: Path) -> dict[str, bytes]:
    """Every file under ``skill_dir`` by POSIX relative path, to compare skill roots.

    Example: ``skill_tree_bytes(repo / ".claude/skills/risk-models")["SKILL.md"]``.
    """
    return {
        path.relative_to(skill_dir).as_posix(): path.read_bytes()
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file()
    }
