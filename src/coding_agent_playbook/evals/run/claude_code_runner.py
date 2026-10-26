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
non-interactive *print* mode (``claude -p <prompt>``) run with ``cwd=scratch_dir``.

Registered under the ``coding_agent_playbook.runners`` entry-point group as
``claude_code`` (see ``pyproject.toml``); discover it via that group rather than
instantiating directly.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.agent_env import unattended_agent_env
from coding_agent_playbook.evals.run.claude_code_route import routed_argv, routed_env
from coding_agent_playbook.evals.run.cli_argv import PROMPT_TOKEN, build_cli_argv
from coding_agent_playbook.evals.run.harness_runner import AgentRun, HarnessRunner

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.run.claude_code_route import ClaudeCodeRoute

#: Name of the Claude Code executable looked up on ``PATH``.
_CLI = "claude"

#: Default command: the ``claude`` CLI in non-interactive print mode. The bare
#: ``{prompt}`` token is interpolated with the rendered prompt per invocation.
_DEFAULT_COMMAND: tuple[str, ...] = (_CLI, "-p", PROMPT_TOKEN)

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
    (``claude_code_route``); ``None`` keeps the user's own Claude Code settings.
    """

    name = "claude_code"
    requires_resolved_prompt = True
    accepts_model = True
    accepts_endpoint = True

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        model: str | None = None,
        route: ClaudeCodeRoute | None = None,
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

        stdout and stderr are merged into the transcript; the process return code
        is recorded (``0`` = the agent loop completed). No shell is used — the
        command is an explicit arg-list — and the working directory is the agent's
        scratch repo so any edits land in the tree the scoring layers read. The
        child env is marked unattended, so lifecycle-hook asks degrade to deny; on
        an endpoint it is isolated too, and the token is redacted from the transcript.
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
        transcript = completed.stdout
        if completed.stderr:
            transcript = f"{transcript}{completed.stderr}" if transcript else completed.stderr
        if self.route is not None:
            transcript = self.route.redact(transcript)
        return AgentRun(transcript=transcript, returncode=completed.returncode)
