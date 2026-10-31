"""Tests for the thin, opt-in ``ClaudeCodeRunner`` (PR R1c).

These are **hermetic**: the real ``claude`` CLI is never invoked in CI. We prove
the subprocess plumbing with a *fake* command (a tiny ``python -c`` program that
writes a file into the working dir) and gate the single real-CLI smoke test on
both the CLI being present **and** an explicit ``PLAYBOOK_E2E_CLAUDE=1`` opt-in,
mirroring the ``importorskip``/skip pattern used for the radon/execution tests.
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
from coding_agent_playbook.evals.run.claude_code_route import ClaudeCodeKeyRoute, ClaudeCodeRoute
from coding_agent_playbook.evals.run.claude_code_runner import (
    ISOLATED_ALLOWED_TOOLS,
    ClaudeCodeRunner,
)
from coding_agent_playbook.evals.run.fake_runner import write_files
from coding_agent_playbook.evals.run.harness_runner import AgentRun, Candidate, materialize
from coding_agent_playbook.evals.sample import EvalSample, SampleInvocation
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


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_a_timed_out_agent_takes_its_child_processes_with_it(tmp_path: Path) -> None:
    """Regression: the timeout killed the CLI only; its workers ran on through the eval run."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with reaped_grandchild(tmp_path / "grandchild.pid") as pid_file:
        program = spawning_program(pid_file)
        runner = ClaudeCodeRunner(command=[sys.executable, "-c", program], timeout=TIMEOUT_S)
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


_PRINT_VENV = (
    "import os, sys; "
    "sys.stdout.write(os.environ['PATH'].split(os.pathsep)[0] + '|' "
    "+ os.environ.get('VIRTUAL_ENV', '<unset>'))"
)


@pytest.mark.parametrize(
    "route",
    [
        None,
        ClaudeCodeKeyRoute("k0"),
        ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m", token="t0k3n"),
    ],
    ids=["plain", "key-isolated", "routed"],
)
def test_invoke_agent_runs_on_the_scratch_venv(
    tmp_path: Path, route: ClaudeCodeKeyRoute | ClaudeCodeRoute | None
) -> None:
    """The agent's ``python``/``pytest`` are the sample's, synced by ``materialize``."""
    scratch = tmp_path / "scratch"
    (scratch / ".venv" / "bin").mkdir(parents=True)
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", _PRINT_VENV], route=route)

    run = runner._invoke_agent("p", scratch)

    venv = scratch.absolute() / ".venv"
    assert run.transcript == f"{venv / 'bin'}|{venv}"


def test_invoke_agent_without_a_scratch_venv_keeps_the_parent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", _PRINT_VENV])

    run = runner._invoke_agent("p", tmp_path)

    assert run.transcript == f"{os.environ['PATH'].split(os.pathsep)[0]}|<unset>"


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
    assert runner._build_command("p") == [
        "claude",
        "-p",
        "p",
        "--output-format",
        "json",
        "--model",
        "claude-opus-5-5",
    ]


def test_no_model_leaves_the_cli_on_its_default_model() -> None:
    assert "--model" not in ClaudeCodeRunner()._build_command("p")


_ISOLATED = ["--permission-mode", "acceptEdits", "--allowedTools", ISOLATED_ALLOWED_TOOLS]


@pytest.mark.parametrize(
    "route",
    [
        ClaudeCodeKeyRoute("k0"),
        ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m", token="t0k3n"),
    ],
)
def test_a_routed_run_accepts_edits_and_allows_only_the_listed_tools(
    route: ClaudeCodeKeyRoute | ClaudeCodeRoute,
) -> None:
    # An isolated run has no personal default mode, and -p auto-denies prompts.
    argv = ClaudeCodeRunner(model="m", route=route)._build_command("p")
    assert argv[-4:] == _ISOLATED
    assert "bypassPermissions" not in argv


def test_the_isolated_allow_list_is_read_search_git_python_pytest_uv_and_ls() -> None:
    # No catch-all Bash and no network or file-deleting commands: anything else is denied.
    tools = ISOLATED_ALLOWED_TOOLS.split(",")
    assert tools == [
        "Read",
        "Grep",
        "Glob",
        "Bash(git:*)",
        "Bash(python:*)",
        "Bash(python3:*)",
        "Bash(pytest:*)",
        "Bash(uv:*)",
        "Bash(ls:*)",
    ]


def test_an_unrouted_run_keeps_the_user_permission_mode() -> None:
    assert "--permission-mode" not in ClaudeCodeRunner(model="m")._build_command("p")


# --------------------------------------------------------------------------- #
# JSON output: answer, token usage and reported model (spec #281 ticket 07)
# --------------------------------------------------------------------------- #

_RESULT_JSON = (
    '{"type": "result", "subtype": "success", "is_error": %s, "result": "the answer", '
    '"total_cost_usd": 99.0, "modelUsage": {"claude-opus-5-5": {"inputTokens": 100, '
    '"cacheReadInputTokens": 20, "cacheCreationInputTokens": 5, "outputTokens": 40}}}'
)


def _printing(stdout: str, exit_code: int = 0) -> list[str]:
    """A command that prints ``stdout`` and exits with ``exit_code``, standing in for ``claude``."""
    program = f"import sys; sys.stdout.write({stdout!r}); sys.exit({exit_code})"
    return [sys.executable, "-c", program]


