"""Reading ``opencode run --format json`` output (``evals.run.opencode_output``)."""

from __future__ import annotations

import json

import pytest

from coding_agent_playbook.evals.run.opencode_output import OpenCodeOutput, parse_opencode_output


def _line(event_type: str, **data: object) -> str:
    return json.dumps({"type": event_type, "timestamp": 1, "sessionID": "ses_1", **data})


def _step(tokens: dict[str, object], cost: float = 0.0) -> str:
    return _line("step_finish", part={"reason": "stop", "cost": cost, "tokens": tokens})


def test_text_parts_form_the_transcript_and_step_totals_are_summed() -> None:
    stdout = "\n".join(
        [
            _line("step_start", part={}),
            _line("text", part={"type": "text", "text": "Looking at the code."}),
            _line("tool_use", part={"tool": "edit"}),
            _step(
                {"input": 100, "output": 20, "reasoning": 5, "cache": {"read": 30, "write": 10}},
                cost=0.25,
            ),
            _line("text", part={"type": "text", "text": "Done."}),
            _step({"input": 50, "output": 10, "reasoning": 0, "cache": {"read": 0, "write": 0}}),
        ]
    )
    output = parse_opencode_output(stdout)
    assert output == OpenCodeOutput(
        text="Looking at the code.\nDone.",
        input_tokens=190,
        output_tokens=35,
        cost_usd=0.25,
        steps=2,
    )


def test_error_events_are_kept_in_the_transcript() -> None:
    stdout = _line("error", error={"name": "APIError", "data": {"message": "401 Unauthorized"}})
    output = parse_opencode_output(stdout)
    assert output is not None
    assert output.text == "error: APIError: 401 Unauthorized"
    assert output.steps == 0


def test_missing_token_fields_count_as_zero() -> None:
    output = parse_opencode_output(_step({"input": 7}))
    assert output is not None
    assert (output.input_tokens, output.output_tokens, output.cost_usd) == (7, 0, 0.0)


@pytest.mark.parametrize("stdout", ["", "hello from a plain agent", "[1, 2]\n"])
def test_output_that_is_not_json_lines_is_none(stdout: str) -> None:
    assert parse_opencode_output(stdout) is None


def test_stray_non_json_lines_are_kept_in_the_transcript() -> None:
    stdout = "\n".join(["warming up", _line("text", part={"text": "hi"})])
    output = parse_opencode_output(stdout)
    assert output is not None
    assert output.text == "warming up\nhi"
