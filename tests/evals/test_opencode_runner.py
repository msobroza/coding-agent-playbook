"""Tests for the thin, opt-in ``OpenCodeRunner`` (PR R3 Track O).

These are **hermetic**: the real ``opencode`` CLI is never invoked in CI. We prove
the subprocess plumbing with a *fake* command (a tiny ``python -c`` program that
writes a file into the working dir) and gate the single real-CLI smoke test on
both the CLI being present **and** an explicit ``PLAYBOOK_E2E_OPENCODE=1`` opt-in,
mirroring the ``ClaudeCodeRunner`` smoke-test pattern.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from importlib import metadata
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.endpoints import Endpoint
from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt
from coding_agent_playbook.evals.run.fake_runner import write_files
from coding_agent_playbook.evals.run.harness_runner import AgentRun, materialize
from coding_agent_playbook.evals.run.opencode_route import (
    OpenCodeKeyRoute,
    OpenCodeRoute,
    opencode_route,
)
from coding_agent_playbook.evals.run.opencode_runner import OpenCodeRun, OpenCodeRunner
from coding_agent_playbook.evals.sample import EvalSample, SampleInvocation
from coding_agent_playbook.evals.token_usage import TokenUsage
from tests._process_tree import (
    TIMEOUT_S,
    is_alive,
    reaped_grandchild,
    recorded_pid,
    spawning_program,
)

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


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_timed_out_agent_takes_its_child_processes_with_it(tmp_path: Path) -> None:
    """Regression: the timeout killed the CLI only; its workers ran on through the eval run."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with reaped_grandchild(tmp_path / "grandchild.pid") as pid_file:
        program = spawning_program(pid_file)
        runner = OpenCodeRunner(command=[sys.executable, "-c", program], timeout=TIMEOUT_S)
        with pytest.raises(subprocess.TimeoutExpired):
            runner._invoke_agent("p", scratch)
        assert not is_alive(recorded_pid(pid_file))


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


_PRINT_VENV = (
    "import os, sys; "
    "sys.stdout.write(os.environ['PATH'].split(os.pathsep)[0] + '|' "
    "+ os.environ.get('VIRTUAL_ENV', '<unset>'))"
)


@pytest.mark.parametrize(
    "route",
    [
        None,
        OpenCodeKeyRoute("anthropic/m", "k0"),
        OpenCodeRoute(Endpoint("e", "openai-chat", "https://x/v1"), "m", token="t0k3n"),
    ],
    ids=["plain", "key-isolated", "routed"],
)
def test_invoke_agent_runs_on_the_scratch_venv(
    tmp_path: Path, route: OpenCodeKeyRoute | OpenCodeRoute | None
) -> None:
    """The agent's ``python``/``pytest`` are the sample's, synced by ``materialize``."""
    scratch = tmp_path / "scratch"
    (scratch / ".venv" / "bin").mkdir(parents=True)
    runner = OpenCodeRunner(command=[sys.executable, "-c", _PRINT_VENV], route=route)

    run = runner._invoke_agent("p", scratch)

    venv = scratch.absolute() / ".venv"
    assert run.transcript == f"{venv / 'bin'}|{venv}"


@pytest.mark.parametrize(
    "route",
    [
        None,
        OpenCodeKeyRoute("anthropic/m", "k0"),
        OpenCodeRoute(Endpoint("e", "openai-chat", "https://x/v1"), "m", token="t0k3n"),
    ],
    ids=["plain", "key-isolated", "routed"],
)
def test_invoke_agent_runs_with_the_scratch_as_pwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: OpenCodeKeyRoute | OpenCodeRoute | None
) -> None:
    """Regression: OpenCode's project directory is ``PWD``; the caller's let it edit the caller's tree."""
    monkeypatch.setenv("PWD", "/the/caller/checkout")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    program = "import os, sys; sys.stdout.write(os.environ['PWD'])"
    runner = OpenCodeRunner(command=[sys.executable, "-c", program], route=route)

    run = runner._invoke_agent("p", scratch)

    assert run.transcript == str(scratch.absolute())


def test_invoke_agent_without_a_scratch_venv_keeps_the_parent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    runner = OpenCodeRunner(command=[sys.executable, "-c", _PRINT_VENV])

    run = runner._invoke_agent("p", tmp_path)

    assert run.transcript == f"{os.environ['PATH'].split(os.pathsep)[0]}|<unset>"


# --------------------------------------------------------------------------- #
# Prompt-strictness: a real runner must not be fed a placeholder
# --------------------------------------------------------------------------- #


def test_runner_requires_resolved_prompt_flag() -> None:
    assert OpenCodeRunner.requires_resolved_prompt is True


def test_render_prompt_strict_raises_on_unresolvable(tmp_path: Path) -> None:
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, prompt_id="nonexistent")
    with pytest.raises(PromptResolutionError):
        render_prompt(sample, strict=True)


