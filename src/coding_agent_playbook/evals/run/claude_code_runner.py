"""``ClaudeCodeRunner`` — the one thin, opt-in real runner (PR R1c).

The single non-hermetic :class:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner`
shipped in v1.1: its :meth:`_invoke_agent` drives the **Claude Code CLI** bound to
the sample's scratch repo via a plain ``subprocess`` arg-list (no shell), captures
the combined stdout/stderr as the :class:`~coding_agent_playbook.evals.run.harness_runner.AgentRun`
transcript, and records the process return code. Everything before/after the
invocation (materialize → render → capture → score) is the fixed
:meth:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner.run_sample` template.

This runner is **opt-in and never exercised in CI**. There is no import of the
CLI at module top — the only dependency is ``shutil``/``subprocess`` from the
stdlib, and the executable is discovered at call time. :meth:`available` returns
``False`` when the ``claude`` binary is not on ``PATH`` so callers can skip it
cleanly, mirroring the ``radon`` lazy-availability pattern.

Because it feeds a real agent, it sets
:attr:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner.requires_resolved_prompt`
``True``: an unresolvable ``prompt_id`` raises
:class:`~coding_agent_playbook.evals.prompting.PromptResolutionError` rather than
driving the agent with the FakeRunner's placeholder.

The exact CLI contract is **configurable**, not hard-locked: ``command`` is an
arg-list template (with an optional ``{prompt}`` token interpolated per call) and
``timeout`` bounds the run. The default targets the ``claude`` CLI in
non-interactive *print* mode with JSON output (``claude -p <prompt> --output-format
json``) run with ``cwd=scratch_dir``: the result object carries the answer, the
token usage and the model that ran (``claude_code_output``).

Registered under the ``coding_agent_playbook.runners`` entry-point group as
``claude_code`` (see ``pyproject.toml``); discover it via that group rather than
instantiating directly.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.agent_env import unattended_agent_env
from coding_agent_playbook.evals.run.claude_code_output import (
    JSON_OUTPUT_ARGS,
    parse_claude_code_output,
)
from coding_agent_playbook.evals.run.claude_code_route import routed_argv, routed_env
from coding_agent_playbook.evals.run.cli_argv import PROMPT_TOKEN, build_cli_argv
from coding_agent_playbook.evals.run.harness_runner import AgentRun, HarnessRunner

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.run.claude_code_route import ClaudeCodeIsolation

#: Name of the Claude Code executable looked up on ``PATH``.
_CLI = "claude"

#: Default command: the ``claude`` CLI in non-interactive print mode, printing one
#: JSON result object (token usage and model, ticket 07). The bare ``{prompt}``
#: token is interpolated with the rendered prompt per invocation.
_DEFAULT_COMMAND: tuple[str, ...] = (_CLI, "-p", PROMPT_TOKEN, *JSON_OUTPUT_ARGS)

#: Default wall-clock bound (seconds) for one agent invocation.
_DEFAULT_TIMEOUT = 600.0


class ClaudeCodeRunner(HarnessRunner):
    """A :class:`HarnessRunner` that drives the Claude Code CLI in ``scratch_dir``.

    ``command`` is the arg-list template used to spawn the agent; a single
    ``{prompt}`` token (anywhere in the list) is replaced by the rendered prompt.
    When the template contains no token, the prompt is appended as a trailing
    argument so a custom command still receives it. ``timeout`` bounds the run.
    ``model`` (an Eval target's model) is passed as ``--model <model>``, exactly
    as written; ``None`` leaves the CLI on its own default model. ``route``
    (an Eval target's endpoint) isolates the run and points it at that endpoint
    (``claude_code_route``), or, under ``--record`` without an endpoint, a
    ``ClaudeCodeKeyRoute`` isolates it on an API key; ``None`` keeps the user's
    own Claude Code settings.
    """

    name = "claude_code"
    cli = _CLI
    requires_resolved_prompt = True
    accepts_model = True
    accepts_endpoint = True

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        model: str | None = None,
        route: ClaudeCodeIsolation | None = None,
    ) -> None:
        self.model = model
        self.route = route
        self._command: tuple[str, ...] = tuple(command) if command is not None else _DEFAULT_COMMAND
        self._timeout = timeout

    @classmethod
    def available(cls) -> bool:
        """``True`` when the ``claude`` executable is on ``PATH``.

        Lets callers skip this opt-in runner cleanly in air-gapped/CI environments
        without importing or invoking the CLI.
        """
        return shutil.which(_CLI) is not None

    def _build_command(self, prompt: str) -> list[str]:
        """The argv for one run: the template with ``prompt`` and the model (``cli_argv``)."""
        return routed_argv(build_cli_argv(self._command, prompt, self.model), self.route)

    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        """Run the configured command with ``cwd=scratch_dir`` and capture output.

        When stdout is the JSON result object its answer is the transcript and its
        token usage and model are recorded; otherwise stdout is kept as is. stderr
        is appended either way. The return code is the process's, or ``1`` when it
        exits ``0`` but reports ``is_error``. No shell is used — the
        command is an explicit arg-list — and the working directory is the agent's
        scratch repo so any edits land in the tree the scoring layers read. The
        child env is marked unattended, so lifecycle-hook asks degrade to deny; on
        an endpoint it is isolated too, and its token and headers are redacted from
        the decoded transcript (and the raw output when it is not JSON).
        """
        with routed_env(self.route, unattended_agent_env()) as env:
            completed = subprocess.run(
                self._build_command(prompt),
                cwd=scratch_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        stderr = self._redact(completed.stderr)
        # Parse the raw stdout, then redact what came out of it: JSON escapes a
        # secret (a newline as \n, a quote as \"), so redacting before the
        # decode would miss it and the decoded transcript would carry it.
        parsed = parse_claude_code_output(completed.stdout, self.model)
        if parsed is None:
            return AgentRun(
                _with_stderr(self._redact(completed.stdout), stderr), completed.returncode
            )
        # A failed run says so in is_error; never count it as completed.
        returncode = completed.returncode or (1 if parsed.is_error else 0)
        reported_model = parsed.reported_model
        return AgentRun(
            transcript=_with_stderr(self._redact(parsed.transcript), stderr),
            returncode=returncode,
            reported_model=None if reported_model is None else self._redact(reported_model),
            usage=parsed.usage,
        )

    def _redact(self, text: str) -> str:
        """``text`` with the endpoint token removed; unchanged without a route."""
        return text if self.route is None else self.route.redact(text)


def _with_stderr(transcript: str, stderr: str) -> str:
    """``transcript`` followed by ``stderr`` (the CLI's warnings), when there is any."""
    if not stderr:
        return transcript
    return f"{transcript}{stderr}" if transcript else stderr
