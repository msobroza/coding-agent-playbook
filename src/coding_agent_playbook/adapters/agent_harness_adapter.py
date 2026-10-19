"""Agent Harness output adapter (PR H Track H2).

Renders canonical ``Rule`` / ``Prompt`` / ``Skill`` artifacts into a
``HARNESS.md``-rooted Agent Harness tree (``specs/prH-agent-harness.md`` §B).
Unlike the per-file adapters, this one **buffers** every artifact during
``write_rule`` / ``write_prompt`` / ``write_skill`` and composes the whole tree
in :meth:`finalize`, so ``HARNESS.md`` can index everything that was emitted.

Layout (§B):

- ``skills/<id>/SKILL.md`` (+ ``scripts/`` + ``references/``) and ``skills/SKILLS.md``.
- ``prompts/<slash>/SKILL.md`` (skill-shaped leaf) and ``prompts/PROMPTS.md``.
- ``rules/<priority:02d>-<id>.md`` for ``scope=always`` rules and ``rules/RULES.md``.
- ``references/<id>.md`` for ``scope=scoped`` rules and ``references/REFERENCES.md``.
- ``HARNESS.md`` (root role summary + dir index + "Always consult these" pointer).
- ``.leaf-detectors`` (``skill=SKILL.md``) when any skill/prompt leaf exists.
- ``.playbook/manifest.toml`` (round-trip sidecar) + ``.playbook/.harnessleaf``.
- ``.playbook/hooks/<id>/`` hook sidecars and ``rules/30-guardrail-<id>.md``
  advisories (:mod:`._harness_hooks`, specs/prK-lifecycle-hooks.md §C.6).

Eval tasks are authoring-only and never dispatched to adapters, so this adapter
never emits an ``evals/`` directory — consistent with the five built-in adapters.

The playbook sentinel is written as the **first body line** of every generated
text file (frontmatter must stay on line 1 for the harness parser), one of the
two anchored positions ``generated_output.sentinel.has_sentinel`` accepts; a sentinel quoted
anywhere else is user prose. ``cleanup_stale`` never deletes inside a skill
directory (``skills/<id>/``): stale skill output — the ``SKILL.md``, copied
scripts and references — is settled only by ``playbook sync``'s lockfile
leftover policy (SPEC §4.2 step 9), like every native skill root.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook.adapters._harness_hooks import (
    copy_scripts,
    emit_hook_sidecars,
    guardrail_rules,
    stale_sidecar_candidates,
)
from coding_agent_playbook.adapters._skill_sources import copyable_skill_files
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.generated_output.file_identity import FileSet
from coding_agent_playbook.generated_output.output_io import write_output_bytes, write_output_text
from coding_agent_playbook.harness import emitter, manifest
from coding_agent_playbook.renderer import render_inline_prompt_markdown

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from coding_agent_playbook.harness.manifest import ManifestEntry
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.renderer import RuleRegistry
    from coding_agent_playbook.types import Prompt, Rule, Skill

#: The single leaf type this adapter emits (skill-shaped leaves for both skills
#: and prompts). Declared in the root ``.leaf-detectors`` file.
_SKILL_PRIMARY_FILE = "SKILL.md"

#: Top-level directory names, in the order they appear in the HARNESS.md index.
_TOP_LEVEL_DIRS = ("skills", "prompts", "rules", "references")

#: Single generated files at the harness root.
_ROOT_FILES = ("HARNESS.md", ".leaf-detectors")


class AgentHarnessAdapter(Adapter):
    """Adapter that emits an Agent Harness tree under the repo root.

    Registers under ``coding_agent_playbook.adapters`` as ``agent_harness``.
    **Opt-in** — it is not force-enabled like ``agents_md`` and is not in the
    default-adapter set; enable it via ``adapters_enabled`` in the config. The
    orchestrator discovers and instantiates it through the entry point — never
    construct it directly outside of tests.

    The optional ``rule_registry`` is used to inline a prompt's
    ``includes_rules:`` as a ``## Reference rules`` appendix (mirrors
    :class:`ContinueAdapter`): this tree's scoped rules are top-level
    ``references/<id>.md`` files, not skill references, so there is no skill to
    point at (P3-6). When omitted, ``includes_rules:`` is declarative-only.

    Uniqueness assumption: leaf paths are keyed on canonical ids/slashes —
    scoped rules at ``references/<id>.md``, always-rules at
    ``rules/<priority:02d>-<id>.md``, and prompts at ``prompts/<slash>/`` — so a
    duplicate id/slash within one artifact set is last-write-wins. The canonical
    layer guarantees these are unique, so collisions never reach the adapter.
    """

    name = "agent_harness"

    output_locations: ClassVar[tuple[str, ...]] = (
        *_ROOT_FILES,
        *(f"{dir_name}/" for dir_name in _TOP_LEVEL_DIRS),
        f"{manifest.SIDECAR_DIRNAME}/",
    )

    def __init__(self, *, rule_registry: RuleRegistry | None = None) -> None:
        self._rule_registry = rule_registry
        self._rules: list[Rule] = []
        self._prompts: list[Prompt] = []
        self._skills: list[Skill] = []
        self._hooks: list[ResolvedHook] = []

    # --- buffering hooks ---------------------------------------------------

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Buffer a rendered rule for :meth:`finalize` to place. Writes nothing."""
        del repo_root
        self._rules.append(rule)
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Buffer a rendered prompt for :meth:`finalize` to place. Writes nothing."""
        del repo_root
        self._prompts.append(prompt)
        return []

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Buffer a skill for :meth:`finalize` to place. Writes nothing."""
        del repo_root
        self._skills.append(skill)
        return []

    def write_hook(self, hook: ResolvedHook, repo_root: Path) -> list[Path]:
        """Buffer a hook for :meth:`finalize`: its sidecar always, its advisory if any (§C.6)."""
        del repo_root
        self._hooks.append(hook)
        return []

    # --- composition -------------------------------------------------------

    def finalize(self, repo_root: Path) -> list[Path]:
        """Compose the whole harness tree from the buffered artifacts.

        Emits skills, prompts, rules, references, the routing files,
        ``HARNESS.md``, ``.leaf-detectors`` and the ``.playbook/`` sidecar.
        Returns every path written (``[]`` when nothing was buffered).
        """
        if not (self._rules or self._prompts or self._skills or self._hooks):
            return []

        written: list[Path] = []
        entries: list[ManifestEntry] = []

        written.extend(self._emit_skills(repo_root, entries))
        written.extend(self._emit_prompts(repo_root, entries))
        always_rules, scoped_rules = self._partition_rules()
        advisories = guardrail_rules(self._hooks)
        written.extend(self._emit_always_rules(repo_root, always_rules, entries, advisories))
        written.extend(self._emit_scoped_rules(repo_root, scoped_rules, entries))
        written.extend(emit_hook_sidecars(self._hooks, repo_root, entries))

        written.append(self._emit_harness_md(repo_root, [*always_rules, *advisories]))

        if self._skills or self._prompts:
            written.append(self._emit_leaf_detectors(repo_root))

        written.extend(self._emit_sidecar(repo_root, entries))
        return written

    # --- skills ------------------------------------------------------------

    def _emit_skills(self, repo_root: Path, entries: list[ManifestEntry]) -> list[Path]:
        if not self._skills:
            return []
        written: list[Path] = []
        for skill in self._skills:
            skill_id = str(skill.frontmatter.get("id", "skill"))
            skill_dir = repo_root / "skills" / skill_id
            skill_dir.mkdir(parents=True, exist_ok=True)

            name = str(skill.frontmatter.get("name", skill_id))
            description = str(skill.frontmatter.get("description", ""))
            frontmatter = emitter.frontmatter_block({"name": name, "description": description})
            skill_md = skill_dir / "SKILL.md"
            write_output_text(skill_md, emitter.with_sentinel_body(frontmatter, skill.body))
            written.append(skill_md)

            scripts, script_paths = copy_scripts(
                skill.scripts_dir, skill_dir / "scripts", repo_root
            )
            written.extend(script_paths)
            written.extend(self._copy_references(skill, skill_dir))

            entries.append(
                manifest.ManifestEntry(
                    kind="skill",
                    path=self._rel(skill_md, repo_root),
                    id=skill_id,
                    # Record name + the source body in the sidecar so lossless
                    # reconstruction is uniform with rules/prompts (independent
                    # of the on-disk leaf), even though a skill's SKILL.md is a
                    # near-verbatim copy of the source body today.
                    name=name,
                    body=skill.body,
                    extra_frontmatter=self._skill_extra_frontmatter(skill),
                    scripts=scripts,
                )
            )
        written.append(self._emit_routing(repo_root, "skills", "Skills available in this harness."))
        return written

    @staticmethod
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

    @staticmethod
    def _skill_extra_frontmatter(skill: Skill) -> dict[str, object]:
        """Frontmatter keys beyond ``id``/``name``/``description`` go to the sidecar."""
        reserved = {"id", "name", "description"}
        return {k: v for k, v in skill.frontmatter.items() if k not in reserved}

    # --- prompts -----------------------------------------------------------

    def _emit_prompts(self, repo_root: Path, entries: list[ManifestEntry]) -> list[Path]:
        if not self._prompts:
            return []
        written: list[Path] = []
        for prompt in self._prompts:
            fm = prompt.frontmatter
            slash = fm.slash
            prompt_dir = repo_root / "prompts" / slash
            prompt_dir.mkdir(parents=True, exist_ok=True)

            frontmatter = emitter.frontmatter_block(
                {"name": fm.name, "description": fm.description}
            )
            body = self._prompt_body(prompt)
            skill_md = prompt_dir / "SKILL.md"
            write_output_text(skill_md, emitter.with_sentinel_body(frontmatter, body))
            written.append(skill_md)

            entries.append(
                manifest.ManifestEntry(
                    kind="prompt",
                    path=self._rel(skill_md, repo_root),
                    id=fm.id,
                    # The leaf body inlines ``includes_rules`` (rendered
                    # presentation); the sidecar stores the ORIGINAL un-rendered
                    # source body + ``is_templated`` so the lossless importer
                    # reconstructs the prompt from here, not the rendered leaf.
                    name=fm.name,
                    body=prompt.template_body,
                    is_templated=prompt.is_templated,
                    slash=slash,
                    version=fm.version,
                    applies_if=dict(fm.applies_if),
                    input_variables=[dict(v) for v in fm.input_variables],
                    includes_rules=list(fm.includes_rules),
                    eval_tasks=list(fm.eval_tasks),
                    output_contract=list(fm.output_contract),
                    write_scope=dict(fm.write_scope),
                )
            )
        written.append(
            self._emit_routing(repo_root, "prompts", "Prompts available in this harness.")
        )
        return written

    def _prompt_body(self, prompt: Prompt) -> str:
        """Build a prompt-leaf body: the titled body, its rules inline, an input-variable note.

        ``includes_rules:`` is inlined through the rule registry as the
        ``## Reference rules`` appendix (``render_inline_prompt_markdown``): pure
        markdown with no sentinel and no ``disallowed-tools`` block, since the
        leaf's own ``SKILL.md`` envelope carries both. Input variables are noted
        so the agent knows what to substitute.
        """
        rendered = render_inline_prompt_markdown(
            prompt.body, dataclasses.asdict(prompt.frontmatter), self._rule_registry
        )

        note = emitter.input_variables_note(prompt.frontmatter.input_variables)
        if note:
            return f"{rendered.rstrip(chr(10))}\n\n{note}"
        return rendered

    # --- rules -------------------------------------------------------------

    def _partition_rules(self) -> tuple[list[Rule], list[Rule]]:
        always = [r for r in self._rules if r.frontmatter.scope == "always"]
        scoped = [r for r in self._rules if r.frontmatter.scope != "always"]
        return always, scoped

    def _emit_always_rules(
        self,
        repo_root: Path,
        rules: list[Rule],
        entries: list[ManifestEntry],
        advisories: Sequence[Rule] = (),
    ) -> list[Path]:
        """``rules/<NN>-<id>.md`` per always-rule and hook advisory, then ``RULES.md``.

        Advisories are written with ``record_manifest=False``: presentation only,
        so a lossless import never turns one into a ``Rule`` (§C.6).
        """
        if not (rules or advisories):
            return []
        written: list[Path] = []
        for rule, record in [*((r, True) for r in rules), *((r, False) for r in advisories)]:
            target = repo_root / "rules" / self._always_rule_filename(rule)
            written.append(
                self._write_rule_content(target, rule, repo_root, entries, record_manifest=record)
            )
        written.append(self._emit_routing(repo_root, "rules", "Rules to apply every session."))
        return written

    def _emit_scoped_rules(
        self, repo_root: Path, rules: list[Rule], entries: list[ManifestEntry]
    ) -> list[Path]:
        if not rules:
            return []
        written: list[Path] = []
        for rule in rules:
            target = repo_root / "references" / f"{rule.frontmatter.id}.md"
            written.append(self._write_rule_content(target, rule, repo_root, entries))
        written.append(
            self._emit_routing(repo_root, "references", "On-demand references and scoped rules.")
        )
        return written

    def _write_rule_content(
        self,
        target: Path,
        rule: Rule,
        repo_root: Path,
        entries: list[ManifestEntry],
        *,
        record_manifest: bool = True,
    ) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        fm = rule.frontmatter
        frontmatter = emitter.frontmatter_block({"description": fm.description})
        write_output_text(target, emitter.with_sentinel_body(frontmatter, rule.body))
        if not record_manifest:
            return target
        entries.append(
            manifest.ManifestEntry(
                kind="rule",
                path=self._rel(target, repo_root),
                id=fm.id,
                # The harness rule file emits ``description`` only — ``name`` and
                # the un-rendered source body are the sidecar's responsibility so
                # the lossless importer recovers them independently of the leaf.
                name=fm.name,
                body=rule.template_body,
                is_templated=rule.is_templated,
                scope=fm.scope,
                priority=fm.priority,
                globs=list(fm.globs),
                applies_if=dict(fm.applies_if),
                tags=list(fm.tags),
                version=fm.version,
                lint_codes=dict(fm.lint_codes),
                skill=fm.skill,
            )
        )
        return target

    @staticmethod
    def _always_rule_filename(rule: Rule) -> str:
        return f"{rule.frontmatter.priority:02d}-{rule.frontmatter.id}.md"

    # --- routing files -----------------------------------------------------

    def _emit_routing(self, repo_root: Path, dir_name: str, description: str) -> Path:
        target = repo_root / dir_name / f"{dir_name.upper()}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        body = f"Routing index for `{dir_name}/`.\n"
        write_output_text(target, emitter.routing_file(description, body))
        return target

    # --- HARNESS.md --------------------------------------------------------

    def _emit_harness_md(self, repo_root: Path, always_rules: list[Rule]) -> Path:
        name = repo_root.name or "harness"
        description = f"Coding-agent harness for {name}."
        emitted = {
            "skills": bool(self._skills),
            "prompts": bool(self._prompts),
            "rules": bool(always_rules),
            "references": any(r.frontmatter.scope != "always" for r in self._rules),
        }
        frontmatter = emitter.frontmatter_block({"name": name, "description": description})

        sections: list[str] = [
            f"# {name}",
            "",
            "This harness provides the coding rules, prompts and skills for this "
            "project. Consult the routing files in each directory for details.",
            "",
            "## Contents",
            "",
        ]
        # Index what this render emits, never what happens to be on disk: an
        # empty leftover dir (or the user's own ``skills/``) must not change the
        # bytes, or ``sync --check`` (rendering into an empty scratch) drifts.
        for dir_name in (d for d in _TOP_LEVEL_DIRS if emitted[d]):
            sections.append(f"- `{dir_name}/` — see `{dir_name}/{dir_name.upper()}.md`")
        sections.append("")

        if always_rules:
            sections.append("## Always consult these")
            sections.append("")
            sections.append("Read these rules at the start of every session:")
            sections.append("")
            for rule in sorted(
                always_rules, key=lambda r: (r.frontmatter.priority, r.frontmatter.id)
            ):
                rel = f"rules/{self._always_rule_filename(rule)}"
                sections.append(f"- `{rel}` — {rule.frontmatter.description}")
            sections.append("")

        body = "\n".join(sections)
        target = repo_root / "HARNESS.md"
        write_output_text(target, emitter.with_sentinel_body(frontmatter, body))
        return target

    # --- .leaf-detectors ---------------------------------------------------

    def _emit_leaf_detectors(self, repo_root: Path) -> Path:
        target = repo_root / ".leaf-detectors"
        write_output_text(target, emitter.leaf_detectors_file({"skill": _SKILL_PRIMARY_FILE}))
        return target

    # --- sidecar -----------------------------------------------------------

    def _emit_sidecar(self, repo_root: Path, entries: list[ManifestEntry]) -> list[Path]:
        manifest_path = manifest.write_manifest(repo_root, entries)
        leaf_marker = emitter.harnessleaf_path(repo_root / manifest.SIDECAR_DIRNAME)
        write_output_text(leaf_marker, "")
        return [manifest_path, leaf_marker]

    # --- cleanup -----------------------------------------------------------

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        return [repo_root / d for d in _TOP_LEVEL_DIRS]

    def stale_outputs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Sentinel-tagged engine files no longer backing a current artifact (deletes nothing).

        Scans ``skills/``, ``prompts/``, ``rules/``, ``references/`` and the root
        files (``HARNESS.md``, ``.leaf-detectors``) for files that carry the
        sentinel at an anchored position (:meth:`Adapter._carries_sentinel`:
        line 1, or the first body line after frontmatter, where this adapter
        writes it) and were not written this sync. A user file that merely
        quotes the sentinel is never reported. "Not written" compares file
        identity (:class:`FileSet`), so after a case-only id rename on a
        case-insensitive filesystem the file just written is never reported
        under its old spelling.

        Nothing inside a skill directory (``skills/<id>/``) is reported: it mixes
        engine output with files a user may have edited or added, so only the
        lockfile leftover policy (pristine + untracked + listed, SPEC §4.2 step 9)
        deletes there. Only files :meth:`Adapter._scan_targets` admits are opened
        (each once; never a symlink or a secret path — these generic repo-root
        dirs may hold anything). The ABC's ``cleanup_stale`` deletes what this
        returns.
        """
        written = FileSet.of(written_paths)
        return [
            path
            for path in self._scan_targets(self._scan_candidates(repo_root), repo_root)
            if not written.holds(path) and self._carries_sentinel(path)
        ]

    def _scan_candidates(self, repo_root: Path) -> list[Path]:
        """Every path under the output dirs (outside skill dirs), the root files, hook sidecars."""
        candidates = [*(repo_root / n for n in _ROOT_FILES), *stale_sidecar_candidates(repo_root)]
        skills_dir = repo_root / "skills"
        for output_dir in self._output_directories(repo_root):
            if not output_dir.is_dir():
                continue
            candidates.extend(
                path for path in output_dir.rglob("*") if not _inside_skill_dir(path, skills_dir)
            )
        return candidates

    @staticmethod
    def _rel(path: Path, repo_root: Path) -> str:
        return path.relative_to(repo_root).as_posix()


def _inside_skill_dir(path: Path, skills_dir: Path) -> bool:
    """True for ``skills/<id>/...`` (a skill's own files), False for ``skills/SKILLS.md``."""
    try:
        return len(path.relative_to(skills_dir).parts) > 1
    except ValueError:
        return False
