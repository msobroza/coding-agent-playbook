"""The catalog as the docs site shows it: plain records, loaded through the engine's readers.

The page renderer (``catalog_pages``) reads only these records. A change to the
engine's artifact models touches :func:`load_snapshot` and nothing else, and the
tests build records by hand to pin the pages' exact text. Nothing here imports
Sphinx, so the default ``.[dev]`` install runs the tests (ADR 0009).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE, REPO_LOCAL_SOURCE
from coding_agent_playbook.catalog.prompt_sets import DEFAULT_PROMPT_SET, PROMPT_SETS
from coding_agent_playbook.catalog.roots import bundled_plugins, catalog_layer_root, catalog_root
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.skills.membership import member_rules_of
from coding_agent_playbook.skills.playbook_block import playbook_block
from coding_agent_playbook.skills.sections import skill_sections

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.catalog.prompt_sets import PromptSet

#: The title of the section that collects member rules naming no declared section (D42).
OTHER_SECTION_TITLE = "Other"


@dataclass(frozen=True)
class RuleEntry:
    """One rule as listed on a page: ``RuleEntry("pytest-aaa", "Arrange-Act-Assert", "...")``."""

    id: str
    name: str
    description: str
    origin: str = ""  # the layer that adds it, when not the skill's own layer


@dataclass(frozen=True)
class SectionEntry:
    """One section of a skill's index with its member rules, in delivery order."""

    title: str
    impact: str
    summary: str
    open_when: str
    rules: tuple[RuleEntry, ...]


@dataclass(frozen=True)
class ReferenceEntry:
    """One ``playbook.references`` entry: a path inside the skill and its open-when line."""

    path: str
    open_when: str


@dataclass(frozen=True)
class SkillEntry:
    """One skill: its index metadata and where its source lives in the repo."""

    id: str
    description: str
    source_path: str
    use_when: str = ""
    files: str = ""
    capabilities: tuple[str, ...] = ()
    sections: tuple[SectionEntry, ...] = ()
    references: tuple[ReferenceEntry, ...] = ()


@dataclass(frozen=True)
class PluginEntry:
    """One bundled plugin: ``framework.toml``'s name and description, its credit, its skills."""

    layer: str
    name: str
    description: str
    credit: str
    source_path: str
    skills: tuple[SkillEntry, ...]
    always_rules: tuple[RuleEntry, ...]


@dataclass(frozen=True)
class PromptEntry:
    """One prompt id, with the prompt sets that ship it (twins share the id)."""

    id: str
    name: str
    slash: str
    description: str
    prompt_sets: tuple[str, ...]


@dataclass(frozen=True)
class HookEntry:
    """One hook, filed under its hook family (the directory it sits in)."""

    id: str
    name: str
    summary: str
    family: str
    events: tuple[str, ...]
    tier: str
    supports: tuple[str, ...]


@dataclass(frozen=True)
class CatalogSnapshot:
    """Everything the catalog pages show: core, the bundled plugins, prompts and hooks."""

    core_skills: tuple[SkillEntry, ...]
    always_rules: tuple[RuleEntry, ...]
    plugins: tuple[PluginEntry, ...]
    prompts: tuple[PromptEntry, ...]
    hooks: tuple[HookEntry, ...]


def load_snapshot(repo_root: Path) -> CatalogSnapshot:
    """Read core and every bundled plugin through the engine's own readers.

    ``repo_root`` is the checkout the source paths are made relative to; its own
    ``playbook/`` layer, if any, is left out.

    Example: ``load_snapshot(Path(".")).core_skills[0].id`` -> ``"design-patterns"``.
    """
    plugins = bundled_plugins()
    source = FileSystemArtifactSource(repo_root=repo_root, overlay_packages=plugins)
    skills = [s for s in source.list_skills() if s.source_package != REPO_LOCAL_SOURCE]
    rules, errors = source.collect_rules()
    if errors:
        raise errors[0]
    return CatalogSnapshot(
        core_skills=_skill_entries(skills, rules, ENGINE_PACKAGE, repo_root),
        always_rules=_always_rules(rules, ENGINE_PACKAGE),
        plugins=tuple(_plugin_entry(p, skills, rules, repo_root) for p in plugins),
        prompts=_prompt_entries(repo_root, plugins),
        hooks=_hook_entries(source),
    )


def _skill_entries(
    skills: Sequence[Skill], rules: Sequence[Rule], layer: str, repo_root: Path
) -> tuple[SkillEntry, ...]:
    ordered = sorted((s for s in skills if s.source_package == layer), key=_skill_id)
    return tuple(_skill_entry(skill, rules, repo_root) for skill in ordered)


def _skill_id(skill: Skill) -> str:
    return str(skill.frontmatter["id"])


def _skill_entry(skill: Skill, rules: Sequence[Rule], repo_root: Path) -> SkillEntry:
    block = playbook_block(skill)
    source_dir = skill.source_dir
    return SkillEntry(
        id=_skill_id(skill),
        description=str(skill.frontmatter.get("description", "")),
        source_path=_relative(source_dir, repo_root) if source_dir else "",
        use_when=str(block.get("use_when", "")),
        files=str(block.get("files", "")),
        capabilities=tuple(str(c) for c in skill.frontmatter.get("capabilities", ())),
        sections=_section_entries(skill, rules),
        references=tuple(_reference_entry(entry) for entry in block.get("references", ())),
    )


