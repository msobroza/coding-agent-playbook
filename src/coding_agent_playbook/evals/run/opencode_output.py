"""Reading ``opencode run --format json`` output (spec #281 ticket 06b).

OpenCode prints one JSON event per line: ``{"type": ..., "sessionID": ..., ...}``.
``text`` events carry the assistant's text parts; each ``step_finish`` event
carries one model step's ``cost`` and ``tokens``. There is no summary event and
no model id, so the totals are summed over the steps. Input tokens count cache
reads and writes (OpenCode reports them apart), and output tokens count reasoning.
Steps of subagent child sessions are not emitted, so the totals undercount them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

#: The event types this reader uses.
_TEXT: Final = "text"
_STEP_FINISH: Final = "step_finish"
_ERROR: Final = "error"


@dataclass(frozen=True)
class OpenCodeOutput:
    """What one ``opencode run --format json`` printed: the transcript and the step totals.

    ``cost_usd`` is OpenCode's own figure (zero for an endpoint run, whose models
    are declared at zero cost); ``steps`` counts ``step_finish`` events.

    Example::

        >>> OpenCodeOutput("hi", 10, 2, 0.0, 1).output_tokens
        2
    """

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    steps: int


def parse_opencode_output(stdout: str) -> OpenCodeOutput | None:
    """The transcript and token totals in ``stdout``, or ``None`` when it holds no JSON events.

    A line that is not a JSON event (a custom command's log line, say) is kept in
    the transcript as written.

    Example::

        >>> parse_opencode_output('{"type": "text", "part": {"text": "hi"}}').text
        'hi'
        >>> parse_opencode_output("plain text") is None
        True
    """
    lines: list[str] = []
    totals = _Totals()
    seen_event = False
    for raw in stdout.splitlines():
        event = _event(raw)
        if event is None:
            if raw.strip():
                lines.append(raw)
            continue
        seen_event = True
        _read_event(event, lines, totals)
    if not seen_event:
        return None
    return OpenCodeOutput(
        "\n".join(lines), totals.input_tokens, totals.output_tokens, totals.cost_usd, totals.steps
    )


@dataclass
class _Totals:
    """The running sums over ``step_finish`` events."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    steps: int = 0


def _event(raw: str) -> dict[str, object] | None:
    """``raw`` as a JSON event (an object with a string ``type``), else ``None``."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        return None
    return event


def _read_event(event: dict[str, object], lines: list[str], totals: _Totals) -> None:
    """Add a text or error event to ``lines``, a finished step to ``totals``."""
    kind = event["type"]
    part = _mapping(event.get("part"))
    if kind == _TEXT and isinstance(part.get("text"), str):
        lines.append(str(part["text"]))
    elif kind == _ERROR:
        lines.append(_error_line(_mapping(event.get("error"))))
    elif kind == _STEP_FINISH:
        tokens = _mapping(part.get("tokens"))
        cache = _mapping(tokens.get("cache"))
        cached = _number(cache, "read") + _number(cache, "write")
        totals.input_tokens += int(_number(tokens, "input") + cached)
        totals.output_tokens += int(_number(tokens, "output") + _number(tokens, "reasoning"))
        totals.cost_usd += _number(part, "cost")
        totals.steps += 1


def _error_line(error: dict[str, object]) -> str:
    """``error: <name>: <message>`` from an error event, with what it has."""
    message = _mapping(error.get("data")).get("message") or error.get("message")
    named = [str(value) for value in (error.get("name"), message) if value]
    return "error: " + (": ".join(named) or "unknown")


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _number(mapping: dict[str, object], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)
