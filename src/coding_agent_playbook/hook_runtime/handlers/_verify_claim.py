"""stop-ci-parity-gate's ``verify-claim`` stage: no "tests pass" without a passing run (specs/prK-hook-pack.md §E.2).

It applies when the agent's last message matches a ``stop_gate.claim_patterns``
entry ("tests pass", "mypy clean", "ready to merge", ...) and sync rendered at
least one ``stop_gate.verify_commands`` row (with none, nothing could satisfy
it). It is red when the session ledger holds no green run of any verify
command (a ``post_tool_use`` line ``ok: true``; a red run arrives on
``post_tool_use_failure``) after the last ``.py`` edit:

``You said "<claim>"; no passing <cmd> since your last edit. Run it and report the result.``

:func:`completion_claim` is shared with the ``tests`` stage, which runs pytest
only when completion is claimed. Deterministic, under 10 ms: no subprocess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult
from coding_agent_playbook.hook_runtime.stop.tools import py_edit_indexes

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from typing import Any

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan

__all__ = ["STAGE_NAME", "VerifyClaimStage", "completion_claim", "verify_claim_stage"]

STAGE_NAME: Final = "verify-claim"
_CLAIM_CHARS: Final = 60
_COMMAND_CHARS: Final = 80
_MAX_COMMANDS: Final = 3


def completion_claim(ev: CanonicalEvent, cfg: GuardConfig) -> str | None:
    """The text of the first ``claim_patterns`` match in the last assistant message, else ``None``.

    A pattern that does not compile is skipped (validate reports it).

    Example::

        >>> completion_claim(stop_saying_all_tests_pass, cfg)  # doctest: +SKIP
        'tests pass'
    """
    message = ev.stop.last_assistant_message if ev.stop is not None else ""
    if not message:
        return None
    for pattern in cfg.tables.stop_gate().claim_patterns:
        try:
            found = re.search(pattern, message)
        except re.error:
            continue
        if found is not None and found.group(0).strip():
            return found.group(0).strip()
    return None


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyClaimStage:
    """The ``verify-claim`` stage of one Stop.

    Example::

        >>> VerifyClaimStage(claim="tests pass", commands=(("tests", "pytest"),)).name
        'verify-claim'
    """

    claim: str | None
    commands: tuple[tuple[str, str], ...]  # (verify id, command text)
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = True
    mode: str = "block"

    def applies(self, plan: StopPlan) -> bool:
        """Only a completion claim, with a verify command that could back it, needs checking."""
        return self.claim is not None and bool(self.commands)

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Red when no verify command passed after the last ``.py`` edit."""
        if self.claim is None or _green_since_last_edit(plan.ledger, self._ids()):
            return StageResult(STAGE_NAME, "green")
        shown = " or ".join(text for _, text in self.commands[:_MAX_COMMANDS])
        line = (
            f"You said {quote_data(self.claim, _CLAIM_CHARS)}; no passing {shown} since your "
            "last edit. Run it and report the result."
        )
        return StageResult(STAGE_NAME, "red", lines=(line,))

    def _ids(self) -> frozenset[str]:
        return frozenset(verify_id for verify_id, _ in self.commands)


def verify_claim_stage(ev: CanonicalEvent, ctx: HandlerContext) -> VerifyClaimStage:
    """The ``verify-claim`` stage of ``ev``: the coordinator's factory.

    Example: ``verify_claim_stage(stop_event, ctx).applies(plan)``.
    """
    commands = tuple(
        (command.id, _command_text(command.argv))
        for command in ctx.cfg.tables.stop_gate().verify_commands
    )
    return VerifyClaimStage(claim=completion_claim(ev, ctx.cfg), commands=commands)


def _green_since_last_edit(ledger: Sequence[Mapping[str, Any]], ids: frozenset[str]) -> bool:
    edits = py_edit_indexes(ledger)
    after = edits[-1] + 1 if edits else 0
    return any(
        line.get("ev") == "post_tool_use" and line.get("ok") is True and line.get("verify") in ids
        for line in ledger[after:]
    )


def _command_text(argv: Sequence[str]) -> str:
    return clip(" ".join(clean_text(word) for word in argv), _COMMAND_CHARS)
