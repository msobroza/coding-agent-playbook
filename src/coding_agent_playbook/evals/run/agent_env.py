"""The child env the real eval runners spawn an agent with (specs/prK-lifecycle-hooks.md P-D2).

An eval run has nobody to answer a lifecycle hook's ``ask`` prompt. The runners
therefore mark the agent's env unattended, and the hook runtime degrades ``ask``
to ``deny`` deterministically instead of prompting or hanging until the run's
timeout. The agent also runs on the sample's own environment: the scratch
``.venv`` that ``materialize``'s ``uv sync`` creates. Both real runners share
this one helper so they cannot drift apart.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: Shared name with the hook runtime (§D.3.6). The runtime may not import
#: ``evals``, so it re-declares the name; K2 adds a cross-module equality test.
UNATTENDED_ENV_VAR = "PLAYBOOK_HOOK_UNATTENDED"
#: Where ``uv sync`` (run by ``materialize``) puts the sample's environment in the scratch repo.
SCRATCH_VENV_DIR = ".venv"


def unattended_agent_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of ``base`` (default: ``os.environ``) with the unattended flag forced to ``"1"``.

    The parent env is kept whole (``PATH``, credentials, proxies) because the
    agent CLI needs it; only the flag is added or overridden.

    Example::

        >>> unattended_agent_env({"PATH": "/usr/bin"})
        {'PATH': '/usr/bin', 'PLAYBOOK_HOOK_UNATTENDED': '1'}
    """
    source = os.environ if base is None else base
    return {**source, UNATTENDED_ENV_VAR: "1"}


def scratch_venv_env(base: Mapping[str, str], scratch_dir: Path) -> dict[str, str]:
    """A copy of ``base`` activated on ``<scratch_dir>/.venv`` when that venv exists.

    ``materialize`` syncs a sample's ``setup/`` into that venv. Without it on
    ``PATH`` the agent ran ``pytest`` on the system Python and the sample's own
    package did not import (the v0.2.0 generate-tests/edge-cases runs edited the
    sample's pyproject to work around it). Like ``activate``: the venv's ``bin``
    goes first on ``PATH``, ``VIRTUAL_ENV`` names it (over an inherited one) and
    ``PYTHONHOME`` is dropped. With no venv, ``base`` is returned unchanged.

    Example::

        >>> from pathlib import Path
        >>> scratch_venv_env({"PATH": "/usr/bin"}, Path("/no/such/scratch"))
        {'PATH': '/usr/bin'}
    """
    venv = scratch_dir.absolute() / SCRATCH_VENV_DIR
    if not (venv / "bin").is_dir():
        return dict(base)
    env = {name: value for name, value in base.items() if name != "PYTHONHOME"}
    inherited = env.get("PATH")
    bin_dir = str(venv / "bin")
    env["PATH"] = bin_dir if not inherited else f"{bin_dir}{os.pathsep}{inherited}"
    env["VIRTUAL_ENV"] = str(venv)
    return env


def agent_env(scratch_dir: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The env every eval agent process starts from: unattended, on the scratch venv, in the scratch.

    Both real runners pass it to their route helper, which keeps ``PATH``,
    ``VIRTUAL_ENV`` and ``PWD`` when it isolates the run, so plain, routed and
    key-isolated runs all get the sample's environment from this one place.

    ``PWD`` names the scratch tree. Why: OpenCode takes its project directory
    from the inherited ``PWD``, not from the process's working directory, so
    with the caller's ``PWD`` the agent read and edited the checkout that
    launched the eval (the first v0.4.0 release eval wrote a sample's tests
    into the caller's catalog, and graded an untouched scratch tree).

    Example::

        >>> from pathlib import Path
        >>> agent_env(Path("/no/such/scratch"), {"PATH": "/usr/bin"})
        {'PATH': '/usr/bin', 'PLAYBOOK_HOOK_UNATTENDED': '1', 'PWD': '/no/such/scratch'}
    """
    env = scratch_venv_env(unattended_agent_env(base), scratch_dir)
    env["PWD"] = str(scratch_dir.absolute())
    return env
