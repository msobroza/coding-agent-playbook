"""Read ``claude -p --output-format json``: the answer, the token usage and the model (ticket 07).

The CLI prints one JSON result object. Verified on Claude Code 2.1.292:

- ``result`` is the final text, the transcript the judge reads;
- ``modelUsage`` is keyed by the model string the CLI sent (an alias appears
  as the id it resolved to, and background work as its own model), each entry
  carrying ``inputTokens``, ``outputTokens``, ``cacheReadInputTokens`` and
  ``cacheCreationInputTokens``; the top-level ``usage`` has the same counts in
  snake case and is the fallback;
- a failed run exits 1 with ``is_error`` true while ``subtype`` still says
  ``success``, so ``is_error`` is the signal;
- ``total_cost_usd`` is a client-side estimate from a bundled price table and is
  meaningless for a custom endpoint, so it is never read.

Anything that is not such an object (a custom ``command``, a crash before the
JSON) yields ``None`` and the runner keeps the raw output as the transcript.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.token_usage import TokenUsage

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The flags that make ``claude -p`` print the JSON result object.
JSON_OUTPUT_ARGS: Final = ("--output-format", "json")

#: ``modelUsage`` keys whose sum is a model's input tokens (cache reads and writes included).
_MODEL_INPUT_KEYS: Final = ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
#: The same counts in the top-level ``usage`` object.
_USAGE_INPUT_KEYS: Final = (
    "input_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


@dataclass(frozen=True)
class ClaudeCodeResult:
    """What one ``claude -p --output-format json`` run reported.

    Example::

        >>> parse_claude_code_output('{"type": "result", "result": "hi"}', None).transcript
        'hi'
    """

    transcript: str
    is_error: bool
    usage: TokenUsage | None
    reported_model: str | None


def parse_claude_code_output(stdout: str, requested_model: str | None) -> ClaudeCodeResult | None:
    """The run's result object read from ``stdout``, or ``None`` when it is not one.

    ``requested_model`` (the model sent with ``--model``) is the reported model
    whenever ``modelUsage`` lists it; otherwise the model that produced the most
    output tokens is (an alias resolves to another key).

    Example::

        >>> out = '{"type": "result", "result": "ok", "modelUsage": {"m": {"inputTokens": 3, "outputTokens": 2}}}'
        >>> parse_claude_code_output(out, "m").usage
        TokenUsage(input_tokens=3, output_tokens=2)
    """
    payload = _result_object(stdout)
    if payload is None:
        return None
    result_text = payload.get("result")
    model_usage = _model_usage(payload)
    return ClaudeCodeResult(
        transcript=result_text if isinstance(result_text, str) else stdout,
        is_error=payload.get("is_error") is True,
        usage=_usage(payload, model_usage),
        reported_model=_reported_model(model_usage, requested_model),
    )


def _result_object(stdout: str) -> dict[str, object] | None:
    """The JSON object ``stdout`` holds when it is a ``"type": "result"`` object."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("type") != "result":
        return None
    return payload


def _model_usage(payload: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    """``modelUsage`` as ``{model: counts}``, dropping entries that are not objects."""
    raw = payload.get("modelUsage")
    if not isinstance(raw, dict):
        return {}
    return {str(model): counts for model, counts in raw.items() if isinstance(counts, dict)}


def _usage(
    payload: Mapping[str, object], model_usage: Mapping[str, Mapping[str, object]]
) -> TokenUsage | None:
    """Tokens summed over every model in ``modelUsage``, else the top-level ``usage``."""
    if model_usage:
        per_model = [_counts(c, _MODEL_INPUT_KEYS, "outputTokens") for c in model_usage.values()]
        return TokenUsage(
            input_tokens=sum(usage.input_tokens for usage in per_model),
            output_tokens=sum(usage.output_tokens for usage in per_model),
        )
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    return _counts(usage, _USAGE_INPUT_KEYS, "output_tokens")


def _counts(
    counts: Mapping[str, object], input_keys: tuple[str, ...], output_key: str
) -> TokenUsage:
    return TokenUsage(
        input_tokens=sum(_count(counts, key) for key in input_keys),
        output_tokens=_count(counts, output_key),
    )


def _count(counts: Mapping[str, object], key: str) -> int:
    """A non-negative token count, ``0`` when absent or not a number."""
    value = counts.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return 0
    return int(value)


def _reported_model(
    model_usage: Mapping[str, Mapping[str, object]], requested_model: str | None
) -> str | None:
    if not model_usage:
        return None
    if requested_model is not None and requested_model in model_usage:
        return requested_model
    return max(model_usage, key=lambda model: _count(model_usage[model], "outputTokens"))
