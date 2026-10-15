"""In-process canaries: synthetic events run through the real pipeline (specs/prK-lifecycle-hooks.md §D.9).

The session-start heartbeat (§E.1) and ``playbook-hook doctor`` both prove the
guards answer by dispatching canned payloads (a benign ``ls``, ``rm -rf /``,
an edit of a protected file) and comparing the combined decision with the one
expected. This module is the mechanism only; K5 adds the heartbeat's
payloads to :data:`DEFAULT_CANARIES`.

Canary runs never pollute a real session: they use the session id
``playbook-doctor-<pid>``, every decision line is tagged ``canary: true``, and
the session directory is removed afterwards.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.hook_runtime.dispatch import dispatch_event
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.harness import CLAUDE_EVENT_NAMES
from coding_agent_playbook.hook_runtime.paths import find_repo
from coding_agent_playbook.hook_runtime.state import StateStore, session_key

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.decision import Decision
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.event import EventName

__all__ = [
    "CANARY_SESSION_PREFIX",
    "DEFAULT_CANARIES",
    "Canary",
    "CanaryResult",
    "canary_session_id",
    "run_canaries",
]

CANARY_SESSION_PREFIX: Final = "playbook-doctor-"


@dataclass(frozen=True, slots=True, kw_only=True)
class Canary:
    """One synthetic event and the combined decision it must produce.

    ``fields`` are the payload fields beyond the common ones (``tool_name``,
    ``tool_input``, ``source``, ...).

    Example::

        Canary(name="rm-root", event=EventName.PRE_TOOL_USE, expect=Decision.DENY,
               fields={"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    """

    name: str
    event: EventName
    expect: Decision
    fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanaryResult:
    """What one canary decided; ``ok`` when that is what it expected."""

    name: str
    ok: bool
    decision: Decision
    latency_ms: int


#: The heartbeat's canaries; K5 (§E.1) adds them with the guards they test.
DEFAULT_CANARIES: Final[tuple[Canary, ...]] = ()


def canary_session_id(pid: int | None = None) -> str:
    """The session id canary runs use: ``playbook-doctor-<pid>``.

    Example::

        >>> canary_session_id(42)
        'playbook-doctor-42'
    """
    return f"{CANARY_SESSION_PREFIX}{os.getpid() if pid is None else pid}"


def run_canaries(
    canaries: Sequence[Canary],
    *,
    repo_root: str,
    deps: RuntimeDeps,
    harness: Harness = Harness.CLAUDE_CODE,
) -> list[CanaryResult]:
    """Dispatch each canary in-process against ``repo_root`` and compare its decision.

    Nothing is written to any stream; the canary session's state is removed afterwards.

    Example::

        >>> [r.ok for r in run_canaries(DEFAULT_CANARIES, repo_root=".", deps=deps)]  # doctest: +SKIP
        []
    """
    session = canary_session_id()
    env = {**deps.env, "CLAUDE_PROJECT_DIR": repo_root}
    quiet = dataclasses.replace(deps, env=env, out=None, err=None)
    project_dir = repo_root if harness is Harness.OPENCODE else None
    results: list[CanaryResult] = []
    try:
        for canary in canaries:
            payload = _payload(canary, session, repo_root)
            started = deps.clock.monotonic()
            trace = dispatch_event(
                canary.event, harness, payload, quiet, project_dir=project_dir, canary=True
            )
            decision = trace.combined.decision
            latency = max(0, round((deps.clock.monotonic() - started) * 1000))
            results.append(CanaryResult(canary.name, decision is canary.expect, decision, latency))
    finally:
        _remove_session(deps, repo_root, session)
    return results


def _payload(canary: Canary, session: str, repo_root: str) -> bytes:
    body = {
        "session_id": session,
        "cwd": repo_root,
        "hook_event_name": CLAUDE_EVENT_NAMES[canary.event],
        "permission_mode": "default",
        **canary.fields,
    }
    return json.dumps(body).encode("utf-8")


def _remove_session(deps: RuntimeDeps, repo_root: str, session: str) -> None:
    store = deps.state
    if store is None:
        repo = find_repo(repo_root)
        if repo is None:
            return
        store = StateStore.for_repo(repo)
    shutil.rmtree(store.path(f"sessions/{session_key(session)}"), ignore_errors=True)
