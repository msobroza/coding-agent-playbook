"""ml-unsafe-deserialization-guard: block new unsafe deserialization sinks (specs/prK-hook-pack.md §E.3).

Default, ``pre_tool_use`` on Edit/Write/NotebookEdit of ``.py`` and ``.ipynb``
files, rendered only in ML repositories (linked rule
``ml-serialization-security``). The edit's post-image is built in memory
(``_sink_writes``) and ``_sink_scan.new_sink_calls`` counts only the sink
calls it adds, from the hook's ``config.block`` / ``config.warn`` rows:

- a new **block** sink (``pickle.loads``, ``torch.load(weights_only=False)``,
  ``trust_remote_code=True``, ...) is denied with the safe API;
- under a ``# playbook: trusted-artifact <provenance>`` comment on the call
  line or the line above, it passes when that comment is committed at
  ``HEAD`` and asks when it is new (a self-written waiver vouches for nothing);
- a new **warn** call (bare ``torch.load``, ``eval``, ``shell=True``) is
  one context line, once per pattern per file per session.

Frozen eval fixtures, secret paths and files outside the worktree are never
judged. Bash-written sinks are K8's Stop rescan, through
:func:`new_sink_calls` (re-exported here). ``on_error: ask``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.handlers._sink_scan import (
    SinkHit,
    SinkTable,
    new_sink_calls,
)
from coding_agent_playbook.hook_runtime.handlers._sink_writes import SinkWrite, sink_writes
from coding_agent_playbook.hook_runtime.registry import ConfigKey, register_hook_handler

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = [
    "CONFIG_SCHEMA",
    "PRAGMA",
    "SinkHit",
    "SinkTable",
    "deser_sink_guard",
    "new_sink_calls",
    "trusted_artifact_line",
]

#: ``[hooks.ml-unsafe-deserialization-guard]`` may add rows, never remove the engine's.
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {
    "block": ConfigKey("list", "extend"),
    "warn": ConfigKey("list", "extend"),
}
#: The escape: a provenance must follow the marker.
PRAGMA: Final = re.compile(r"#\s*playbook:\s*trusted-artifact\s+\S")
_ESCAPE: Final = (
    "For an artifact you trust, ask the user to confirm a "
    "`# playbook: trusted-artifact <provenance>` comment above the call."
)
_UNVOUCHED: Final = (
    "Confirm the artifact's provenance: a comment written in this session cannot vouch for it."
)
_DEFAULT_ADVICE: Final = "Load a data-only format instead."

type Verdict = Literal["deny", "ask", "context", "pass"]


@dataclass(frozen=True, slots=True)
class _Judged:
    """One new sink call of one file, with what the guard makes of it."""

    write: SinkWrite
    hit: SinkHit
    verdict: Verdict

    @property
    def where(self) -> str:
        """``"<rel>:<line>"``; a notebook's line is in its joined cells, so it is left out."""
        rel = self.write.rel
        return quote_data(rel if self.write.notebook else f"{rel}:{self.hit.line}")


@register_hook_handler(
    "deser_sink_guard",
    events=["pre_tool_use"],
    decisions=["deny", "ask", "context", "none"],
    config_schema=CONFIG_SCHEMA,
)
def deser_sink_guard(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """Deny or ask on an edit adding an unsafe sink; one context line per new risky call.

    Example::

        >>> deser_sink_guard(write_adding_pickle_loads, ctx).decision  # doctest: +SKIP
        <Decision.DENY: 'deny'>
    """
    if ev.tool is None or ev.repo is None:
        return None
    writes = sink_writes(ev.tool, os.path.realpath(ev.repo.worktree_root), ctx.cfg)
    if not writes:
        return None
    table = SinkTable.from_config(ctx.config)
    judged = [
        _Judged(write, hit, _verdict(write, hit, ctx))
        for write in writes
        for hit in new_sink_calls(write.pre, write.post, table)
    ]
    return _result(judged, ctx)


def trusted_artifact_line(text: str, line: int) -> str | None:
    """The stripped line holding a trusted-artifact pragma for a call on ``line``, else ``None``.

    The pragma counts on the call line itself or on the line above.

    Example::

        >>> trusted_artifact_line("# playbook: trusted-artifact s3://m/v3\\nm = load(p)\\n", 2)
        '# playbook: trusted-artifact s3://m/v3'
    """
    lines = text.splitlines()
    for number in (line, line - 1):
        if 0 < number <= len(lines) and PRAGMA.search(lines[number - 1]):
            return lines[number - 1].strip()
    return None


def _verdict(write: SinkWrite, hit: SinkHit, ctx: HandlerContext) -> Verdict:
    pragma = trusted_artifact_line(write.post, hit.line)
    if pragma is not None and _committed(write, pragma, ctx):
        return "pass"
    if hit.kind == "warn":
        return "context"
    return "deny" if pragma is None else "ask"


def _committed(write: SinkWrite, pragma: str, ctx: HandlerContext) -> bool:
    """Whether ``pragma`` is a line of the file at ``HEAD`` (a notebook: of its code cells)."""
    if not write.notebook:
        from coding_agent_playbook.hook_runtime.escape import pragma_at_head

        return pragma_at_head(ctx.git, write.rel, pragma)
    from coding_agent_playbook.hook_runtime.handlers._notebook_cells import notebook_code

    blob = ctx.git.cat_head(write.rel)
    code = None if blob is None else notebook_code(blob.decode("utf-8", errors="replace"))
    return code is not None and any(line.strip() == pragma for line in code.splitlines())


def _result(judged: Sequence[_Judged], ctx: HandlerContext) -> HandlerResult | None:
    hook_id = ctx.hook.id
    denied = [j for j in judged if j.verdict == "deny"]
    if denied:
        reason = _deny_reason(denied[0], len(denied))
        return HandlerResult(
            decision=Decision.DENY, hook_id=hook_id, rule_id="unsafe_sink", reason=reason
        )
    asked = [j for j in judged if j.verdict == "ask"]
    if asked:
        first = asked[0]
        head = f"{first.where} adds {first.hit.callee}(...) under a new trusted-artifact comment."
        return HandlerResult(
            decision=Decision.ASK,
            hook_id=hook_id,
            rule_id="trusted_artifact_pragma",
            reason=f"{head}\n{_UNVOUCHED}",
        )
    lines = [_context_line(j) for j in judged if j.verdict == "context" and _first_time(j, ctx)]
    if not lines:
        return None
    return HandlerResult(
        decision=Decision.CONTEXT, hook_id=hook_id, rule_id="risky_call", context=tuple(lines)
    )


def _deny_reason(first: _Judged, count: int) -> str:
    more = f" (and {count - 1} more)" if count > 1 else ""
    head = f"{first.where} adds {first.hit.callee}(...){more}: loading untrusted data this way runs code."
    return "\n".join((head, first.hit.row.advice or _DEFAULT_ADVICE, _ESCAPE))


def _context_line(judged: _Judged) -> str:
    advice = judged.hit.row.advice
    return f"{judged.where} {judged.hit.callee}(...)" + (f": {advice}" if advice else "")


def _first_time(judged: _Judged, ctx: HandlerContext) -> bool:
    """Once per pattern per file per session (§E.3)."""
    return ctx.session.once(f"deser:{judged.write.rel}:{judged.hit.row.call}")
