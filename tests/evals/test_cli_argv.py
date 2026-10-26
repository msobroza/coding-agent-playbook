"""The argv the CLI runners and the LLM judge spawn (``evals.run.cli_argv``)."""

from __future__ import annotations

from coding_agent_playbook.evals.run.cli_argv import build_cli_argv


def test_prompt_token_is_interpolated_and_no_model_adds_no_flag() -> None:
    assert build_cli_argv(("claude", "-p", "{prompt}"), "do it") == ["claude", "-p", "do it"]


def test_template_without_token_gets_the_prompt_appended() -> None:
    assert build_cli_argv(("opencode", "run"), "do it") == ["opencode", "run", "do it"]


def test_model_is_appended_verbatim() -> None:
    argv = build_cli_argv(("opencode", "run", "{prompt}"), "do it", "my-org/coder:32b")
    assert argv == ["opencode", "run", "do it", "--model", "my-org/coder:32b"]
