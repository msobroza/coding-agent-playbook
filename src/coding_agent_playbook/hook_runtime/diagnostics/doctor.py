"""``playbook-hook doctor``: is this worktree's hook runtime healthy? (specs/prK-lifecycle-hooks.md §D.9).

Human-run and read-only (it never syncs). It checks what fails silently in
production, because a harness fails open on every launcher or interpreter
error (§D.4): the ``guard_config.json`` digest against its lock entry, the
interpreter pin (it exists, is executable, runs ``-I`` on Python >= 3.12 and
imports this engine), the state root's mode and owner, the ``machine.json``
tool signatures, the external handlers' trust approvals and, when set, the
``PLAYBOOK_HOOK_WRAPPER_PREFIXES`` declaration. Then OpenCode
(``_doctor_opencode``): the ``opencode --version`` floor (>= 1.18.29),
``OPENCODE_DISABLE_PROJECT_CONFIG`` and the shim's lockfile digest and
registrations. A shim that does not match its lockfile entry is never read.
Last, the guard-decision-log summary (``_doctor_decisions``): per guard, the
deny/ask/override/degraded counts of the last ``--since`` days (default 30),
and the hook calls the dispatcher ignored as foreign or outside git
(``_doctor_ignored``, D79), most recent first; outside git only those.

``--repin [PYTHON]`` is the one write: it overwrites the interpreter pin
(default: this interpreter, unresolved) before checking. Exit codes: 0
healthy, 1 degraded, 2 broken (also for usage errors, as argparse does).
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime.config.pin import ensure_interpreter_pin
from coding_agent_playbook.hook_runtime.diagnostics._doctor_checks import (
    SEVERITY,
    Check,
    environment_checks,
)
from coding_agent_playbook.hook_runtime.diagnostics._doctor_decisions import (
    DEFAULT_SINCE_DAYS,
    decision_log_checks,
)
from coding_agent_playbook.hook_runtime.diagnostics._doctor_ignored import ignored_call_checks
from coding_agent_playbook.hook_runtime.diagnostics._doctor_opencode import opencode_checks
from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
from coding_agent_playbook.hook_runtime.dispatch.paths import find_repo

if TYPE_CHECKING:
    import argparse
    from collections.abc import Sequence
    from typing import TextIO

__all__ = ["Check", "exit_code", "main", "run_doctor"]


def run_doctor(
    repo_dir: str,
    *,
    deps: RuntimeDeps,
    repin: str | None = None,
    since_days: int = DEFAULT_SINCE_DAYS,
) -> list[Check]:
    """Every check of the worktree holding ``repo_dir``; ``repin`` rewrites the pin first.

    The decision-log rows summarize the last ``since_days`` days.

    Example::

        >>> [c.name for c in run_doctor(".", deps=RuntimeDeps())]  # doctest: +SKIP
        ['guard_config', 'pin', 'state', 'machine.json', 'trust', 'opencode', 'opencode-shim']
    """
    repo = find_repo(repo_dir)
    if repo is None:
        return [
            Check("repo", "broken", f"{repo_dir} is not in a git repository; hooks are git-only"),
            *ignored_call_checks(None, deps, since_days=since_days),
        ]
    checks: list[Check] = []
    if repin is not None:
        checks.append(_repin(repo.git_dir, repin))
    return [
        *checks,
        *environment_checks(repo, deps),
        *opencode_checks(repo, deps),
        *decision_log_checks(repo, deps, since_days=since_days),
        *ignored_call_checks(repo, deps, since_days=since_days),
    ]


def _repin(git_dir: str, interpreter: str) -> Check:
    result = ensure_interpreter_pin(
        git_dir=git_dir, executable=interpreter or sys.executable, force=True
    )
    if result is None:
        return Check("repin", "broken", "the state root is unusable; the pin was not written")
    return Check("repin", "ok", f"pinned {result.interpreter}")


def exit_code(checks: Sequence[Check]) -> int:
    """0 healthy, 1 degraded, 2 broken: the worst check decides (a warning is healthy).

    Example::

        >>> exit_code([Check("pin", "ok", ""), Check("state", "degraded", "")])
        1
    """
    return max((SEVERITY[check.severity] for check in checks), default=0)


def main(
    argv: Sequence[str], *, deps: RuntimeDeps | None = None, stdout: TextIO | None = None
) -> int:
    """``playbook-hook doctor [--repo DIR] [--repin [PYTHON]] [--since DAYS] [--format text|json]``.

    Example::

        >>> main(["--format", "json"])  # doctest: +SKIP
        0
    """
    try:
        ns = _parser().parse_args(list(argv))
    except SystemExit as exc:  # argparse already printed the usage
        return 2 if exc.code else 0
    checks = run_doctor(ns.repo, deps=deps or RuntimeDeps(), repin=ns.repin, since_days=ns.since)
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
    parser.add_argument(
        "--since",
        type=int,
        default=DEFAULT_SINCE_DAYS,
        metavar="DAYS",
        help="days of guard-decision-log to summarize (default: 30)",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser
