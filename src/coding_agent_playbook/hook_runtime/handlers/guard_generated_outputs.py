"""guard-generated-outputs: deny hand-edits to generated files; point at the canonical source (specs/prK-hook-pack.md §E.1).

The targets are the file tool's write paths (Edit, MultiEdit, Write,
NotebookEdit, OpenCode's ``apply_patch`` headers) and every Bash write target
``shell.parse.write_targets`` extracts. Each is classified against the rendered
protected set (``protected.classify``); the first protected one denies with
a reason of at most 4 lines chosen by its provenance, which always ends in
``then run playbook validate && playbook sync`` (the next sync would silently
overwrite the edit), except for a hook artifact: that is the user's guardrail
configuration, so the reason says to ask the user and teaches no command.

What passes: creating a new path, reading (``cp AGENTS.md /tmp/x`` writes only
``/tmp/x``), and the restore commands (``playbook sync``, ``playbook init``,
``git checkout|restore``; the ``restore_commands`` config key, an ``extend``
key), whose argv-derived targets are exempt while their redirects stay
checked. ``PLAYBOOK_ALLOW_GENERATED_EDIT=1`` counts only from the hook
process env (``EscapeHatches``), never from a command's ``VAR=1`` prefix.

No subprocess, render or TOML read on any path; ``machine.json`` is read only
when a target lies outside the repository (installed resources). Shell parsing
errs toward false negatives: the ``drift`` Stop stage is the backstop.
"""

from __future__ import annotations

import dataclasses
import posixpath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import clean_text, quote_data
from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.config.protected import classify, protected_paths
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._targets import (
    file_write_paths,
    shell_write_targets,
)
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.config.pin import MachinePins
    from coding_agent_playbook.hook_runtime.config.protected import ProtectedEntry, ProtectedHit
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["CONFIG_SCHEMA", "deny_reason", "guard_generated_outputs"]

CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "extra_protected": ConfigKey("list", "extend"),
    "restore_commands": ConfigKey("list", "extend"),
}
#: The engine's restore commands; ``HOOK.md`` ships them and overlays may add more.
DEFAULT_RESTORE_COMMANDS: Final = ("playbook sync", "playbook init", "git checkout", "git restore")

_TAIL: Final = "then run playbook validate && playbook sync"
_ARTIFACT_KINDS: Final = frozenset({"rule", "prompt", "skill", "hook"})
_PATH_CHARS: Final = 80
_ID_CHARS: Final = 60


