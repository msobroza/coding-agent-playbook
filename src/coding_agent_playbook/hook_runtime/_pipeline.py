"""Pipeline steps 3-9 for an event that parsed inside a repository (specs/prK-lifecycle-hooks.md §D.1).

Config (with its digest), selection, the fan-out under the watchdog, the one
write, then the post-write records. ``dispatch`` owns steps 1-2 and the paths
that never reach a config. The async ``post_tool_use`` dispatch (OQ-19) runs
only its async-routed handlers and writes nothing (:func:`_run_async`).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._decision_log import (
    DISPATCHER_ID,
    DecisionLog,
    LogLine,
    lines_for,
)
from coding_agent_playbook.hook_runtime._event_memo import EventMemo
from coding_agent_playbook.hook_runtime._execute import (
    Progress,
    failure_result,
    results_of,
    run_handlers,
)
from coding_agent_playbook.hook_runtime._faults import config_fault_results, degraded_lines
from coding_agent_playbook.hook_runtime._ports import LazyGit, open_trust_store
from coding_agent_playbook.hook_runtime._post_write import PostWrite, record_after_write
from coding_agent_playbook.hook_runtime._selection import select_hooks
from coding_agent_playbook.hook_runtime._tail import DispatchTrace
from coding_agent_playbook.hook_runtime.active_prompt import observe as observe_active_prompt
from coding_agent_playbook.hook_runtime.config import ConfigFault, load_guard_config
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.harness import WireOutput
from coding_agent_playbook.hook_runtime.ledger import Ledger
from coding_agent_playbook.hook_runtime.registry import (
    HandlerContext,
    ResolveContext,
    resolve_handler,
)
from coding_agent_playbook.hook_runtime.session import SessionState
from coding_agent_playbook.hook_runtime.state import StateStore
from coding_agent_playbook.hook_runtime.watchdog import Watchdog

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from coding_agent_playbook.hook_runtime._selection import Selected
    from coding_agent_playbook.hook_runtime._tail import Responder
    from coding_agent_playbook.hook_runtime.config import GuardConfig
    from coding_agent_playbook.hook_runtime.decision import CombinedResult
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps, TrustPort
    from coding_agent_playbook.hook_runtime.escape import EscapeHatches
    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.registry import HandlerFn, Untrusted

__all__ = ["Shared", "run_configured"]

_DISABLED_NOTE: Final = "Playbook hook {hook_id} is off this session (PLAYBOOK_HOOKS_DISABLE)."


@dataclass(frozen=True, slots=True, kw_only=True)
class Shared:
    """What steps 3-9 take from the dispatch: deps, the responder, the start time.

    ``asynchronous`` is the async ``post_tool_use`` dispatch (OQ-19, ``--async``).
    """

    deps: RuntimeDeps
    responder: Responder
    started: float
    canary: bool = False
    asynchronous: bool = False


def run_configured(
    ev: CanonicalEvent, repo: RepoInfo, hatches: EscapeHatches, shared: Shared
) -> DispatchTrace:
    """Steps 3-9 for ``ev`` in ``repo``; returns the trace of what was written.

    Example::

        >>> run_configured(ev, ev.repo, EscapeHatches(), shared).wire.exit_code  # doctest: +SKIP
        0
    """
    deps = shared.deps
    store = deps.state or StateStore.for_repo(repo, clock=deps.clock)
    session = SessionState(store, ev.session_id)
    cfg = deps.guard_config or load_guard_config(
        repo,
        store,
        platform=deps.platform,
        home=deps.home,
        refresh_digest=ev.name is EventName.SESSION_START,
    )
    if isinstance(cfg, ConfigFault):
        if shared.asynchronous:
            return DispatchTrace(wire=WireOutput())  # the synchronous dispatch reports it
        return _config_fault(ev, cfg, store, session, shared)
    if ev.tool is not None:
        ev = dataclasses.replace(ev, tool=ev.tool.with_shell_config(cfg.shell))
    if shared.asynchronous:
        return _run_async(ev, repo, cfg, store, session, hatches, shared)
    log = DecisionLog(
        store, ev, now=deps.clock.time, enabled=cfg.logging.decisions, canary=shared.canary
    )
    log.write(_escape_lines(hatches, session))
    # Before any hook: a guard's deny must not skip recording the prompt (OQ-45).
    observe_active_prompt(ev, cfg, store)
    selection = select_hooks(cfg, ev, hatches)
    progress = Progress(selection.selected)
    dog = _watchdog(ev, cfg, progress, log, shared)
    try:
        ran = run_handlers(
            ev,
            progress,
            resolve=_resolver(ev, repo, cfg, deps),
            context=_contexts(ev, repo, cfg, store, session, hatches, shared),
            once=session.once,
            clock=deps.clock,
        )
    finally:
        dog.cancel()
    results = [*results_of(ran), *_disabled_notes(selection.disabled, session)]
    combined, wire = shared.responder.respond(
        ev, results, unattended_ask=cfg.unattended_ask, session=session
    )
    post = PostWrite(
        ev=ev, cfg=cfg, ran=ran, combined=combined, store=store, session=session, log=log, deps=deps
    )
    for note in record_after_write(post):
        shared.responder.gate.note(note)
    if store.stateless_reason is not None:
        shared.responder.gate.note(f"playbook-hook: running stateless ({store.stateless_reason})")
    return DispatchTrace(wire=wire, combined=combined, ran=tuple(ran), written=True)


def _run_async(
    ev: CanonicalEvent,
    repo: RepoInfo,
    cfg: GuardConfig,
    store: StateStore,
    session: SessionState,
    hatches: EscapeHatches,
    shared: Shared,
) -> DispatchTrace:
    """The async ``post_tool_use`` dispatch (OQ-19): async-routed handlers only, empty stdout.

    Claude delivers an async hook's output on the next turn, so nothing is
    written; the synchronous dispatch already did the ledger, asks and notes.
    Only the decision-log lines of a failing handler are recorded. The
    watchdog still bounds a hung handler, falling back to the same empty output.
    """
    deps = shared.deps
    progress = Progress(select_hooks(cfg, ev, hatches, asynchronous=True).selected)
    dog = Watchdog(deps, shared.responder.gate, fallback=WireOutput)
    if progress.selected:
        dog.arm(cfg.deadlines_ms[ev.name] / 1000 - (deps.clock.monotonic() - shared.started))
    try:
        ran = run_handlers(
            ev,
            progress,
            resolve=_resolver(ev, repo, cfg, deps),
            context=_contexts(ev, repo, cfg, store, session, hatches, shared),
            once=session.once,
            clock=deps.clock,
        )
    finally:
        dog.cancel()
    combined = shared.responder.combine(ev, results_of(ran), unattended_ask=cfg.unattended_ask)
    log = DecisionLog(
        store, ev, now=deps.clock.time, enabled=cfg.logging.decisions, canary=shared.canary
    )
    log.write(lines_for(ran, combined.outcomes))
    return DispatchTrace(wire=WireOutput(), combined=combined, ran=tuple(ran))


def _config_fault(
    ev: CanonicalEvent, fault: ConfigFault, store: StateStore, session: SessionState, shared: Shared
) -> DispatchTrace:
    results = config_fault_results(ev.name, fault, session.once)
    combined, wire = shared.responder.respond(ev, results, session=session)
    deps = shared.deps
    log = DecisionLog(store, ev, now=deps.clock.time, enabled=True, canary=shared.canary)
    log.write(degraded_lines(combined.outcomes))
    return DispatchTrace(wire=wire, combined=combined, written=True)


def _resolver(
    ev: CanonicalEvent, repo: RepoInfo, cfg: GuardConfig, deps: RuntimeDeps
) -> Callable[[Selected], HandlerFn | Untrusted]:
    resolve = deps.resolve_handler or resolve_handler
    trust: list[TrustPort | None] = []

    def trust_store() -> TrustPort | None:
        if not trust:  # read the user-local file once, and only for an external handler
            trust.append(open_trust_store(repo, deps))
        return trust[0]

    rctx = ResolveContext(cfg=cfg, repo=repo, proc=deps.proc, env=deps.env, trust=trust_store)

    def run(selected: Selected) -> HandlerFn | Untrusted:
        return resolve(selected.record, ev.name, rctx)

    return run


def _contexts(
    ev: CanonicalEvent,
    repo: RepoInfo,
    cfg: GuardConfig,
    store: StateStore,
    session: SessionState,
    hatches: EscapeHatches,
    shared: Shared,
) -> Callable[[Selected], HandlerContext]:
    deps = shared.deps
    git = LazyGit(repo, deps, state=store, secret_paths=cfg.secret_paths)
    ledger = None
    if store.usable:
        ledger = Ledger(
            store,
            ev.session_id,
            path_classes=cfg.path_classes,
            secret_paths=cfg.secret_paths,
            now=deps.clock.time,
            platform=deps.platform,
        )
    deadline = shared.started + cfg.deadlines_ms[ev.name] / 1000
    memo = EventMemo()  # one per event: hooks share work on it (the §E.3 single ruff call)

    def make(selected: Selected) -> HandlerContext:
        return HandlerContext(
            hook=selected.record,
            config=selected.record.handlers[ev.name].config,
            cfg=cfg,
            git=git,
            session=session,
            ledger=ledger,
            proc=deps.proc,
            clock=deps.clock,
            deadline=deadline,
            hatches=hatches,
            platform=deps.platform,
            home=deps.home,
            env=deps.env,
            deps=deps,
            memo=memo,
        )

    return make


def _watchdog(
    ev: CanonicalEvent, cfg: GuardConfig, progress: Progress, log: DecisionLog, shared: Shared
) -> Watchdog:
    """The deadline timer; armed only when some hook runs, so a quiet event imports no thread."""
    fired: list[CombinedResult] = []
    responder = shared.responder

    def fallback() -> WireOutput:
        pending = [
            failure_result(s, once=None, reason=progress.failure_reason(s))
            for s in progress.pending()
            if s.is_guard
        ]
        results = [*results_of(progress.ran), *pending]
        fired.append(responder.combine(ev, results, unattended_ask=cfg.unattended_ask))
        return responder.render(ev.name, fired[-1])

    def on_fire() -> None:
        pending = progress.pending()
        line = LogLine(
            hook_id=pending[0].record.id if pending else DISPATCHER_ID,
            rule_id="watchdog",
            decision="degraded",
            effective=fired[-1].decision.value if fired else "none",
            degraded=True,
        )
        log.write([line])

    dog = Watchdog(shared.deps, responder.gate, fallback=fallback, on_fire=on_fire)
    if progress.selected:
        elapsed = shared.deps.clock.monotonic() - shared.started
        dog.arm(cfg.deadlines_ms[ev.name] / 1000 - elapsed)
    return dog


def _escape_lines(hatches: EscapeHatches, session: SessionState) -> list[LogLine]:
    """One ``escape`` line per hatch per session; a settings-file hatch is logged as ignored."""
    lines = [
        LogLine(hook_id=DISPATCHER_ID, decision="escape", effective="none", escape=name)
        for name in hatches.used
        if session.once(f"escape:{name}")
    ]
    lines.extend(
        LogLine(
            hook_id=DISPATCHER_ID,
            rule_id=name,
            decision="escape",
            effective="none",
            escape="escape_via_settings_env",
        )
        for name in hatches.via_settings_env
        if session.once(f"escape_via_settings_env:{name}")
    )
    return lines


def _disabled_notes(disabled: Sequence[str], session: SessionState) -> list[HandlerResult]:
    """One user note per session per hook ``PLAYBOOK_HOOKS_DISABLE`` switched off (§D.7)."""
    return [
        HandlerResult(
            decision=Decision.NONE,
            hook_id=hook_id,
            user_note=_DISABLED_NOTE.format(hook_id=hook_id),
        )
        for hook_id in disabled
        if session.once(f"disabled:{hook_id}")
    ]
