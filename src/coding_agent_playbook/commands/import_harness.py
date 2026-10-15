"""``playbook import-harness <path> [--into <dir>]`` (PR H Track H3).

Parses an Agent Harness tree back into canonical ``Rule`` / ``Prompt`` / ``Skill``
(and, from the sidecar, ``Hook``: :mod:`._import_hooks`) artifacts and writes
them into an overlay directory (default ``playbook/``) in the
:class:`~coding_agent_playbook.sources.filesystem.FileSystemArtifactSource` layout,
so a later ``playbook sync`` can re-read them.

Two fidelity tiers (``specs/prH-agent-harness.md`` §C):

- **Lossless** — when a ``.playbook/manifest.toml`` sidecar is present, every
  non-native field (rule ``scope``/``globs``/..., prompt ``includes_rules``/...,
  skill ``extra_frontmatter`` + per-script ``executable`` bit) is rebuilt from
  the manifest, keyed by each artifact's harness-relative path. Script exec bits
  are restored on POSIX (``os.chmod(p, mode | 0o111)``; no-op on Windows).
- **Best-effort** — no sidecar (a foreign harness): kinds are inferred from
  directory placement (skill leaf -> ``Skill``; ``prompts/*`` -> ``Prompt``;
  ``rules/*.md`` -> ``Rule`` scope=always; ``references/*.md`` -> ``Rule``
  scope=scoped; raw/non-md -> opaque asset). Non-native fields are defaulted and
  every lossy assumption is collected as a warning and reported to stderr — the
  importer never silently guesses (CLAUDE.md).

The parsing/reconstruction core (:func:`import_harness` -> :class:`ImportResult`)
is kept separate from file writing so callers (and the round-trip test) can assert
on the reconstructed objects directly.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.commands._import_files import (
    copy_tree,
    harness_root_for,
    restore_exec_bit,
)
from coding_agent_playbook.commands._import_hooks import (
    guardrail_warning,
    hook_from_entry,
    write_hook,
)
from coding_agent_playbook.harness.manifest import Manifest, ManifestEntry, read_manifest
from coding_agent_playbook.harness.models import (
    ContentFile,
    Harness,
    HarnessDirectory,
    LeafMarker,
    NotAHarnessError,
    RawAsset,
    SkillLeaf,
)
from coding_agent_playbook.harness.parser import parse_harness
from coding_agent_playbook.types import (
    Hook,
    HookSchemaError,
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
    split_frontmatter,
)

if TYPE_CHECKING:
    import argparse

#: Source-package marker recorded on every imported artifact.
IMPORTED_SOURCE_PACKAGE = "<imported>"

_SENTINEL_PREFIX = f"{sentinel_line('html')}\n\n"


@dataclass
class ImportResult:
    """Reconstructed canonical artifacts plus any lossiness warnings.

    ``raw_assets`` are non-markdown passthrough files (a foreign harness may
    ship binaries with no canonical home); they are written verbatim but cannot
    be re-read as canonical artifacts.
    """

    rules: list[Rule] = field(default_factory=list)
    prompts: list[Prompt] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)
    raw_assets: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --- body helpers ----------------------------------------------------------


def _strip_sentinel(body: str) -> str:
    """Drop the leading ``<!-- SENTINEL -->`` line the emitter places.

    The adapter writes the sentinel as the first body line (frontmatter must
    stay on line 1). A foreign harness has no sentinel, so this is a no-op then.
    """
    if body.startswith(_SENTINEL_PREFIX):
        return body[len(_SENTINEL_PREFIX) :]
    return body


def _read_md(path: Path) -> tuple[dict[str, Any], str]:
    """Split a harness ``.md`` into (frontmatter, sentinel-stripped body).

    A foreign harness's content file may legitimately carry no frontmatter
    (``description`` is optional). In that case the whole text is the body and
    the frontmatter is empty — never raise on a fenceless content file.
    """
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, raw_body = split_frontmatter(text)
    except ValueError:
        return {}, _strip_sentinel(text)
    return frontmatter, _strip_sentinel(raw_body)


# --- lossless reconstruction (manifest present) ----------------------------


def _description_from_disk(path: Path) -> str:
    """Read ``description`` from the leaf frontmatter (natively emitted, lossless)."""
    frontmatter, _ = _read_md(path)
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
    _, body = _read_md(path)
    return body


def _rule_from_entry(path: Path, entry: ManifestEntry) -> Rule:
    """Rebuild a ``Rule`` from the manifest entry (lossless source of truth).

    The harness leaf carries only ``description`` + a rendered body; every other
    canonical field — including ``name`` and the un-rendered source ``body`` —
    comes from the sidecar so reconstruction never depends on the rendered file.
    """
    description = _description_from_disk(path)
    body = _body_from_entry(path, entry)
    is_templated = bool(entry.is_templated) if entry.is_templated is not None else False
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
        ),
        body=body,
        template_body=body,
        is_templated=is_templated,
        source_path=path,
        source_package=IMPORTED_SOURCE_PACKAGE,
    )


def _prompt_from_entry(path: Path, entry: ManifestEntry) -> Prompt:
    """Rebuild a ``Prompt`` from the manifest entry (lossless source of truth).

    The harness leaf inlines ``includes_rules`` into its rendered ``SKILL.md``
    body, so the original un-inlined body and the ``is_templated`` flag come from
    the sidecar, NOT the on-disk file. ``name``/``description`` are natively
    emitted on the leaf; ``name`` is also recorded in the sidecar for uniformity.
    """
    frontmatter, _ = _read_md(path)
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
            eval_tasks=list(entry.eval_tasks),
            output_contract=list(entry.output_contract),
        ),
        body=body,
        template_body=body,
        is_templated=bool(entry.is_templated) if entry.is_templated is not None else False,
        source_path=path,
        source_package=IMPORTED_SOURCE_PACKAGE,
    )


def _skill_from_entry(path: Path, entry: ManifestEntry) -> Skill:
    """Rebuild a ``Skill`` (frontmatter + body + side dirs), restoring exec bits.

    ``name`` and the source ``body`` are taken from the sidecar (the lossless
    source of truth), falling back to the on-disk leaf only for legacy manifests.
    ``description`` is natively emitted on ``SKILL.md``.
    """
    frontmatter, _ = _read_md(path)
    body = _body_from_entry(path, entry)
    name = entry.name if entry.name is not None else str(frontmatter.get("name", entry.id))
    rebuilt: dict[str, Any] = {
        "id": entry.id,
        "name": name,
        "description": str(frontmatter.get("description", "")),
    }
    rebuilt.update(entry.extra_frontmatter)

    skill_dir = path.parent
    harness_root = harness_root_for(path, entry.path)
    for script in entry.scripts:
        if script.executable:
            restore_exec_bit(harness_root / script.path)

    scripts_dir = skill_dir / "scripts"
    references_dir = skill_dir / "references"
    return Skill(
        frontmatter=rebuilt,
        body=body,
        scripts_dir=scripts_dir if scripts_dir.is_dir() else None,
        references_dir=references_dir if references_dir.is_dir() else None,
        source_package=IMPORTED_SOURCE_PACKAGE,
    )


def _import_lossless(root: Path, manifest: Manifest) -> ImportResult:
    """Rebuild every artifact from the manifest's path -> entry index."""
    result = ImportResult()
    index = manifest.index_by_path()
    for rel_path, entry in index.items():
        absolute = root / rel_path
        if not absolute.is_file():
            result.warnings.append(f"manifest entry {rel_path!r} has no file on disk; skipped")
            continue
        if entry.kind == "rule":
            result.rules.append(_rule_from_entry(absolute, entry))
        elif entry.kind == "prompt":
            result.prompts.append(_prompt_from_entry(absolute, entry))
        elif entry.kind == "skill":
            result.skills.append(_skill_from_entry(absolute, entry))
        elif entry.kind == "hook":
            _import_hook(root, absolute, entry, result)
        else:  # eval_task or unknown — no canonical adapter home
            result.warnings.append(
                f"manifest entry {rel_path!r} has unsupported kind {entry.kind!r}; skipped"
            )
    return result


