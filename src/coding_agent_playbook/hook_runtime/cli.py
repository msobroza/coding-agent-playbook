"""``playbook-hook``: one ``main`` for harnesses and humans (specs/prK-lifecycle-hooks.md §D.1).

Harnesses run ``<pin> -I -m coding_agent_playbook.hook_runtime dispatch <event>
--harness H [--project-dir DIR]`` (the one argv of D-14, plus a trailing
``--async`` on the one async ``post_tool_use`` registration, OQ-19); humans run the
``playbook-hook`` console script for ``simulate``, ``doctor`` and
``--version``. Both reach :func:`main`.

``dispatch`` is hand-parsed (no ``argparse`` on the hot path) and **never
exits 2**: an unknown flag, a missing argument or trailing junk becomes a
``ContractFault`` for the failure policy, so a usage error or a version-skewed
engine can never pass for a deny. It exits ``0`` or ``DENY_EXIT``. At the
process entry only, fd 1 is moved to fd 2, so stray prints from handlers,
overlay code or child processes land on stderr and the one JSON object on the
real stdout stays parseable. ``simulate`` and ``doctor`` are cold paths that
import ``argparse`` lazily and may exit 2 on usage errors.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.event import EventName, Harness

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from typing import BinaryIO, TextIO

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps

__all__ = ["ASYNC_FLAG", "USAGE", "DispatchArgs", "async_problem", "main", "parse_dispatch_argv"]

USAGE: Final = (
    "usage: playbook-hook dispatch <event> --harness claude_code|opencode [--project-dir DIR]"
    " [--async]\n"
    "       playbook-hook simulate <event> [options] < payload.json\n"
    "       playbook-hook doctor [options]\n"
    "       playbook-hook --version"
)
_FLAGS: Final = ("--harness", "--project-dir")
#: The one boolean flag: the async ``post_tool_use`` dispatch (OQ-19), valid on no other event.
ASYNC_FLAG: Final = "--async"
#: Exit code of a human usage error (``simulate``, ``doctor``, no subcommand); never ``dispatch``.
USAGE_EXIT: Final = 2


@dataclass(frozen=True, slots=True)
class DispatchArgs:
    """The parsed ``dispatch`` argv; ``problem`` set means a ``ContractFault``.

    ``event`` is ``None`` when it is missing or unknown (nothing can be
    rendered for it); ``harness`` is ``None`` when missing or unknown.

    Example::

        >>> parse_dispatch_argv(["stop", "--harness", "claude_code"]).problem is None
        True
    """

    event: EventName | None
    harness: Harness | None
    project_dir: str | None
    problem: str | None = None
    asynchronous: bool = False

    def project_root(self, env: Mapping[str, str], cwd: str) -> str:
        """``--project-dir``, else ``CLAUDE_PROJECT_DIR``, else the cwd (§D.1)."""
        return self.project_dir or env.get("CLAUDE_PROJECT_DIR") or cwd


def parse_dispatch_argv(args: Sequence[str]) -> DispatchArgs:
    """Parse ``<event> --harness H [--project-dir DIR] [--async]``; never raises.

    ``--async`` on any event but ``post_tool_use`` is a problem, so the event
    goes to the failure policy like any other bad argv.

    Example::

        >>> parse_dispatch_argv(["pre_tool_use", "--harness", "opencode", "--x"]).problem
        "unexpected argument '--x'"
    """
    if not args or args[0].startswith("-"):
        return DispatchArgs(None, None, None, "missing event")
    try:
        event = EventName(args[0])
    except ValueError:
        return DispatchArgs(None, None, None, f"unknown event {args[0]!r}")
    rest = list(args[1:])
    asynchronous = ASYNC_FLAG in rest
    values, problems = _flags([arg for arg in rest if arg != ASYNC_FLAG])
    if rest.count(ASYNC_FLAG) > 1:
        problems.append(f"{ASYNC_FLAG} given twice")
    wrong_event = async_problem(event) if asynchronous else None
    if wrong_event is not None:
        problems.append(wrong_event)
        asynchronous = False
    harness = None
    if "--harness" not in values:
        problems.append("missing --harness")
    else:
        try:
            harness = Harness(values["--harness"])
        except ValueError:
            problems.append(f"unknown harness {values['--harness']!r}")
    problem = "; ".join(problems) or None
    return DispatchArgs(
        event, harness, values.get("--project-dir"), problem, asynchronous and problem is None
    )


def async_problem(event: EventName) -> str | None:
    """Why ``--async`` cannot apply to ``event``, or ``None`` on ``post_tool_use`` (OQ-19).

    Example::

        >>> async_problem(EventName.STOP)
        "--async is valid only for post_tool_use, got 'stop'"
    """
    if event is EventName.POST_TOOL_USE:
        return None
    return f"{ASYNC_FLAG} is valid only for post_tool_use, got {event.value!r}"


def _flags(rest: list[str]) -> tuple[dict[str, str], list[str]]:
    """The two known flags' values, and every problem with the rest."""
    values: dict[str, str] = {}
    problems: list[str] = []
    while rest:
        flag = rest.pop(0)
        if flag not in _FLAGS:
            problems.append(f"unexpected argument {flag!r}")
        elif not rest:
            problems.append(f"{flag} needs a value")
        elif flag in values:
            problems.append(f"{flag} given twice")
            rest.pop(0)
        else:
            values[flag] = rest.pop(0)
    return values, problems


