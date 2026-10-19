"""Claude Code adapter (SPEC §10.3).

Translates canonical ``Rule`` / ``Prompt`` / ``Skill`` artifacts into Claude
Code's native layout:

- Always rules are **buffered** during ``write_rule`` and composed during
  ``finalize`` (priority then ``id`` order) into one unscoped rules file,
  ``.claude/rules/coding-agent-playbook.md``, next to a rule-free
  ``.claude/CLAUDE.md`` stub (SPEC §10.3.1). A generated ``## Where guidance
  lives`` section follows them, byte-identical to the one in ``AGENTS.md``. A
  member rule (one that names a skill in ``skill:``) is not in that file: it is
  a reference of its skill under ``.claude/skills/<skill>/references/``
  (ADR 0001, specs/prS-skills-context.md 6.4.6).
- Prompts are written immediately to ``.claude/commands/{slash}.md`` as pure
  markdown (no top-level frontmatter — Claude Code commands are plain md).
- Skills are written natively to ``.claude/skills/{id}/`` (``SKILL.md`` plus
  byte-copied ``scripts/`` and ``references/``, and the rendered member rules)
  through the shared
  :class:`~coding_agent_playbook.adapters._skill_writer.SkillWriter`, so the
  output is byte-identical to the ``opencode`` / ``shared_skills`` skill roots.
- Hooks it enforces become managed groups in the co-owned
  ``.claude/settings.json`` plus the committed ``.claude/hooks/playbook/launch.sh``
  (:mod:`._claude_hooks`, specs/prK-lifecycle-hooks.md §C.2); the rest degrade
  to rules-file sections through :meth:`write_rule` (§C.4.2) and get their full
  text in ``.claude/skills/playbook-guardrails/`` (D6, D26), and the
  session-start heartbeat line closes the rules file.

Why the rules (and, since PR K, the hook advisories and the heartbeat line)
leave ``.claude/CLAUDE.md``: OpenCode v1 (anomalyco/opencode v1.19.3,
``session/instruction.ts:171-218`` via ``tool/read.ts:300``) attaches the first
``AGENTS.md``/``CLAUDE.md`` of every directory between a file it reads and its
working directory, so when its read tool opened a file under ``.claude/`` (once
per uncompacted session, SPEC §10.6) it added a second full copy of the rules
the root ``AGENTS.md`` already gives it, plus a heartbeat instruction a hookless
OpenCode session can never satisfy. Neither OpenCode v1.19.3 nor v2 (dev
24c7f7a) discovers ``.claude/rules/`` by default (v1 looks up files named
``AGENTS.md``/``CLAUDE.md``/``CONTEXT.md``; v2 only ``AGENTS.md``, and its
``.claude/`` compatibility reads only ``skills/``), while Claude Code loads a
``.claude/rules/*.md`` file without ``paths:`` frontmatter "at launch with the
same priority as ``.claude/CLAUDE.md``" (code.claude.com/docs/en/memory).
Live-verified on Claude Code 2.1.292 (2026-10-16): with ``AGENTS.md``, a
header-only ``.claude/CLAUDE.md`` and a ``.claude/rules/`` file, Claude loads
only the rules file, from the repo root and from a subdirectory.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

from coding_agent_playbook.adapters._claude_hooks import (
    ClaudeHookEmitter,
    plans_launcher,
    runs_natively,
)
from coding_agent_playbook.adapters._owned_files import (
    check_engine_owned,
    check_unlinked,
    crosses_symlink,
    write_engine_owned,
)
from coding_agent_playbook.adapters._skill_writer import SkillWriter
from coding_agent_playbook.adapters._where_guidance import WhereGuidanceBuffer
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_rule_paths import (
    CLAUDE_CODE_COMPOSITES,
    CLAUDE_MD_PATH,
    CLAUDE_RULES_PATH,
)
from coding_agent_playbook.adapters.claude_settings import CLAUDE_SETTINGS_PATH
from coding_agent_playbook.generated_output.output_io import write_output_bytes, write_output_text
from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hook_policy import HOOK_SUPPORT
from coding_agent_playbook.hook_policy.guardrails_skill import has_guardrail_text
from coding_agent_playbook.hook_registrations import LAUNCHER_PATH
from coding_agent_playbook.renderer import render_for
from coding_agent_playbook.skill_membership import is_skill_member

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.adapters.claude_settings import MergeResult
    from coding_agent_playbook.config.tables.hooks import HooksConfig
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.lockfile.model import LockEntry, Lockfile
    from coding_agent_playbook.prompt_rule_delivery import SkillReferenceIndex
    from coding_agent_playbook.types import Prompt, Rule, Skill

#: The committed launcher's directory: sentinel-scanned, and a declared output location.
_LAUNCHER_DIR = LAUNCHER_PATH.rsplit("/", 1)[0]

#: The stub is this title's header alone; the rules file opens with the other
#: (paths and the WHY of the stub: :mod:`.claude_rule_paths`).
_CLAUDE_MD_TITLE: Final = "# CLAUDE.md"
_RULES_FILE_TITLE: Final = "# Project rules (coding-agent-playbook)"


def _generated_header(title: str) -> str:
    """Sentinel line, ``title`` heading and the generated-by line both files open with.

    Example: ``_generated_header("# CLAUDE.md")`` is the whole ``.claude/CLAUDE.md`` stub.
    """
    return f"{sentinel_line('html')}\n{title}\n\nThis file is generated by coding-agent-playbook.\n"


def check_rule_files_writable(repo_root: Path) -> None:
    """Raise :class:`~._owned_files.UserOwnedFileError` unless both rule files may be written.

    The rules file must be engine-owned (nothing there, or an unshared
    sentinel-tagged regular file; no symlink on the way): ``.claude/rules/``
    holds the user's own files.
    The stub keeps its plain overwrite of a regular file, but never through a
    symlink or a hard link, and never over a directory or a FIFO: the common
    ``.claude/CLAUDE.md -> ../AGENTS.md`` link, or the same file hard-linked,
    turned ``AGENTS.md`` into the 4-line stub for every other tool (review
    round 2, final review). ``playbook sync`` calls this on the real repo before
    any adapter writes; :meth:`ClaudeCodeAdapter.finalize` calls it again
    before writing either file.

    Example: ``check_rule_files_writable(ctx.repo_root)``.
    """
    check_engine_owned(repo_root / CLAUDE_RULES_PATH, repo_root)
    check_unlinked(repo_root / CLAUDE_MD_PATH, repo_root)


def _write_output(path: Path, text: str) -> Path:
    """Write ``text`` to ``path`` as UTF-8 LF bytes (creating its parent) and return ``path``.

    Bytes, not text, like the rules file (:func:`~._owned_files.write_engine_owned`):
    ``write_text`` would write the stub CRLF on Windows (final review).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    write_output_bytes(path, text.encode("utf-8"))
    return path


