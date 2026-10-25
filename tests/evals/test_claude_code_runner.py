"""Tests for the thin, opt-in ``ClaudeCodeRunner`` (PR R1c).

These are **hermetic**: the real ``claude`` CLI is never invoked in CI. We prove
the subprocess plumbing with a *fake* command (a tiny ``python -c`` program that
writes a file into the working dir) and gate the single real-CLI smoke test on
both the CLI being present **and** an explicit ``PLAYBOOK_E2E_CLAUDE=1`` opt-in,
mirroring the ``importorskip``/skip pattern used for the radon/execution tests.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from importlib import metadata
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner
from coding_agent_playbook.evals.run.fake_runner import write_files
from coding_agent_playbook.evals.run.harness_runner import AgentRun, materialize
from coding_agent_playbook.evals.sample import EvalSample, SampleInvocation

if TYPE_CHECKING:
    from pathlib import Path


def _make_setup(sample_dir: Path) -> None:
    setup = sample_dir / "setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "mod.py").write_text("x = 1\n", encoding="utf-8")


def _make_sample(sample_dir: Path, *, prompt_id: str = "refactor") -> EvalSample:
    return EvalSample(
        id="t-fixture",
        prompt_id=prompt_id,
        description="fixture sample",
        source_path=sample_dir / "sample.toml",
        source_package="<test>",
        invocation=SampleInvocation(prompt_args="do the thing"),
    )


# --------------------------------------------------------------------------- #
# available() guard
# --------------------------------------------------------------------------- #


def test_available_false_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert ClaudeCodeRunner.available() is False


def test_available_true_when_cli_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/claude")
    assert ClaudeCodeRunner.available() is True


# --------------------------------------------------------------------------- #
# _invoke_agent subprocess plumbing (fake command, no real CLI)
# --------------------------------------------------------------------------- #


def test_invoke_agent_runs_configured_command_and_mutates_scratch(tmp_path: Path) -> None:
    """A fake command writes a file into ``cwd`` and prints to stdout.

    Proves: the configured arg-list runs with ``cwd=scratch_dir`` (the file lands
    in the scratch tree), stdout is captured into ``AgentRun.transcript``, and the
    process returncode is recorded — all without the real ``claude`` CLI.
    """
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    program = textwrap.dedent(
        """\
        import pathlib, sys
        pathlib.Path("out.txt").write_text("agent-was-here", encoding="utf-8")
        sys.stdout.write("hello from fake agent")
        """
    )
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", program])

    run = runner._invoke_agent("the prompt", scratch)

    assert isinstance(run, AgentRun)
    assert (scratch / "out.txt").read_text(encoding="utf-8") == "agent-was-here"
    assert "hello from fake agent" in run.transcript
    assert run.returncode == 0


def test_invoke_agent_captures_stderr_and_nonzero_returncode(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    program = textwrap.dedent(
        """\
        import sys
        sys.stderr.write("boom")
        sys.exit(3)
        """
    )
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", program])

    run = runner._invoke_agent("the prompt", scratch)

    assert run.returncode == 3
    assert "boom" in run.transcript


def test_invoke_agent_substitutes_prompt_placeholder(tmp_path: Path) -> None:
    """A ``{prompt}`` token in the command template is replaced by the prompt."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    runner = ClaudeCodeRunner(
        command=[sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", "{prompt}"]
    )
    run = runner._invoke_agent("PROMPT-TOKEN", scratch)
    assert "PROMPT-TOKEN" in run.transcript


def test_default_command_targets_claude_print_mode() -> None:
    """The default command drives the ``claude`` CLI in non-interactive print mode."""
    runner = ClaudeCodeRunner()
    cmd = runner._build_command("the prompt")
    assert cmd[0] == "claude"
    assert "the prompt" in cmd


