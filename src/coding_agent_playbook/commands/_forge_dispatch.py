"""Run one parsed forge operation on the push remote's forge (spec prF §6.3).

:func:`perform` is the dispatch: ``which`` needs no forge CLI; an operation
the forge lacks, or an option of it the forge lacks, exits 3 before any call
(Q30); every other operation opens the forge CLI (``_forge_cli``: version and
host checks) and runs its handler with an :class:`~._forge_op.Op`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._forge_cli import open_cli
from coding_agent_playbook.commands._forge_issues import ISSUE_HANDLERS
from coding_agent_playbook.commands._forge_meta import META_HANDLERS
from coding_agent_playbook.commands._forge_op import Op, printed
from coding_agent_playbook.commands._forge_pulls import PULL_HANDLERS, pull_source
from coding_agent_playbook.commands._forge_stop import ForgeStop, unsupported
from coding_agent_playbook.forge.operations import BODY_OPTIONS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.commands._forge_args import Call
    from coding_agent_playbook.commands._forge_op import Outcome
    from coding_agent_playbook.commands._forge_repo import ForgeRemote

__all__ = ["perform"]

_HANDLERS: Final[Mapping[str, Callable[[Op], Outcome]]] = {
    **ISSUE_HANDLERS,
    **PULL_HANDLERS,
    **META_HANDLERS,
}


def perform(call: Call, remote: ForgeRemote, env: Mapping[str, str]) -> Outcome:
    """Run ``call`` on ``remote``'s forge; a :class:`ForgeStop` for the exits decided here."""
    if call.name == "which":
        return printed(remote.which())
    forge = remote.forge
    translation = call.operation.translation(forge)
    if translation is None:
        raise unsupported(call.name, forge, "this forge has no such feature")
    given = set(call.options) | call.flags | (BODY_OPTIONS if call.body is not None else set())
    lacking = sorted(given & translation.unsupported)
    if lacking:
        raise unsupported(f"{call.name} {lacking[0]}", forge, "this forge has no such feature")
    if call.operation.opens_pull_request:  # before any forge CLI call (Q43)
        pull_source(remote)
    handler = _HANDLERS.get(call.name)
    if handler is None:  # pragma: no cover - every catalogue operation has a handler
        raise ForgeStop(1, f"`{call.name}` has no handler")
    return handler(Op(call, remote, open_cli(remote, env), translation))
