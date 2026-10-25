"""``playbook-hook simulate``: run the exact dispatch pipeline on one payload (specs/prK-lifecycle-hooks.md §D.9).

It is ``run_event`` itself, not a model of it, so what it prints is what a
harness would get:

- the environment is the process environment plus ``--env NAME=VALUE``
  overrides, so kill switches can be tried; for ``claude_code`` it sets
  ``CLAUDE_PROJECT_DIR`` to ``--repo`` unless overridden, or the §C.5.2
  foreign check would make every simulation inert;
- state goes to an ephemeral directory unless ``--state DIR`` is given, so
  the real decision log is never touched by default;
- ``--unattended`` forces ask degradation; ``--config PATH`` runs a given
  ``guard_config.json`` without the lockfile digest check;
- ``--async`` is the async ``post_tool_use`` dispatch (OQ-19): only the
  async-routed handlers run and nothing is written; on any other event it is
  a contract fault, exactly as the ``dispatch`` argv would be.

``--format json`` prints ``{exit_code, stdout, stderr, decisions, combined,
latency_ms}``; ``exit_code`` is the **harness-facing** code (a pre_tool_use
deny is 2, though the dispatch process itself exits 10). Any completed
simulation exits 0, whatever it decided; a usage error exits 2.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from coding_agent_playbook.hook_runtime.cli import async_problem
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, parse_guard_config
from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.dispatch.event import EventName, Harness
from coding_agent_playbook.hook_runtime.dispatch.policy import UNATTENDED_ENV_VAR
from coding_agent_playbook.hook_runtime.dispatch.run import dispatch_event
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME, StateStore

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterator, Sequence
    from typing import BinaryIO, TextIO

    from coding_agent_playbook.hook_runtime.dispatch.tail import DispatchTrace

__all__ = ["SimulateArgs", "SimulateReport", "SimulateUsageError", "build_parser", "main", "run"]


class SimulateUsageError(ValueError):
    """A simulate argument the pipeline cannot use (e.g. an unusable ``--config``)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SimulateArgs:
    """One simulation; every field mirrors a ``simulate`` flag.

    Example: ``SimulateArgs(event=EventName.PRE_TOOL_USE, repo="/r", unattended=True)``.
    """

    event: EventName
    harness: Harness = Harness.CLAUDE_CODE
    repo: str = "."
    config: str | None = None
    state: str | None = None
    unattended: bool = False
    env: tuple[tuple[str, str], ...] = ()
    format: Literal["text", "json"] = "text"
    asynchronous: bool = False


@dataclass(frozen=True, slots=True)
class SimulateReport:
    """What a simulation decided, and how long the pipeline took."""

    trace: DispatchTrace
    latency_ms: int

    def to_json(self) -> dict[str, Any]:
        """The ``--format json`` document."""
        wire, combined = self.trace.wire, self.trace.combined
        decisions = [
            {
                "hook_id": done.result.hook_id,
                "rule_id": done.result.rule_id,
                "decision": done.result.decision.value,
                "effective": outcome.effective.value,
                "degraded": done.result.degraded,
                "latency_ms": done.latency_ms,
            }
            for done, outcome in zip(self.trace.ran, combined.outcomes, strict=False)
        ]
        return {
            "exit_code": wire.harness_exit_code,
            "stdout": wire.stdout,
            "stderr": wire.stderr,
            "decisions": decisions,
            "combined": {
                "decision": combined.decision.value,
                "reason": combined.reason,
                "context": list(combined.context),
                "user_notes": list(combined.user_notes),
            },
            "latency_ms": self.latency_ms,
        }

    def to_text(self) -> str:
        """The ``--format text`` lines: the wire output, then one summary line."""
        wire = self.trace.wire
        lines = [f"stdout: {wire.stdout.rstrip()}" if wire.stdout else "stdout: (empty)"]
        if wire.stderr:
            lines.append(f"stderr: {wire.stderr.rstrip()}")
        lines.append(
            f"exit_code={wire.harness_exit_code} decision={self.trace.combined.decision.value} "
            f"latency_ms={self.latency_ms}"
        )
        return "\n".join(lines)


