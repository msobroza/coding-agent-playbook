"""The effective hook records and their ``guard_config.json`` schema (specs/prK-lifecycle-hooks.md §A.7).

:class:`ResolvedHook` is one hook that is on, after every layer and config merge;
:meth:`ResolvedHook.to_json` builds the **single** hook record of
``guard_config.json``, typed as the runtime's ``HookRecordJson`` (§D.8.2
references it field by field), with one name per field: ``supports``,
``matcher``, ``timeout_ms``. Every value is
machine-independent (K-6): an external handler's argv holds the logical launcher
and the repo-relative script copy under :data:`HOOK_SCRIPTS_DIR`, never an
absolute path; the interpreter comes from the per-machine pin at run time.

Stdlib-only and sync-time only, like the rest of ``hooks``.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple

from coding_agent_playbook.artifacts.hook_schema import MATCHER_KEYS
from coding_agent_playbook.hooks.enforcement import advisory_text, guardrail_summary
from coding_agent_playbook.hooks.resolution.tables import HOOK_SCRIPTS_DIR

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.hook_schema import HookHandler, HookMatcher
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.hook_runtime.config.schema import HandlerRecordJson, HookRecordJson

#: ``entry_point`` is a builtin name resolved at sync to an out-of-tree handler of the
#: ``coding_agent_playbook.hook_handlers`` group (``target`` + ``dist``; in-tree wins).
HandlerKind = Literal["builtin", "entry_point", "external"]

#: The ``scripts/`` dir of a hook directory, copied as ``<HOOK_SCRIPTS_DIR>/<id>/`` (§C.0).
_SCRIPTS = "scripts"


@dataclass(frozen=True)
class ResolvedHandler:
    """One event's handler with its merged config: a builtin name, an entry point or an argv.

    Example::

        >>> ResolvedHandler("builtin", name="guard_x").to_json()
        {'kind': 'builtin', 'name': 'guard_x', 'config': {}}
    """

    kind: HandlerKind
    name: str | None = None
    argv: tuple[str, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)
    target: str | None = None
    dist: str | None = None

    def to_json(self) -> HandlerRecordJson:
        """``{"kind", "name"|"target"+"dist"|"argv", "config"}``, the config deep-copied."""
        config = copy.deepcopy(self.config)
        if self.kind == "builtin":
            return {"kind": self.kind, "name": self.name, "config": config}
        if self.kind == "entry_point":
            return {"kind": self.kind, "target": self.target, "dist": self.dist, "config": config}
        return {"kind": self.kind, "argv": list(self.argv), "config": config}


@dataclass(frozen=True)
class ResolvedHook:
    """One hook that is on, as ``guard_config.json`` and the renderers see it (§A.7).

    ``matcher`` has an entry per declared event (inherited linked-rule globs
    included), ``on_error`` is clamped per event, ``supports`` is narrowed to
    the adapters that receive hooks. ``advisory`` (not serialized) is the §A.8
    advisory rule K3 routes, or None: its body is the §C.4.1 projection (the
    hook body plus one enforcement line). ``definition`` (not serialized, not
    compared) is the merged ``Hook`` it came from: the template the sync renders
    and the canonical form the agent_harness sidecar copies.

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
    definition: Hook | None = field(default=None, compare=False, repr=False)

    @property
    def name(self) -> str:
        """The human-readable name heading the advisory (the id without a definition)."""
        return self.id if self.definition is None else self.definition.frontmatter.name

    @property
    def guardrail_text(self) -> str:
        """The hook's one-line guardrail: its ``summary``, else its body's first sentence (D6).

        Without a definition, the advisory body's first sentence (its body comes
        first, the enforcement line after it); ``""`` without either. Not serialized.

        Example: ``guardrail_line(hook.id, hook.guardrail_text)``.
        """
        if self.definition is not None:
            return guardrail_summary(self.definition.frontmatter.summary, self.definition.body)
        return "" if self.advisory is None else guardrail_summary("", self.advisory.body)

    @property
    def declared_supports(self) -> tuple[str, ...]:
        """The frontmatter's ``supports``, before ``[hooks] adapters`` narrowed it.

        The advisory's enforcement line reads these, never :attr:`supports`, so
        committed advisory bytes never depend on which adapters a repo enables.
        """
        if self.definition is None:
            return self.supports
        return tuple(dict.fromkeys(self.definition.frontmatter.supports))

    def with_rendered_body(self, body: str) -> ResolvedHook:
        """A copy carrying ``body``, the rendered ``HOOK.md`` body (§C.1.3).

        The advisory body becomes ``body`` plus the static enforcement line; a
        body that renders blank drops the advisory; a suppressed advisory
        (``[hooks] advisory = false``) stays suppressed. The definition's
        ``body`` is replaced too, its ``template_body`` kept.

        Example::

            hook = hook.with_rendered_body(render_hook_body(hook.definition, ctx, env))
        """
        definition = self.definition
        if definition is not None and definition.body != body:
            definition = dataclasses.replace(definition, body=body)
        if self.advisory is None or not body.strip():
            return dataclasses.replace(self, advisory=None, definition=definition)
        text = advisory_text(body, self.events, self.declared_supports)
        rule = dataclasses.replace(self.advisory, body=text, template_body=text)
        return dataclasses.replace(self, advisory=rule, definition=definition)

    def to_json(self) -> HookRecordJson:
        """The ``guard_config.json`` record: JSON-ready values, copies of every container.

        Its keys are exactly the runtime's ``HOOK_RECORD_KEYS``; the advisory, the
        definition and ``guardrail_text`` are never part of it.
        """
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


#: The ``SkippedHook.gate`` values of the applicability gates (§A.7 item 1): a hook
#: off only because of them turns on once the facts change (resync-on-detector-input-change).
APPLICABILITY_GATES: Final = frozenset({"applies_if", "linked_rule"})


@dataclass(frozen=True)
class SkippedHook:
    """A hook that is off, and why; feeds ``playbook check`` and the sync summary.

    ``gate`` names the first gate that turned it off (``definition``,
    ``switch``, ``applies_if``, ``linked_rule``, ``adapters``); it is not
    compared, so a test may build one from its id and reason alone.

    Example: ``SkippedHook("guard-x", "disabled by [hooks] disable")``.
    """

    id: str
    reason: str
    gate: str = field(default="", compare=False)


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
