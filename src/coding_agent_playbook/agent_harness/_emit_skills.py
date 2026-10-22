"""The skill-shaped leaves of the ``agent_harness`` adapter (``specs/prH-agent-harness.md`` §B).

``skills/<id>/SKILL.md`` (the authored body plus the generated rules index, byte-copied
``scripts/``, ``references/`` and ``examples/``; member rules come from :mod:`._emit_rules`) and
``prompts/<slash>/SKILL.md``, each with its manifest entry. AH-2 (#143) moved these
per-kind emitters out of :class:`~.adapter.AgentHarnessAdapter` to bring it under
its 400-line budget; they take every input as an argument and hold no state. The
adapter keeps the prompt-body render (it owns the rule registry) and the routing files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.agent_harness import emitter, manifest
from coding_agent_playbook.agent_harness.hook_sidecars import copy_script_files
from coding_agent_playbook.generated_output.output_io import write_output_bytes, write_output_text
from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.generated_output.source_files import published_skill_files
from coding_agent_playbook.rendering.formats import with_sentinel_body
from coding_agent_playbook.skills.document import emitted_body

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.skill import SideDirName, Skill

#: Skill frontmatter keys the leaf carries natively; every other key goes to the sidecar.
_NATIVE_SKILL_KEYS = frozenset({"id", "name", "description"})
#: The pytest config file that keeps a consumer's test run out of the skills' examples.
_EXAMPLES_CONFTEST: Final = "conftest.py"
_EXAMPLES_CONFTEST_TEXT: Final = (
    f"{sentinel_line('hash')}\n"
    '"""Keep pytest out of the skills\' examples: each runs its tests in its own environment."""\n'
    "\n"
    'collect_ignore_glob = ["*/examples"]\n'
)


def emit_skill_leaves(
    skills: Sequence[Skill], repo_root: Path, entries: list[manifest.ManifestEntry]
) -> list[Path]:
    """Write each skill's ``skills/<id>/`` leaf and append its manifest entry; return the paths.

    Example: ``written = emit_skill_leaves(self._skills, repo_root, entries)``.
    """
    written: list[Path] = []
    examples: list[Path] = []
    for skill in skills:
        leaf, copied_examples = _emit_skill_leaf(skill, repo_root, entries)
        written.extend(leaf)
        examples.extend(copied_examples)
    if examples:
        written.append(_emit_examples_conftest(repo_root))
    return written


def _emit_skill_leaf(
    skill: Skill, repo_root: Path, entries: list[manifest.ManifestEntry]
) -> tuple[list[Path], list[Path]]:
    """Write one ``skills/<id>/`` leaf: (every path written, the ``examples/`` files among them)."""
    skill_id = str(skill.frontmatter.get("id", "skill"))
    skill_dir = repo_root / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    name = str(skill.frontmatter.get("name", skill_id))
    description = str(skill.frontmatter.get("description", ""))
    frontmatter = emitter.frontmatter_block({"name": name, "description": description})
    skill_md = skill_dir / "SKILL.md"
    # The rules index (prU D46.7) is presentation; the entry keeps the authored body.
    write_output_text(skill_md, with_sentinel_body(frontmatter, emitted_body(skill)))
    scripts_root = skill_dir / "scripts"
    scripts, script_paths = copy_script_files(
        published_skill_files(skill, "scripts", scripts_root), repo_root
    )
    path = skill_md.relative_to(repo_root).as_posix()
    entries.append(_skill_entry(skill, path, skill_id, name, scripts))
    references = _copy_side_files(skill, skill_dir, "references")
    examples = _copy_side_files(skill, skill_dir, "examples")
    return [skill_md, *script_paths, *references, *examples], examples


def _emit_examples_conftest(repo_root: Path) -> Path:
    """Write ``skills/conftest.py``, which keeps pytest out of every ``skills/<id>/examples/``.

    The native skill roots are dot-directories, which pytest never enters; the
    harness tree is not, so without this a consumer's plain ``pytest`` would
    collect an example's tests, which need the example's own environment (prU
    D48). The file sits outside every skill dir, so the stale scan settles it
    once no example is left, and the importer never reads it.
    """
    target = repo_root / "skills" / _EXAMPLES_CONFTEST
    write_output_text(target, _EXAMPLES_CONFTEST_TEXT)
    return target


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


def _copy_side_files(skill: Skill, skill_dir: Path, name: SideDirName) -> list[Path]:
    """Byte-copy the skill's published ``references/`` or ``examples/`` files (prU D48, D58).

    Filtered like ``scripts/``, and a file a failed ``applies_if`` withholds is
    not written.
    """
    paths: list[Path] = []
    for src, dst in published_skill_files(skill, name, skill_dir / name):
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
        eval_samples=list(fm.eval_samples),
        output_contract=list(fm.output_contract),
        write_scope=dict(fm.write_scope),
    )
