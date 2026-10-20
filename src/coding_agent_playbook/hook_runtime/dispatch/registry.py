"""The handler registry: builtin declarations, the static module map, run-time resolution (§D.3.1).

:func:`register_hook_handler` records a builtin's :class:`HandlerDeclaration`
(events, decisions, ``CONFIG_SCHEMA``, ``MUTATES_INPUT``, the builtin-only
``mutates_edited_file`` capability of :data:`MUTATES_EDITED_FILE_HANDLERS`, the
``argv0s`` a shell guard inspects, which the dispatcher's prefilter reads,
specs/prK-hook-pack.md §E.4, and an optional ``FAILURE_REASON`` the failure
policy shows instead of its generic one, §E.5 pii-prompt-guard). The
dispatcher stays import-light: :data:`_BUILTIN_HANDLER_MODULES` maps each name to its module, so
only the modules bound to the current event are imported (no scan; a test
checks map and decorators agree), and an out-of-tree handler, resolved at sync
to ``{"kind": "entry_point", "target": "pkg.mod:attr"}``, is imported directly,
only when ``pkg`` is in ``[hooks] allow_code_from`` (no ``importlib.metadata``,
D-12). External scripts run through :mod:`.external`, behind a trust approval.
Stdlib-only, so sync-time code (the ``hooks`` package) reads the same declarations.
"""

from __future__ import annotations

import importlib
import re
import sys
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.config.keys import ConfigKey, ConfigKind, KeyPolicy
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import EventName
from coding_agent_playbook.hook_runtime.dispatch.event_memo import EventMemo

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, HookRecord
    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.deps import (
        Clock,
        ProcPort,
        RuntimeDeps,
        TrustPort,
    )
    from coding_agent_playbook.hook_runtime.dispatch.escape import EscapeHatches
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.state.ledger import Ledger
    from coding_agent_playbook.hook_runtime.state.session import SessionState

__all__ = [
    "HANDLER_ATTR",
    "MUTATES_EDITED_FILE_HANDLERS",
    "ConfigKey",
    "ConfigKind",
    "HandlerContext",
    "HandlerDeclaration",
    "HandlerFn",
    "HandlerResolutionError",
    "HandlerResolver",
    "KeyPolicy",
    "ResolveContext",
    "Untrusted",
    "builtin_handler_modules",
    "declaration_of",
    "edited_file_mutation_problem",
    "load_builtin",
    "register_hook_handler",
    "registered_handlers",
    "resolve_handler",
]

#: The attribute the decorator sets on a handler function: its declaration.
HANDLER_ATTR: Final = "__playbook_hook_handler__"