class ClaudeCodeAdapter(Adapter):
    """Adapter for Anthropic's Claude Code (``.claude/`` layout).

    The optional ``rule_registry`` (the sync's ``RuleRegistryImpl``) is used
    only as a ``SkillReferenceIndex``: :func:`render_for` builds each command's
    ``## Before you start`` block from it, naming the skill references of the
    prompt's ``includes_rules``; a command never carries rule text (D15). When
    callers (or tests) omit it, prompts render with no block —
    ``includes_rules:`` becomes purely declarative.
    """

    name = "claude_code"

    #: Native skills root; Claude Code discovers ``.claude/skills/<name>/SKILL.md``.
    _SKILL_WRITER: ClassVar[SkillWriter] = SkillWriter(Path(".claude") / "skills")
    native_skills_root: ClassVar[str | None] = _SKILL_WRITER.root.as_posix()

    output_locations: ClassVar[tuple[str, ...]] = (
        *CLAUDE_CODE_COMPOSITES,
        ".claude/commands/",
        _SKILL_WRITER.location,
        f"{_LAUNCHER_DIR}/",
    )

    #: Every canonical event, with every decision it allows (§C.5.1).
    hook_support: ClassVar[Mapping[str, frozenset[str]]] = HOOK_SUPPORT["claude_code"]

    #: Co-owned with the user and Claude Code itself: only managed elements are
    #: ours (scoped lock entries), so the file is never deleted or gitignored.
    shared_outputs: ClassVar[tuple[str, ...]] = (CLAUDE_SETTINGS_PATH,)

    #: The launcher carries no artifact of its own: a ``kind = "runtime"`` lock entry (§B.6).
    runtime_outputs: ClassVar[tuple[str, ...]] = (LAUNCHER_PATH,)

    def __init__(self, *, rule_registry: SkillReferenceIndex | None = None) -> None:
        # Buffer of (priority, rule_id, rendered_section) tuples populated by
        # ``write_rule``. ``finalize`` sorts by (priority, rule_id) and joins.
        self._buffered_rules: list[tuple[int, str, str]] = []
        self._where = WhereGuidanceBuffer()
        self._rule_registry = rule_registry
        self._hooks = ClaudeHookEmitter(self.name, self.hook_support)

    def begin_sync(
        self,
        repo_root: Path,
        prior_lock: Lockfile | None,
        *,
        hooks_config: HooksConfig | None = None,
    ) -> None:
        """Remember the real repo (``settings.json`` is read there), the prior hashes and ``[hooks]``.

        Example: ``adapter.begin_sync(ctx.repo_root, lock, hooks_config=cfg)``.
        """
        self._hooks.begin(repo_root, prior_lock, hooks_config)

    def write_hook(self, hook: ResolvedHook, repo_root: Path) -> list[Path]:
        """Buffer a hook Claude Code enforces; degrade any other to a rules-file section.

        A natively enforced hook adds no advisory here: its deny reasons and
        the session-start briefing carry the context (§C.4.2). Writes nothing;
        :meth:`finalize` does.

        Example: ``adapter.write_hook(hook, repo_root)`` -> ``[]``.
        """
        if self._hooks.add(hook):
            return []
        return super().write_hook(hook, repo_root)

    def writes_guardrails_skill(self, hooks: Sequence[ResolvedHook]) -> bool:
        """``True`` only for a hook with guardrail text that Claude Code cannot run (D6, D26).

        Claude Code runs the core pack natively, so its skill listing pays for
        no guardrails skill; an overlay hook without ``claude_code`` in
        ``supports``, or one whose events Claude cannot reach, degrades and gets
        its full text there. :func:`~._claude_hooks.runs_natively` is the test
        :meth:`write_hook` uses too, so the two never disagree.

        Example: ``adapter.writes_guardrails_skill([native_hook])`` -> ``False``.
        """
        degraded = (h for h in hooks if not runs_natively(h, self.name, self.hook_support))
        return has_guardrail_text(degraded)

    def planned_runtime_outputs(self, hooks: Sequence[ResolvedHook]) -> tuple[str, ...]:
        """``(LAUNCHER_PATH,)`` exactly when :meth:`finalize` writes the launcher for ``hooks``.

        Same plan as the emitter (any registration), so ``playbook sync``
        refuses a user's same-named file only when it would overwrite it.

        Example: ``adapter.planned_runtime_outputs([])`` -> ``()``.
        """
        return (LAUNCHER_PATH,) if plans_launcher(hooks, self.name, self.hook_support) else ()

    def managed_lock_entries(self) -> list[LockEntry]:
        """One scoped entry per managed ``settings.json`` element, unchanged ones included."""
        return self._hooks.entries()

    @property
    def settings_merge(self) -> MergeResult | None:
        """What the last :meth:`finalize` merge did (warnings, counts), or None if it never ran."""
        return self._hooks.merge

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Buffer a rendered claude_md_section for ``finalize`` to compose.

        Claude Code consumes rules through one composed rules file rather than
        per-rule files, so this method writes nothing immediately. The
        buffered tuple records (priority, rule_id, rendered_section) so
        ``finalize`` can sort by ``(priority, rule_id)`` for stable output. A
        member rule is skipped (E3): its skill's reference delivers it. The
        advisory rule of a hook this adapter cannot enforce has ``skill=None``,
        so it keeps its full section (H16).

        Example: ``adapter.write_rule(member_rule, repo_root)`` -> ``[]``, nothing buffered.
        """
        if is_skill_member(rule):
            return []
        rendered_section = render_for(
            rule.source_path or Path("inline"),
            rule.body,
            "claude_md_section",
            frontmatter=dataclasses.asdict(rule.frontmatter),
        )
        self._buffered_rules.append(
            (rule.frontmatter.priority, rule.frontmatter.id, rendered_section)
        )
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a Claude Code slash-command to ``.claude/commands/{slash}.md``.

        Claude Code commands are pure markdown (no top-level frontmatter
        fence); the ``prompt_claude_command`` renderer handles that shape
        plus the ``## Before you start`` block pointing at skills (D15).

        Example: ``adapter.write_prompt(prompt, repo_root)`` -> ``[.claude/commands/review.md]``.
        """
        rendered = render_for(
            prompt.source_path or Path("inline"),
            prompt.body,
            "prompt_claude_command",
            frontmatter=dataclasses.asdict(prompt.frontmatter),
            skill_references=self._rule_registry,
        )
        output_path = repo_root / ".claude" / "commands" / f"{prompt.frontmatter.slash}.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_output_text(output_path, rendered)
        return [output_path]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Write a native skill directory under ``.claude/skills/<id>/``.

        Buffers the skill's ``## Where guidance lives`` line for the rules
        file, then delegates to the shared :class:`SkillWriter` (``SKILL.md``
        with ``name`` = id and the sentinel as first body line, plus byte-copied
        ``scripts/`` and ``references/`` and the member references). This
        adapter does NOT degrade to ``Skill.to_prompt`` — siblings without
        native skill support (e.g. Continue) use the ABC default.

        Example: ``adapter.write_skill(skill, repo_root)`` -> ``[.../SKILL.md, ...]``.
        """
        self._where.add(skill)
        return self._SKILL_WRITER.write(skill, repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        """Compose the ``.claude/CLAUDE.md`` stub and the rules file, then the hook outputs.

        ``settings.json`` is merged first: a file that cannot be merged safely
        raises :class:`~.claude_settings.SettingsMergeError` before this adapter
        writes anything. A rules-file path the user holds, or a symlinked stub,
        raises :class:`~._owned_files.UserOwnedFileError` (``playbook sync``
        checks both on the real repo before any adapter runs). Returns the
        paths written; ``settings.json`` only when the merge changed it.

        Example::

            adapter.write_rule(rule, repo_root)
            adapter.finalize(repo_root)
            # [repo_root/.claude/CLAUDE.md, repo_root/.claude/rules/coding-agent-playbook.md]
        """
        hook_paths = self._compose_settings(repo_root)
        return [*self._compose_rule_files(repo_root), *hook_paths]

    def _compose_rule_files(self, repo_root: Path) -> list[Path]:
        """Write the rule-free stub and the rules file; ``[]`` when there is nothing to carry.

        Nothing buffered and no heartbeat line writes neither file, so a stale
        engine-owned pair is left to :meth:`stale_outputs`. Both paths are
        checked (:func:`check_rule_files_writable`) before either is written, so
        a refusal (:class:`~._owned_files.UserOwnedFileError`) leaves neither
        half-written: the rules file only over nothing or a sentinel-tagged
        file, the stub over any regular file that is not a hard link, and
        neither through a symlink.
        """
        body = self._rules_body()
        if body is None:
            return []
        check_rule_files_writable(repo_root)
        rules_path = repo_root / CLAUDE_RULES_PATH
        rules_text = f"{_generated_header(_RULES_FILE_TITLE)}\n{body}"
        return [
            _write_output(repo_root / CLAUDE_MD_PATH, _generated_header(_CLAUDE_MD_TITLE)),
            write_engine_owned(rules_path, repo_root, rules_text.encode("utf-8")),
        ]

    def _rules_body(self) -> str | None:
        """The rules file's body, or ``None`` when no section, Where entry or heartbeat exists.

        Sections (always rules, and advisories of hooks this adapter cannot
        enforce) are sorted by ``(priority, rule_id)`` and joined by the blank
        lines ``claude_md_section`` already emits, so they stay byte-identical
        to the ``AGENTS.md`` sections; the ``## Where guidance lives`` section
        follows them. The fixed heartbeat line closes the body when the
        session-start briefing runs here.
        """
        heartbeat = self._hooks.heartbeat()
        ordered = sorted(self._buffered_rules, key=lambda item: (item[0], item[1]))
        sections = self._where.after([section for _, _, section in ordered])
        if not (sections or heartbeat):
            return None
        body = "\n".join(sections)
        if heartbeat:
            body += ("\n" if sections else "") + heartbeat + "\n"
        return body

    def _compose_settings(self, repo_root: Path) -> list[Path]:
        """Merge the managed groups into ``settings.json``; write the launcher when any exists."""
        return self._hooks.emit(repo_root)

    def _output_directories(self, repo_root: Path) -> Iterable[Path]:
        """``.claude/commands/`` and the launcher dir use the sentinel scan.

        ``.claude/skills/`` is never scanned: stale skill output is settled by
        ``playbook sync``'s lockfile leftover policy (SPEC §4.2 step 9, §10.8).
        ``settings.json`` is never stale: managed elements are removed inside
        :meth:`finalize`, and the co-owned file itself is never deleted.
        ``.claude/rules/`` is never scanned either: only its one engine file is
        checked (:meth:`stale_outputs`), every other rules file is the user's.
        """
        return [repo_root / ".claude" / "commands", repo_root / _LAUNCHER_DIR]

    def stale_outputs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Generated files that no longer back a current artifact (deletes nothing).

        - ``.claude/commands/``: every sentinel-tagged file not in
          ``written_paths`` (the ABC's sentinel scan).
        - ``.claude/CLAUDE.md`` and ``.claude/rules/coding-agent-playbook.md``:
          each only if it carries the sentinel, was not re-written this sync
          (``finalize`` skipped it) and is reached through no symlink, so a
          user-authored or linked file at either path is preserved. No other
          ``.claude/rules/`` file is ever reported.

        "Sentinel-tagged" is the shared anchored rule (``_sentinel.has_sentinel``
        via :meth:`Adapter._carries_sentinel`). ``.claude/skills/`` is
        deliberately left out: a skill dir mixes engine output with files a user
        may have edited or added, so only the lockfile leftover policy
        (pristine + untracked + listed) may delete there.

        Example::

            orphans = adapter.stale_outputs(set(), repo_root)  # no rule applies
            # [repo_root/.claude/CLAUDE.md, repo_root/.claude/rules/coding-agent-playbook.md]
        """
        stale = self._stale_by_sentinel(written_paths, repo_root)
        composites = (repo_root / rel for rel in CLAUDE_CODE_COMPOSITES)
        stale.extend(
            path for path in composites if self._is_stale_composite(path, repo_root, written_paths)
        )
        return stale

    def _is_stale_composite(self, path: Path, repo_root: Path, written_paths: set[Path]) -> bool:
        """An engine-owned (sentinel-tagged) composite file this sync did not re-write.

        Never one reached through a symlink (the file itself, ``.claude`` or
        ``.claude/rules``): the engine never writes through a link, so whatever
        it reaches is the user's, possibly outside the repo — the rule of
        :meth:`Adapter._scan_targets` and the lockfile orphan scan.
        """
        if crosses_symlink(path, repo_root) or not path.is_file():
            return False
        return path.resolve() not in written_paths and self._carries_sentinel(path)
