"""A fake ``claude`` (and ``opencode``) CLI for the ``playbook eval`` endpoint tests (spec #281).

:class:`FakeClaudeCli` replaces ``subprocess.run`` for those two executables
only: it records each argv and child environment (and what the isolated config
dir held, and the working directory with whether it held a ``CLAUDE.md``), then answers like the real CLI would. ``--version`` prints a version
line; a call that asks for ``--output-format json`` gets one
``{"type": "result", ...}`` object carrying the answer, so the runner's JSON
parse and redaction run; anything else gets the answer as plain text.

Example::

    def test_x(monkeypatch: pytest.MonkeyPatch) -> None:
        cli = FakeClaudeCli(monkeypatch, answer="done")
        ...
        argv, env = cli.calls[0]
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.judge import LLMJudge
from coding_agent_playbook.evals.run.claude_code_output import JSON_OUTPUT_ARGS
from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner
from coding_agent_playbook.evals.run.opencode_runner import OpenCodeRunner

if TYPE_CHECKING:
    import pytest

#: What ``claude --version`` prints.
FAKE_CLAUDE_VERSION = "2.1.300"


class FakeClaudeCli:
    """Stands in for the ``claude`` CLI: records argv, env, the config dir and cwd; answers."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answer: str = "1", rc: int = 0) -> None:
        self.calls: list[tuple[list[str], dict[str, str] | None]] = []
        self.config_dir_entries: list[list[str]] = []
        #: Each call's ``cwd`` (``None`` when the caller passed none), in call order.
        self.cwds: list[Path | None] = []
        #: Whether each call's ``cwd`` held a ``CLAUDE.md`` at call time.
        self.cwd_had_claude_md: list[bool] = []
        self._answer = answer
        self._rc = rc
        self._real_run = subprocess.run
        for cls in (ClaudeCodeRunner, OpenCodeRunner, LLMJudge):
            monkeypatch.setattr(cls, "available", classmethod(lambda _cls: True))
        monkeypatch.setattr(subprocess, "run", self._run)

    def _run(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if not args or args[0] not in ("claude", "opencode"):
            return self._real_run(args, **kwargs)
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(
                args, 0, f"{FAKE_CLAUDE_VERSION} (Claude Code)\n", ""
            )
        env = kwargs.get("env")
        self.calls.append((list(args), dict(env) if env is not None else None))
        self._record_cwd(kwargs.get("cwd"))
        if env is not None and "CLAUDE_CONFIG_DIR" in env:
            self.config_dir_entries.append(
                sorted(p.name for p in Path(env["CLAUDE_CONFIG_DIR"]).iterdir())
            )
        return subprocess.CompletedProcess(args, self._rc, self._stdout(args), "")

    def _record_cwd(self, cwd: str | Path | None) -> None:
        """Keep ``cwd`` and whether it held a ``CLAUDE.md`` when the CLI started."""
        path = None if cwd is None else Path(cwd)
        self.cwds.append(path)
        self.cwd_had_claude_md.append(path is not None and (path / "CLAUDE.md").exists())

    def _stdout(self, args: list[str]) -> str:
        """The answer as a JSON result object when the call asks for JSON, else as is."""
        if not _asks_for_json(args):
            return self._answer
        result: dict[str, object] = {
            "type": "result",
            "subtype": "success" if self._rc == 0 else "error",
            "is_error": self._rc != 0,
            "result": self._answer,
        }
        if "--model" in args:
            model = args[args.index("--model") + 1]
            result["modelUsage"] = {model: {"inputTokens": 10, "outputTokens": 5}}
        return json.dumps(result)


def _asks_for_json(args: list[str]) -> bool:
    """``True`` when ``args`` holds ``--output-format json`` as adjacent words."""
    width = len(JSON_OUTPUT_ARGS)
    return any(tuple(args[i : i + width]) == JSON_OUTPUT_ARGS for i in range(len(args)))