#: Registry name -> module; the pack tracks (K5-K10) add a row per handler.
_BUILTIN_HANDLER_MODULES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "guard_generated_outputs": (
            "coding_agent_playbook.hook_runtime.handlers.protect.guard_generated_outputs"
        ),
        "control_plane_guard": "coding_agent_playbook.hook_runtime.handlers.protect.control_plane_guard",
        "validate_then_sync_on_canonical_edit": (
            "coding_agent_playbook.hook_runtime.handlers.protect.validate_then_sync_on_canonical_edit"
        ),
        "resync_on_detector_input_change": (
            "coding_agent_playbook.hook_runtime.handlers.protect.resync_on_detector_input_change"
        ),
        "eval_task_authoring_lint": (
            "coding_agent_playbook.hook_runtime.handlers.protect.eval_task_authoring_lint"
        ),
        "guard_eval_fixtures": "coding_agent_playbook.hook_runtime.handlers.protect.guard_eval_fixtures",
        "stop_drift_and_orphan_gate": (
            "coding_agent_playbook.hook_runtime.handlers.protect.stop_drift_and_orphan_gate"
        ),
        "session_start_playbook_briefing": (
            "coding_agent_playbook.hook_runtime.handlers.protect.session_start_playbook_briefing"
        ),
        "stop_ci_parity_gate": (
            "coding_agent_playbook.hook_runtime.handlers.verify.stop_ci_parity_gate"
        ),
        "clean_code_metrics_nonregression": (
            "coding_agent_playbook.hook_runtime.handlers.verify.clean_code_metrics_nonregression"
        ),
        "clean_code_metrics_nonregression:post_edit": (
            "coding_agent_playbook.hook_runtime.handlers.verify.clean_code_metrics_nonregression"
        ),
        "docstring_nonregression": (
            "coding_agent_playbook.hook_runtime.handlers.verify.docstring_nonregression"
        ),
        "docstring_nonregression:post_edit": (
            "coding_agent_playbook.hook_runtime.handlers.verify.docstring_nonregression"
        ),
        "gate_weakening_guard": (
            "coding_agent_playbook.hook_runtime.handlers.verify.gate_weakening_guard"
        ),
        "gate_weakening_guard:pre_edit": (
            "coding_agent_playbook.hook_runtime.handlers.verify.gate_weakening_guard_edit"
        ),
        "block_precommit_bypass": (
            "coding_agent_playbook.hook_runtime.handlers.verify.block_precommit_bypass"
        ),
        "tests_with_source_nudge": (
            "coding_agent_playbook.hook_runtime.handlers.verify.tests_with_source_nudge"
        ),
        "subagent_stop_verify": (
            "coding_agent_playbook.hook_runtime.handlers.verify.subagent_stop_verify"
        ),
        "prompt_output_contract_on_stop": (
            "coding_agent_playbook.hook_runtime.handlers.verify.prompt_output_contract_on_stop"
        ),
        "prompt_scope_guard": "coding_agent_playbook.hook_runtime.handlers.feedback.prompt_write_scope_guard",
        "ruff_post_edit": "coding_agent_playbook.hook_runtime.handlers.feedback.ruff_feedback",
        "ruff_lint_feedback": "coding_agent_playbook.hook_runtime.handlers.feedback.ruff_feedback",
        "toolchain_hint": "coding_agent_playbook.hook_runtime.handlers.feedback.toolchain_missing_hint",
        "skill_nudge": "coding_agent_playbook.hook_runtime.handlers.feedback.skill_nudge",
        "deser_sink_guard": "coding_agent_playbook.hook_runtime.handlers.feedback.ml_unsafe_deserialization_guard",
        "notebook_hygiene": "coding_agent_playbook.hook_runtime.handlers.feedback.notebook_output_hygiene",
        "notebook_hygiene:stop_stage": "coding_agent_playbook.hook_runtime.handlers.feedback.notebook_output_hygiene",
        "coverage_diff_gate": (
            "coding_agent_playbook.hook_runtime.handlers.verify.coverage_diff_gate"
        ),
        "secret_path_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.secrets_path_guard"
        ),
        "secret_content_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.secret_content_guard"
        ),
        "stop_secret_sweep": "coding_agent_playbook.hook_runtime.handlers.safety.stop_diff_sweep",
        "destructive_command_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.destructive_command_guard"
        ),
        "git_policy_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.git_commit_push_policy_guard"
        ),
        "command_convention_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.command_convention_guard"
        ),
        "commit_message_convention": (
            "coding_agent_playbook.hook_runtime.handlers.safety.commit_message_convention"
        ),
        "dependency_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.dependency_allowlist_guard"
        ),
        "exfil_guard": "coding_agent_playbook.hook_runtime.handlers.safety.exfil_channel_guard",
        "exfil_guard:session_start": (
            "coding_agent_playbook.hook_runtime.handlers.safety.exfil_channel_guard"
        ),
        "taint_escalation": "coding_agent_playbook.hook_runtime.handlers.safety.taint_escalation",
        "taint_escalation:marker": (
            "coding_agent_playbook.hook_runtime.handlers.safety.taint_escalation"
        ),
        "taint_escalation:session_start": (
            "coding_agent_playbook.hook_runtime.handlers.safety.taint_escalation"
        ),
        # K9: the decision sink is never selected (``routing``); it is mapped so
        # validate (H6) can read its declaration like any other builtin.
        "decision_log": "coding_agent_playbook.hook_runtime.handlers.audit.guard_decision_log",
        "activity_log": "coding_agent_playbook.hook_runtime.handlers.audit.local_audit_log",
        "precompact_checkpoint": (
            "coding_agent_playbook.hook_runtime.handlers.audit.precompact_checkpoint"
        ),
        "precompact_checkpoint:reinject": (
            "coding_agent_playbook.hook_runtime.handlers.audit.precompact_checkpoint"
        ),
        "pii_prompt_guard": "coding_agent_playbook.hook_runtime.handlers.safety.pii_prompt_guard",
        "network_egress_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.network_egress_guard"
        ),
        "sensitive_read_guard": (
            "coding_agent_playbook.hook_runtime.handlers.safety.sensitive_data_read_guard"
        ),
    }
)
#: The only handlers that may rewrite the file the tool just edited (specs/prK-hook-pack.md
#: §E.3): an engine builtin, on ``post_tool_use``. No external or entry-point handler, ever (L6).
MUTATES_EDITED_FILE_HANDLERS: Final = frozenset({"ruff_post_edit"})
_MUTATION_EVENT: Final = EventName.POST_TOOL_USE

