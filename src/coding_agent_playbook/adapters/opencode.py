"""OpenCode adapter. See SPEC.md §10.6.

OpenCode reads ``AGENTS.md`` natively for rules (walking up the directory
tree and loading every ``AGENTS.md`` on the way; v1 also falls back to
``CLAUDE.md`` when none exists and, on reads, attaches a subdirectory
``CLAUDE.md`` such as ``.claude/CLAUDE.md``; the v2 core reads ``AGENTS.md``
only — SPEC §10.6), so rules are routed through the AGENTS.md adapter. The
``claude_code`` adapter keeps ``.claude/CLAUDE.md`` rule-free (its rules, hook
advisories and heartbeat line live in ``.claude/rules/``, which neither
OpenCode v1.19.3 nor v2 (dev 24c7f7a) discovers by default), so that v1
attachment adds only a short header, not a second copy of the rules. This
adapter writes OpenCode's own native outputs:

- prompts -> ``.opencode/command/<slash>.md`` slash commands;
- skills  -> ``.opencode/skills/<id>/`` (``SKILL.md`` + ``scripts/`` +
  ``references/``) through the shared
  :class:`~coding_agent_playbook.adapters.skill_dirs.writer.SkillWriter`, so OpenCode
  no longer depends on the ``claude_code`` adapter being enabled for skills. A
  scoped rule that names a skill (a member rule, ADR 0001) reaches OpenCode
  here, as ``references/<rule-id>.md`` of that skill;
- hooks   -> exactly one generated V1 plugin, ``.opencode/plugins/playbook-hooks.js``
  (specs/prK-lifecycle-hooks.md §C.3), which forwards the events OpenCode can
  enforce to ``playbook-hook``. It is the one exception to SPEC §10.6.4's "never
  touch ``.opencode/plugin(s)/``": the adapter owns that single path, every
  other file there stays the user's, and ``opencode.json`` is never touched.
  A user file already at that path (no sentinel line) or a symlink on the way
  is refused, never overwritten (``generated_output.write_guard``).
  Hook advisories reach OpenCode through ``AGENTS.md``, like rules, and as the
  sections of the ``playbook-guardrails`` skill written here
  (:meth:`OpenCodeAdapter.writes_guardrails_skill`, D6).

OpenCode *also* scans ``.agents/skills/`` and ``.claude/skills/`` (compatibility
roots), so with ``shared_skills`` and ``claude_code`` enabled the same skill is
found up to three times. That is safe: OpenCode keeps one skill per key — v2
keys a ``Map`` by the skill directory name (``packages/core/src/skill.ts:100-101``)
and registers one copy per id with precedence ``.opencode > .agents > .claude``;
v1.19.x keys a record by frontmatter ``name`` and logs one "duplicate skill name"
warning per extra copy (``packages/opencode/src/skill/index.ts:125-134``), which
``OPENCODE_DISABLE_EXTERNAL_SKILLS`` / ``OPENCODE_DISABLE_CLAUDE_CODE_SKILLS``
silence; the engine sets neither. The engine writes ``name`` = id = directory
name and every copy is byte-identical.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.skill_dirs.writer import SkillWriter
from coding_agent_playbook.generated_output.file_identity import FileSet
from coding_agent_playbook.generated_output.output_io import write_output_text
from coding_agent_playbook.generated_output.symlinks import real_path
from coding_agent_playbook.generated_output.write_guard import write_engine_owned
from coding_agent_playbook.hooks.guardrails_skill import has_guardrail_text
from coding_agent_playbook.hooks.registrations.opencode import (
    OPENCODE_SHIM_PATH,
    plan_opencode_reg,
    render_opencode_shim,
)
from coding_agent_playbook.hooks.resolution.tables import HOOK_SUPPORT
from coding_agent_playbook.rendering.formats import render_for

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook
    from coding_agent_playbook.rendering.prompt_rule_delivery import SkillReferenceIndex


class OpenCodeAdapter(Adapter):
    """Translate canonical prompts, skills and hooks into OpenCode's native layout.

    Rules are an intentional no-op on this adapter: OpenCode picks up always
    rules from the AGENTS.md adapter's output (``AGENTS.md`` at repo root), and
    member rules as references of the skills :meth:`write_skill` writes. See
    SPEC.md §10.6 and §10.6.4 for the OpenCode-touches/does-not-touch matrix.

    The optional ``rule_registry`` (the sync's ``RuleRegistryImpl``) is used
    only as a ``SkillReferenceIndex``: :func:`render_for` builds each command's
    ``## Before you start`` block from it, naming the skill references of the
    prompt's ``includes_rules``; a command never carries rule text (D15). When
    callers (or tests) omit it, prompts render with no block —
    ``includes_rules:`` becomes purely declarative.

    Hooks are buffered by :meth:`write_hook` and rendered by :meth:`finalize`
    into the one shim; with no hook OpenCode enforces, nothing is written.
    """

    name = "opencode"

    #: Native skills root; OpenCode discovers ``.opencode/skills/<name>/SKILL.md``.
    _SKILL_WRITER: ClassVar[SkillWriter] = SkillWriter(Path(".opencode") / "skills")
    native_skills_root: ClassVar[str | None] = _SKILL_WRITER.root.as_posix()

    #: The shim is declared as a file, never its directory: the leftover policy
    #: may delete a pristine stale shim but never prunes the user's plugins dir.
    output_locations: ClassVar[tuple[str, ...]] = (
        ".opencode/command/",
        _SKILL_WRITER.location,
        OPENCODE_SHIM_PATH,
    )

    #: pre_tool_use, post_tool_use, session_start (degraded), stop (evidence-only).
    #: pre_compact is not registered: its only decision is ``none`` (§C.1.2).
    hook_support: ClassVar[Mapping[str, frozenset[str]]] = HOOK_SUPPORT["opencode"]

    #: The shim carries no artifact of its own: a ``kind = "runtime"`` lock entry (§B.6).
    runtime_outputs: ClassVar[tuple[str, ...]] = (OPENCODE_SHIM_PATH,)

    def __init__(self, *, rule_registry: SkillReferenceIndex | None = None) -> None:
        self._rule_registry = rule_registry
        self._hooks: list[ResolvedHook] = []

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Return ``[]`` — OpenCode reads ``AGENTS.md`` natively.

        Rules are emitted by the AGENTS.md adapter at the repo root, which
        OpenCode picks up by walking up the directory tree (``CLAUDE.md`` is
        read by v1 only; see SPEC §10.6). Duplicating them here would only
        create drift, so this method is intentionally a no-op.
        """
        del rule, repo_root
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a single OpenCode slash command to ``.opencode/command/<slash>.md``.

        The body is shaped by :func:`render_for` using the
        ``prompt_opencode_command`` format, which:

        * emits the YAML envelope ``---\\ndescription: ...\\n---``,
        * replaces ``{{ var }}`` placeholders for each ``input_variables``
          entry with ``$ARGUMENTS`` (single variable) or ``$1`` / ``$2`` / …
          (multiple variables), and
        * inserts the ``## Before you start`` block naming the skill
          references of ``includes_rules`` (D15), when any is active.

        See SPEC §10.6.1 for the canonical OpenCode command layout and
        SPEC §9.7 for the renderer contract.
        """
        target = repo_root / ".opencode" / "command" / f"{prompt.frontmatter.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_for(
            prompt.source_path or Path("inline"),
            prompt.body,
            "prompt_opencode_command",
            frontmatter=dataclasses.asdict(prompt.frontmatter),
            skill_references=self._rule_registry,
        )
        write_output_text(target, rendered)
        return [target]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Write a native skill directory under ``.opencode/skills/<id>/``.

        Delegates to the shared :class:`SkillWriter`, so the bytes are
        identical to the ``.claude/skills/`` and ``.agents/skills/`` copies.
        Duplicate discovery via those roots is safe (see the module
        docstring: OpenCode keeps one skill per name/id).
        """
        return self._SKILL_WRITER.write(skill, repo_root)

    def write_hook(self, hook: ResolvedHook, repo_root: Path) -> list[Path]:
        """Buffer ``hook`` for :meth:`finalize`; write nothing, return ``[]``.

        Every hook is kept, whatever its ``supports``: the shim's timeouts are
        planned against the deadlines ``guard_config.json`` gets over all of them
        (§D.4). There is no advisory channel here: OpenCode reads ``AGENTS.md``,
        which carries every hook's advisory (§C.1.2).

        Example: ``adapter.write_hook(hook, repo_root)`` -> ``[]``.
        """
        del repo_root
        self._hooks.append(hook)
        return []

    def writes_guardrails_skill(self, hooks: Sequence[ResolvedHook]) -> bool:
        """``True`` when any on hook has guardrail text: OpenCode reads the ``AGENTS.md`` lines.

        Example: ``adapter.writes_guardrails_skill([])`` -> ``False``.
        """
        return has_guardrail_text(hooks)

    def planned_runtime_outputs(self, hooks: Sequence[ResolvedHook]) -> tuple[str, ...]:
        """``(OPENCODE_SHIM_PATH,)`` exactly when :meth:`finalize` writes the shim for ``hooks``.

        Same plan as :meth:`finalize` (a non-empty ``REG``), so ``playbook sync``
        refuses a user's same-named plugin only when it would overwrite it.

        Example: ``adapter.planned_runtime_outputs([])`` -> ``()``.
        """
        return (OPENCODE_SHIM_PATH,) if plan_opencode_reg(hooks) else ()

    def finalize(self, repo_root: Path) -> list[Path]:
        """Write the shim when any buffered hook is enforced on OpenCode; return it.

        The bytes are UTF-8 with LF endings (``write_text`` would emit CRLF on
        Windows) and depend only on the hooks, never on their order. An empty
        ``REG`` writes nothing, and a stale shim is left to :meth:`stale_outputs`.
        A same-named user plugin (no sentinel line) or a symlink on the way raises
        :class:`~.write_guard.UserOwnedFileError` and is never overwritten;
        ``playbook sync`` reports it before any adapter writes.

        Example: ``adapter.finalize(repo_root)`` -> ``[repo_root / OPENCODE_SHIM_PATH]``.
        """
        reg = plan_opencode_reg(self._hooks)
        if not reg:
            return []
        shim = render_opencode_shim(reg).encode("utf-8")
        return [write_engine_owned(repo_root / OPENCODE_SHIM_PATH, repo_root, shim)]

    def stale_outputs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Stale commands (the ABC's sentinel scan) plus a shim this sync did not write.

        The shim is checked as one path, never by walking ``.opencode/plugins/``:
        that dir holds the user's plugins and V2 plugin packages (with their
        ``node_modules``), and a sentinel there does not make a file ours. A shim
        reached through a symlink, or lacking the line-1 sentinel, is the user's.
        Deletes nothing.
        """
        stale = self._stale_by_sentinel(written_paths, repo_root)
        shim = repo_root / OPENCODE_SHIM_PATH
        if self._is_stale_shim(shim, FileSet.of(written_paths), repo_root):
            stale.append(shim)
        return stale

    def _is_stale_shim(self, shim: Path, written: FileSet, repo_root: Path) -> bool:
        """Engine-owned (sentinel, reached without a symlink, not a secret) and not written."""
        spelled = repo_root.resolve().joinpath(OPENCODE_SHIM_PATH)
        # real_path: Path.resolve() raises on a link loop on Python 3.12
        if real_path(spelled) != spelled or written.holds(shim):
            return False
        return bool(self._scan_targets([shim], repo_root)) and self._carries_sentinel(shim)

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        """``.opencode/command/`` is scanned by the ABC's anchored sentinel scan.

        Commands carry the sentinel as the first body line, after the
        ``description`` frontmatter (OpenCode's gray-matter only reads
        frontmatter at offset 0) — the second anchored position
        ``generated_output.sentinel.has_sentinel`` accepts; commands older engines wrote with
        the sentinel on line 1 are still recognised.

        ``.opencode/skills/`` is never scanned: stale skill output is settled by
        ``playbook sync``'s lockfile leftover policy (SPEC §4.2 step 9, §10.8).
        ``.opencode/plugins/`` is never scanned either: :meth:`stale_outputs`
        checks the one shim path. Per SPEC.md §10.6.4, the OpenCode adapter must
        not touch ``.opencode/agent/``, any other file in ``.opencode/plugin(s)/``,
        ``opencode.json``, ``AGENTS.md``, or ``.claude/`` — those belong to the
        user or to sibling adapters.
        """
        return [repo_root / ".opencode" / "command"]
