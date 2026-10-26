"""What ``--record`` refuses: unpinned target and judge models (``evals.model_pins``, ticket 07)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.model_pins import (
    RecordRefusedError,
    check_recordable,
    is_moving_alias,
)
from coding_agent_playbook.evals.targets import EvalTarget


@pytest.mark.parametrize(
    "model",
    [
        "opus",
        "Sonnet",
        "haiku",
        "opusplan",
        "default",
        "best",
        "sonnet[1m]",
        "anthropic/opus",
        "claude-sonnet-latest",
        "llama3:latest",
        "latest",
    ],
)
def test_moving_aliases_are_recognised(model: str) -> None:
    assert is_moving_alias(model)


@pytest.mark.parametrize(
    "model",
    ["claude-opus-5-5", "claude-haiku-4-5-20251001", "my-org/coder-32b-instruct", "opus-lateste"],
)
def test_pinned_models_are_not_aliases(model: str) -> None:
    assert not is_moving_alias(model)


def test_a_target_without_a_model_is_refused() -> None:
    with pytest.raises(RecordRefusedError, match="explicit model"):
        check_recordable(EvalTarget("default", "claude_code"), judge_model=None, uses_judge=False)


def test_a_moving_alias_target_is_refused() -> None:
    target = EvalTarget("t", "claude_code", "opus")
    with pytest.raises(RecordRefusedError, match="'opus' is a moving alias"):
        check_recordable(target, judge_model=None, uses_judge=False)


def test_a_judge_without_a_model_is_refused_when_the_run_uses_a_judge() -> None:
    target = EvalTarget("t", "claude_code", "claude-opus-5-5")
    with pytest.raises(RecordRefusedError, match=r"\[evals.judge\] model"):
        check_recordable(target, judge_model=None, uses_judge=True)


def test_a_moving_alias_judge_is_refused() -> None:
    target = EvalTarget("t", "claude_code", "claude-opus-5-5")
    with pytest.raises(RecordRefusedError, match="'sonnet'"):
        check_recordable(target, judge_model="sonnet", uses_judge=True)


def test_pinned_models_pass_and_no_judge_needs_no_judge_model() -> None:
    target = EvalTarget("t", "claude_code", "claude-opus-5-5")
    check_recordable(target, judge_model=None, uses_judge=False)
    check_recordable(target, judge_model="claude-opus-5-5", uses_judge=True)


def test_a_moving_alias_small_model_is_refused() -> None:
    # PR #310 review: the background model must stay fixed between releases too.
    target = EvalTarget("t", "claude_code", "claude-opus-5-5", small_model="haiku")
    with pytest.raises(RecordRefusedError, match="small_model 'haiku' is a moving alias"):
        check_recordable(target, judge_model=None, uses_judge=False)


def test_a_pinned_small_model_passes() -> None:
    target = EvalTarget("t", "claude_code", "claude-opus-5-5", small_model="claude-haiku-4-5")
    check_recordable(target, judge_model=None, uses_judge=False)
