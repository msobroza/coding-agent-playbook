"""``playbook-hook doctor``: is this worktree's hook runtime healthy? (specs/prK-lifecycle-hooks.md §D.9).

Human-run and read-only (it never syncs). It checks what fails silently in
production, because a harness fails open on every launcher or interpreter
error (§D.4): the ``guard_config.json`` digest against its lock entry, the
interpreter pin (it exists, is executable, runs ``-I`` on Python >= 3.12 and
imports this engine), the state root's mode and owner, the ``machine.json``
tool signatures and the external handlers' trust approvals.

``--repin [PYTHON]`` is the one write: it overwrites the interpreter pin
(default: this interpreter, unresolved) before checking. Exit codes: 0
healthy, 1 degraded, 2 broken (also for usage errors, as argparse does).
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime._doctor_checks import (
    SEVERITY,
    Check,
    environment_checks,
)
from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.paths import find_repo
from coding_agent_playbook.hook_runtime.pin import ensure_interpreter_pin

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence
    from typing import TextIO

__all__ = ["Check", "exit_code", "main", "run_doctor"]


def run_doctor(repo_dir: str, *, deps: RuntimeDeps, repin: str | None = None) -> list[Check]:
    """Every check of the worktree holding ``repo_dir``; ``repin`` rewrites the pin first.

    Example::

        >>> [c.name for c in run_doctor(".", deps=RuntimeDeps())]  # doctest: +SKIP
        ['guard_config', 'pin', 'state', 'machine.json', 'trust']
    """
    repo = find_repo(repo_dir)
    if repo is None:
        return [
            Check("repo", "broken", f"{repo_dir} is not in a git repository; hooks are git-only")
        ]
    checks: list[Check] = []
    if repin is not None:
        checks.append(_repin(repo.git_dir, repin))
    return [*checks, *environment_checks(repo, deps)]


def _repin(git_dir: str, interpreter: str) -> Check:
    result = ensure_interpreter_pin(
        git_dir=git_dir, executable=interpreter or sys.executable, force=True
    )
    if result is None:
        return Check("repin", "broken", "the state root is unusable; the pin was not written")
    return Check("repin", "ok", f"pinned {result.interpreter}")


def exit_code(checks: Sequence[Check]) -> int:
    """0 healthy, 1 degraded, 2 broken: the worst check decides.

    Example::

        >>> exit_code([Check("pin", "ok", ""), Check("state", "degraded", "")])
        1
    """
    return max((SEVERITY[check.severity] for check in checks), default=0)


def main(
    argv: Sequence[str], *, deps: RuntimeDeps | None = None, stdout: TextIO | None = None
) -> int:
    """``playbook-hook doctor [--repo DIR] [--repin [PYTHON]] [--format text|json]``.

    Example::

        >>> main(["--format", "json"])  # doctest: +SKIP
        0
    """
    try:
        ns = _parser().parse_args(list(argv))
    except SystemExit as exc:  # argparse already printed the usage
        return 2 if exc.code else 0
    checks = run_doctor(ns.repo, deps=deps or RuntimeDeps(), repin=ns.repin)
    code = exit_code(checks)
    print(_render(checks, code, ns.format), file=stdout or sys.stdout)
    return code


def _render(checks: Sequence[Check], code: int, fmt: str) -> str:
    status = ("healthy", "degraded", "broken")[code]
    if fmt == "json":
        rows = [{"name": c.name, "severity": c.severity, "detail": c.detail} for c in checks]
        return json.dumps({"status": status, "exit_code": code, "checks": rows}, indent=2)
    lines = [f"{c.severity.upper():<9}{c.name}: {c.detail}" for c in checks]
    return "\n".join([*lines, f"playbook-hook doctor: {status}"])


def _parser() -> argparse.ArgumentParser:
    import argparse  # cold path only: never on dispatch (§D.1)

    parser = argparse.ArgumentParser(
        prog="playbook-hook doctor", description="Check this worktree's hook runtime."
    )
    parser.add_argument("--repo", default=os.curdir, help="repository root (default: the cwd)")
    parser.add_argument(
        "--repin",
        nargs="?",
        const="",
        default=None,
        metavar="PYTHON",
        help="rewrite the interpreter pin (default: this interpreter)",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser
