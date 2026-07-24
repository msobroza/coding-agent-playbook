"""System utilities: thin wrappers around shell command execution.

Derived (paraphrased) from CVE-2026-27602 (CrossCommitVuln-Bench, CC BY 4.0,
A. Majumdar). Original fixture code; upstream project source was not consulted.
"""

from __future__ import annotations

import subprocess


def exec_cmd(command: str) -> tuple[int, bytes, bytes]:
    """Run a shell command string and return (returncode, stdout, stderr).

    The whole ``command`` is handed to the shell, so any shell metacharacters in
    it are interpreted rather than treated as literal argument text.
    """
    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate()
    return proc.returncode, stdout, stderr
