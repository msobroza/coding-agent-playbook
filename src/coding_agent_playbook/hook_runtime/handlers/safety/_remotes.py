"""The session's remotes snapshot: the git remotes configured at session start (specs/prK-hook-pack.md §E.4).

exfil-channel-guard's ``session_start`` companion records ``git remote -v``
once per session; a push to one of those remotes is not egress, and a forge
CLI or ``playbook forge`` command line that names no host reaches one of
their hosts (specs/prF-forge-adapter.md §8.2): :class:`ForgeHosts` names them,
never running git. URLs are stored
without userinfo, and read back without it, so a credential in a remote URL
never lands in the state directory (Q56).

A private module: it registers no handler.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.judges.hosts import extract_hosts, without_userinfo
from coding_agent_playbook.hook_runtime.state.store import StateUnavailable, session_key

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.judges.forge_calls import ForgeCall

__all__ = ["REMOTES_DOCUMENT", "ForgeHosts", "read_snapshot", "write_snapshot"]

#: The per-session snapshot of the configured remotes, under ``sessions/<key>/``.
REMOTES_DOCUMENT: Final = "remotes.json"


def write_snapshot(ev: CanonicalEvent, ctx: HandlerContext) -> None:
    """Record ``git remote -v`` (userinfo dropped) unless this session already has a snapshot.

    Example: ``write_snapshot(session_start_event, ctx)`` stores ``[["origin", "https://h/r"]]``.
    """
    if ev.repo is None or not ev.session_id:
        return
    store, rel = ctx.session.store, _document(ev)
    with suppress(StateUnavailable):
        if store.read_json(rel).get("remotes") is None:
            pairs = [[name, without_userinfo(url)] for name, url in ctx.git.remote_urls()]
            store.write_json(rel, {"remotes": pairs})


def read_snapshot(ev: CanonicalEvent, ctx: HandlerContext) -> list[tuple[str, str]] | None:
    """The snapshot's ``(name, url)`` pairs (userinfo dropped), or ``None`` without one.

    Example: ``read_snapshot(ev, ctx) == [("origin", "https://github.com/org/repo.git")]``.
    """
    if not ev.session_id:
        return None
    try:
        stored = ctx.session.store.read_json(_document(ev)).get("remotes")
    except StateUnavailable:
        return None
    if not isinstance(stored, list):
        return None
    pairs = (pair for pair in stored if isinstance(pair, list) and len(pair) == 2)
    return [(str(name), without_userinfo(str(url))) for name, url in pairs]


class ForgeHosts:
    """The hosts a forge CLI or ``playbook forge`` command line reaches: the ones it names,
    else the snapshot's (read once).

    A forge CLI reaches the remotes on its own forge (the host-to-forge rules
    of ``forge.hosts`` without ``[forge]``, Q48: its public host, a host named
    after it, its host env vars); ``playbook forge`` the push remote, which
    only ``git config`` names, so every remote. Empty: unknown (no snapshot,
    or no remote on that forge). Never ``git remote -v``.

    Example: ``ForgeHosts(ev, ctx)(forge_call(seg)) == ("gitlab.com",)``.
    """

    def __init__(self, ev: CanonicalEvent, ctx: HandlerContext) -> None:
        self._ev = ev
        self._ctx = ctx
        self._hosts: tuple[str, ...] | None = None

    def __call__(self, call: ForgeCall) -> tuple[str, ...]:
        if call.hosts:
            return call.hosts
        if self._hosts is None:
            pairs = read_snapshot(self._ev, self._ctx) or []
            self._hosts = tuple(extract_hosts([url for _, url in pairs]))
        if call.forge is None:
            return self._hosts
        from coding_agent_playbook.forge.hosts import forge_for_host

        env = self._ctx.env
        return tuple(
            host
            for host in self._hosts
            if (found := forge_for_host(host, {}, env)) is not None and found.forge == call.forge
        )


def _document(ev: CanonicalEvent) -> str:
    return f"sessions/{session_key(ev.session_id)}/{REMOTES_DOCUMENT}"
