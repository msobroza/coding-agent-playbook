"""Artifact identity: the id and the template name an artifact is known by (H11).

- :func:`artifact_id_of` — the id the overlay merge keys collisions on, and that
  ``playbook render`` and the lockfile builder look provenance up by.
- :func:`template_source` — the name of an artifact's template in error messages.
- :func:`source_package_of` — the layer an artifact came from, for collision records.

A stdlib leaf: the rule registry imports :func:`template_source` from here, so
rendering never imports the sync context (split out of the sync orchestration module
in A5, specs/prT-package-layout.md 4.19).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule


def artifact_id_of(artifact: object) -> str:
    """Return the artifact's ID for collision tracking and provenance lookups.

    Rules/Prompts carry a dataclass frontmatter (``frontmatter.id``); Skills
    carry an open dict (``frontmatter["id"]``). Skills without an explicit id
    fall back to ``"skill"`` to mirror :meth:`Skill.to_prompt`'s behaviour.

    Public helper (no underscore) — ``commands/render.py`` reuses it when
    looking up overlay collisions by ID.
    """
    frontmatter = artifact.frontmatter  # type: ignore[attr-defined]
    if hasattr(frontmatter, "id"):
        return str(frontmatter.id)
    if isinstance(frontmatter, dict):
        return str(frontmatter.get("id", "skill"))
    raise TypeError(f"cannot extract id from artifact {artifact!r}")


def source_package_of(artifact: object) -> str:
    """The layer ``artifact`` came from (its ``source_package``), else ``"<unknown>"``.

    Public, unlike in the orchestration module it left: ``catalog.resolve`` records
    collision winners and losers with it (A5, a name that now crosses a package).
    Example: ``source_package_of(rule)`` -> ``"<repo-local>"``.
    """
    package = getattr(artifact, "source_package", None)
    return str(package) if package is not None else "<unknown>"


def template_source(artifact: Rule | Prompt) -> str:
    """Name ``artifact``'s template in error messages: its source path, else its id.

    Example: ``template_source(rule)`` -> ``"/repo/playbook/rules/x.md.j2"``.
    """
    path = artifact.source_path
    return str(path) if path is not None else artifact_id_of(artifact)
