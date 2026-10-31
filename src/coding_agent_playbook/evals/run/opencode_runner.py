"""``OpenCodeRunner`` — a second thin, opt-in real runner (PR R3 Track O).

A :class:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner` that drives the
**OpenCode CLI** bound to the sample's scratch repo, mirroring the opt-in
``ClaudeCodeRunner``: its :meth:`_invoke_agent` spawns the CLI via a plain
``subprocess`` arg-list (no shell) in ``--format json`` mode, reads the
:class:`~coding_agent_playbook.evals.run.harness_runner.AgentRun` transcript and the token
totals from its JSON events (``opencode_output``), keeps stderr apart from them,
and records the process return code. Everything before/after the invocation (materialize →
render → capture → score) is the fixed
:meth:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner.run_sample` template.

This runner is **opt-in and never exercised in CI**. There is no import of the
CLI at module top — the only dependency is ``shutil``/``subprocess`` from the
stdlib, and the executable is discovered at call time. :meth:`available` returns
``False`` when the ``opencode`` binary is not on ``PATH`` so callers can skip it
cleanly, mirroring the ``radon`` lazy-availability pattern.

Because it feeds a real agent, it sets
:attr:`~coding_agent_playbook.evals.run.harness_runner.HarnessRunner.requires_resolved_prompt`
``True``: an unresolvable ``prompt_id`` raises
:class:`~coding_agent_playbook.evals.prompting.PromptResolutionError` rather than
driving the agent with the FakeRunner's placeholder.

The exact CLI contract is **configurable**, not hard-locked: ``command`` is an
arg-list template (with an optional ``{prompt}`` token interpolated per call) and
``timeout`` bounds the run. The default targets the ``opencode`` CLI in its
non-interactive *run* mode (``opencode run --format json <prompt>``) with
``cwd=scratch_dir``. An Eval target's endpoint gives the runner a ``route``
(``opencode_route``): the run is then isolated and pointed at that endpoint.

Registered under the ``coding_agent_playbook.runners`` entry-point group as
``opencode`` (see ``pyproject.toml``); discover it via that group rather than
instantiating directly.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.agent_env import agent_env
from coding_agent_playbook.evals.run.cli_argv import PROMPT_TOKEN, build_cli_argv
from coding_agent_playbook.evals.run.harness_runner import AgentRun, HarnessRunner, with_stderr
from coding_agent_playbook.evals.run.opencode_output import OpenCodeOutput, parse_opencode_output
from coding_agent_playbook.evals.run.opencode_route import routed_opencode_env
from coding_agent_playbook.evals.token_usage import TokenUsage
from coding_agent_playbook.grading import bounded_subprocess

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.run.opencode_route import OpenCodeIsolation

#: Name of the OpenCode executable looked up on ``PATH``.
_CLI = "opencode"

#: Default command: the ``opencode`` CLI in non-interactive run mode, printing JSON
#: events. The bare ``{prompt}`` token is interpolated with the rendered prompt.
_DEFAULT_COMMAND: tuple[str, ...] = (_CLI, "run", "--format", "json", PROMPT_TOKEN)

#: Default wall-clock bound (seconds) for one agent invocation.
_DEFAULT_TIMEOUT = 600.0


@dataclass
class OpenCodeRun(AgentRun):
    """An :class:`AgentRun` plus what OpenCode's JSON events reported.

    ``output`` holds the summed token and cost totals; ``None`` when stdout held
    no JSON events (a custom command, or a run that failed before its first one).
    Its token totals also fill ``usage``, so release metrics count them.
    """

    output: OpenCodeOutput | None = None


class OpenCodeRunner(HarnessRunner):
    """A :class:`HarnessRunner` that drives the OpenCode CLI in ``scratch_dir``.

    ``command`` is the arg-list template used to spawn the agent; a single
    ``{prompt}`` token (anywhere in the list) is replaced by the rendered prompt.
    When the template contains no token, the prompt is appended as a trailing
    argument so a custom command still receives it. ``timeout`` bounds the run.
    ``model`` (an Eval target's model) is passed as ``--model <model>``, exactly
    as written; ``None`` leaves the CLI on its own default model. ``route`` (an
    Eval target's endpoint) isolates the run and points it at that endpoint, the
    model then sent as ``playbook-target/<model>``; under ``--record`` without
    an endpoint, an ``OpenCodeKeyRoute`` isolates it on an API key. ``None``
    keeps the user's own OpenCode setup.
    """

    name = "opencode"
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
        route: OpenCodeIsolation | None = None,
    ) -> None:
        self.model = model
        self.route = route
        self._command: tuple[str, ...] = tuple(command) if command is not None else _DEFAULT_COMMAND
        self._timeout = timeout

    @classmethod
    def available(cls) -> bool:
        """``True`` when the ``opencode`` executable is on ``PATH``.

        Lets callers skip this opt-in runner cleanly in air-gapped/CI environments
        without importing or invoking the CLI.
        """
        return shutil.which(_CLI) is not None

    def _build_command(self, prompt: str) -> list[str]:
        """The argv for one run: the template with ``prompt`` and the model (``cli_argv``)."""
        model = self.model if self.route is None else self.route.model_ref
        return build_cli_argv(self._command, prompt, model)

    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> OpenCodeRun:
        """Run the configured command with ``cwd=scratch_dir`` and capture output.

        The transcript is the text OpenCode's JSON events carry (raw stdout when
        there are none), then stderr, read apart so it never breaks the JSON
        lines. The process return code is recorded (``0`` = the agent loop
        completed). No shell is used and the working directory is the agent's
        scratch repo, so any edits land in the tree the scoring layers read. The
        child env is marked unattended, so lifecycle-hook asks degrade to deny, and
        runs on the scratch ``.venv`` (``agent_env``) when the sample has one; on
        an endpoint it is isolated too, and the token is redacted from the transcript.
        """
        with routed_opencode_env(self.route, agent_env(scratch_dir)) as env:
            # In a process group of its own: the CLI's workers and MCP servers die with it.
            completed = bounded_subprocess.run_bounded(
                self._build_command(prompt), cwd=scratch_dir, env=env, timeout_s=self._timeout
            )
        output = parse_opencode_output(completed.stdout)
        transcript = completed.stdout if output is None else output.text
        transcript = with_stderr(transcript, completed.stderr)
        return OpenCodeRun(
            transcript=self._redact(transcript),
            returncode=completed.returncode,
            usage=_usage(output),
            output=output,
        )

    def _redact(self, text: str) -> str:
        """``text`` with the endpoint token and header values removed; unchanged without a route."""
        return text if self.route is None else self.route.redact(text)


def _usage(output: OpenCodeOutput | None) -> TokenUsage | None:
    """The token counts of ``output`` for release metrics; ``None`` without JSON events.

    OpenCode's own ``cost_usd`` is not carried: cost comes only from a target's
    declared price (``token_usage``).

    Example::

        >>> _usage(OpenCodeOutput("hi", 10, 2, 0.0, 1))
        TokenUsage(input_tokens=10, output_tokens=2)
    """
    if output is None:
        return None
    return TokenUsage(output.input_tokens, output.output_tokens)