#: snake_case, plus ``:<role>`` for a companion bound to a second event (K-2).
_NAME: Final = re.compile(r"[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*)?")


@dataclass(frozen=True, slots=True, kw_only=True)
class HandlerDeclaration:
    """What a handler promises (§B.5 H6): the registry half of the hook contract.

    Example::

        >>> declaration_of(guard_x).decisions  # doctest: +SKIP
        frozenset({<Decision.DENY: 'deny'>})
    """

    name: str
    module: str
    events: frozenset[EventName]
    decisions: frozenset[Decision]
    config_schema: Mapping[str, ConfigKey]
    mutates_input: bool = False
    mutates_edited_file: bool = False
    config_domain: str | None = None
    argv0s: frozenset[str] | None = None
    argv0_rows: str | None = None
    failure_reason: str | None = None
    fn: HandlerFn = field(compare=False, repr=False)


#: A hook handler: ``None`` means ``NONE``; it never writes stdout or mutates ``ev``.
#: A lazily evaluated alias, not a ``Protocol`` class: building one costs hot-path import time.
type HandlerFn = Callable[[CanonicalEvent, HandlerContext], HandlerResult | None]


@dataclass(frozen=True, slots=True, kw_only=True)
class HandlerContext:
    """What a handler may use besides the event (§D.3.1).

    ``hook`` is its ``guard_config.hooks.<id>`` record and ``config`` the merged
    ``handler.config`` of the firing event. ``git`` is ``SafeGit`` (built on
    first use); ``ledger`` is ``None`` when the state root is unusable.
    ``deadline`` is the event's watchdog deadline on ``clock.monotonic()``;
    ``env`` is the hook process environment (``CLAUDE_CONFIG_DIR``,
    ``XDG_STATE_HOME``: where user-level files live), never a command's prefix.
    ``deps`` is the dispatch's own ``RuntimeDeps`` (``None`` in a hand-built
    context), for the cold paths that re-enter the pipeline or open a
    user-local store: the session-start heartbeat's in-process canaries and
    its pending-trust probe (specs/prK-hook-pack.md §E.1). ``memo`` is shared by
    every hook of this event: the §E.3 post-edit hooks run one ruff call per
    edited file through it (a hand-built context gets a private one).
    """

    hook: HookRecord
    config: Mapping[str, Any]
    cfg: GuardConfig
    git: GitPort
    session: SessionState
    ledger: Ledger | None
    proc: ProcPort
    clock: Clock
    deadline: float
    hatches: EscapeHatches
    platform: str = sys.platform
    home: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    deps: RuntimeDeps | None = None
    memo: EventMemo = field(default_factory=EventMemo)


class HandlerResolutionError(Exception):
    """A hook's handler cannot be found or loaded; an internal error for the failure policy."""


@dataclass(frozen=True, slots=True)
class Untrusted:
    """A handler skipped because no user-local approval covers it (§B.4); never an error.

    ``reason`` names the gate, never a path or a command.
    """

    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolveContext:
    """What resolving a hook's handler may read: the config, the repo, the trust store.

    ``trust`` is called only for an external handler, so the user-local
    trust file is read only when such a hook fires.
    """

    cfg: GuardConfig
    repo: RepoInfo
    proc: ProcPort
    env: Mapping[str, str]
    trust: Callable[[], TrustPort | None]
    builtin_modules: Mapping[str, str] = field(default_factory=lambda: _BUILTIN_HANDLER_MODULES)


