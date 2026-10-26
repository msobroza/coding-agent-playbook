"""Reading ``claude -p --output-format json`` (``evals.run.claude_code_output``, spec #281 ticket 07)."""

from __future__ import annotations

import json

from coding_agent_playbook.evals.run.claude_code_output import parse_claude_code_output
from coding_agent_playbook.evals.token_usage import TokenUsage


def _result(**fields: object) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, **fields})


def test_requested_model_is_reported_when_model_usage_lists_it() -> None:
    usage = {
        "claude-haiku-4-5-20251001": {"inputTokens": 9, "outputTokens": 900},
        "claude-opus-5-5": {"inputTokens": 50, "outputTokens": 10},
    }
    parsed = parse_claude_code_output(_result(modelUsage=usage), "claude-opus-5-5")
    assert parsed is not None
    assert parsed.reported_model == "claude-opus-5-5"
    assert parsed.usage == TokenUsage(59, 910)


def test_an_alias_reports_the_model_with_the_most_output() -> None:
    usage = {
        "claude-haiku-4-5-20251001": {"outputTokens": 3},
        "claude-sonnet-5-5": {"outputTokens": 30},
    }
    parsed = parse_claude_code_output(_result(modelUsage=usage), "sonnet")
    assert parsed is not None
    assert parsed.reported_model == "claude-sonnet-5-5"


def test_top_level_usage_is_the_fallback_and_counts_cache_tokens_as_input() -> None:
    usage = {
        "input_tokens": 10,
        "cache_read_input_tokens": 4,
        "cache_creation_input_tokens": 1,
        "output_tokens": 6,
    }
    parsed = parse_claude_code_output(_result(usage=usage), None)
    assert parsed is not None
    assert (parsed.usage, parsed.reported_model) == (TokenUsage(15, 6), None)


def test_is_error_is_the_failure_signal_even_when_subtype_says_success() -> None:
    parsed = parse_claude_code_output(_result(is_error=True, result="API Error: 401"), None)
    assert parsed is not None
    assert (parsed.is_error, parsed.transcript) == (True, "API Error: 401")


def test_output_without_usage_has_no_tokens() -> None:
    parsed = parse_claude_code_output(_result(result="ok"), None)
    assert parsed is not None
    assert parsed.usage is None


def test_anything_but_a_result_object_is_not_parsed() -> None:
    assert parse_claude_code_output("plain text", None) is None
    assert parse_claude_code_output('{"type": "system"}', None) is None
    assert parse_claude_code_output("[1, 2]", None) is None
