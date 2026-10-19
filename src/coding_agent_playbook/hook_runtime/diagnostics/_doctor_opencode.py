"""The OpenCode checks of ``playbook-hook doctor`` (specs/prK-lifecycle-hooks.md §D.9, §C.3.7, QC-14).

OpenCode turns the playbook's hooks off without a word in three ways that
doctor can see from outside:

- **An OpenCode older than 1.18.29.** It cannot load the shim's ``{id,
  server}`` default export and only logs that (``Effect.logError``). When
  ``opencode`` is on PATH, ``opencode --version`` runs through
  ``deps.proc`` with a timeout. A version it cannot read is a warning, not a
  verdict.
- **``OPENCODE_DISABLE_PROJECT_CONFIG``.** It drops every project plugin and
  is reported when doctor's own environment sets it. Its CLI twin ``--pure``
  is a flag of a single OpenCode run that no environment shows, so it is
  only named in the shim's report.
- **A shim that differs from what sync rendered.** Its bytes are hashed
  against their lockfile entry first. A mismatch is reported without being
  read. Only a matching shim's ``REG`` line is parsed, as JSON, never run,
  to list the registrations.

A finding is ``degraded`` only when this worktree has a shim. Without one,
OpenCode runs no playbook hooks here, so the same finding is a ``warning``.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.config.lock_digest import expected_digest
from coding_agent_playbook.hook_runtime.config.schema import LOCKFILE_REL
from coding_agent_playbook.hook_runtime.diagnostics._doctor_checks import Check, read_regular_file
from coding_agent_playbook.hook_runtime.harness.opencode import OPENCODE_SHIM_REL
from coding_agent_playbook.hook_runtime.proc import ProcTimeout

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.diagnostics._doctor_checks import Severity
    from coding_agent_playbook.hook_runtime.dispatch.event import RepoInfo

__all__ = [
    "DISABLE_PROJECT_CONFIG",
    "OPENCODE_MIN_VERSION",
    "REG_LINE_PREFIX",
    "VERSION_PROBE_TIMEOUT_S",
    "check_opencode",
    "opencode_checks",
    "parse_opencode_version",
    "project_config_check",
    "read_shim_reg",
    "shim_check",
]

#: The first V1 documenting the ``{id, server}`` default-object export (QC-14).
OPENCODE_MIN_VERSION: Final = (1, 18, 29)
#: ``opencode --version`` is a Bun binary's cold start: seconds, never minutes.
VERSION_PROBE_TIMEOUT_S: Final = 10.0
DISABLE_PROJECT_CONFIG: Final = "OPENCODE_DISABLE_PROJECT_CONFIG"
#: The shim's one ``REG`` line: this prefix, then compact JSON (``opencode_reg_json``).
REG_LINE_PREFIX: Final = "const REG = "
_FLOOR: Final = ".".join(str(part) for part in OPENCODE_MIN_VERSION)
_VERSION: Final = re.compile(rb"(\d+)\.(\d+)\.(\d+)")
#: How OpenCode itself reads a boolean flag variable (``truthy()`` in its flag module).
_TRUTHY: Final = frozenset({"1", "true"})
_VERSION_CHECK: Final = "opencode"
_CONFIG_CHECK: Final = "opencode-config"
_SHIM_CHECK: Final = "opencode-shim"


def opencode_checks(repo: RepoInfo, deps: RuntimeDeps) -> list[Check]:
    """The OpenCode findings for ``repo``'s worktree: version, environment, shim (each if any).

    Example::

        >>> [c.name for c in opencode_checks(repo, deps)]  # doctest: +SKIP
        ['opencode', 'opencode-shim']
    """
    shim = shim_check(Path(repo.worktree_root))
    in_use = shim is not None
    found = (
        check_opencode(deps, in_use=in_use),
        project_config_check(deps.env, in_use=in_use),
        shim,
    )
    return [check for check in found if check is not None]


def check_opencode(deps: RuntimeDeps, *, in_use: bool = True) -> Check | None:
    """``opencode --version`` against the 1.18.29 floor; ``None`` when OpenCode is not on PATH.

    Example::

        >>> check_opencode(deps).detail  # doctest: +SKIP
        'OpenCode 1.19.0 (>= 1.18.29)'
    """
    program = deps.proc.which("opencode", path=deps.env.get("PATH"))
    if program is None:
        return None
    version = _probe_version(program, deps)
    if isinstance(version, str):
        return Check(_VERSION_CHECK, "warning", f"{version}; OpenCode hooks need >= {_FLOOR}")
    shown = ".".join(str(part) for part in version)
    if version < OPENCODE_MIN_VERSION:
        detail = (
            f"OpenCode {shown} is below {_FLOOR}: it fails to load the playbook plugin, "
            "silently; upgrade OpenCode"
        )
        return Check(_VERSION_CHECK, _severity(in_use), detail)
    return Check(_VERSION_CHECK, "ok", f"OpenCode {shown} (>= {_FLOOR})")


def _probe_version(program: str, deps: RuntimeDeps) -> tuple[int, int, int] | str:
    """The version ``program --version`` prints, or why it could not be read."""
    try:
        result = deps.proc.run(
            [program, "--version"], timeout=VERSION_PROBE_TIMEOUT_S, env=dict(deps.env)
        )
    except ProcTimeout:
        return f"'opencode --version' timed out after {VERSION_PROBE_TIMEOUT_S:g} s"
    except OSError as exc:  # the program vanished between which() and run()
        return f"cannot run opencode: {type(exc).__name__}"
    version = parse_opencode_version(result.stdout) if result.ok else None
    return "cannot read a version from 'opencode --version'" if version is None else version


def parse_opencode_version(output: bytes) -> tuple[int, int, int] | None:
    """The first ``X.Y.Z`` in ``output`` (a ``v`` or ``opencode`` prefix is fine), else ``None``.

    Example::

        >>> parse_opencode_version(b"opencode 1.19.0\\n")
        (1, 19, 0)
    """
    match = _VERSION.search(output)
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def project_config_check(env: Mapping[str, str], *, in_use: bool = True) -> Check | None:
    """Report ``OPENCODE_DISABLE_PROJECT_CONFIG`` when OpenCode would honor it; else ``None``.

    Example::

        >>> project_config_check({"OPENCODE_DISABLE_PROJECT_CONFIG": "1"}).severity
        'degraded'
    """
    value = env.get(DISABLE_PROJECT_CONFIG)
    if value is None or value.lower() not in _TRUTHY:
        return None
    detail = (
        f"{DISABLE_PROJECT_CONFIG}={value} is set: OpenCode skips project plugins, "
        "so the playbook shim never loads"
    )
    return Check(_CONFIG_CHECK, _severity(in_use), detail)


def shim_check(worktree_root: Path) -> Check | None:
    """The shim against its lockfile entry, then its registrations; ``None`` if neither exists.

    A shim whose sha256 differs from the entry is reported without being read.

    Example::

        >>> shim_check(Path(".")).severity  # doctest: +SKIP
        'ok'
    """
    expected = expected_digest(worktree_root / LOCKFILE_REL, OPENCODE_SHIM_REL, None)
    data = read_regular_file(worktree_root / OPENCODE_SHIM_REL)
    if data is None:
        if expected is None:
            return None
        detail = f"{OPENCODE_SHIM_REL} is missing or not a regular file: OpenCode runs no hooks"
        return Check(_SHIM_CHECK, "broken", f"{detail}; run playbook sync")
    if expected is None:
        detail = f"no lockfile entry vouches for {OPENCODE_SHIM_REL}, so it is not read"
        return Check(_SHIM_CHECK, "degraded", f"{detail}; run playbook sync")
    if hashlib.sha256(data).hexdigest() != expected:
        detail = f"{OPENCODE_SHIM_REL} differs from its lockfile entry (hand-edited?); not read"
        return Check(_SHIM_CHECK, "broken", f"{detail}; run playbook sync")
    return _registrations(read_shim_reg(data.decode("utf-8", "replace")))


def read_shim_reg(text: str) -> dict[str, object] | None:
    """The shim's embedded ``REG`` object, parsed as JSON from its ``const REG =`` line.

    ``None`` when no line starts with the prefix or its value is not a JSON object.

    Example::

        >>> read_shim_reg('const REG = {"stop":{"timeout_ms":5000}}\\n')
        {'stop': {'timeout_ms': 5000}}
    """
    line = next((ln for ln in text.splitlines() if ln.startswith(REG_LINE_PREFIX)), None)
    if line is None:
        return None
    try:
        reg = json.loads(line.removeprefix(REG_LINE_PREFIX))
    except ValueError:
        return None
    return reg if isinstance(reg, dict) else None


def _registrations(reg: dict[str, object] | None) -> Check:
    if reg is None:
        detail = f"{OPENCODE_SHIM_REL} has no readable REG line; run playbook sync"
        return Check(_SHIM_CHECK, "broken", detail)
    listing = "; ".join(_describe(event, entry) for event, entry in sorted(reg.items()))
    detail = f"{len(reg)} OpenCode registration(s): {listing} ('opencode --pure' skips them)"
    return Check(_SHIM_CHECK, "ok", detail)


def _describe(event: str, entry: object) -> str:
    """``pre_tool_use (7000 ms: bash, edit)``; ``every tool`` for ``"*"``."""
    fields = entry if isinstance(entry, dict) else {}
    head = f"{fields.get('timeout_ms', '?')} ms"
    tools = fields.get("tools")
    if tools is None:
        return f"{event} ({head})"
    shown = ", ".join(str(t) for t in tools) if isinstance(tools, list) else "every tool"
    return f"{event} ({head}: {shown})"


def _severity(in_use: bool) -> Severity:
    """A gap in OpenCode only degrades a worktree whose hooks OpenCode is meant to run."""
    return "degraded" if in_use else "warning"