def run(args: SimulateArgs, payload: bytes, *, deps: RuntimeDeps | None = None) -> SimulateReport:
    """Run ``payload`` through the dispatch pipeline under ``args``; raises :class:`SimulateUsageError`.

    ``deps`` supplies the seams (``FakeHandlerResolver`` in tests); its env is
    the base the ``--env`` overrides apply to.

    Example::

        >>> run(SimulateArgs(event=EventName.STOP, repo="."), b"{}").trace.wire.exit_code
        ... # doctest: +SKIP
        0
    """
    base = deps or RuntimeDeps()
    repo = os.path.realpath(args.repo)
    config = _config(args.config, base)
    with _state_root(args.state) as root:
        sim = dataclasses.replace(
            base,
            env=_env(args, base.env, repo),
            state=StateStore(root, clock=base.clock),
            guard_config=config,
            out=None,
            err=None,
        )
        started = base.clock.monotonic()
        project_dir = repo if args.harness is Harness.OPENCODE else None
        problem = async_problem(args.event) if args.asynchronous else None
        trace = dispatch_event(
            args.event,
            args.harness,
            payload,
            sim,
            project_dir=project_dir,
            argv_problem=problem,
            asynchronous=args.asynchronous and problem is None,
        )
        latency = max(0, round((base.clock.monotonic() - started) * 1000))
    return SimulateReport(trace, latency)


def _env(args: SimulateArgs, base: Any, repo: str) -> dict[str, str]:
    env = dict(base)
    overrides = dict(args.env)
    if args.harness is Harness.CLAUDE_CODE and "CLAUDE_PROJECT_DIR" not in overrides:
        env["CLAUDE_PROJECT_DIR"] = repo
    if args.unattended:
        env[UNATTENDED_ENV_VAR] = "1"
    env.update(overrides)
    return env


def _config(path: str | None, deps: RuntimeDeps) -> GuardConfig | None:
    if path is None:
        return None
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise SimulateUsageError(f"--config {path}: {exc.strerror}") from exc
    parsed = parse_guard_config(data, platform=deps.platform, home=deps.home)
    if not isinstance(parsed, GuardConfig):
        raise SimulateUsageError(f"--config {path}: {parsed.detail}")
    return parsed


@contextmanager
def _state_root(state: str | None) -> Iterator[str]:
    """``--state DIR``'s state root, or an ephemeral one removed afterwards."""
    if state is not None:
        yield os.path.join(state, STATE_DIR_NAME)
        return
    with tempfile.TemporaryDirectory(prefix="playbook-hook-simulate-") as temp:
        yield os.path.join(temp, STATE_DIR_NAME)


# --- argparse front ------------------------------------------------------------------------


def main(
    argv: Sequence[str],
    *,
    deps: RuntimeDeps | None = None,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """``playbook-hook simulate ...``: 0 for any completed simulation, 2 on a usage error.

    Example::

        >>> main(["pre_tool_use", "--format", "json"], stdin=open("bash_rm_root.json", "rb"))
        ... # doctest: +SKIP
        0
    """
    out = stdout or sys.stdout
    try:
        args = _parse(argv)
        payload = (stdin or sys.stdin.buffer).read()
        report = run(args, payload, deps=deps)
    except SystemExit as exc:  # argparse's usage error (it already printed the usage)
        return 2 if exc.code else 0
    except SimulateUsageError as exc:
        print(f"playbook-hook simulate: error: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report.to_json(), indent=2) if args.format == "json" else report.to_text()
    print(text, file=out)
    return 0


def _parse(argv: Sequence[str]) -> SimulateArgs:
    parser = build_parser()
    ns = parser.parse_args(list(argv))
    env: list[tuple[str, str]] = []
    for item in ns.env:
        name, sep, value = item.partition("=")
        if not sep or not name:
            parser.error(f"--env expects NAME=VALUE, got {item!r}")
        env.append((name, value))
    return SimulateArgs(
        event=EventName(ns.event),
        harness=Harness(ns.harness),
        repo=ns.repo,
        config=ns.config,
        state=ns.state,
        unattended=ns.unattended,
        env=tuple(env),
        format=ns.format,
        asynchronous=ns.asynchronous,
    )


def build_parser() -> argparse.ArgumentParser:
    """The ``playbook-hook simulate`` parser; the docs site's CLI page renders it too.

    Example::

        >>> build_parser().parse_args(["stop"]).harness
        'claude_code'
    """
    import argparse  # cold path only: never on dispatch (§D.1)

    parser = argparse.ArgumentParser(
        prog="playbook-hook simulate",
        description="Run one hook payload (stdin) through the exact dispatch pipeline.",
    )
    parser.add_argument("event", choices=[e.value for e in EventName])
    parser.add_argument("--harness", choices=[h.value for h in Harness], default="claude_code")
    parser.add_argument("--repo", default=".", help="repository root (default: the cwd)")
    parser.add_argument("--config", help="a guard_config.json to run instead (no digest check)")
    parser.add_argument("--state", help="state dir to use (default: an ephemeral one)")
    parser.add_argument("--unattended", action="store_true", help="force ask degradation")
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--async",
        dest="asynchronous",
        action="store_true",
        help="the async post_tool_use dispatch (async-routed handlers only, no output)",
    )
    return parser
