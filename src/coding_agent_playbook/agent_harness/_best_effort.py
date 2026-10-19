"""The best-effort tier of ``playbook import-harness``: a foreign harness, no sidecar.

Kinds are inferred from directory placement (skill leaf -> ``Skill``; ``prompts/*``
-> ``Prompt``; ``rules/*.md`` -> ``Rule`` scope=always; ``references/*.md`` ->
``Rule`` scope=scoped; raw/non-md -> opaque asset), and every lossy assumption is
collected as a warning. A ``guardrail-*`` rule file is only a degraded hook
advisory, so its import as a ``Rule`` is flagged as lossy too. AH-1 (#134) split
this walk out of :mod:`.importer`; AH-2 (#143) has the importer pass its
``ImportResult`` in, so this module no longer imports it back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness._import_writes import read_harness_md, strip_sentinel
from coding_agent_playbook.agent_harness.models import LeafMarker, RawAsset, SkillLeaf
from coding_agent_playbook.agent_harness.parser import parse_harness
from coding_agent_playbook.artifacts.hook_schema import ADVISORY_RULE_PREFIX
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.agent_harness.importer import ImportResult
    from coding_agent_playbook.agent_harness.models import ContentFile, HarnessDirectory

_NO_SIDECAR = (
    "no .playbook/manifest.toml sidecar found; reconstructing best-effort. "
    "Non-native fields (rule scope/globs/priority, prompt includes_rules, "
    "skill extra frontmatter, script exec bits) are inferred or defaulted."
)


def read_best_effort(root: Path, result: ImportResult, *, source_package: str) -> None:
    """Infer canonical artifacts from a foreign harness's directory structure into ``result``.

    Example: ``read_best_effort(root, result, source_package="<imported>")``.
    """
    tree = parse_harness(root)
    result.warnings.append(_NO_SIDECAR)
    for directory in tree.directories:
        _walk_directory(directory, result, source_package)


def guardrail_warning(rule_id: str) -> str | None:
    """The lossiness warning for a best-effort rule that is really a hook advisory, else None.

    Example::

        >>> guardrail_warning("guardrail-x") is not None, guardrail_warning("typing")
        (True, None)
    """
    if not rule_id.startswith(ADVISORY_RULE_PREFIX):
        return None
    return (
        f"rule {rule_id!r}: looks like a degraded hook advisory; the canonical hook "
        "cannot be reconstructed without .playbook/manifest.toml"
    )


def _walk_directory(directory: HarnessDirectory, result: ImportResult, source_package: str) -> None:
    # An opaque directory (.harnessleaf for itself) is not recursed by the parser
    # either: skip the whole unit, its own content included, and warn.
    if directory.is_opaque:
        result.warnings.append(
            f"opaque directory {directory.name!r} (.harnessleaf) skipped — no canonical mapping"
        )
        return
    top = _top_level_name(directory)
    for leaf in directory.leaves:
        if isinstance(leaf, SkillLeaf):
            _best_effort_leaf(leaf, top, result, source_package)
        elif isinstance(leaf, LeafMarker):
            result.warnings.append(
                f"opaque leaf {leaf.path.name!r} (.harnessleaf) skipped — no canonical mapping"
            )
    for item in directory.content:
        _best_effort_content(item, top, result, source_package)
    for child in directory.children:
        _walk_directory(child, result, source_package)


def _top_level_name(directory: HarnessDirectory) -> str:
    """The branch's top-level dir name, recovered from the routing-file name."""
    return directory.routing_file_name.removesuffix(".md").lower()


def _best_effort_leaf(leaf: SkillLeaf, top: str, result: ImportResult, source_package: str) -> None:
    """A skill leaf -> ``Skill`` (prompts/ leaves are skill-shaped too -> Prompt)."""
    if top == "prompts":
        _best_effort_prompt(leaf, result, source_package)
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
            body=strip_sentinel(leaf.body),
            scripts_dir=scripts_dir if scripts_dir.is_dir() else None,
            references_dir=references_dir if references_dir.is_dir() else None,
            source_package=source_package,
        )
    )


def _best_effort_prompt(leaf: SkillLeaf, result: ImportResult, source_package: str) -> None:
    """A ``prompts/<slash>/`` leaf -> ``Prompt`` with defaulted non-native fields."""
    slash = leaf.path.name
    body = strip_sentinel(leaf.body)
    result.warnings.append(
        f"prompt {slash!r}: includes_rules/input_variables/version not recoverable "
        "without sidecar; defaulted"
    )
    result.prompts.append(
        Prompt(
            frontmatter=PromptFrontmatter(
                id=slash, name=leaf.name or slash, description=leaf.description, slash=slash
            ),
            body=body,
            template_body=body,
            is_templated=False,
            source_path=leaf.path / "SKILL.md",
            source_package=source_package,
        )
    )


def _best_effort_content(
    item: ContentFile | RawAsset, top: str, result: ImportResult, source_package: str
) -> None:
    """Markdown content -> ``Rule`` (scope from dir placement); raw -> opaque asset."""
    if isinstance(item, RawAsset):
        result.raw_assets.append(item.path)
        result.warnings.append(
            f"raw asset {item.path.name!r}: no canonical home; copied as opaque passthrough"
        )
        return
    frontmatter, body = read_harness_md(item.path)
    # The emitter prefixes always-rules with ``<priority>-``; strip a leading
    # ``NN-`` so the canonical id matches what was emitted.
    rule_id = _strip_priority_prefix(item.filename.removesuffix(".md.j2").removesuffix(".md"))
    scope = "scoped" if top == "references" else "always"
    if (lossy := guardrail_warning(rule_id)) is not None:
        result.warnings.append(lossy)
    result.warnings.append(_scope_warning(rule_id, scope, top))
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
            source_package=source_package,
        )
    )


def _scope_warning(rule_id: str, scope: str, top: str) -> str:
    """The lossiness warning of a best-effort rule; a scoped one also needs a ``skill:``."""
    skill_hint = "; a scoped rule needs 'skill: <skill-id>' before playbook sync accepts it"
    return (
        f"rule {rule_id!r}: scope inferred as {scope!r} from {top}/ placement; "
        "globs/applies_if/priority/tags/version not recoverable without sidecar"
        + (skill_hint if scope == "scoped" else "")
    )


def _strip_priority_prefix(name: str) -> str:
    """Drop a leading ``NN-`` priority prefix from an always-rule filename stem."""
    head, sep, tail = name.partition("-")
    if sep and head.isdigit():
        return tail
    return name
