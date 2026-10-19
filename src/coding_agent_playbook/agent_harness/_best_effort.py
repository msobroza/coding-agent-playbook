"""The best-effort walk of ``playbook import-harness``: a foreign harness, no sidecar.

Kinds are inferred from directory placement (skill leaf -> ``Skill``; ``prompts/*``
-> ``Prompt``; ``rules/*.md`` -> ``Rule`` scope=always; ``references/*.md`` ->
``Rule`` scope=scoped; raw/non-md -> opaque asset), and every lossy assumption is
collected as a warning. Split out of :mod:`.importer` by AH-1 (#134), which kept
that module under its 500-line budget (specs/prT-package-layout.md 4.6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness._import_hooks import guardrail_warning
from coding_agent_playbook.agent_harness.importer import (
    IMPORTED_SOURCE_PACKAGE,
    ImportResult,
    _read_md,
    _strip_sentinel,
)
from coding_agent_playbook.agent_harness.models import LeafMarker, RawAsset, SkillLeaf
from coding_agent_playbook.agent_harness.parser import parse_harness
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.agent_harness.models import (
        ContentFile,
        Harness,
        HarnessDirectory,
    )


# --- best-effort reconstruction (no manifest) ------------------------------


def _import_best_effort(root: Path) -> ImportResult:
    """Infer canonical artifacts from a foreign harness's directory structure."""
    harness = parse_harness(root)
    result = ImportResult()
    result.warnings.append(
        "no .playbook/manifest.toml sidecar found; reconstructing best-effort. "
        "Non-native fields (rule scope/globs/priority, prompt includes_rules, "
        "skill extra frontmatter, script exec bits) are inferred or defaulted."
    )
    _walk_harness(harness, result)
    return result


def _walk_harness(harness: Harness, result: ImportResult) -> None:
    for directory in harness.directories:
        _walk_directory(directory, result)


def _walk_directory(directory: HarnessDirectory, result: ImportResult) -> None:
    top = _top_level_name(directory)
    # A directory carrying a ``.harnessleaf`` marker FOR ITSELF is opaque: the
    # parser records a LeafMarker at the directory's own path and does not
    # recurse. Treat the whole unit as opaque — skip its content too — and warn.
    if any(
        isinstance(leaf, LeafMarker) and leaf.path == directory.path for leaf in directory.leaves
    ):
        result.warnings.append(
            f"opaque directory {directory.name!r} (.harnessleaf) skipped — no canonical mapping"
        )
        return
    for leaf in directory.leaves:
        if isinstance(leaf, SkillLeaf):
            _best_effort_leaf(leaf, top, result)
        elif isinstance(leaf, LeafMarker):
            result.warnings.append(
                f"opaque leaf {leaf.path.name!r} (.harnessleaf) skipped — no canonical mapping"
            )
    for item in directory.content:
        _best_effort_content(item, top, result)
    for child in directory.children:
        _walk_directory(child, result)


def _top_level_name(directory: HarnessDirectory) -> str:
    """The branch's top-level dir name, recovered from the routing-file name."""
    return directory.routing_file_name.removesuffix(".md").lower()


def _best_effort_leaf(leaf: SkillLeaf, top: str, result: ImportResult) -> None:
    """A skill leaf -> ``Skill`` (prompts/ leaves are skill-shaped too -> Prompt)."""
    body = _strip_sentinel(leaf.body)
    if top == "prompts":
        slash = leaf.path.name
        result.warnings.append(
            f"prompt {slash!r}: includes_rules/input_variables/version not recoverable "
            "without sidecar; defaulted"
        )
        result.prompts.append(
            Prompt(
                frontmatter=PromptFrontmatter(
                    id=slash,
                    name=leaf.name or slash,
                    description=leaf.description,
                    slash=slash,
                ),
                body=body,
                template_body=body,
                is_templated=False,
                source_path=leaf.path / "SKILL.md",
                source_package=IMPORTED_SOURCE_PACKAGE,
            )
        )
        return

    skill_id = leaf.path.name
    result.warnings.append(
        f"skill {skill_id!r}: extra frontmatter + script exec bits not recoverable "
        "without sidecar; using on-disk bits as-is"
    )
    scripts_dir = leaf.path / "scripts"
    references_dir = leaf.path / "references"
    result.skills.append(
        Skill(
            frontmatter={
                "id": skill_id,
                "name": leaf.name or skill_id,
                "description": leaf.description,
            },
            body=body,
            scripts_dir=scripts_dir if scripts_dir.is_dir() else None,
            references_dir=references_dir if references_dir.is_dir() else None,
            source_package=IMPORTED_SOURCE_PACKAGE,
        )
    )


def _best_effort_content(item: ContentFile | RawAsset, top: str, result: ImportResult) -> None:
    """Markdown content -> ``Rule`` (scope from dir placement); raw -> opaque asset."""
    if isinstance(item, RawAsset):
        result.raw_assets.append(item.path)
        result.warnings.append(
            f"raw asset {item.path.name!r}: no canonical home; copied as opaque passthrough"
        )
        return

    frontmatter, body = _read_md(item.path)
    rule_id = item.filename.removesuffix(".md.j2").removesuffix(".md")
    # The emitter prefixes always-rules with ``<priority>-``; strip a leading
    # ``NN-`` so the canonical id matches what was emitted.
    rule_id = _strip_priority_prefix(rule_id)
    scope = "scoped" if top == "references" else "always"
    if (lossy := guardrail_warning(rule_id)) is not None:
        result.warnings.append(lossy)
    skill_hint = "; a scoped rule needs 'skill: <skill-id>' before playbook sync accepts it"
    result.warnings.append(
        f"rule {rule_id!r}: scope inferred as {scope!r} from {top}/ placement; "
        "globs/applies_if/priority/tags/version not recoverable without sidecar"
        + (skill_hint if scope == "scoped" else "")
    )
    result.rules.append(
        Rule(
            frontmatter=RuleFrontmatter(
                id=rule_id,
                name=rule_id,
                description=str(frontmatter.get("description", "")),
                scope=scope,  # type: ignore[arg-type]
            ),
            body=body,
            template_body=body,
            is_templated=item.filename.endswith(".md.j2"),
            source_path=item.path,
            source_package=IMPORTED_SOURCE_PACKAGE,
        )
    )


def _strip_priority_prefix(name: str) -> str:
    """Drop a leading ``NN-`` priority prefix from an always-rule filename stem."""
    head, sep, tail = name.partition("-")
    if sep and head.isdigit():
        return tail
    return name
