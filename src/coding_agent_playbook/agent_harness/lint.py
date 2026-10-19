"""The structural lint behind ``playbook validate-harness`` (AH-2, #143).

``harnesses-ref``-equivalent checks on a parsed Agent Harness tree
(``specs/prH-agent-harness.md`` §A, Track H4). The root's own ``name`` and
``description`` are checked by :func:`~.parser.parse_harness`, which raises
when either is empty, so the lint starts from a parsed :class:`HarnessTree`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.models import ContentFile, SkillLeaf

if TYPE_CHECKING:
    from coding_agent_playbook.agent_harness.models import HarnessDirectory, HarnessTree


@dataclass(frozen=True, slots=True)
class HarnessFinding:
    """One lint finding, anchored at a path (a string, as the report prints it)."""

    path: str
    message: str


@dataclass(frozen=True, slots=True)
class HarnessFindings:
    """Every finding of one lint run: ``errors`` always fail, ``warnings`` only under strict."""

    errors: tuple[HarnessFinding, ...] = ()
    warnings: tuple[HarnessFinding, ...] = ()

    def failed(self, *, strict: bool) -> bool:
        """Errors fail; with ``strict``, warnings fail too (``validate-harness --strict``).

        ``strict`` is a reporting choice, not a lint input (AH-D3), so it lives here.

        Example: ``HarnessFindings(warnings=(finding,)).failed(strict=True) is True``.
        """
        return bool(self.errors) or (strict and bool(self.warnings))


def lint_harness(tree: HarnessTree) -> HarnessFindings:
    """Skill leaves without name or description are errors; missing routing files and
    undescribed content are warnings; opaque ``.harnessleaf`` directories are never inspected.

    Example: ``lint_harness(parse_harness(Path("build/harness"))).errors == ()``.
    """
    errors: list[HarnessFinding] = []
    warnings: list[HarnessFinding] = []
    for directory in tree.directories:
        _check_skill_leaves(directory, errors)
        _check_routing_and_content(directory, warnings)
    return HarnessFindings(errors=tuple(errors), warnings=tuple(warnings))


def _check_skill_leaves(directory: HarnessDirectory, errors: list[HarnessFinding]) -> None:
    """Recurse a grouping directory, flagging skill leaves with empty metadata."""
    if directory.is_opaque:
        return
    for leaf in directory.leaves:
        if isinstance(leaf, SkillLeaf):
            errors.extend(_skill_leaf_errors(leaf))
    for child in directory.children:
        _check_skill_leaves(child, errors)


def _skill_leaf_errors(leaf: SkillLeaf) -> list[HarnessFinding]:
    """One error per empty ``name`` / ``description`` field, in that order."""
    fields = {"name": leaf.name, "description": leaf.description}
    return [
        HarnessFinding(str(leaf.path), f"skill leaf has empty {field!r}")
        for field, value in fields.items()
        if not value
    ]


def _check_routing_and_content(directory: HarnessDirectory, warnings: list[HarnessFinding]) -> None:
    """Recurse a grouping directory, warning on a missing routing file or description.

    Routing presence is an existence check on the model's ``path`` +
    ``routing_file_name``: a parsed directory's ``description`` is ``None`` both
    when its routing file is absent and when it has no ``description``.
    """
    if directory.is_opaque:
        return
    if not (directory.path / directory.routing_file_name).is_file():
        message = f"grouping directory lacks its routing file {directory.routing_file_name!r}"
        warnings.append(HarnessFinding(str(directory.path), message))
    warnings.extend(
        HarnessFinding(str(item.path), "content '.md' lacks a 'description'")
        for item in directory.content
        if isinstance(item, ContentFile) and not item.description
    )
    for child in directory.children:
        _check_routing_and_content(child, warnings)
