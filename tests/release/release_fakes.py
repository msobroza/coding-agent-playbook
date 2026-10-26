"""Named fakes for ``scripts/release.py``: git, commitizen and ``playbook forge`` in one host.

:class:`FakeReleaseHost` answers the commands the script runs from a small state
(tags, open pull requests, commitizen's answers, the log) and records each one,
so the tests assert on what the script ran and wrote, and never start a process.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from release import Completed

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

BASE = "ba5e" * 10
PR_URL = "https://forge.example/pulls/77"
_FIELD = "\x1f"
_RECORD = "\x1e"


@dataclass
class FakeReleaseHost:
    """git, ``uv tool run … cz`` and ``python -m coding_agent_playbook.cli forge`` in one fake.

    ``cz_next`` maps the extra ``--get-next`` arguments (``()`` or
    ``("--increment", "MINOR")``) to ``(exit code, stdout)``. ``fail_on`` names a
    command word (``"push"``, ``"commit"``, ``"pr create"``) that exits 1.
    """

    tags: list[str] = field(default_factory=list)
    open_pulls: list[dict[str, object]] = field(default_factory=list)
    cz_next: dict[tuple[str, ...], tuple[int, str]] = field(default_factory=dict)
    log: list[tuple[str, str]] = field(default_factory=list)
    head: str = BASE
    fail_on: str | None = None
    status: str = ""
    inner_exit: int = 0
    commands: list[list[str]] = field(default_factory=list)
    envs: list[Mapping[str, str] | None] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
    ) -> Completed:
        command = list(argv)
        self.commands.append(command)
        self.envs.append(env)
        words = " ".join(command)
        if self.fail_on is not None and f" {self.fail_on}" in f" {words}":
            return Completed(1, "", f"{self.fail_on} failed")
        if "prepare-checkout" in command:
            return Completed(self.inner_exit, "inner out\n", "")
        if "cz" in command:
            return self._cz(command[command.index("cz") + 1 :], cwd)
        if "forge" in command:
            return self._forge(command[command.index("forge") + 3 :])
        return self._git(command[1:])

    def ran(self, *words: str) -> bool:
        """Whether some command held ``words`` in this order, contiguously."""
        needle = list(words)
        return any(
            command[i : i + len(needle)] == needle
            for command in self.commands
            for i in range(len(command))
        )

    def _git(self, args: list[str]) -> Completed:
        handlers: dict[str, Callable[[list[str]], Completed]] = {
            "rev-parse": self._rev_parse,
            "tag": lambda _: Completed(0, "".join(f"{t}\n" for t in self.tags)),
            "log": lambda _: Completed(0, self._log_text()),
            "status": lambda _: Completed(0, self.status),
        }
        handler = handlers.get(args[0])
        return handler(args) if handler else Completed(0)

    def _rev_parse(self, args: list[str]) -> Completed:
        ref = args[-1]
        if ref.startswith("refs/tags/"):
            return Completed(0 if ref.removeprefix("refs/tags/") in self.tags else 1)
        return Completed(0, f"{self.head}\n")

    def _log_text(self) -> str:
        return "".join(f"{subject}{_FIELD}{body}{_RECORD}\n" for subject, body in self.log)

    def _cz(self, args: list[str], cwd: Path) -> Completed:
        if "--get-next" in args:
            extra = tuple(a for a in args if a not in ("bump", "--get-next", "--yes"))
            code, out = self.cz_next.get(extra, (21, ""))
            return Completed(code, out, "[NO_COMMITS_TO_BUMP]" if code == 21 else "")
        version = args[1]
        pyproject = cwd / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        new = re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1)
        pyproject.write_text(new, encoding="utf-8")
        return Completed(0)

    def _forge(self, args: list[str]) -> Completed:
        if args[:2] == ["pr", "list"]:
            return Completed(0, json.dumps(self.open_pulls))
        return Completed(0, f"{PR_URL}\n")
