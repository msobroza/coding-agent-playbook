#!/usr/bin/env python3
"""Human-in-the-loop reproduction loop.
Copy this file, edit the steps below, and run it.
The agent runs the script; the user follows prompts in their terminal.

Usage:
  python3 hitl_loop_template.py

Two helpers:
  step("<instruction>")          → show instruction, wait for Enter
  capture("VAR", "<question>")   → show question, store the answer under VAR

At the end, captured values are printed as KEY=VALUE for the agent to parse.

`capture` prints its value back to the terminal, where the agent reads it,
so capture observations, and leave signing in to the user as a `step`.
"""

from __future__ import annotations

import re
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

EXIT_NO_TERMINAL = 2
EXIT_INTERRUPTED = 130
_CAPTURE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# capture() stores each answer here, in capture order.
CAPTURED: dict[str, str] = {}


def _out(text: str) -> None:
    """Write ``text`` to stdout and flush; the only writer to stdout."""
    sys.stdout.write(text)
    sys.stdout.flush()


def _read_answer(prompt: str) -> str:
    """Show ``prompt`` on stderr and return the line read, trimmed of blanks.

    The prompt goes to stderr and the leading and trailing blanks go, as with a
    shell ``read -r -p``. ``EOFError`` and ``KeyboardInterrupt`` propagate.
    """
    sys.stderr.write(prompt)
    sys.stderr.flush()
    return input().strip(" \t")


def step(instruction: str) -> None:
    """step("<instruction>") shows the instruction and waits for Enter."""
    _out(f"\n>>> {instruction}\n")
    _read_answer("    [Enter when done] ")


def capture(name: str, question: str) -> str:
    """capture("VAR", "<question>") shows the question and stores the answer under VAR.

    Example: ``capture("ERRORED", "Did it throw an error? (y/n)")`` -> ``"y"``.
    """
    if not _CAPTURE_NAME_RE.fullmatch(name):
        raise ValueError(
            f"capture name {name!r} must be an identifier such as ERROR_MSG "
            "(letters, digits and underscores, not starting with a digit)"
        )
    _out(f"\n>>> {question}\n")
    answer = _read_answer("    > ")
    CAPTURED[name] = answer
    return answer


def _print_captured() -> None:
    """Print every captured value as KEY=VALUE, in capture order."""
    _out("\n--- Captured ---\n")
    for name, value in CAPTURED.items():
        _out(f"{name}={value}\n")


def _no_terminal_message(script: Path) -> str:
    """What to tell the agent when no human can answer at this terminal."""
    return (
        "This HITL loop needs a human at an interactive terminal, and stdin here is not one "
        "(or it was closed).\n"
        "Ask the user to run it in their own terminal, follow the prompts, and paste back the "
        '"--- Captured ---" block:\n'
        f"    python3 {shlex.quote(str(script))}\n"
    )


def run_hitl_loop(steps: Callable[[], None]) -> int:
    """Run ``steps`` with a human at the terminal; return the exit status.

    0 after printing the Captured block; 2 when stdin is not a terminal or an
    answer hits end of file; 130 on Ctrl-C. Example:
    ``raise SystemExit(run_hitl_loop(hitl_steps))``.
    """
    if not sys.stdin.isatty():
        sys.stderr.write(_no_terminal_message(Path(__file__).resolve()))
        sys.stderr.flush()
        return EXIT_NO_TERMINAL
    try:
        steps()
    except EOFError:
        sys.stderr.write(_no_terminal_message(Path(__file__).resolve()))
        sys.stderr.flush()
        return EXIT_NO_TERMINAL
    except KeyboardInterrupt:
        _out("\n")
        return EXIT_INTERRUPTED
    _print_captured()
    return 0


def hitl_steps() -> None:
    """The steps the human takes, in order: one step() or capture() call each."""
    # --- edit below ---------------------------------------------------------

    step("Open the app at its local dev server address and sign in.")

    capture("ERRORED", "Click the 'Export' button. Did it throw an error? (y/n)")

    capture("ERROR_MSG", "Paste the error message (or 'none'):")

    # --- edit above ---------------------------------------------------------


if __name__ == "__main__":
    raise SystemExit(run_hitl_loop(hitl_steps))
