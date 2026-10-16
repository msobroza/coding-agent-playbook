"""Running ``node`` from tests, when the machine has it (specs/prK-lifecycle-hooks.md §C.3.7, §C.7).

The OpenCode shim's own behaviour is only observable under a JS runtime, so
the node-driven tests skip cleanly without one; CI's ubuntu runner has node.
``node`` is found by walking ``PATH`` with an explicit executable check, never
through ``shutil.which``: the CLI suite stubs ``which`` globally.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

#: One node run never needs more: every scenario's slowest step is a 200 ms timeout.
NODE_TIMEOUT_S = 30
_SYSTEM_PATH = "/usr/bin:/bin"


def find_node() -> str | None:
    """The first executable ``node`` on ``PATH``, or ``None``.

    Example::

        >>> find_node() is None or find_node().endswith("node")  # doctest: +SKIP
        True
    """
    name = "node.exe" if sys.platform == "win32" else "node"
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory or ".") / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


NODE = find_node()
needs_node = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


def run_node(
    args: list[str], *, stdin: str = "", cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``node <args>`` with a minimal env and a bounded wait; the caller asserts the code.

    The env carries only a system ``PATH`` and ``HOME``, so a spawned fake
    dispatcher sees the same tools on every machine.

    Example::

        run_node(["--check", str(module)])
    """
    assert NODE is not None, "guard the caller with @needs_node"
    return subprocess.run(
        [NODE, *args],
        input=stdin,
        cwd=cwd,
        env={"PATH": _SYSTEM_PATH, "HOME": os.environ.get("HOME", "/")},
        capture_output=True,
        text=True,
        timeout=NODE_TIMEOUT_S,
        check=False,
    )