def _import_hook(root: Path, absolute: Path, entry: ManifestEntry, result: ImportResult) -> None:
    """Rebuild a hook from its sidecar entry; one that no longer parses is warned about and skipped."""
    try:
        hook = hook_from_entry(
            absolute, entry, harness_root=root, source_package=IMPORTED_SOURCE_PACKAGE
        )
    except HookSchemaError as exc:
        result.warnings.append(f"manifest entry {entry.path!r}: {exc}; skipped")
        return
    result.hooks.append(hook)


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
    result.warnings.append(
        f"rule {rule_id!r}: scope inferred as {scope!r} from {top}/ placement; "
        "globs/applies_if/priority/tags/version not recoverable without sidecar"
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


# --- public core -----------------------------------------------------------


def import_harness(harness_root: Path) -> ImportResult:
    """Parse the harness at ``harness_root`` into canonical artifacts.

    Uses the ``.playbook/manifest.toml`` sidecar for lossless reconstruction when
    present, else falls back to best-effort structural inference (surfacing the
    lossiness as warnings).

    Raises:
        NotAHarnessError: when ``harness_root`` has no ``HARNESS.md``.
    """
    if not (harness_root / "HARNESS.md").is_file():
        raise NotAHarnessError(f"no HARNESS.md at {harness_root}")
    manifest = read_manifest(harness_root)
    if manifest is not None:
        return _import_lossless(harness_root, manifest)
    return _import_best_effort(harness_root)


# --- file writing ----------------------------------------------------------


def _write_rule(rule: Rule, into: Path) -> None:
    # ALL rules (always + scoped) go under ``rules/``: that is the only directory
    # ``FileSystemArtifactSource.list_rules`` reads, so a scoped rule written to
    # ``references/`` would be silently dropped on the next ``playbook sync``.
    # ``scope`` lives in the frontmatter that ``to_markdown`` emits, so a scoped
    # rule stays scoped without needing a separate directory.
    suffix = ".md.j2" if rule.is_templated else ".md"
    target = into / "rules" / f"{rule.frontmatter.id}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rule.to_markdown(), encoding="utf-8")


def _write_prompt(prompt: Prompt, into: Path) -> None:
    suffix = ".md.j2" if prompt.is_templated else ".md"
    target = into / "prompts" / f"{prompt.frontmatter.id}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(prompt.to_markdown(), encoding="utf-8")


def _write_skill(skill: Skill, into: Path) -> None:
    skill_id = str(skill.frontmatter.get("id", "skill"))
    skill_dir = into / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skill, skill_dir / "SKILL.md")
    if skill.scripts_dir is not None and skill.scripts_dir.is_dir():
        copy_tree(skill.scripts_dir, skill_dir / "scripts", restore_exec=True)
    if skill.references_dir is not None and skill.references_dir.is_dir():
        copy_tree(skill.references_dir, skill_dir / "references", restore_exec=False)