def test_a_cli_warning_lands_after_the_answer_on_its_own_line(tmp_path: Path) -> None:
    # Claude Code warns on stderr for a non-Anthropic model; glued onto a final
    # "approve" it failed every review verdict gate (Qwen record, 2026-10-29).
    result = json.dumps({"type": "result", "is_error": False, "result": "approve"})
    warning = '[claude-code:unrecognized_model] {"model":"qwen/qwen3.8-27b"}\n'
    program = f"import sys; sys.stdout.write({result!r}); sys.stderr.write({warning!r})"

    run = ClaudeCodeRunner(command=[sys.executable, "-c", program])._invoke_agent("p", tmp_path)

    assert run.transcript == f"approve\n{warning}"


def test_json_result_gives_the_answer_tokens_and_model(tmp_path: Path) -> None:
    runner = ClaudeCodeRunner(command=_printing(_RESULT_JSON % "false"), model="claude-opus-5-5")

    run = runner._invoke_agent("p", tmp_path)

    assert run.transcript == "the answer"
    assert run.returncode == 0
    assert run.reported_model == "claude-opus-5-5"
    assert run.usage is not None
    assert (run.usage.input_tokens, run.usage.output_tokens) == (125, 40)


def test_json_error_with_exit_zero_counts_as_a_failed_run(tmp_path: Path) -> None:
    run = ClaudeCodeRunner(command=_printing(_RESULT_JSON % "true"))._invoke_agent("p", tmp_path)
    assert run.returncode == 1


def test_non_json_output_is_kept_as_the_transcript_without_usage(tmp_path: Path) -> None:
    run = ClaudeCodeRunner(command=_printing("plain text"))._invoke_agent("p", tmp_path)
    assert (run.transcript, run.usage, run.reported_model) == ("plain text", None, None)


def test_routed_json_run_parses_usage_and_redacts_the_token(tmp_path: Path) -> None:
    # Ticket 06 x 07: an endpoint run still reads the JSON result, and a token the
    # agent echoed never reaches the transcript the judge grades.
    route = ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "internal-opus", token="t0k3n")
    stdout = (_RESULT_JSON % "false").replace("the answer", "leaked t0k3n")
    runner = ClaudeCodeRunner(command=_printing(stdout), model="internal-opus", route=route)

    run = runner._invoke_agent("p", tmp_path)

    assert run.transcript == "leaked [redacted]"
    assert run.usage is not None
    assert run.usage.output_tokens == 40


def test_routed_json_run_redacts_secrets_that_json_escapes(tmp_path: Path) -> None:
    # Regression (PR #310 review): JSON escapes a multi-line headers value (\n) and a
    # token holding a quote, so redacting the raw stdout before the decode missed
    # them and the decoded transcript the judge grades carried both secrets.
    headers, token = "X-Org: org-1\nX-Key: hdr-secret-123", 'tok"en'
    route = ClaudeCodeRoute(
        Endpoint("e", "anthropic", "https://x"), "m", token=token, headers=headers
    )
    stdout = json.dumps({"type": "result", "result": f"env: {headers} tok={token}"})
    runner = ClaudeCodeRunner(command=_printing(stdout), model="m", route=route)

    run = runner._invoke_agent("p", tmp_path)

    assert "hdr-secret-123" not in run.transcript
    assert token not in run.transcript
    assert run.transcript == "env: [redacted] tok=[redacted]"


def test_route_redacts_each_header_line_on_its_own() -> None:
    route = ClaudeCodeRoute(
        Endpoint("e", "anthropic", "https://x"), "m", headers="X-Org: org-1\nX-Key: k1"
    )
    assert route.redact("saw X-Key: k1 only") == "saw [redacted] only"


def test_route_redacts_a_header_value_printed_on_its_own() -> None:
    # PR #310 review: an agent may print just a header's value, without its name.
    route = ClaudeCodeRoute(
        Endpoint("e", "anthropic", "https://x"), "m", headers="X-Org: org-1\nX-Key: k1-secret"
    )
    assert route.redact("value k1-secret") == "value [redacted]"


def test_route_redacts_a_non_ascii_secret_in_its_unescaped_json_form() -> None:
    # json.dumps(..., ensure_ascii=False) keeps the non-ASCII letter but escapes the quote.
    route = ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m", token='tök"en')
    assert route.redact('{"t": "tök\\"en"}') == '{"t": "[redacted]"}'


class _PassedReport:
    """The one field ``_run_trial`` reads from a report."""

    passed = True


class _RecordingScore:
    """Stands in for ``harness_runner.score``: records the diff each judge would be handed."""

    def __init__(self) -> None:
        self.diffs: list[str] = []

    def __call__(
        self, _sample: object, _baseline: object, candidate: Candidate, **_kw: object
    ) -> _PassedReport:
        self.diffs.append(candidate.diff)
        return _PassedReport()


def test_a_token_written_into_a_file_is_redacted_from_the_graded_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression (PR #310 review): the judge grades the diff, so a token the agent
    # wrote into a file reached the judge's argv unredacted.
    from coding_agent_playbook.evals.run import harness_runner

    recorder = _RecordingScore()
    monkeypatch.setattr(harness_runner, "score", recorder)
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir)
    route = ClaudeCodeRoute(Endpoint("e", "anthropic", "https://x"), "m", token="t0k3n-in-file")
    program = 'import pathlib; pathlib.Path("leak.txt").write_text("t0k3n-in-file\\n")'
    runner = ClaudeCodeRunner(command=[sys.executable, "-c", program], model="m", route=route)

    runner._run_trial(
        _make_sample(sample_dir),
        "p",
        tmp_path / "scratch",
        judge=None,
        judge_samples=1,
        fail_fast=True,
    )

    assert len(recorder.diffs) == 1
    assert "leak.txt" in recorder.diffs[0]
    assert "t0k3n-in-file" not in recorder.diffs[0]
    assert "+[redacted]" in recorder.diffs[0]