def main(
    argv: Sequence[str] | None = None,
    *,
    deps: RuntimeDeps | None = None,
    stdin: BinaryIO | None = None,
) -> int:
    """Run one ``playbook-hook`` subcommand and return the process exit code.

    With ``deps`` (tests, in-process callers) streams come from ``deps`` and
    no file descriptor is touched; without, ``dispatch`` does the fd-1 move.

    Example::

        >>> main(["--version"])  # doctest: +SKIP
        0
    """
    args = list(sys.argv[1:] if argv is None else argv)
    command, rest = (args[0], args[1:]) if args else ("", [])
    if command == "dispatch":
        return _dispatch(rest, deps, stdin)
    if command == "--version":
        from coding_agent_playbook import __version__

        print(f"playbook-hook {__version__}")
        return 0
    if command == "simulate":
        from coding_agent_playbook.hook_runtime.diagnostics.simulate import main as simulate_main

        return simulate_main(rest, deps=deps, stdin=stdin)
    if command == "doctor":
        from coding_agent_playbook.hook_runtime.diagnostics.doctor import main as doctor_main

        return doctor_main(rest, deps=deps)
    print(USAGE, file=sys.stderr)
    return 0 if command in ("-h", "--help") else USAGE_EXIT


def _dispatch(args: Sequence[str], deps: RuntimeDeps | None, stdin: BinaryIO | None) -> int:
    parsed = parse_dispatch_argv(args)
    if parsed.event is None:
        return 0  # no event to render for: inert, never an exit 2
    if deps is not None:
        return _run(parsed, parsed.event, deps, stdin or sys.stdin.buffer)
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps

    with _real_stdout() as out:
        return _run(parsed, parsed.event, RuntimeDeps.default(out=out), sys.stdin.buffer)


def _run(parsed: DispatchArgs, event: EventName, deps: RuntimeDeps, stdin: BinaryIO) -> int:
    from coding_agent_playbook.hook_runtime.dispatch import run_event

    wire = run_event(
        event,
        parsed.harness or Harness.CLAUDE_CODE,
        stdin,
        deps,
        project_dir=parsed.project_dir,
        argv_problem=parsed.problem,
        asynchronous=parsed.asynchronous,
    )
    return wire.exit_code


@contextmanager
def _real_stdout() -> Iterator[TextIO]:  # pragma: no cover - exercised by subprocess tests
    """Point fd 1 at stderr for the rest of the process; yield the real stdout.

    Only the one rendered output goes to the real stdout; a ``print`` from a
    handler or a child process inheriting fd 1 goes to stderr instead.
    """
    sys.stdout.flush()
    real = os.dup(1)
    os.dup2(2, 1)
    out = os.fdopen(real, "w", encoding="utf-8")
    try:
        yield out
    finally:
        out.close()
