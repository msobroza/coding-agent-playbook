"""prompt-output-contract-on-stop: the ``output-contract`` Stop stage (specs/prK-hook-pack.md §E.2).

While the turn's active playbook prompt (:mod:`...state.active_prompt`, resolved per
turn) declares an ``output_contract``, every one of its regexes must match the
last 4,000 characters of ``last_assistant_message``, e.g. ``/review-core``'s final
``approve`` / ``request changes`` verdict line.

- It judges that message only. The active prompt's resolution reads at most
  the transcript's turn-opening entry (its slash, never its text), and not at
  all once the turn is resolved.
- The contract comes from ``guard_config.prompts`` (rendered at sync), never
  from a prompt file read at run time.
- A miss is a context line (``warn``); ``[hooks.prompt-output-contract-on-stop]
  block_once = true`` makes the first miss per prompt invocation a deny line
  inside the coordinator's one combined reason, then context again.
- ``needs_diff`` is false: a review turn changes no file, so the stage still
  runs on a tree equal to ``HEAD``. Under 10 ms, no subprocess.
- With no active prompt, a prompt without a contract, or an empty message
  (OpenCode's ``session.idle`` carries none), it is inert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.hook_config import HookConfig
from coding_agent_playbook.hook_runtime.dispatch.caps import clean_text, clip, quote_data
from coding_agent_playbook.hook_runtime.dispatch.registry import ConfigKey, register_hook_handler
from coding_agent_playbook.hook_runtime.state.active_prompt import resolve_active_prompt
from coding_agent_playbook.hook_runtime.stop.alone import run_alone
from coding_agent_playbook.hook_runtime.stop.stages import StageCost, StageResult

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.dispatch.decision import HandlerResult
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerContext
    from coding_agent_playbook.hook_runtime.state.active_prompt import ActivePrompt
    from coding_agent_playbook.hook_runtime.state.session import SessionState
    from coding_agent_playbook.hook_runtime.stop.stages import StopPlan

__all__ = [
    "CONFIG_SCHEMA",
    "STAGE_NAME",
    "TAIL_CHARS",
    "OutputContractStage",
    "output_contract_stage",
    "prompt_output_contract_on_stop",
]

STAGE_NAME: Final = "output-contract"
#: Only the end of the turn is checked: where a verdict or a conclusion lands.
TAIL_CHARS: Final = 4_000
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "stage": ConfigKey("string", "replace", (STAGE_NAME,)),
    "block_once": ConfigKey("boolean"),
}
#: Keeps one contract line inside the 160-character reason line.
_PATTERN_CHARS: Final = 90


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputContractStage:
    """The ``output-contract`` stage of one Stop.

    Example::

        >>> output_contract_stage(stop_after_review, ctx).run(plan, deadline).status
        ... # doctest: +SKIP
        'warn'
    """

    prompt: ActivePrompt | None
    contract: tuple[str, ...]
    message: str
    session: SessionState
    block_once: bool = False
    name: str = STAGE_NAME
    cost: StageCost = StageCost.DETERMINISTIC
    needs_diff: bool = False
    mode: str = "warn"

    def applies(self, plan: StopPlan) -> bool:
        """Only an active prompt with a contract, and a message to hold it to."""
        return self.prompt is not None and bool(self.contract) and bool(self.message)

    def run(self, plan: StopPlan, deadline: float) -> StageResult:
        """Green when every contract regex matches the message's tail; else warn (or red once)."""
        tail = self.message[-TAIL_CHARS:]
        missing = [pattern for pattern in self.contract if not _matches(pattern, tail)]
        if self.prompt is None or not missing:
            return StageResult(STAGE_NAME, "green")
        slash = quote_data(f"/{self.prompt.slash}")
        lines = tuple(
            f"{slash}: no final answer matches `{_shown(pattern)}`; end with it."
            for pattern in missing
        )
        return StageResult(STAGE_NAME, "red" if self._blocks() else "warn", lines=lines)

    def _blocks(self) -> bool:
        """``block_once``: the first miss of this prompt invocation is red, later ones context."""
        if not self.block_once or self.prompt is None:
            return False
        prompt = self.prompt
        return self.session.once(f"{STAGE_NAME}:block:{prompt.slash}:{prompt.turn_id or ''}")


def output_contract_stage(ev: CanonicalEvent, ctx: HandlerContext) -> OutputContractStage:
    """The ``output-contract`` stage of ``ev``: the coordinator's factory.

    Example: ``output_contract_stage(stop_event, ctx).applies(plan)``.
    """
    prompt = resolve_active_prompt(ev, ctx.cfg, ctx.session.store)
    message = ev.stop.last_assistant_message if ev.stop is not None else ""
    return OutputContractStage(
        prompt=prompt,
        contract=() if prompt is None else ctx.cfg.tables.prompt_output_contract(prompt.slash),
        message=message,
        session=ctx.session,
        block_once=HookConfig(ctx.config, CONFIG_SCHEMA).flag("block_once", False),
    )


@register_hook_handler(
    "prompt_output_contract_on_stop",
    events=["stop"],
    decisions=["deny", "none"],
    config_schema=CONFIG_SCHEMA,
)
def prompt_output_contract_on_stop(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Run the ``output-contract`` stage alone (no coordinator selected).

    Example: ``prompt_output_contract_on_stop(stop_after_review, ctx)``.
    """
    return run_alone(output_contract_stage(ev, ctx), ev, ctx)


def _matches(pattern: str, text: str) -> bool:
    """``pattern`` found in ``text``; a pattern that does not compile is skipped (validate's job)."""
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return True


def _shown(pattern: str) -> str:
    return clip(" ".join(clean_text(pattern).split()).replace("`", "'"), _PATTERN_CHARS)
