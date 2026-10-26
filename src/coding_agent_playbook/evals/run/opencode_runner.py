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
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.evals.run.agent_env import unattended_agent_env
from coding_agent_playbook.evals.run.cli_argv import PROMPT_TOKEN, build_cli_argv
from coding_agent_playbook.evals.run.harness_runner import AgentRun, HarnessRunner
from coding_agent_playbook.evals.run.opencode_output import OpenCodeOutput, parse_opencode_output
from coding_agent_playbook.evals.run.opencode_route import routed_opencode_env

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.evals.run.opencode_route import OpenCodeRoute

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
    model then sent as ``playbook-target/<model>``; ``None`` keeps the user's
    own OpenCode setup.
    """

    name = "opencode"
    requires_resolved_prompt = True
    accepts_model = True
    accepts_endpoint = True

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        model: str | None = None,
        route: OpenCodeRoute | None = None,
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
        child env is marked unattended, so lifecycle-hook asks degrade to deny; on
        an endpoint it is isolated too, and the token is redacted from the transcript.
        """
        with routed_opencode_env(self.route, unattended_agent_env()) as env:
            completed = subprocess.run(
                self._build_command(prompt),
                cwd=scratch_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        output = parse_opencode_output(completed.stdout)
        transcript = completed.stdout if output is None else output.text
        if completed.stderr:
            transcript = f"{transcript}{completed.stderr}" if transcript else completed.stderr
        if self.route is not None:
            transcript = self.route.redact(transcript)
        return OpenCodeRun(transcript=transcript, returncode=completed.returncode, output=output)
