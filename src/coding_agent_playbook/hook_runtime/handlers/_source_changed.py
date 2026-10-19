"""Shared plumbing of the post_tool_use source-changed hooks (specs/prK-hook-pack.md §E.0.4, §E.1).

validate-then-sync-on-canonical-edit, resync-on-detector-input-change and
eval-task-authoring-lint share:

- the 2 s per-session debounce (``SessionState.debounce``, :data:`DEBOUNCE_S`);
- :func:`run_playbook`: ``playbook <args>`` as a **child process** on the
  dispatcher's own interpreter (the pinned one the launcher started), never an
  in-process import: ``commands.validate`` and ``commands.eval`` import
  jinja2, which L3 keeps out of the dispatcher (OQ-27).
  The child gets at most 8 s, below the hooks' ``timeout: 10``, and never
  more than the event deadline leaves;
- :func:`fail_lines`: the ``FAIL <path>: <msg>`` lines of ``playbook
  validate`` that mention the edited file or its id, quoted as data, capped;
- :func:`timed_out`: the quality failure class (§E.0.5): fail open, one note
  per session per hook.

A private module: it registers no handler.
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import clean_text, quote_data
from coding_agent_playbook.hook_runtime.decision import Decision, HandlerResult

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.hook_runtime.proc import ProcResult
    from coding_agent_playbook.hook_runtime.registry import HandlerContext

__all__ = [
    "CHILD_TIMEOUT_S",
    "DEBOUNCE_S",
    "MAX_FAIL_LINES",
    "context_result",
    "fail_lines",
    "run_playbook",
    "timed_out",
]

DEBOUNCE_S: Final = 2.0
#: The child's own cap: below the hooks' ``timeout: 10`` (the §D.4 limits nest).
CHILD_TIMEOUT_S: Final = 8.0
MAX_FAIL_LINES: Final = 15
#: Under this much time before the event deadline, a child is not started at all.
_MIN_CHILD_S: Final = 1.0
_DEADLINE_MARGIN_S: Final = 0.5
_LINE_CHARS: Final = 240
_CLI: Final = ("-I", "-m", "coding_agent_playbook.cli")
_FAIL: Final = "FAIL "


def run_playbook(
    ctx: HandlerContext, repo_root: str, args: Sequence[str], *, timeout_s: float = CHILD_TIMEOUT_S
) -> ProcResult | None:
    """Run ``playbook <args> --repo-root <repo_root>``; ``None`` when no time is left for it.

    Raises ``ProcTimeout`` when the child outlives its timeout.

    Example::

        >>> run_playbook(ctx, "/r", ["validate"]).ok  # doctest: +SKIP
        True
    """
    left = ctx.deadline - ctx.clock.monotonic() - _DEADLINE_MARGIN_S
    timeout = min(timeout_s, left)
    if timeout < _MIN_CHILD_S:
        return None
    argv = [sys.executable, *_CLI, *args, "--repo-root", repo_root]
    return ctx.proc.run(argv, timeout=timeout, env=dict(ctx.env) or None, cwd=repo_root)


def fail_lines(
    output: bytes, *, paths: Iterable[str], ids: Iterable[str], cap: int = MAX_FAIL_LINES
) -> list[str]:
    """The ``FAIL`` lines of ``output`` naming one of ``paths`` or ``ids``, quoted, at most ``cap``.

    A path matches as a substring (validate may print it absolute); an id
    only as a whole word. Past ``cap``, the last line says how many more.

    Example::

        >>> fail_lines(b"FAIL a.md: x\\nFAIL b.md: y\\n", paths=["a.md"], ids=[])
        ['"FAIL a.md: x"']
    """
    needles = [p for p in paths if p]
    words = [re.compile(rf"(?<![\w-]){re.escape(i)}(?![\w-])") for i in ids if i]
    text = output.decode("utf-8", errors="replace")
    matched = [
        line
        for line in text.splitlines()
        if line.startswith(_FAIL)
        and (any(n in line for n in needles) or any(w.search(line) for w in words))
    ]
    shown = [quote_data(clean_text(line), _LINE_CHARS) for line in matched]
    if len(shown) <= cap:
        return shown
    hidden = len(shown) - (cap - 1)
    return [*shown[: cap - 1], f"… {hidden} more FAIL lines (run playbook validate)"]


def context_result(ctx: HandlerContext, text: str, rule_id: str = "") -> HandlerResult:
    """One ``context`` item from this hook.

    Example::

        >>> context_result(ctx, "resolve before finishing").decision  # doctest: +SKIP
        <Decision.CONTEXT: 'context'>
    """
    return HandlerResult(
        decision=Decision.CONTEXT, hook_id=ctx.hook.id, rule_id=rule_id, context=(text,)
    )


def timed_out(ctx: HandlerContext, what: str) -> HandlerResult | None:
    """Fail open on a child that timed out (or had no time left): one note per session.

    Example::

        >>> timed_out(ctx, "playbook validate").user_note  # doctest: +SKIP
        'validate-then-sync-on-canonical-edit: playbook validate timed out; ...'
    """
    if not ctx.session.once(f"note:{ctx.hook.id}:timeout"):
        return None
    note = f"{ctx.hook.id}: {what} timed out; skipped this time (the drift gate still applies)."
    return HandlerResult(
        decision=Decision.NONE, hook_id=ctx.hook.id, rule_id="timeout", user_note=note
    )
