"""The version of the harness CLI a runner drives, for the release metrics target block (ticket 07).

Both shipped CLIs print their version first on ``--version`` (``claude --version``
prints ``2.1.292 (Claude Code)``). A harness version change is noted when two
release metrics files are compared, so the probe is bounded and never fails the
run: a missing binary, a timeout or output without a version gives ``None``.
"""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.run.agent_env import unattended_agent_env

if TYPE_CHECKING:
    from collections.abc import Callable

    type RunCommand = Callable[..., subprocess.CompletedProcess[str]]

#: Wall-clock bound (seconds) of one ``--version`` call.
_VERSION_TIMEOUT: Final = 30.0
#: The first dotted version number in the output, with any pre-release suffix.
_VERSION: Final = re.compile(r"\d+(?:\.\d+)+(?:[-+.][0-9A-Za-z.]+)?")


def harness_cli_version(cli: str | None, run: RunCommand | None = None) -> str | None:
    """The version ``<cli> --version`` prints, or ``None`` (no CLI, or no version found).

    ``run`` defaults to :func:`subprocess.run`, looked up at call time; a test may pass a fake.

    Example::

        >>> harness_cli_version(None) is None
        True
    """
    if cli is None:
        return None
    run_command = run if run is not None else subprocess.run
    try:
        completed = run_command(
            [cli, "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT,
            check=False,
            env=unattended_agent_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    match = _VERSION.search(completed.stdout)
    return match.group(0) if match else None
