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

Eval tasks are authoring-only and never dispatched to adapters, so this adapter
never emits an ``evals/`` directory — consistent with the four built-in adapters.

The playbook :data:`SENTINEL` is written as the **first body line** of every
generated text file (frontmatter must stay on line 1 for the harness parser).
``cleanup_stale`` therefore detects the sentinel *anywhere* in a file and tracks
non-sentinel engine files (scripts/raw/markers) through the prior manifest.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.harness import emitter, manifest
from coding_agent_playbook.renderer import SENTINEL, render_for

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.harness.manifest import ManifestEntry
    from coding_agent_playbook.renderer import RuleRegistry
    from coding_agent_playbook.types import Prompt, Rule, Skill

#: The single leaf type this adapter emits (skill-shaped leaves for both skills
#: and prompts). Declared in the root ``.leaf-detectors`` file.
_SKILL_PRIMARY_FILE = "SKILL.md"

#: Top-level directory names, in the order they appear in the HARNESS.md index.
_TOP_LEVEL_DIRS = ("skills", "prompts", "rules", "references")


class AgentHarnessAdapter(Adapter):
    """Adapter that emits an Agent Harness tree under the repo root.

    Registers under ``coding_agent_playbook.adapters`` as ``agent_harness``.
    **Opt-in** — it is not force-enabled like ``agents_md`` and is not in the
    default-adapter set; enable it via ``adapters_enabled`` in the config. The
    orchestrator discovers and instantiates it through the entry point — never
    construct it directly outside of tests.

    The optional ``rule_registry`` is used to inline a prompt's
    ``includes_rules:`` (mirrors :class:`ContinueAdapter`). When omitted,
    ``includes_rules:`` is declarative-only.

    Uniqueness assumption: leaf paths are keyed on canonical ids/slashes —
    scoped rules at ``references/<id>.md``, always-rules at
    ``rules/<priority:02d>-<id>.md``, and prompts at ``prompts/<slash>/`` — so a
    duplicate id/slash within one artifact set is last-write-wins. The canonical
    layer guarantees these are unique, so collisions never reach the adapter.
    """

    name = "agent_harness"

    def __init__(self, *, rule_registry: RuleRegistry | None = None) -> None:
        self._rule_registry = rule_registry
        self._rules: list[Rule] = []
        self._prompts: list[Prompt] = []
        self._skills: list[Skill] = []
        # Populated at the start of finalize() from the prior manifest so
        # cleanup_stale can recognise non-sentinel engine files (scripts/raw).
        self._prior_engine_files: set[Path] = set()

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

    # --- composition -------------------------------------------------------

    def finalize(self, repo_root: Path) -> list[Path]:
        """Compose the whole harness tree from the buffered artifacts.

        Reads the prior ``.playbook/manifest.toml`` first (so ``cleanup_stale``
        can identify the non-sentinel engine files it previously emitted), then
        emits skills, prompts, rules, references, the routing files,
        ``HARNESS.md``, ``.leaf-detectors`` and the ``.playbook/`` sidecar.
        Returns every path written (``[]`` when nothing was buffered).
        """
        self._prior_engine_files = self._read_prior_engine_files(repo_root)

        if not (self._rules or self._prompts or self._skills):
            return []

        written: list[Path] = []
        entries: list[ManifestEntry] = []

        written.extend(self._emit_skills(repo_root, entries))
        written.extend(self._emit_prompts(repo_root, entries))
        always_rules, scoped_rules = self._partition_rules()
        written.extend(self._emit_always_rules(repo_root, always_rules, entries))
        written.extend(self._emit_scoped_rules(repo_root, scoped_rules, entries))

        written.append(self._emit_harness_md(repo_root, always_rules))

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
            skill_md.write_text(
                emitter.with_sentinel_body(frontmatter, skill.body), encoding="utf-8"
            )
            written.append(skill_md)

            scripts, script_paths = self._copy_scripts(skill, skill_dir, repo_root)
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

    def _copy_scripts(
        self, skill: Skill, skill_dir: Path, repo_root: Path
    ) -> tuple[list[manifest.ScriptEntry], list[Path]]:
        if skill.scripts_dir is None or not skill.scripts_dir.is_dir():
            return [], []
        scripts: list[manifest.ScriptEntry] = []
        paths: list[Path] = []
        dst_root = skill_dir / "scripts"
        for src in sorted(skill.scripts_dir.rglob("*")):
            if not src.is_file():
                continue
            dst = dst_root / src.relative_to(skill.scripts_dir)
            executable = emitter.copy_script(src, dst)
            scripts.append(
                manifest.ScriptEntry(path=self._rel(dst, repo_root), executable=executable)
            )
            paths.append(dst)
        return scripts, paths

    @staticmethod
    def _copy_references(skill: Skill, skill_dir: Path) -> list[Path]:
        if skill.references_dir is None or not skill.references_dir.is_dir():
            return []
        dst_root = skill_dir / "references"
        paths: list[Path] = []
        for src in sorted(skill.references_dir.rglob("*")):
            if not src.is_file():
                continue
            dst = dst_root / src.relative_to(skill.references_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
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
            skill_md.write_text(emitter.with_sentinel_body(frontmatter, body), encoding="utf-8")
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
                )
            )
        written.append(
            self._emit_routing(repo_root, "prompts", "Prompts available in this harness.")
        )
        return written

    def _prompt_body(self, prompt: Prompt) -> str:
        """Build a prompt-leaf body: the rendered command + an input-variable note.

        ``includes_rules:`` is inlined through the rule registry by reusing the
        ``prompt_claude_command`` renderer (pure markdown + the
        ``## Reference rules`` appendix). Input variables are noted so the agent
        knows what to substitute.
        """
        rendered = render_for(
            prompt.source_path or Path("inline"),
            prompt.body,
            "prompt_claude_command",
            frontmatter=dataclasses.asdict(prompt.frontmatter),
            rule_registry=self._rule_registry,
        )
        # The claude-command renderer prepends its own sentinel comment; drop it
        # so this leaf carries exactly one sentinel (placed by with_sentinel_body).
        rendered = self._strip_leading_sentinel(rendered)

        note = self._input_variables_note(prompt)
        if note:
            return f"{rendered.rstrip(chr(10))}\n\n{note}"
        return rendered

    @staticmethod
    def _strip_leading_sentinel(text: str) -> str:
        marker = f"<!-- {SENTINEL} -->\n"
        return text[len(marker) :] if text.startswith(marker) else text

    @staticmethod
    def _input_variables_note(prompt: Prompt) -> str:
        variables = prompt.frontmatter.input_variables
        if not variables:
            return ""
        lines = ["## Input variables", ""]
        for var in variables:
            varname = str(var.get("name", ""))
            desc = str(var.get("description", "")).strip()
            lines.append(f"- `{varname}`" + (f" — {desc}" if desc else ""))
        return "\n".join(lines) + "\n"

    # --- rules -------------------------------------------------------------

    def _partition_rules(self) -> tuple[list[Rule], list[Rule]]:
        always = [r for r in self._rules if r.frontmatter.scope == "always"]
        scoped = [r for r in self._rules if r.frontmatter.scope != "always"]
        return always, scoped

    def _emit_always_rules(
        self, repo_root: Path, rules: list[Rule], entries: list[ManifestEntry]
    ) -> list[Path]:
        if not rules:
            return []
        written: list[Path] = []
        for rule in rules:
            target = repo_root / "rules" / self._always_rule_filename(rule)
            written.append(self._write_rule_content(target, rule, repo_root, entries))
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
        self, target: Path, rule: Rule, repo_root: Path, entries: list[ManifestEntry]
    ) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        fm = rule.frontmatter
        frontmatter = emitter.frontmatter_block({"description": fm.description})
        target.write_text(emitter.with_sentinel_body(frontmatter, rule.body), encoding="utf-8")
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
        target.write_text(emitter.routing_file(description, body), encoding="utf-8")
        return target

    # --- HARNESS.md --------------------------------------------------------

    def _emit_harness_md(self, repo_root: Path, always_rules: list[Rule]) -> Path:
        name = repo_root.name or "harness"
        description = f"Coding-agent harness for {name}."
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
        present = [d for d in _TOP_LEVEL_DIRS if (repo_root / d).is_dir()]
        for dir_name in present:
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
        target.write_text(emitter.with_sentinel_body(frontmatter, body), encoding="utf-8")
        return target

    # --- .leaf-detectors ---------------------------------------------------

    def _emit_leaf_detectors(self, repo_root: Path) -> Path:
        target = repo_root / ".leaf-detectors"
        target.write_text(
            emitter.leaf_detectors_file({"skill": _SKILL_PRIMARY_FILE}), encoding="utf-8"
        )
        return target

    # --- sidecar -----------------------------------------------------------

    def _emit_sidecar(self, repo_root: Path, entries: list[ManifestEntry]) -> list[Path]:
        manifest_path = manifest.write_manifest(repo_root, entries)
        leaf_marker = emitter.harnessleaf_path(repo_root / manifest.SIDECAR_DIRNAME)
        leaf_marker.write_text("", encoding="utf-8")
        return [manifest_path, leaf_marker]

    # --- cleanup -----------------------------------------------------------

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        return [repo_root / d for d in _TOP_LEVEL_DIRS]

    def _read_prior_engine_files(self, repo_root: Path) -> set[Path]:
        """Resolve the non-sentinel engine files recorded by the prior manifest.

        Scripts and raw assets carry no sentinel, so ``cleanup_stale`` cannot
        recognise them by reading their contents. The prior manifest's script
        paths give their ownership; this is read at the START of ``finalize``
        before the manifest is overwritten.
        """
        prior = manifest.read_manifest(repo_root)
        if prior is None:
            return set()
        files: set[Path] = set()
        for entry in prior.entries:
            for script in entry.scripts:
                files.add((repo_root / script.path).resolve())
        return files

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Remove engine-owned files no longer backing a current artifact.

        Engine ownership is established two ways, preserving user files:

        - **Text files** carrying :data:`SENTINEL` anywhere in their contents.
        - **Non-sentinel files** (scripts/raw assets) whose path was recorded in
          the **prior** ``.playbook/manifest.toml`` (stashed at finalize start).

        Files that are neither — user-authored markdown without the sentinel, or
        binary assets the engine never wrote — are never deleted. Single root
        files (``HARNESS.md``, ``.leaf-detectors``) are handled separately.
        """
        deleted: list[Path] = []
        deleted.extend(self._scan_output_dirs(written_paths, repo_root))
        deleted.extend(self._scan_root_files(written_paths, repo_root))
        return deleted

    def _scan_output_dirs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        deleted: list[Path] = []
        for output_dir in self._output_directories(repo_root):
            if not output_dir.is_dir():
                continue
            for path in output_dir.rglob("*"):
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if resolved in written_paths:
                    continue
                if self._is_engine_owned(path, resolved):
                    path.unlink()
                    deleted.append(path)
        return deleted

    def _scan_root_files(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        deleted: list[Path] = []
        for filename in ("HARNESS.md", ".leaf-detectors"):
            path = repo_root / filename
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved in written_paths:
                continue
            if self._has_sentinel(path) or resolved in self._prior_engine_files:
                path.unlink()
                deleted.append(path)
        return deleted

    def _is_engine_owned(self, path: Path, resolved: Path) -> bool:
        if resolved in self._prior_engine_files:
            return True
        return self._has_sentinel(path)

    @staticmethod
    def _has_sentinel(path: Path) -> bool:
        try:
            return SENTINEL in path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return False

    @staticmethod
    def _rel(path: Path, repo_root: Path) -> str:
        return path.relative_to(repo_root).as_posix()