#: Finds the function that runs a hook record on an event; ``FakeHandlerResolver`` scripts it.
type HandlerResolver = Callable[[HookRecord, EventName, ResolveContext], HandlerFn | Untrusted]


# --- registration ------------------------------------------------------------------------

_REGISTRY: dict[str, HandlerDeclaration] = {}


def register_hook_handler[F: Callable[..., Any]](
    name: str,
    *,
    events: Iterable[str],
    decisions: Iterable[str],
    config_schema: Mapping[str, ConfigKey] | None = None,
    mutates_input: bool = False,
    mutates_edited_file: bool = False,
    config_domain: str | None = None,
    argv0s: Iterable[str] | None = None,
    argv0_rows: str | None = None,
    failure_reason: str | None = None,
) -> Callable[[F], F]:
    """Register the decorated function as builtin handler ``name``; returns it unchanged.

    ``events`` and ``decisions`` are the canonical names it serves and may
    return; ``config_schema`` is its ``CONFIG_SCHEMA`` (empty: no config keys).
    ``mutates_edited_file`` is honored only for :data:`MUTATES_EDITED_FILE_HANDLERS`
    (validate reports any other declaration; resolution refuses it).
    ``argv0s`` are the commands a shell guard inspects (``mkfs*``: a prefix),
    plus the ``argv0`` of each row of its ``argv0_rows`` config key: on a
    shell call none of whose segments runs one, the guard is not called.
    ``failure_reason`` replaces the failure policy's generic ask/deny reason
    when the guard fails internally (its ``FAILURE_REASON``; a quality hook's
    failure has no reason, so it is ignored there).

    Example::

        @register_hook_handler("guard_x", events=["pre_tool_use"], decisions=["deny"])
        def guard_x(ev, ctx): ...
    """
    if not _NAME.fullmatch(name):
        raise ValueError(f"handler name {name!r} must be snake_case, or '<name>:<role>'")
    event_set = frozenset(EventName(e) for e in events)
    decision_set = frozenset(Decision(d) for d in decisions)

    def decorate(fn: F) -> F:
        declaration = HandlerDeclaration(
            name=name,
            module=fn.__module__,
            events=event_set,
            decisions=decision_set,
            config_schema=MappingProxyType(dict(config_schema or {})),
            mutates_input=mutates_input,
            mutates_edited_file=mutates_edited_file,
            config_domain=config_domain,
            argv0s=None if argv0s is None else frozenset(argv0s),
            argv0_rows=argv0_rows,
            failure_reason=failure_reason,
            fn=fn,
        )
        _remember(declaration)
        setattr(fn, HANDLER_ATTR, declaration)
        return fn

    return decorate


def _remember(declaration: HandlerDeclaration) -> None:
    """Record ``declaration``; a re-import of the same module replaces its own entry."""
    known = _REGISTRY.get(declaration.name)
    if known is not None and known.module != declaration.module:
        raise ValueError(
            f"handler name {declaration.name!r} is registered by {known.module!r} "
            f"and again by {declaration.module!r}"
        )
    _REGISTRY[declaration.name] = declaration


def registered_handlers() -> Mapping[str, HandlerDeclaration]:
    """Every declaration the decorator has recorded in this process, read-only."""
    return MappingProxyType(dict(_REGISTRY))


def builtin_handler_modules() -> Mapping[str, str]:
    """The static registry-name -> module map of the in-tree handlers."""
    return _BUILTIN_HANDLER_MODULES


def declaration_of(obj: object) -> HandlerDeclaration | None:
    """The declaration a decorated function carries, else ``None``."""
    found = getattr(obj, HANDLER_ATTR, None)
    return found if isinstance(found, HandlerDeclaration) else None


