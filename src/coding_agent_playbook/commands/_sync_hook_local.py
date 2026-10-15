"""Machine-local hook effects of a write-mode ``playbook sync`` (specs/prK-lifecycle-hooks.md §B.4, §C.2.7, §D.8.3).

Nothing here touches the repository or the lockfile; it runs after the
lockfile is saved, in write mode only, when hooks are live:

- **pins**: the per-worktree interpreter pin the committed launcher reads
  (first writer wins) and ``machine.json`` with the logical tools' absolute
  argv and the layers' absolute ``resources/`` dirs (the guards resolve
  ``guard_config.json``'s ``pkg:`` ids through them), both under the git dir
  (``hook_runtime.pin``). Outside git there is no pin, so the hooks stay
  inactive and sync says so;
- **trust on first use**: each external handler whose code (source, launcher,
  args, script bytes) the user-local trust store has not approved is listed
  with its source, full command and old -> new script hash, then asked
  ``[y/N]``; so is the Stop gate's execution-stage list (``typecheck``,
  ``tests``: they run pytest, ``conftest.py`` and mypy plugins), by the sha256
  of the rendered ``stop_gate.stages``. Only when stdin and stdout are TTYs:
  there is deliberately no non-interactive approve flag, as an agent's shell
  has no TTY (§B.4).

Every machine effect is injected through :class:`SyncHookDeps`, so tests never
write a real pin or trust store, nor read a terminal.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.hook_registrations import stop_stage_records
from coding_agent_playbook.hook_runtime import pin
from coding_agent_playbook.security.trust import (
    HandlerApproval,
    TrustStore,
    TrustStoreError,
    default_trust_store_path,
    sha256_of_json,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hook_runtime.pin import PinResult

__all__ = [
    "PINNED_TOOLS",
    "PROJECT_PYTHON",
    "PinWriter",
    "RuntimePinWriter",
    "SyncHookDeps",
    "approve_pending",
    "execution_digest",
    "handler_approval",
    "project_python",
    "write_pins",
]

#: Logical tools the builtins run, pinned per worktree; Stop stage tools join them.
PINNED_TOOLS: Final = ("ruff", "cz")
#: The project's own interpreter (the execution stages' tool), not a program on PATH.
PROJECT_PYTHON: Final = "project_python"
_VENV_PYTHONS: Final = (".venv/bin/python", ".venv/Scripts/python.exe")
_PROMPT: Final = "Approve it? [y/N]: "
_YES: Final = frozenset({"y", "yes"})


class PinWriter(Protocol):
    """The two pin writers sync calls (``hook_runtime.pin`` in production)."""

    def ensure_interpreter_pin(self, repo_root: Path) -> PinResult | None:
        """Pin this interpreter unless a usable pin exists; ``None`` outside git."""

    def write_machine_pins(
        self,
        repo_root: Path,
        tools: Mapping[str, Sequence[str]],
        engine_version: str,
        resource_roots: Mapping[str, str] | None = None,
    ) -> Path | None:
        """Rewrite ``machine.json`` with ``tools`` and ``resource_roots``; ``None`` outside git."""


@dataclass(frozen=True)
class RuntimePinWriter:
    """:class:`PinWriter` over ``hook_runtime.pin``, discovering the git dir from ``repo_root``.

    Example: ``RuntimePinWriter().ensure_interpreter_pin(repo_root)``.
    """

    def ensure_interpreter_pin(self, repo_root: Path) -> PinResult | None:
        """See :func:`hook_runtime.pin.ensure_interpreter_pin` (``sys.executable``, unresolved)."""
        return pin.ensure_interpreter_pin(start=str(repo_root))

    def write_machine_pins(
        self,
        repo_root: Path,
        tools: Mapping[str, Sequence[str]],
        engine_version: str,
        resource_roots: Mapping[str, str] | None = None,
    ) -> Path | None:
        """See :func:`hook_runtime.pin.write_machine_pins`."""
        return pin.write_machine_pins(
            tools=tools,
            engine_version=engine_version,
            resource_roots=resource_roots,
            start=str(repo_root),
        )


def _user_trust_store(repo_root: Path) -> TrustStore:
    return TrustStore(default_trust_store_path(), repo_root=repo_root)


def _stdio_is_tty() -> bool:
    # Either stream may be None (pythonw, a detached process): never a terminal then.
    streams = (sys.stdin, sys.stdout)
    return all(stream is not None and stream.isatty() for stream in streams)


@dataclass(frozen=True)
class SyncHookDeps:
    """The machine-local seams of a write-mode sync; every default is the real one.

    Example::

        execute(repo, hook_deps=SyncHookDeps(pins=FakePinWriter(), is_tty=lambda: False))
    """

    pins: PinWriter = field(default_factory=RuntimePinWriter)
    trust_store: Callable[[Path], TrustStore] = _user_trust_store
    is_tty: Callable[[], bool] = _stdio_is_tty
    ask: Callable[[str], str] = input
    which: Callable[[str], str | None] = shutil.which


def write_pins(
    repo_root: Path,
    deps: SyncHookDeps,
    *,
    engine_version: str,
    resource_roots: Mapping[str, str] | None = None,
    stage_tools: Iterable[str] = (),
) -> None:
    """Pin the interpreter (first writer wins), the tools and the layers' resource dirs.

    ``stage_tools`` are the logical tools of ``stop_gate.stages``: the Stop
    stage runner finds them only through these pins (§D.8.3). Warns when
    outside git, where nothing is pinned.

    Example: ``write_pins(ctx.repo_root, SyncHookDeps(), engine_version="0.2.0")``.
    """
    result = deps.pins.ensure_interpreter_pin(repo_root)
    if result is None:
        print(
            f"warning: hooks are git-only: {repo_root} is not in a git work tree (or its "
            "playbook-hooks state dir is unusable), so no interpreter pin was written "
            "and the hooks stay inactive here.",
            file=sys.stderr,
        )
        return
    if result.written:
        print(f"✓ Pinned the hook interpreter for this worktree: {result.interpreter}")
    if result.ephemeral:
        print(
            f"warning: the pinned hook interpreter {result.interpreter} lives in a uv/pipx "
            "cache that may be deleted; re-pin with 'playbook-hook doctor --repin <python>'.",
            file=sys.stderr,
        )
    names = dict.fromkeys((*PINNED_TOOLS, *stage_tools))
    tools = {name: [path] for name in names if (path := _locate(name, repo_root, deps))}
    deps.pins.write_machine_pins(repo_root, tools, engine_version, resource_roots)


def project_python(repo_root: Path, which: Callable[[str], str | None]) -> str | None:
    """The project's interpreter: its ``.venv`` one (unresolved), else ``python3`` on PATH.

    Example: ``project_python(repo_root, shutil.which)`` is ``<repo>/.venv/bin/python``.
    """
    for rel in _VENV_PYTHONS:
        candidate = repo_root / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)  # never resolved: the venv symlink keeps its site-packages
    return which("python3") or which("python")


def _locate(name: str, repo_root: Path, deps: SyncHookDeps) -> str | None:
    return project_python(repo_root, deps.which) if name == PROJECT_PYTHON else deps.which(name)


def handler_approval(hook: ResolvedHook) -> HandlerApproval | None:
    """The trust entry ``hook``'s external handler needs, as the dispatcher computes it.

    Mirrors ``hook_runtime._external.approval_of``: the first external handler
    in event-name order (``guard_config.json`` sorts its keys), the launcher,
    the args after the script, and the script digest. ``None`` without one.

    Example: ``handler_approval(hook).launcher == "sh"``.
    """
    external = [h for _, h in sorted(hook.handlers.items()) if h.kind == "external"]
    if not external:
        return None
    argv = external[0].argv
    return HandlerApproval(
        source=hook.source_package,
        launcher=argv[0],
        args_sha256=sha256_of_json(list(argv[2:])),
        script_sha256=hook.script_sha256 or "",
    )


def approve_pending(
    hooks: Sequence[ResolvedHook], repo_root: Path, deps: SyncHookDeps
) -> list[str]:
    """Ask, per unapproved external handler, whether to trust it; return the approved ids.

    Without a TTY nothing is asked: one note names the pending hooks.

    Example: ``approve_pending(sync_hooks.resolved, ctx.repo_root, SyncHookDeps())``.
    """
    wanted = _wanted(hooks)
    digest = execution_digest(hooks)
    if not wanted and digest is None:
        return []  # engine builtins only: the trust store is never opened
    try:
        store = deps.trust_store(repo_root)
    except TrustStoreError as exc:
        print(f"warning: hook approvals unavailable: {exc}", file=sys.stderr)
        return []
    pending = [(h, a) for h, a in wanted if not store.allows_handler(h.id, a)]
    stages = digest is not None and not store.allows_execution(digest)
    if not pending and not stages:
        return []
    if not deps.is_tty():
        _pending_note(pending, stages=stages)
        return []
    approved = _ask_each(pending, store, deps)
    if stages and digest is not None and _ask_execution(hooks, digest, store, deps):
        approved.append("stop gate")
    return approved


def _pending_note(pending: list[tuple[ResolvedHook, HandlerApproval]], *, stages: bool) -> None:
    review = "run 'playbook sync' in a terminal to review them."
    if pending:
        ids = ", ".join(hook.id for hook, _ in pending)
        print(
            f"note: {len(pending)} hook handler(s) await approval on this machine ({ids}); {review}"
        )
    if stages:
        print(f"note: the stop gate's execution stages await approval on this machine; {review}")


def execution_digest(hooks: Sequence[ResolvedHook]) -> str | None:
    """The sha256 the Stop gate's execution stages need approved, ``None`` without one.

    The same digest the runtime checks (``GatePolicy.stages_sha256``): every
    rendered stage record, so any change to the list needs a new approval.

    Example: ``execution_digest(hooks)`` is ``None`` until ``typecheck`` or ``tests`` is on.
    """
    records = stop_stage_records(hooks)
    if not any(record.cost == "execution" for record in records):
        return None
    return sha256_of_json([record.to_json() for record in records])


def _ask_execution(
    hooks: Sequence[ResolvedHook], digest: str, store: TrustStore, deps: SyncHookDeps
) -> bool:
    """Show the execution stages' commands and ask; record the approval on yes."""
    print("The Stop gate runs repo-controlled code (tests, conftest.py, mypy plugins):")
    for record in stop_stage_records(hooks):
        if record.cost == "execution":
            print(f"  {record.name}: {' '.join([record.tool, *record.args])}")
    try:
        answer = deps.ask(_PROMPT)
    except EOFError:
        answer = ""
    if answer.strip().lower() not in _YES:
        return False
    try:
        store.approve_execution(digest)
    except TrustStoreError as exc:
        print(f"warning: the stop gate approval was not recorded: {exc}", file=sys.stderr)
        return False
    return True


