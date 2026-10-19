"""Tests for the thin, opt-in ``OpenCodeRunner`` (PR R3 Track O).

These are **hermetic**: the real ``opencode`` CLI is never invoked in CI. We prove
the subprocess plumbing with a *fake* command (a tiny ``python -c`` program that
writes a file into the working dir) and gate the single real-CLI smoke test on
both the CLI being present **and** an explicit ``PLAYBOOK_E2E_OPENCODE=1`` opt-in,
mirroring the ``ClaudeCodeRunner`` smoke-test pattern.
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
from coding_agent_playbook.evals.run.fake_runner import write_files
from coding_agent_playbook.evals.run.harness_runner import AgentRun, materialize
from coding_agent_playbook.evals.run.opencode_runner import OpenCodeRunner
from coding_agent_playbook.evals.task import EvalTask, TaskInvocation

if TYPE_CHECKING:
    from pathlib import Path


def _make_setup(task_dir: Path) -> None:
    setup = task_dir / "setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "mod.py").write_text("x = 1\n", encoding="utf-8")


def _make_task(task_dir: Path, *, prompt_id: str = "refactor") -> EvalTask:
    return EvalTask(
        id="t-fixture",
        prompt_id=prompt_id,
        description="fixture task",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        invocation=TaskInvocation(prompt_args="do the thing"),
    )


# --------------------------------------------------------------------------- #
# available() guard
# --------------------------------------------------------------------------- #


def test_available_false_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert OpenCodeRunner.available() is False


def test_available_true_when_cli_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/local/bin/opencode")
    assert OpenCodeRunner.available() is True


# --------------------------------------------------------------------------- #
# _invoke_agent subprocess plumbing (fake command, no real CLI)
# --------------------------------------------------------------------------- #


def test_invoke_agent_runs_configured_command_and_mutates_scratch(tmp_path: Path) -> None:
    """A fake command writes a file into ``cwd`` and prints to stdout.

    Proves: the configured arg-list runs with ``cwd=scratch_dir`` (the file lands
    in the scratch tree), stdout is captured into ``AgentRun.transcript``, and the
    process returncode is recorded — all without the real ``opencode`` CLI.
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
    runner = OpenCodeRunner(command=[sys.executable, "-c", program])

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
    runner = OpenCodeRunner(command=[sys.executable, "-c", program])

    run = runner._invoke_agent("the prompt", scratch)

    assert run.returncode == 3
    assert "boom" in run.transcript


def test_invoke_agent_substitutes_prompt_placeholder(tmp_path: Path) -> None:
    """A ``{prompt}`` token in the command template is replaced by the prompt."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    runner = OpenCodeRunner(
        command=[sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", "{prompt}"]
    )
    run = runner._invoke_agent("PROMPT-TOKEN", scratch)
    assert "PROMPT-TOKEN" in run.transcript


def test_prompt_appended_when_template_has_no_token(tmp_path: Path) -> None:
    """A command template with no ``{prompt}`` token gets the prompt appended."""
    runner = OpenCodeRunner(command=[sys.executable, "-c", "pass"])
    cmd = runner._build_command("APPENDED-PROMPT")
    assert cmd[-1] == "APPENDED-PROMPT"


def test_default_command_targets_opencode_run_mode() -> None:
    """The default command drives the ``opencode`` CLI in non-interactive run mode."""
    runner = OpenCodeRunner()
    cmd = runner._build_command("the prompt")
    assert cmd[0] == "opencode"
    assert "run" in cmd
    assert "the prompt" in cmd


def test_timeout_is_configurable(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    program = "import time; time.sleep(5)"
    runner = OpenCodeRunner(command=[sys.executable, "-c", program], timeout=0.2)
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
    runner = OpenCodeRunner(command=[sys.executable, "-c", program])

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
    runner = OpenCodeRunner(command=[sys.executable, "-c", program])

    run = runner._invoke_agent("p", scratch)

    assert run.transcript == f"{os.environ['PATH']}|kept"


# --------------------------------------------------------------------------- #
# Prompt-strictness: a real runner must not be fed a placeholder
# --------------------------------------------------------------------------- #


def test_runner_requires_resolved_prompt_flag() -> None:
    assert OpenCodeRunner.requires_resolved_prompt is True


def test_render_prompt_strict_raises_on_unresolvable(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, prompt_id="nonexistent")
    with pytest.raises(PromptResolutionError):
        render_prompt(task, strict=True)


def test_run_task_raises_rather_than_feeding_placeholder(tmp_path: Path) -> None:
    """``OpenCodeRunner.run_task`` on an unresolvable prompt raises (no placeholder)."""
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = _make_task(task_dir, prompt_id="nonexistent")
    # Use a harmless fake command so we never reach the real CLI even if the raise
    # regressed; the strict prompt resolution must fail first.
    runner = OpenCodeRunner(command=[sys.executable, "-c", ""])
    with pytest.raises(PromptResolutionError):
        runner.run_task(task, tmp_path / "scratch")


# --------------------------------------------------------------------------- #
# Registry / discovery
# --------------------------------------------------------------------------- #


def test_opencode_runner_is_registered_via_entry_point() -> None:
    eps = metadata.entry_points(group="coding_agent_playbook.runners")
    by_name = {ep.name: ep for ep in eps}
    assert "opencode" in by_name
    loaded = by_name["opencode"].load()
    assert loaded is OpenCodeRunner
    assert loaded.name == "opencode"


# --------------------------------------------------------------------------- #
# Real-CLI smoke test — NEVER runs in CI
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not (shutil.which("opencode") and os.environ.get("PLAYBOOK_E2E_OPENCODE") == "1"),
    reason="real opencode CLI smoke test: needs the CLI on PATH and PLAYBOOK_E2E_OPENCODE=1",
)
def test_real_opencode_smoke(tmp_path: Path) -> None:  # pragma: no cover - opt-in only
    task_dir = tmp_path / "task"
    _make_setup(task_dir)
    task = EvalTask(
        id="smoke",
        prompt_id="refactor",
        description="d",
        source_path=task_dir / "task.toml",
        source_package="<test>",
        invocation=TaskInvocation(prompt_args="create a file named DONE.txt"),
    )
    # Drive a real run; we only assert it produced a transcript without crashing.
    baseline = materialize(task, tmp_path / "scratch")
    write_files({})(baseline.repo_root)  # no-op; keep import used
    runner = OpenCodeRunner()
    run = runner._invoke_agent("create a file named DONE.txt", baseline.repo_root)
    assert isinstance(run.transcript, str)