def _section_entries(skill: Skill, rules: Sequence[Rule]) -> tuple[SectionEntry, ...]:
    members = member_rules_of(_skill_id(skill), rules)
    sections = skill_sections(skill)
    declared = {section.id for section in sections}
    entries = [
        SectionEntry(
            title=section.title,
            impact=section.impact.value,
            summary=section.summary,
            open_when=section.open_when,
            rules=_rule_entries(skill, [r for r in members if r.frontmatter.section == section.id]),
        )
        for section in sections
    ]
    other = [rule for rule in members if rule.frontmatter.section not in declared]
    if other:
        entries.append(SectionEntry(OTHER_SECTION_TITLE, "", "", "", _rule_entries(skill, other)))
    return tuple(entries)


def _rule_entries(skill: Skill, rules: Sequence[Rule]) -> tuple[RuleEntry, ...]:
    return tuple(_rule_entry(rule, home_layer=skill.source_package) for rule in rules)


def _rule_entry(rule: Rule, *, home_layer: str) -> RuleEntry:
    origin = "" if rule.source_package == home_layer else rule.source_package
    fm = rule.frontmatter
    return RuleEntry(fm.id, fm.name, fm.description, origin)


def _reference_entry(entry: Any) -> ReferenceEntry:
    return ReferenceEntry(str(entry.get("path", "")), str(entry.get("open_when", "")))


def _always_rules(rules: Sequence[Rule], layer: str) -> tuple[RuleEntry, ...]:
    always = [r for r in rules if r.source_package == layer and r.frontmatter.scope == "always"]
    always.sort(key=lambda rule: rule.frontmatter.id)
    return tuple(_rule_entry(rule, home_layer=layer) for rule in always)


def _plugin_entry(
    layer: str, skills: Sequence[Skill], rules: Sequence[Rule], repo_root: Path
) -> PluginEntry:
    root = catalog_layer_root(layer)
    if root is None:
        raise ValueError(f"bundled plugin {layer!r} has no directory under {catalog_root()}")
    framework = tomllib.loads((root / "framework.toml").read_text(encoding="utf-8"))
    return PluginEntry(
        layer=layer,
        name=str(framework.get("name", root.name)),
        description=str(framework.get("description", "")),
        credit=_first_paragraph((root / "README.md").read_text(encoding="utf-8")),
        source_path=_relative(root, repo_root),
        skills=_skill_entries(skills, rules, layer, repo_root),
        always_rules=_always_rules(rules, layer),
    )


def _first_paragraph(markdown: str) -> str:
    """The first paragraph after the title: a plugin README's credit and license line."""
    paragraphs = [p for p in markdown.split("\n\n") if p.strip()]
    body = [p for p in paragraphs if not p.lstrip().startswith("#")]
    return " ".join(body[0].split()) if body else ""


def _prompt_entries(repo_root: Path, plugins: Sequence[str]) -> tuple[PromptEntry, ...]:
    """One entry per prompt id; name and description come from the default set when it has one."""
    per_set = {ps: _prompts_by_id(repo_root, plugins, ps) for ps in PROMPT_SETS}
    ids = sorted({prompt_id for prompts in per_set.values() for prompt_id in prompts})
    entries = []
    for prompt_id in ids:
        sets = tuple(ps for ps in PROMPT_SETS if prompt_id in per_set[ps])
        base = per_set[DEFAULT_PROMPT_SET].get(prompt_id) or per_set[sets[0]][prompt_id]
        fm = base.frontmatter
        entries.append(PromptEntry(fm.id, fm.name, fm.slash, fm.description, sets))
    return tuple(entries)


def _prompts_by_id(
    repo_root: Path, plugins: Sequence[str], prompt_set: PromptSet
) -> dict[str, Prompt]:
    source = FileSystemArtifactSource(
        repo_root=repo_root, overlay_packages=list(plugins), prompt_set=prompt_set
    )
    return {
        prompt.frontmatter.id: prompt
        for prompt in source.list_prompts()
        if prompt.source_package != REPO_LOCAL_SOURCE
    }


def _hook_entries(source: FileSystemArtifactSource) -> tuple[HookEntry, ...]:
    hooks, errors = source.collect_hooks()
    if errors:
        raise errors[0]
    entries = [
        HookEntry(
            id=hook.frontmatter.id,
            name=hook.frontmatter.name,
            summary=hook.frontmatter.summary or hook.frontmatter.description,
            family=hook.source_path.parent.parent.name if hook.source_path else "",
            events=tuple(str(event) for event in hook.frontmatter.events),
            tier=str(hook.frontmatter.tier),
            supports=tuple(hook.frontmatter.supports),
        )
        for hook in hooks
        if hook.source_package != REPO_LOCAL_SOURCE
    ]
    return tuple(sorted(entries, key=lambda entry: (entry.family, entry.id)))


def _relative(path: Path, repo_root: Path) -> str:
    """``path`` relative to the checkout, POSIX-style; absolute when outside it."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
