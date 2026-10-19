"""The skill-shaped leaves of the ``agent_harness`` adapter (``specs/prH-agent-harness.md`` §B).

``skills/<id>/SKILL.md`` (plus byte-copied ``scripts/`` and ``references/``) and
``prompts/<slash>/SKILL.md``, each with its manifest entry. AH-2 (#143) moved these
per-kind emitters out of :class:`~.adapter.AgentHarnessAdapter` to bring it under
its 400-line budget; they take every input as an argument and hold no state. The
adapter keeps the prompt-body render (it owns the rule registry) and the routing files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness import emitter, manifest
from coding_agent_playbook.agent_harness.hook_sidecars import copy_scripts
from coding_agent_playbook.generated_output.output_io import write_output_bytes, write_output_text
from coding_agent_playbook.generated_output.source_files import copyable_skill_files
from coding_agent_playbook.rendering.formats import with_sentinel_body

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.skill import Skill

#: Skill frontmatter keys the leaf carries natively; every other key goes to the sidecar.
_NATIVE_SKILL_KEYS = frozenset({"id", "name", "description"})


def emit_skill_leaves(
    skills: Sequence[Skill], repo_root: Path, entries: list[manifest.ManifestEntry]
) -> list[Path]:
    """Write each skill's ``skills/<id>/`` leaf and append its manifest entry; return the paths.

    Example: ``written = emit_skill_leaves(self._skills, repo_root, entries)``.
    """
    written: list[Path] = []
    for skill in skills:
        written.extend(_emit_skill_leaf(skill, repo_root, entries))
    return written


def _emit_skill_leaf(
    skill: Skill, repo_root: Path, entries: list[manifest.ManifestEntry]
) -> list[Path]:
    skill_id = str(skill.frontmatter.get("id", "skill"))
    skill_dir = repo_root / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    name = str(skill.frontmatter.get("name", skill_id))
    description = str(skill.frontmatter.get("description", ""))
    frontmatter = emitter.frontmatter_block({"name": name, "description": description})
    skill_md = skill_dir / "SKILL.md"
    write_output_text(skill_md, with_sentinel_body(frontmatter, skill.body))
    scripts, script_paths = copy_scripts(skill.scripts_dir, skill_dir / "scripts", repo_root)
    path = skill_md.relative_to(repo_root).as_posix()
    entries.append(_skill_entry(skill, path, skill_id, name, scripts))
    return [skill_md, *script_paths, *_copy_references(skill, skill_dir)]


def _skill_entry(
    skill: Skill, path: str, skill_id: str, name: str, scripts: list[manifest.ScriptEntry]
) -> manifest.ManifestEntry:
    """The sidecar entry of a skill leaf: name and source body too, though the leaf has both.

    Recording them keeps lossless reconstruction uniform with rules and prompts
    (independent of the on-disk leaf), even though a skill's ``SKILL.md`` is a
    near-verbatim copy of the source body today.
    """
    extra = {k: v for k, v in skill.frontmatter.items() if k not in _NATIVE_SKILL_KEYS}
    return manifest.ManifestEntry(
        kind="skill",
        path=path,
        id=skill_id,
        name=name,
        body=skill.body,
        extra_frontmatter=extra,
        scripts=scripts,
    )


def _copy_references(skill: Skill, skill_dir: Path) -> list[Path]:
    """Byte-copy the skill's publishable references, filtered like ``scripts/``."""
    if skill.references_dir is None:
        return []
    dst_root = skill_dir / "references"
    paths: list[Path] = []
    for src in copyable_skill_files(skill.references_dir, dst_root):
        dst = dst_root / src.relative_to(skill.references_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        write_output_bytes(dst, src.read_bytes())
        paths.append(dst)
    return paths


def emit_prompt_leaves(
    prompts: Sequence[tuple[Prompt, str]], repo_root: Path, entries: list[manifest.ManifestEntry]
) -> list[Path]:
    """Write each ``(prompt, leaf body)`` as ``prompts/<slash>/SKILL.md`` plus its manifest entry.

    The leaf body is the rendered presentation (rules inlined); the entry records
    the un-rendered source body and ``is_templated``, so the lossless importer
    rebuilds the prompt from the sidecar, never from the leaf.

    Example: ``emit_prompt_leaves([(prompt, body)], repo_root, entries)``.
    """
    written: list[Path] = []
    for prompt, body in prompts:
        fm = prompt.frontmatter
        prompt_dir = repo_root / "prompts" / fm.slash
        prompt_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = emitter.frontmatter_block({"name": fm.name, "description": fm.description})
        skill_md = prompt_dir / "SKILL.md"
        write_output_text(skill_md, with_sentinel_body(frontmatter, body))
        written.append(skill_md)
        entries.append(_prompt_entry(prompt, skill_md.relative_to(repo_root).as_posix()))
    return written


def _prompt_entry(prompt: Prompt, path: str) -> manifest.ManifestEntry:
    fm = prompt.frontmatter
    return manifest.ManifestEntry(
        kind="prompt",
        path=path,
        id=fm.id,
        name=fm.name,
        body=prompt.template_body,
        is_templated=prompt.is_templated,
        slash=fm.slash,
        version=fm.version,
        applies_if=dict(fm.applies_if),
        input_variables=[dict(v) for v in fm.input_variables],
        includes_rules=list(fm.includes_rules),
        eval_tasks=list(fm.eval_tasks),
        output_contract=list(fm.output_contract),
        write_scope=dict(fm.write_scope),
    )