@register_hook_handler(
    "guard_generated_outputs",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "none"],
    config_schema=CONFIG_SCHEMA,
)
def guard_generated_outputs(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny the first write target ``playbook sync`` owns; ``None`` (pass) otherwise.

    Example::

        >>> guard_generated_outputs(edit_of_agents_md, ctx).reason.splitlines()[-1]
        ... # doctest: +SKIP
        'It is generated from rules; edit playbook/rules/<id> (ids: playbook check), then ...'
    """
    if ctx.hatches.allow_generated_edit or ev.tool is None or ev.repo is None:
        return None
    config = HookConfig(ctx.config, CONFIG_SCHEMA)
    targets = _targets(ev, ctx, config)
    if not targets:
        return None
    pset = protected_paths(
        ctx.cfg,
        _machine(ev, targets),
        platform=ctx.platform,
        extra=config.strings("extra_protected", blanks="keep", strict=True),
    )
    for target in targets:
        hit = classify(pset, target)
        if hit is not None:
            return HandlerResult(
                decision=Decision.DENY,
                hook_id=ctx.hook.id,
                rule_id=hit.kind,
                reason=deny_reason(hit, composite=_is_singleton(pset.output_dirs, target)),
            )
    return None


def deny_reason(hit: ProtectedHit, *, composite: bool = False) -> str:
    """The ≤4-line reason for ``hit``, chosen by provenance (§E.1).

    ``composite`` marks a sentinel hit on a multi-source singleton
    (``AGENTS.md``, ``.claude/CLAUDE.md``, ``.claude/rules/coding-agent-playbook.md``)
    that has no lock row.

    Example::

        >>> deny_reason(ProtectedHit("AGENTS.md", "hook_artifact")).splitlines()[1]
        'Do not edit it; ask the user.'
    """
    path = quote_data(hit.path, _PATH_CHARS)
    entry = hit.entry
    if hit.kind == "hook_artifact":
        return (
            f"{path} is a playbook guardrail file (hook configuration); only the user may "
            "change it.\nDo not edit it; ask the user."
        )
    if hit.kind == "resource":
        return (
            f"{path} is an installed engine or overlay resource and is read-only.\n"
            "Add a same-id override under playbook/{rules,prompts,skills}/ (repo-local wins),"
            f"\n{_TAIL}"
        )
    if composite or (entry is not None and entry.kind == "composite"):
        return f"{_generated(path)}\n{_composite_fix()}"
    if entry is None or entry.kind not in _ARTIFACT_KINDS or not entry.artifact_id:
        return f"{_generated(path)}\n{_generic_fix()}"
    return _artifact_reason(path, entry)


def _artifact_reason(path: str, entry: ProtectedEntry) -> str:
    """A rule/prompt/skill/hook output: edit the repo-local source, else override by id."""
    kind, artifact = entry.kind, clean_text(entry.artifact_id)[:_ID_CHARS]
    origin = (
        f"{path} is generated by playbook sync from {kind} {quote_data(artifact)} "
        f"(source {quote_data(entry.source, _ID_CHARS)}); hand edits are overwritten."
    )
    if entry.source == "<repo-local>":
        source = quote_data(f"playbook/{kind}s/{artifact}")
        return f"{origin}\nEdit its source {source} instead, {_TAIL}"
    return (
        f"{origin}\nAdd a same-id override under playbook/{kind}s/ (repo-local wins; never edit "
        f"installed packages),\n{_TAIL}"
    )


def _generated(path: str) -> str:
    return f"{path} is generated by playbook sync; hand edits are overwritten."


def _composite_fix() -> str:
    return f"It is generated from rules; edit playbook/rules/<id> (ids: playbook check), {_TAIL}"


def _generic_fix() -> str:
    return f"Edit the canonical source under playbook/ (or add a same-id override there),\n{_TAIL}"


def _targets(ev: CanonicalEvent, ctx: HandlerContext, config: HookConfig) -> list[NormalizedPath]:
    """Every path the call writes: file-tool write paths, then the Bash write targets.

    A Bash command none of whose segments writes anything (``ls``, ``pytest``,
    ``git status``: most of them) stops here, before the restore rules are read
    and any target is normalized (review finding #8); a restore exemption only
    removes targets, so it could not add one.
    """
    tool = ev.tool
    if tool is None:
        return []
    found = file_write_paths(tool)
    command = tool.command
    if command is not None and _any_write_target(command.segments):
        restore = _restore_commands(config)
        found.extend(shell_write_targets(ev, ctx, lambda s: _segment_targets(s, restore)))
    return found


def _any_write_target(segments: Sequence[Segment]) -> bool:
    from coding_agent_playbook.hook_runtime.shell.parse import write_targets  # Bash branch only

    return any(write_targets(segment) for segment in segments)


def _segment_targets(segment: Segment, restore: Sequence[tuple[str, ...]]) -> list[str]:
    """``write_targets`` of ``segment``; a restore command keeps only its redirect targets."""
    from coding_agent_playbook.hook_runtime.shell.parse import write_targets  # Bash branch only

    if _is_restore(segment.argv, restore):
        return write_targets(dataclasses.replace(segment, argv=()))
    return write_targets(segment)


def _restore_commands(config: HookConfig) -> list[tuple[str, ...]]:
    commands = (
        config.strings("restore_commands", blanks="keep", strict=True) or DEFAULT_RESTORE_COMMANDS
    )
    return [tuple(command.split()) for command in commands if command.split()]


def _is_restore(argv: Sequence[str], restore: Sequence[tuple[str, ...]]) -> bool:
    """Whether ``argv`` starts with one of ``restore``'s word sequences (program by basename)."""
    if not argv:
        return False
    words = (posixpath.basename(argv[0]), *argv[1:])
    return any(words[: len(command)] == command for command in restore)


def _machine(ev: CanonicalEvent, targets: Iterable[NormalizedPath]) -> MachinePins | None:
    """``machine.json``, read only when a target lies outside the repository."""
    if ev.repo is None or all(target.same_repo for target in targets):
        return None
    from coding_agent_playbook.hook_runtime.config.pin import read_machine_pins

    return read_machine_pins(git_dir=ev.repo.git_dir)


def _is_singleton(output_dirs: Iterable[str], target: NormalizedPath) -> bool:
    """Whether ``target`` is a composite singleton (an ``output_dirs`` file, not a dir)."""
    return any(target.key == entry for entry in output_dirs if not entry.endswith("/"))