def edited_file_mutation_problem(
    declaration: HandlerDeclaration, *, in_tree: bool, events: Iterable[str]
) -> str | None:
    """Why ``declaration``'s ``mutates_edited_file`` is not allowed here, or ``None``.

    Allowed only for an in-tree builtin of :data:`MUTATES_EDITED_FILE_HANDLERS`
    bound to ``post_tool_use`` alone (an extension of the L6 trust contract).

    Example::

        >>> edited_file_mutation_problem(load_builtin("ruff_post_edit"), in_tree=True,
        ...     events=["pre_tool_use"])  # doctest: +SKIP
        "handler 'ruff_post_edit' declares mutates_edited_file, allowed on post_tool_use only; ..."
    """
    if not declaration.mutates_edited_file:
        return None
    name = declaration.name
    if not in_tree or name not in MUTATES_EDITED_FILE_HANDLERS:
        allowed = ", ".join(sorted(MUTATES_EDITED_FILE_HANDLERS))
        return (
            f"handler {name!r} declares mutates_edited_file; only the engine builtins "
            f"({allowed}) may rewrite the edited file (L6)"
        )
    elsewhere = [event for event in events if event != _MUTATION_EVENT.value]
    if elsewhere:
        return (
            f"handler {name!r} declares mutates_edited_file, allowed on "
            f"{_MUTATION_EVENT.value} only; it is bound to {elsewhere!r}"
        )
    return None


def load_builtin(
    name: str, *, modules: Mapping[str, str] = _BUILTIN_HANDLER_MODULES
) -> HandlerDeclaration:
    """Import in-tree handler ``name``'s module and return its declaration.

    Example: ``load_builtin("nope")`` raises ``HandlerResolutionError`` naming the known ones.
    """
    module = modules.get(name)
    if module is None:
        known = ", ".join(sorted(modules)) or "none"
        raise HandlerResolutionError(f"no builtin handler {name!r}; known handlers: {known}")
    _import(module)
    declaration = _REGISTRY.get(name)
    if declaration is None or declaration.module != module:
        raise HandlerResolutionError(f"module {module!r} does not register handler {name!r}")
    return declaration


# --- resolution ---------------------------------------------------------------------------


def resolve_handler(
    record: HookRecord, event: EventName, ctx: ResolveContext
) -> HandlerFn | Untrusted:
    """The function that runs ``record`` on ``event``, or why it may not run.

    Raises :class:`HandlerResolutionError` for a handler that cannot load.

    Example::

        >>> resolve_handler(cfg.hooks["guard-x"], EventName.PRE_TOOL_USE, ctx)  # doctest: +SKIP
        <function guard_x ...>
    """
    spec = record.handlers.get(event)
    if spec is None:
        raise HandlerResolutionError(f"hook {record.id!r} binds no handler to {event.value!r}")
    if spec.kind == "builtin":
        declaration = load_builtin(spec.name or "", modules=ctx.builtin_modules)
        _refuse_mutation(declaration, in_tree=True, event=event)
        return declaration.fn
    if spec.kind == "entry_point":
        found = _entry_point(spec.target or "", ctx.cfg.allow_code_from)
        if not isinstance(found, Untrusted):
            _refuse_mutation(declaration_of(found), in_tree=False, event=event)
        return found
    from coding_agent_playbook.hook_runtime.dispatch.external import external_handler

    return external_handler(record, event, ctx)


def _refuse_mutation(
    declaration: HandlerDeclaration | None, *, in_tree: bool, event: EventName
) -> None:
    """The runtime backstop of validate's ``mutates_edited_file`` rule."""
    if declaration is None:
        return
    problem = edited_file_mutation_problem(declaration, in_tree=in_tree, events=[event.value])
    if problem is not None:
        raise HandlerResolutionError(problem)


def _entry_point(target: str, allow_code_from: frozenset[str]) -> HandlerFn | Untrusted:
    """Import ``pkg.mod:attr`` directly, when ``pkg`` is in ``allow_code_from``."""
    module, _, attr = target.partition(":")
    if not module or not attr:
        raise HandlerResolutionError(f"entry point target {target!r} is not 'module:attr'")
    package = module.split(".")[0]
    if package not in allow_code_from:
        return Untrusted(f"package {package!r} is not in [hooks] allow_code_from")
    obj: object = _import(module)
    for part in attr.split("."):
        obj = getattr(obj, part, None)
    if not callable(obj):
        raise HandlerResolutionError(f"entry point target {target!r} is not callable")
    return obj  # validate (H6) checked its declaration at sync; here it only must be callable


def _import(module: str) -> object:
    try:
        return importlib.import_module(module)
    except Exception as exc:  # any import-time failure is the handler's internal error
        raise HandlerResolutionError(f"cannot import {module!r}: {type(exc).__name__}") from exc