def test_run_sample_raises_rather_than_feeding_placeholder(tmp_path: Path) -> None:
    """``OpenCodeRunner.run_sample`` on an unresolvable prompt raises (no placeholder)."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    sample = _make_sample(sample_dir, prompt_id="nonexistent")
    # Use a harmless fake command so we never reach the real CLI even if the raise
    # regressed; the strict prompt resolution must fail first.
    runner = OpenCodeRunner(command=[sys.executable, "-c", ""])
    with pytest.raises(PromptResolutionError):
        runner.run_sample(sample, tmp_path / "scratch")


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
    runner = OpenCodeRunner()
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
    runner = OpenCodeRunner(command=[sys.executable, "-c", echo_argv, "{prompt}"], model="org/m:v1")

    run = runner._invoke_agent("PROMPT", scratch)

    assert run.transcript == repr(["PROMPT", "--model", "org/m:v1"])
    assert runner.model == "org/m:v1"


def test_default_command_with_a_model_adds_the_model_flag() -> None:
    runner = OpenCodeRunner(model="claude-opus-5-5")
    assert runner._build_command("p") == [
        "opencode",
        "run",
        "--format",
        "json",
        "p",
        "--model",
        "claude-opus-5-5",
    ]


def test_no_model_leaves_the_cli_on_its_default_model() -> None:
    assert "--model" not in OpenCodeRunner()._build_command("p")


# --------------------------------------------------------------------------- #
# JSON output and endpoints (spec #281 ticket 06b)
# --------------------------------------------------------------------------- #

_TOKEN = "fake-endpoint-token-0000"


def _json_events_program(stderr: str = "") -> str:
    """A fake ``opencode run --format json``: two events on stdout, ``stderr`` on stderr."""
    events = [
        {"type": "text", "part": {"text": "edited mod.py"}},
        {"type": "step_finish", "part": {"cost": 0, "tokens": {"input": 12, "output": 3}}},
    ]
    lines = "\n".join(json.dumps(event) for event in events)
    return f"import sys; sys.stdout.write({lines!r}); sys.stderr.write({stderr!r})"


def test_default_command_prints_json_events() -> None:
    assert OpenCodeRunner()._build_command("p")[:4] == ["opencode", "run", "--format", "json"]


def test_json_events_give_the_transcript_and_the_step_totals(tmp_path: Path) -> None:
    runner = OpenCodeRunner(command=[sys.executable, "-c", _json_events_program("a warning\n")])

    run = runner._invoke_agent("p", tmp_path)

    assert isinstance(run, OpenCodeRun)
    assert run.transcript == "edited mod.py\na warning\n"
    assert run.output is not None
    assert (run.output.input_tokens, run.output.output_tokens, run.output.steps) == (12, 3, 1)


def test_json_event_totals_fill_the_usage_release_metrics_read(tmp_path: Path) -> None:
    # Ticket 07 x 06b: OpenCode runs report usage in the metrics file like Claude Code runs.
    runner = OpenCodeRunner(command=[sys.executable, "-c", _json_events_program()])

    run = runner._invoke_agent("p", tmp_path)

    assert run.usage == TokenUsage(input_tokens=12, output_tokens=3)


def test_plain_stdout_reports_no_usage(tmp_path: Path) -> None:
    run = OpenCodeRunner(command=[sys.executable, "-c", "print('plain')"])._invoke_agent(
        "p", tmp_path
    )
    assert run.usage is None


def test_routed_runner_redacts_what_the_judge_grades() -> None:
    assert OpenCodeRunner(route=_route())._redact(f"+{_TOKEN}") == "+[redacted]"


def test_plain_stdout_is_the_transcript_and_reports_no_totals(tmp_path: Path) -> None:
    runner = OpenCodeRunner(command=[sys.executable, "-c", "print('plain')"])
    run = runner._invoke_agent("p", tmp_path)
    assert isinstance(run, OpenCodeRun)
    assert (run.transcript, run.output) == ("plain\n", None)


def _route() -> OpenCodeRoute:
    endpoint = Endpoint("internal", "openai-chat", "https://llm.internal.example/v1", "T")
    return opencode_route(endpoint, "coder-32b", env={"T": _TOKEN})


def test_routed_run_sends_the_provider_qualified_model() -> None:
    runner = OpenCodeRunner(model="coder-32b", route=_route())
    assert runner._build_command("p")[-2:] == ["--model", "playbook-target/coder-32b"]
    assert runner.model == "coder-32b"


def test_routed_run_spawns_with_the_isolated_env_and_redacts_the_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fake-personal-key")
    program = (
        "import json, os, sys; "
        "cfg = json.loads(os.environ['OPENCODE_CONFIG_CONTENT']); "
        "sys.stdout.write(cfg['enabled_providers'][0] + ' ' + str('OPENAI_API_KEY' in os.environ)); "
        "sys.stderr.write(' 401 for ' + os.environ['PLAYBOOK_ENDPOINT_TOKEN'])"
    )
    runner = OpenCodeRunner(command=[sys.executable, "-c", program], route=_route())

    run = runner._invoke_agent("p", tmp_path)

    assert run.transcript == "playbook-target False\n 401 for [redacted]"


def test_opencode_runner_accepts_an_endpoint() -> None:
    assert OpenCodeRunner.accepts_endpoint is True
