"""``python -m coding_agent_playbook.cli`` keeps working: the hook runtime and ``playbook ci`` spawn it."""

from __future__ import annotations

import subprocess
import sys

from tests.import_probe import PROBE_TIMEOUT_S, probe_env


def test_python_dash_m_cli_prints_help() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-m", "coding_agent_playbook.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_S,
        env=probe_env(),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage: " in result.stdout
