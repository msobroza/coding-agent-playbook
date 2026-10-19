"""External handlers: an overlay's or the repo's own script, run behind a trust approval (§D.3.1).

Sync byte-copies the script to ``.coding-agent-playbook/hooks/scripts/<id>/``
and renders a repo-relative argv ``[launcher, script, *args]``. Before it runs:

- the user must have approved exactly this code on this machine: a §B.4
  trust entry for ``(source, launcher, sha256(args), script_sha256)``;
- the copy on disk must still hash to that ``script_sha256``, so an agent
  editing the copy turns the hook ``untrusted``, never into new code;
- the launcher resolves through the per-worktree pins (``machine.json``, the
  interpreter pin for ``python``), else ``PATH``; never the repo.

The script reads the canonical event on stdin (``playbook.hook.event/1``) and
prints one JSON object ``{"decision", "reason"?, "context"?, "user_note"?}``.
Anything else (another key such as ``allow`` or ``updatedInput``, invalid JSON,
a non-zero exit) is a contract violation for the failure policy (L6).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.registry import HandlerResolutionError, Untrusted

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.config.guard_config import HookRecord
    from coding_agent_playbook.hook_runtime.dispatch.event import (
        CanonicalEvent,
        EventName,
        ToolCall,
    )
    from coding_agent_playbook.hook_runtime.registry import HandlerContext, ResolveContext
    from coding_agent_playbook.security.trust import HandlerApproval

__all__ = [
    "EVENT_SCHEMA",
    "HOOK_SCRIPTS_DIR",
    "ExternalContractError",
    "ExternalHandler",
    "approval_of",
    "copied_scripts_sha256",
    "event_document",
    "external_handler",
    "parse_external_output",
]

EVENT_SCHEMA: Final = "playbook.hook.event/1"
#: Where sync copies hook scripts; the twin of ``hooks.resolution.tables.HOOK_SCRIPTS_DIR``.
HOOK_SCRIPTS_DIR: Final = ".coding-agent-playbook/hooks/scripts"
_OUTPUT_KEYS: Final = frozenset({"decision", "reason", "context", "user_note"})
_MAX_SCRIPT_BYTES: Final = 16 * 1024 * 1024


class ExternalContractError(Exception):
    """An external handler broke its output contract; an internal error (§D.4)."""


def external_handler(
    record: HookRecord, event: EventName, ctx: ResolveContext
) -> ExternalHandler | Untrusted:
    """The runnable external handler of ``record`` on ``event``, or why it is untrusted.

    Example::

        >>> external_handler(cfg.hooks["bnp-sql"], EventName.PRE_TOOL_USE, ctx)  # doctest: +SKIP
        Untrusted(reason='no user approval covers this handler's code')
    """
    argv = record.handlers[event].argv
    if len(argv) < 2:
        raise HandlerResolutionError(f"external handler of {record.id!r} has no script")
    root = ctx.repo.worktree_root
    if copied_scripts_sha256(record, root) != record.script_sha256:
        return Untrusted("the copied script differs from the approved one")
    if not _approved(record, argv, ctx):
        return Untrusted("no user approval covers this handler's code")
    launcher = _launcher_argv(argv[0], ctx)
    command = (*launcher, os.path.join(root, *argv[1].split("/")), *argv[2:])
    return ExternalHandler(record=record, argv=command, cwd=root, env=dict(ctx.env))


def _approved(record: HookRecord, argv: Sequence[str], ctx: ResolveContext) -> bool:
    trust = ctx.trust()
    return trust is not None and trust.allows_handler(record.id, approval_of(record, argv))


def approval_of(record: HookRecord, argv: Sequence[str] | None = None) -> HandlerApproval:
    """The trust entry that lets ``record``'s external handler run (§B.4).

    ``argv`` defaults to the first external handler's; the interpreter path is
    never part of it, so one approval holds on every machine of the user's.

    Example::

        >>> approval_of(cfg.hooks["bnp-sql"]).launcher  # doctest: +SKIP
        'python'
    """
    from coding_agent_playbook.security.trust import HandlerApproval, sha256_of_json

    if argv is None:
        argv = next(s.argv for s in record.handlers.values() if s.kind == "external")
    return HandlerApproval(
        source=record.source_package,
        launcher=argv[0],
        args_sha256=sha256_of_json(list(argv[2:])),
        script_sha256=record.script_sha256 or "",
    )


def _launcher_argv(launcher: str, ctx: ResolveContext) -> tuple[str, ...]:
    """The launcher as pinned for this worktree (``machine.json``, the interpreter pin), else PATH."""
    from coding_agent_playbook.hook_runtime.config.pin import (
        read_interpreter_pin,
        read_machine_pins,
    )

    git_dir = ctx.repo.git_dir
    pins = read_machine_pins(git_dir=git_dir)
    pinned = None if pins is None else pins.tool(launcher)
    if pinned is not None:
        return pinned.argv
    interpreter = read_interpreter_pin(git_dir=git_dir) if launcher == "python" else None
    found = interpreter or ctx.proc.which(launcher)
    if found is None:
        raise HandlerResolutionError(f"launcher {launcher!r} is neither pinned nor on PATH")
    return (found,)


def copied_scripts_sha256(record: HookRecord, root: str) -> str | None:
    """The digest the trust store approved, recomputed over the copies under ``root``.

    Mirrors ``hooks.resolution.resolved.script_sha256``: one script's own sha256, or
    one sha256 over every ``scripts/<path>\\0<digest>\\n`` pair; ``None`` when
    a copy is missing, a symlink or not a regular file.
    """
    prefix = f"{HOOK_SCRIPTS_DIR}/{record.id}/"
    copies = sorted(
        {
            spec.argv[1]
            for spec in record.handlers.values()
            if spec.kind == "external" and len(spec.argv) > 1
        }
    )
    if not copies or not all(c.startswith(prefix) and ".." not in c.split("/") for c in copies):
        return None
    digests = [_file_sha256(os.path.join(root, *c.split("/"))) for c in copies]
    if any(d is None for d in digests):
        return None
    if len(digests) == 1:
        return digests[0]
    pairs = "".join(
        f"scripts/{c.removeprefix(prefix)}\0{d}\n" for c, d in zip(copies, digests, strict=True)
    )
    return hashlib.sha256(pairs.encode("utf-8")).hexdigest()


def _file_sha256(path: str) -> str | None:
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_SCRIPT_BYTES:
            return None
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalHandler:
    """A trusted external handler, ready to run once per event."""

    record: HookRecord
    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str]

    def __call__(self, ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
        """Run the script with the canonical event on stdin and parse its verdict."""
        remaining = max(0.05, ctx.deadline - ctx.clock.monotonic())
        timeout = min(self.record.timeout_ms / 1000, remaining)
        stdin = json.dumps(event_document(ev, ctx.config), separators=(",", ":")).encode("utf-8")
        result = ctx.proc.run(self.argv, timeout=timeout, env=self.env, input=stdin, cwd=self.cwd)
        if not result.ok:
            raise ExternalContractError(f"external handler exited {result.returncode}")
        return parse_external_output(result.stdout, hook_id=self.record.id)


def parse_external_output(stdout: bytes, *, hook_id: str) -> HandlerResult:
    """The script's one JSON object as a ``HandlerResult``; raises :class:`ExternalContractError`.

    Example::

        >>> parse_external_output(b'{"decision": "none"}', hook_id="x").decision
        <Decision.NONE: 'none'>
    """
    try:
        document = json.loads(stdout.decode("utf-8"))
    except ValueError as exc:
        raise ExternalContractError(f"output is not one JSON object: {type(exc).__name__}") from exc
    if not isinstance(document, dict):
        raise ExternalContractError(f"output is a JSON {type(document).__name__}, not an object")
    extra = sorted(set(document) - _OUTPUT_KEYS)
    if extra:
        raise ExternalContractError(f"output has keys outside the contract: {extra}")
    try:
        decision = Decision(str(document.get("decision")))
    except ValueError:
        raise ExternalContractError(
            f"decision {document.get('decision')!r} is not one of {[d.value for d in Decision]}"
        ) from None
    return HandlerResult(
        decision=decision,
        hook_id=hook_id,
        rule_id="external",
        reason=_text(document, "reason"),
        context=_items(document.get("context", [])),
        user_note=_text(document, "user_note"),
    )


def _text(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key, "")
    if not isinstance(value, str):
        raise ExternalContractError(f"{key} must be a string, got {type(value).__name__}")
    return value


def _items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ExternalContractError("context must be a list of strings")
    return tuple(value)


def event_document(ev: CanonicalEvent, config: Mapping[str, Any]) -> dict[str, Any]:
    """The ``playbook.hook.event/1`` stdin document: the canonical event plus the handler config.

    Example::

        >>> event_document(ev, {})["schema"]  # doctest: +SKIP
        'playbook.hook.event/1'
    """
    document: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "event": ev.name.value,
        "harness": ev.harness.value,
        "session_id": ev.session_id,
        "turn_id": ev.turn_id,
        "cwd": ev.cwd,
        "project_dir": ev.project_dir,
        "permission_mode": ev.permission_mode,
        "agent_id": ev.agent_id,
        "agent_type": ev.agent_type,
        "unattended": ev.unattended,
        "source": ev.source,
        "prompt": ev.prompt,
        "config": dict(config),
    }
    if ev.tool is not None:
        document["tool"] = _tool_document(ev.tool)
    if ev.stop is not None:
        document["stop"] = {
            "stop_hook_active": ev.stop.stop_hook_active,
            "last_assistant_message": ev.stop.last_assistant_message,
        }
    return document


def _tool_document(tool: ToolCall) -> dict[str, Any]:
    response = tool.response
    return {
        "name": tool.name,
        "native_name": tool.native_name,
        "tool_class": tool.tool_class.value,
        "tool_classes": sorted(c.value for c in tool.tool_classes),
        "use_id": tool.use_id,
        "paths": [p.repo_rel or p.path for p in tool.paths],
        "write_paths": [p.repo_rel or p.path for p in tool.write_paths],
        "mcp_server": tool.mcp_server,
        "input": dict(tool.raw_input),
        "response": None
        if response is None
        else {"ok": response.ok, "exit_code": response.exit_code, "error": response.error},
    }
