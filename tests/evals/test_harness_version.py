"""The harness CLI version probe (``evals.run.harness_version``, ticket 07); no real CLI runs."""

from __future__ import annotations

import subprocess
from typing import Any

from coding_agent_playbook.evals.run.harness_version import harness_cli_version


class FakeVersionCli:
    """Answers ``<cli> --version`` with canned output and records the argv."""

    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.argvs: list[list[str]] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.argvs.append(list(args))
        assert kwargs["timeout"] > 0
        return subprocess.CompletedProcess(args, self._returncode, self._stdout, "")


def test_version_is_the_first_version_number_printed() -> None:
    cli = FakeVersionCli("2.1.292 (Claude Code)\n")
    assert harness_cli_version("claude", run=cli) == "2.1.292"
    assert cli.argvs == [["claude", "--version"]]


def test_a_failing_or_versionless_cli_gives_none() -> None:
    assert harness_cli_version("claude", run=FakeVersionCli("2.1.292", returncode=1)) is None
    assert harness_cli_version("opencode", run=FakeVersionCli("no version here")) is None


def test_a_missing_binary_gives_none() -> None:
    def missing(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(args[0])

    assert harness_cli_version("claude", run=missing) is None


def test_a_runner_without_a_cli_has_no_version() -> None:
    assert harness_cli_version(None, run=FakeVersionCli("1.0.0")) is None
