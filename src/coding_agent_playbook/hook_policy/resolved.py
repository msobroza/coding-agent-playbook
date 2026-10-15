"""The effective hook records and their ``guard_config.json`` schema (specs/prK-lifecycle-hooks.md §A.7).

:class:`ResolvedHook` is one hook that is on, after every layer and config merge;
:meth:`ResolvedHook.to_json` is the **single** hook-record schema of
``guard_config.json`` (§D.8.2 references it field by field), with one name per
field: ``supports``, ``matcher``, ``timeout_ms``. Every value is
machine-independent (K-6): an external handler's argv holds the logical launcher
and the repo-relative script copy under :data:`HOOK_SCRIPTS_DIR`, never an
absolute path; the interpreter comes from the per-machine pin at run time.

Stdlib-only and sync-time only, like the rest of ``hook_policy``.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from coding_agent_playbook._hook_schema import MATCHER_KEYS
from coding_agent_playbook.hook_policy.tables import HOOK_SCRIPTS_DIR

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.types import Hook, HookHandler, HookMatcher, Rule

#: K1 emits builtin and external handlers; K2 adds ``entry_point`` (``target`` +
#: ``dist``), resolved at sync from the ``coding_agent_playbook.hook_handlers`` group.
HandlerKind = Literal["builtin", "external"]

#: The ``scripts/`` dir of a hook directory, copied as ``<HOOK_SCRIPTS_DIR>/<id>/`` (§C.0).
_SCRIPTS = "scripts"


@dataclass(frozen=True)
class ResolvedHandler:
    """One event's handler with its merged config: a builtin name or an external argv.

    Example::

        >>> ResolvedHandler("builtin", name="guard_x").to_json()
        {'kind': 'builtin', 'name': 'guard_x', 'config': {}}
    """

    kind: HandlerKind
    name: str | None = None
    argv: tuple[str, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """``{"kind", "name"|"argv", "config"}``, the config deep-copied."""
        target: dict[str, Any] = (
            {"name": self.name} if self.kind == "builtin" else {"argv": list(self.argv)}
        )
        return {"kind": self.kind, **target, "config": copy.deepcopy(self.config)}


@dataclass(frozen=True)
class ResolvedHook:
    """One hook that is on, as ``guard_config.json`` and the renderers see it (§A.7).

    ``matcher`` has an entry per declared event (inherited linked-rule globs
    included), ``on_error`` is clamped per event, ``supports`` is narrowed to
    the adapters that receive hooks. ``advisory`` (not serialized) is the §A.8
    advisory rule K3 routes, or None.

    Example::

        >>> resolved.to_json()["timeout_ms"]  # doctest: +SKIP
        2000
    """

    id: str
    source_package: str
    events: tuple[str, ...]
    priority: int
    matcher: dict[str, HookMatcher]
    handlers: dict[str, ResolvedHandler]
    decisions: tuple[str, ...]
    timeout: float
    on_error: dict[str, str]
    supports: tuple[str, ...]
    mandatory: bool
    script_sha256: str | None
    advisory: Rule | None = None

    def to_json(self) -> dict[str, Any]:
        """The ``guard_config.json`` record: JSON-ready values, copies of every container."""
        return {
            "id": self.id,
            "source_package": self.source_package,
            "events": list(self.events),
            "priority": self.priority,
            "matcher": {event: _matcher_json(entry) for event, entry in self.matcher.items()},
            "handlers": {event: handler.to_json() for event, handler in self.handlers.items()},
            "decisions": list(self.decisions),
            "timeout_ms": round(self.timeout * 1000),
            "on_error": dict(self.on_error),
            "supports": list(self.supports),
            "mandatory": self.mandatory,
            "script_sha256": self.script_sha256,
        }


@dataclass(frozen=True)
class SkippedHook:
    """A hook that is off, and why; feeds ``playbook check`` and the sync summary.

    Example: ``SkippedHook("guard-x", "disabled by [hooks] disable")``.
    """

    id: str
    reason: str


class EffectiveHooks(NamedTuple):
    """What :func:`resolve_effective_hooks` returns: on hooks, off hooks, sync warnings."""

    resolved: list[ResolvedHook]
    skipped: list[SkippedHook]
    warnings: list[str]


def external_argv(hook_id: str, handler: HookHandler) -> tuple[str, ...]:
    """``(launcher, <HOOK_SCRIPTS_DIR>/<hook_id>/<script below scripts/>, *args)``.

    Repo-relative and machine-independent: sync copies ``scripts/`` there (§C.0)
    and the runtime resolves the launcher through its pins (§D.8.3).

    Example::

        >>> external_argv("x", HookHandler(command="python", script="scripts/a.py"))  # doctest: +SKIP
        ('python', '.coding-agent-playbook/hooks/scripts/x/a.py')
    """
    script = PurePosixPath(handler.script or "")
    inside = PurePosixPath(*script.parts[1:]) if script.parts[:1] == (_SCRIPTS,) else script
    return (handler.command or "", f"{HOOK_SCRIPTS_DIR}/{hook_id}/{inside}", *handler.args)


def script_sha256(hook: Hook, handlers: Iterable[HookHandler]) -> str | None:
    """The sha256 the trust store approves (§B.4): of the script's bytes, else None.

    One script: its own digest. Several: one digest over every ``path, digest``
    pair, so any byte change still invalidates the approval. None for a hook
    without an external handler, or when a script is missing, a symlink, or
    outside ``scripts/`` (validate's H7; it is never read then).

    Example::

        >>> script_sha256(builtin_hook, [HookHandler(builtin="x")]) is None  # doctest: +SKIP
        True
    """
    scripts = sorted({h.script for h in handlers if h.is_external and h.script})
    digests = [_file_sha256(hook, script) for script in scripts]
    if not digests or None in digests:
        return None
    if len(digests) == 1:
        return digests[0]
    pairs = "".join(
        f"{script}\0{digest}\n" for script, digest in zip(scripts, digests, strict=True)
    )
    return hashlib.sha256(pairs.encode("utf-8")).hexdigest()


def _file_sha256(hook: Hook, script: str) -> str | None:
    """The digest of ``<hook dir>/<script>`` when it is a regular file inside ``scripts/``."""
    if hook.hook_dir is None or hook.scripts_dir is None:
        return None
    path = hook.hook_dir / script
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if not path.resolve().is_relative_to(hook.scripts_dir.resolve()):
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _matcher_json(entry: HookMatcher) -> dict[str, list[str]]:
    return {key: list(getattr(entry, key)) for key in MATCHER_KEYS}