def _write_skill_md(skill: Skill, target: Path) -> None:
    """Write SKILL.md with the skill's full (reconstructed) frontmatter + body."""
    from coding_agent_playbook.types import format_frontmatter

    target.write_text(format_frontmatter(dict(skill.frontmatter), skill.body), encoding="utf-8")


def _write_raw_asset(asset: Path, into: Path) -> None:
    import shutil

    target = into / "references" / asset.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(asset, target)


def _write_result(result: ImportResult, into: Path) -> None:
    for rule in result.rules:
        _write_rule(rule, into)
    for prompt in result.prompts:
        _write_prompt(prompt, into)
    for skill in result.skills:
        _write_skill(skill, into)
    for hook in result.hooks:
        write_hook(hook, into)
    for asset in result.raw_assets:
        _write_raw_asset(asset, into)


# --- CLI entry -------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    """``playbook import-harness <path> [--into <dir>]`` (SPEC §12)."""
    raw_path = getattr(args, "path", None)
    if not raw_path:
        print("error: import-harness requires a harness path", file=sys.stderr)
        return 2
    harness_root = Path(raw_path)
    into = Path(args.into) if getattr(args, "into", None) else Path.cwd() / "playbook"

    if not harness_root.is_dir():
        print(f"error: {harness_root} is not a directory", file=sys.stderr)
        return 2
    try:
        result = import_harness(harness_root)
    except NotAHarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _write_result(result, into)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    count = len(result.rules) + len(result.prompts) + len(result.skills) + len(result.hooks)
    print(
        f"imported {count} artifact(s) into {into} "
        f"({len(result.rules)} rules, {len(result.prompts)} prompts, "
        f"{len(result.skills)} skills, {len(result.hooks)} hooks)"
    )
    return 0
