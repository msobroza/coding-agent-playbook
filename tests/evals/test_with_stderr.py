"""``with_stderr``: a harness CLI's stderr never joins the answer's last line.

Regression for the Qwen record of 2026-10-29: Claude Code printed
``[claude-code:unrecognized_model] {...}`` on stderr, the runner glued it onto
the answer's final ``approve``, and every review sample's verdict gate (an
``answer_matches`` regex anchored with ``$``) failed — 3 passes in 42 runs.
"""

from __future__ import annotations

import subprocess

import pytest

from coding_agent_playbook.evals.checks.answer import AnswerMatchesCheck
from coding_agent_playbook.evals.run.harness_runner import timed_out_run, with_stderr
from coding_agent_playbook.grading.check import MeasurementSet
from coding_agent_playbook.grading.types import EvalContext

#: The verdict pattern the shipped review samples gate on.
_APPROVES = r"(?im)^\W*(?:verdict\W*)?approve(?: with comments)?\W*$"
_WARNING = '[claude-code:unrecognized_model] {"model":"qwen/qwen3.8-27b"}\n'


@pytest.mark.parametrize(
    ("answer", "stderr", "joined"),
    [
        ("approve", _WARNING, f"approve\n{_WARNING}"),
        ("approve\n", _WARNING, f"approve\n{_WARNING}"),
        ("approve", "", "approve"),
        ("", _WARNING, _WARNING),
        ("", "", ""),
    ],
)
def test_stderr_starts_on_its_own_line(answer: str, stderr: str, joined: str) -> None:
    assert with_stderr(answer, stderr) == joined


def test_a_verdict_line_still_matches_after_a_cli_warning() -> None:
    answer = "Findings: 0 important, 0 nit, 0 pre-existing\n\napprove"
    ctx = EvalContext(
        module=None, source="", label="rubric", artifact=with_stderr(answer, _WARNING)
    )

    result = AnswerMatchesCheck(_APPROVES).grade(ctx, MeasurementSet([], None))

    assert result.passed


def test_a_timed_out_run_keeps_stderr_off_the_partial_answer() -> None:
    exc = subprocess.TimeoutExpired(["agent"], 600, output=b"approve", stderr=b"warn")

    assert timed_out_run(exc, str).transcript.startswith("approve\nwarn\n")
