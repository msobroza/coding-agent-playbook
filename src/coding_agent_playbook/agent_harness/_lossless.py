"""The lossless tier of ``playbook import-harness``: the manifest-entry readers.

A playbook-emitted tree carries ``.playbook/manifest.toml``, and every non-native
field (rule ``scope``/``globs``/..., prompt ``includes_rules``/..., skill
``extra_frontmatter`` and per-script ``executable`` bit, a hook's whole
definition) is rebuilt from its entry, keyed by the artifact's harness-relative
path (``specs/prH-agent-harness.md`` §C). Split out of :mod:`.importer` by AH-2
(#143); the importer passes its ``ImportResult`` in, so nothing here imports it back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.agent_harness._import_writes import (
    read_harness_md,
    restore_recorded_exec_bits,
)
from coding_agent_playbook.agent_harness.hook_sidecars import read_hook_sidecar
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.artifacts.member_reference import skill_member_location
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill, side_dirs_at

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.agent_harness.importer import ImportResult
    from coding_agent_playbook.agent_harness.manifest import Manifest, ManifestEntry


def read_lossless(
    root: Path, manifest: Manifest, result: ImportResult, *, source_package: str
) -> None:
    """Rebuild every artifact of the manifest's path -> entry index into ``result``.

    An entry with no file on disk, an unsupported kind or a hook that no longer
    parses is warned about and skipped.

    Example: ``read_lossless(root, manifest, result, source_package="<imported>")``.
    """
    for rel_path, entry in manifest.index_by_path().items():
        absolute = root / rel_path
        if not absolute.is_file():
            result.warnings.append(f"manifest entry {rel_path!r} has no file on disk; skipped")
        elif entry.kind == "rule":
            result.rules.append(_rule_from_entry(absolute, entry, source_package))
        elif entry.kind == "prompt":
            result.prompts.append(_prompt_from_entry(absolute, entry, source_package))
        elif entry.kind == "skill":
            result.skills.append(_skill_from_entry(absolute, entry, source_package))
        elif entry.kind == "hook":
            _read_hook(absolute, entry, result, source_package)
        else:  # eval_sample or unknown — no canonical adapter home
            result.warnings.append(
                f"manifest entry {rel_path!r} has unsupported kind {entry.kind!r}; skipped"
            )


def _description_from_disk(path: Path) -> str:
    """Read ``description`` from the leaf frontmatter (natively emitted, lossless)."""
    frontmatter, _ = read_harness_md(path)
    return str(frontmatter.get("description", ""))


def _body_from_entry(path: Path, entry: ManifestEntry) -> str:
    """The canonical source body, from the sidecar (the lossless source of truth).

    The harness leaf may rewrite/inline the body (e.g. a prompt's
    ``includes_rules`` are inlined into ``SKILL.md``), so the recorded entry body
    is authoritative. Fall back to the on-disk body only for legacy manifests
    that predate the recorded ``body`` field.
    """
    if entry.body is not None:
        return entry.body
    _, body = read_harness_md(path)
    return body


def _rule_from_entry(path: Path, entry: ManifestEntry, source_package: str) -> Rule:
    """Rebuild a ``Rule`` from the manifest entry (lossless source of truth).

    The harness leaf carries only ``description`` + a rendered body; every other
    canonical field — including ``name`` and the un-rendered source ``body`` —
    comes from the sidecar so reconstruction never depends on the rendered file.
    """
    description = _description_from_disk(path)
    body = _body_from_entry(path, entry)
    is_templated = bool(entry.is_templated) if entry.is_templated is not None else False
    home_skill = location_skill(entry.path, entry.id) if entry.skill is None else None
    return Rule(
        frontmatter=RuleFrontmatter(
            id=entry.id,
            # ``name`` is recorded in the sidecar (the harness rule file has no
            # ``name`` field); fall back to the id only for legacy manifests.
            name=entry.name if entry.name is not None else entry.id,
            description=description,
            scope="scoped" if entry.scope == "scoped" else "always",
            version=entry.version if entry.version is not None else 1,
            globs=list(entry.globs),
            applies_if=dict(entry.applies_if),
            priority=entry.priority if entry.priority is not None else 50,
            tags=list(entry.tags),
            lint_codes=dict(entry.lint_codes),
            skill=entry.skill if home_skill is None else home_skill,
            section=entry.section,
        ),
        body=body,
        template_body=body,
        is_templated=is_templated,
        source_path=path,
        source_package=source_package,
        # An entry at ``skills/<s>/rules/<id>.md`` without ``skill`` was placed by
        # location: a member of ``s`` with no authored ``skill:`` line (prU D22).
        home_skill=home_skill,
        skill_from_location=home_skill is not None,
    )


def location_skill(rel_path: str, rule_id: str) -> str | None:
    """The skill whose ``rules/`` holds ``rel_path`` (``skills/<s>/rules/<id>.md``), else None.

    Example: ``location_skill("skills/risk/rules/limits.md", "limits")`` -> ``"risk"``.
    """
    location = skill_member_location(rel_path)
    if location is None or location[1] != rule_id:
        return None
    return location[0]


def _prompt_from_entry(path: Path, entry: ManifestEntry, source_package: str) -> Prompt:
    """Rebuild a ``Prompt`` from the manifest entry (lossless source of truth).

    The harness leaf inlines ``includes_rules`` into its rendered ``SKILL.md``
    body, so the original un-inlined body and the ``is_templated`` flag come from
    the sidecar, NOT the on-disk file. ``name``/``description`` are natively
    emitted on the leaf; ``name`` is also recorded in the sidecar for uniformity.
    """
    frontmatter, _ = read_harness_md(path)
    body = _body_from_entry(path, entry)
    name = entry.name if entry.name is not None else str(frontmatter.get("name", entry.id))
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=entry.id,
            name=name,
            description=str(frontmatter.get("description", "")),
            slash=entry.slash if entry.slash is not None else entry.id,
            version=entry.version if entry.version is not None else 1,
            applies_if=dict(entry.applies_if),
            input_variables=[dict(v) for v in entry.input_variables],
            includes_rules=list(entry.includes_rules),
            eval_samples=list(entry.eval_samples),
            output_contract=list(entry.output_contract),
            write_scope=dict(entry.write_scope),
        ),
        body=body,
        template_body=body,
        is_templated=bool(entry.is_templated) if entry.is_templated is not None else False,
        source_path=path,
        source_package=source_package,
    )


def _skill_from_entry(path: Path, entry: ManifestEntry, source_package: str) -> Skill:
    """Rebuild a ``Skill`` (frontmatter + body + side dirs), restoring exec bits.

    ``name`` and the source ``body`` are taken from the sidecar (the lossless
    source of truth), falling back to the on-disk leaf only for legacy manifests.
    ``description`` is natively emitted on ``SKILL.md``.
    """
    frontmatter, _ = read_harness_md(path)
    body = _body_from_entry(path, entry)
    name = entry.name if entry.name is not None else str(frontmatter.get("name", entry.id))
    rebuilt: dict[str, Any] = {
        "id": entry.id,
        "name": name,
        "description": str(frontmatter.get("description", "")),
    }
    rebuilt.update(entry.extra_frontmatter)
    restore_recorded_exec_bits(path, entry)
    return Skill(
        frontmatter=rebuilt,
        body=body,
        source_package=source_package,
        **side_dirs_at(path.parent),
    )


def _read_hook(path: Path, entry: ManifestEntry, result: ImportResult, source_package: str) -> None:
    """Rebuild a hook from its sidecar entry; one that no longer parses is warned about and skipped."""
    try:
        hook = read_hook_sidecar(path, entry, source_package=source_package)
    except HookSchemaError as exc:
        result.warnings.append(f"manifest entry {entry.path!r}: {exc}; skipped")
        return
    result.hooks.append(hook)