def _wanted(hooks: Sequence[ResolvedHook]) -> list[tuple[ResolvedHook, HandlerApproval]]:
    """Every hook with an external handler, by id, with the approval it needs."""
    pairs = [(hook, handler_approval(hook)) for hook in sorted(hooks, key=lambda h: h.id)]
    return [(hook, approval) for hook, approval in pairs if approval is not None]


def _ask_each(
    pending: list[tuple[ResolvedHook, HandlerApproval]], store: TrustStore, deps: SyncHookDeps
) -> list[str]:
    approved: list[str] = []
    for hook, approval in pending:
        _describe(hook, approval, store.handler(hook.id))
        try:
            answer = deps.ask(_PROMPT)
        except EOFError:
            answer = ""
        if answer.strip().lower() not in _YES:
            continue
        try:
            store.approve_handler(hook.id, approval)
        except TrustStoreError as exc:
            print(f"warning: approval of {hook.id!r} not recorded: {exc}", file=sys.stderr)
            break
        approved.append(hook.id)
    return approved


def _describe(hook: ResolvedHook, wanted: HandlerApproval, old: HandlerApproval | None) -> None:
    """The pending item: source, the full command line, and old -> new script hash."""
    argv = next(h.argv for _, h in sorted(hook.handlers.items()) if h.kind == "external")
    before = "(not approved)" if old is None else old.script_sha256 or "(none)"
    print(f"Hook {hook.id!r} runs code this machine has not approved:")
    print(f"  source:  {hook.source_package}")
    print(f"  command: {' '.join(argv)}")
    print(f"  script sha256: {before} -> {wanted.script_sha256 or '(none)'}")