def test_timeout_is_configurable(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    program = "import time; time.sleep(5)"
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", program], timeout=0.2)
    with pytest.raises(Exception):  # noqa: B017  (TimeoutExpired or wrapper)
        runner._invoke_agent("p", scratch)


def test_invoke_agent_child_env_is_unattended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent runs marked unattended, so hook asks degrade to deny (P-D2)."""
    monkeypatch.delenv("PLAYBOOK_HOOK_UNATTENDED", raising=False)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    program = (
        "import os, sys; sys.stdout.write(os.environ.get('PLAYBOOK_HOOK_UNATTENDED', '<unset>'))"
    )
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", program])

    run = runner._invoke_agent("p", scratch)

    assert run.transcript == "1"


def test_invoke_agent_child_env_keeps_parent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unattended flag is added to the parent env, never a replacement for it."""
    monkeypatch.setenv("PLAYBOOK_TEST_PARENT_MARKER", "kept")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    program = (
        "import os, sys; "
        "sys.stdout.write(os.environ['PATH'] + '|' + os.environ['PLAYBOOK_TEST_PARENT_MARKER'])"
    )
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", program])

    run = runner._invoke_agent("p", scratch)

    assert run.transcript == f"{os.environ['PATH']}|kept"


# --------------------------------------------------------------------------- #
# Prompt-strictness: a real runner must not be fed a placeholder
# --------------------------------------------------------------------------- #


def test_runner_requires_resolved_prompt_flag() -> None:
    assert ClaudeCodeRunner.requires_resolved_prompt is True


def test_render_prompt_strict_raises_on_unresolvable(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, prompt_id="nonexistent")
    with pytest.raises(PromptResolutionError):
        render_prompt(sample, strict=True)


def test_run_sample_raises_rather_than_feeding_placeholder(tmp_path: Path) -> None:
    """``ClaudeCodeRunner.run_sample`` on an unresolvable prompt raises (no placeholder)."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, prompt_id="nonexistent")
    # Use a harmless fake command so we never reach the real CLI even if the raise
    # regressed; the strict prompt resolution must fail first.
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", ""])
    with pytest.raises(PromptResolutionError):
        runner.run_sample(sample, tmp_path / "scratch")


# --------------------------------------------------------------------------- #
# Registry / discovery
# --------------------------------------------------------------------------- #


def test_claude_code_runner_is_registered_via_entry_point() -> None:
    eps = metadata.entry_points(group="coding_agent_playbook.runners")
    by_name = {ep.name: ep for ep in eps}
    assert "claude_code" in by_name
    loaded = by_name["claude_code"].load()
    assert loaded is ClaudeCodeRunner
    assert loaded.name == "claude_code"


# --------------------------------------------------------------------------- #
# Real-CLI smoke test — NEVER runs in CI
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not (shutil.which("claude") and os.environ.get("PLAYBOOK_E2E_CLAUDE") == "1"),
    reason="real claude CLI smoke test: needs the CLI on PATH and PLAYBOOK_E2E_CLAUDE=1",
)
def test_real_claude_smoke(tmp_path: Path) -> None:  # pragma: no cover - opt-in only
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = EvalSample(
        id="smoke",
        prompt_id="refactor",
        description="d",
        source_path=sample_dir / "sample.toml",
        source_package="<test>",
        invocation=SampleInvocation(prompt_args="create a file named DONE.txt"),
    )
    # Drive a real run; we only assert it produced a transcript without crashing.
    baseline = materialize(sample, tmp_path / "scratch")
    write_files({})(baseline.repo_root)  # no-op; keep import used
    runner = ClaudeCodeRunner()
    run = runner._invoke_agent("create a file named DONE.txt", baseline.repo_root)
    assert isinstance(run.transcript, str)


# --------------------------------------------------------------------------- #
# Eval target model (spec #281 ticket 05)
# --------------------------------------------------------------------------- #


def test_target_model_reaches_the_cli_unchanged(tmp_path: Path) -> None:
    """A target's model is passed as ``--model <model>``, exactly as written."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    echo_argv = "import sys; sys.stdout.write(repr(sys.argv[1:]))"
    runner = ClaudeCodeRunner(
        command=[sys.executable, "-c", echo_argv, "{prompt}"], model="org/m:v1"
    )

    run = runner._invoke_agent("PROMPT", scratch)

    assert run.transcript == repr(["PROMPT", "--model", "org/m:v1"])
    assert runner.model == "org/m:v1"


def test_default_command_with_a_model_adds_the_model_flag() -> None:
    runner = ClaudeCodeRunner(model="claude-opus-5-5")
    assert runner._build_command("p") == ["claude", "-p", "p", "--model", "claude-opus-5-5"]


def test_no_model_leaves_the_cli_on_its_default_model() -> None:
    assert "--model" not in ClaudeCodeRunner()._build_command("p")
