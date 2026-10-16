"""What the Stop coordinator says: the one combined reason and its user notes (specs/prK-lifecycle-hooks.md §D.5.4).

The reason is one header, the red stages' lines (each prefixed ``[<stage>]``)
and at most two ``Also:`` footer lines carrying ``warn`` stages, never more
than 40 lines nor ``OutputCaps.STOP_REASON.max_chars``. Every red stage is
guaranteed three lines; the rest go to the stages in ``STOP_STAGE_ORDER``,
and a stage that overflows ends with ``(+N more)``. A stage line is flattened
to one line with no control character, so repo data quoted in it (stages use
``caps.quote_data``) can never pose as a line of its own.

Notes are addressed to the user: a skipped stage is ``NOT verified``, never
green, and a missing toolchain asks the *user* to re-sync rather than handing
the agent a command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.caps import OutputCaps, clean_text, clip

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.hook_runtime.stop.stages import StageResult

__all__ = [
    "GATE_OFF_NOTE",
    "NO_PINS_ADVICE",
    "compose_reason",
    "green_note",
    "not_verified_note",
    "red_note",
    "toolchain_advice",
    "untrusted_note",
]

_CAP: Final = OutputCaps.STOP_REASON
#: Lines every red stage is guaranteed before the rest are shared out in order.
GUARANTEED_LINES: Final = 3
#: ``Also:`` lines after the red stages (§D.5.4: at most two footer lines).
FOOTER_LINES: Final = 2
#: The widest a reason line may be when only a few lines are shown.
_LINE_CHARS: Final = OutputCaps.REASON.line_chars

GATE_OFF_NOTE: Final = "Playbook stop gate disabled (PLAYBOOK_GATE=off): work NOT verified."
NO_PINS_ADVICE: Final = (
    "no tool pins (machine.json) in this worktree; ask the user to run playbook sync in this "
    "worktree"
)


def compose_reason(
    red: Sequence[StageResult],
    warn: Sequence[StageResult],
    *,
    tree: str | None,
    block_no: int | None,
    max_blocks: int,
) -> str:
    """The combined deny reason for ``red`` (non-empty), ``warn`` under ``Also:``.

    ``block_no`` is ``None`` when the gate cannot block (OpenCode): the header
    then says ``NOT verified`` instead of counting blocks.

    Example::

        >>> compose_reason([StageResult("lint", "red", lines=("x",))], [], tree="1a2b3c4d9",
        ...                block_no=1, max_blocks=2).splitlines()  # doctest: +SKIP
        ['Playbook gate RED — fix before finishing (tree 1a2b3c4d, block 1/2):', '[lint] x']
    """
    footer = _footer(warn)
    body = _body(red, _CAP.max_lines - 1 - len(footer))
    lines = [_header(red, tree, block_no, max_blocks), *body, *footer]
    width = min(_LINE_CHARS, (_CAP.max_chars + 1) // len(lines) - 1)
    return "\n".join(clip(line, width) for line in lines)


def toolchain_advice(tool: str, problem: str) -> str:
    """One line for the **user** about a stage tool that cannot run (§D.5.4 advice targets).

    Example::

        >>> toolchain_advice("ruff", "changed since sync")
        'ruff changed since sync; ask the user to run playbook sync'
    """
    return f"{_flat(tool)} {problem}; ask the user to run playbook sync"


def not_verified_note(result: StageResult) -> str:
    """The note for a skipped stage: it never counts as green.

    Example: ``not_verified_note(skipped_lint) == "NOT verified: lint skipped (timeout)"``.
    """
    return f"NOT verified: {result.stage} skipped ({result.skip_category})"


def red_note(stage: str) -> str:
    """The note when a red gate lets the Stop through: red is never presented as green.

    Example: ``red_note("lint") == "Playbook gate RED at lint — NOT verified."``.
    """
    return f"Playbook gate RED at {stage} — NOT verified."


def green_note(stages: Iterable[str]) -> str:
    """The first-green-per-fingerprint note (§E.2): local checks, CI still authoritative.

    Example: ``green_note(["drift", "lint"])``.
    """
    return f"verified locally ({', '.join(stages)}); the CI matrix is authoritative"


def untrusted_note(stages: Iterable[str]) -> str:
    """Execution stages skipped for want of a user-local approval (§B.4); once per session.

    Example: ``untrusted_note(["tests"])``.
    """
    names = ", ".join(stages)
    return (
        f"Playbook execution stages ({names}) skipped: not approved on this machine; "
        "ask the user to run playbook sync in a terminal."
    )


def _header(red: Sequence[StageResult], tree: str | None, block_no: int | None, most: int) -> str:
    short = _flat(tree or "unknown")[:8]
    if block_no is None:
        return f"Playbook gate RED at {red[0].stage} — NOT verified (tree {short}):"
    return f"Playbook gate RED — fix before finishing (tree {short}, block {block_no}/{most}):"


def _body(red: Sequence[StageResult], budget: int) -> list[str]:
    texts = [[_flat(line) for line in r.lines] or ["(no detail)"] for r in red]
    shares = _allot([len(lines) for lines in texts], budget)
    body: list[str] = []
    for result, lines, share in zip(red, texts, shares, strict=True):
        body.extend(_stage_lines(result.stage, lines, share))
    return body


def _allot(counts: Sequence[int], budget: int) -> list[int]:
    """Lines per stage: up to :data:`GUARANTEED_LINES` each first, then the rest in order."""
    shares: list[int] = []
    for count in counts:
        shares.append(min(GUARANTEED_LINES, count, budget))
        budget -= shares[-1]
    for index, count in enumerate(counts):
        extra = min(count - shares[index], budget)
        shares[index] += extra
        budget -= extra
    return shares


def _stage_lines(stage: str, lines: Sequence[str], share: int) -> list[str]:
    if share <= 0:
        return []
    if len(lines) <= share:
        return [f"[{stage}] {line}" for line in lines]
    shown = lines[: share - 1]
    return [
        *(f"[{stage}] {line}" for line in shown),
        f"[{stage}] (+{len(lines) - len(shown)} more)",
    ]


def _footer(warn: Sequence[StageResult]) -> list[str]:
    items = [_flat(line) for result in warn for line in result.lines]
    if len(items) > FOOTER_LINES:
        items = [*items[: FOOTER_LINES - 1], f"(+{len(items) - FOOTER_LINES + 1} more)"]
    return [f"Also: {item}" for item in items]


def _flat(text: str) -> str:
    """``text`` on one line, without control characters."""
    return " ".join(clean_text(text).split())
