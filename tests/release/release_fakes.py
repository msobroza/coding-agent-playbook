"""Named fakes for ``scripts/release.py``: git, commitizen and ``playbook forge`` in one host.

:class:`FakeTagHost` is the same idea for ``release.py tag`` (git and ``gh``), and
:class:`FakeForgeOverRealGit` runs the real git with only the forge faked.
:class:`FakeReleaseHost` answers the commands the script runs from a small state
(tags, open pull requests, commitizen's answers, the log) and records each one,
so the tests assert on what the script ran and wrote, and never start a process.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from release import Completed, run_process

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
    command word (``"push"``, ``"commit"``, ``"pr create"``) that exits 1;
    ``staged`` is what ``git diff --cached --name-only`` prints. Any
    ``<command>-checkout`` re-run is the inner step: it prints ``inner out``.
    """

    tags: list[str] = field(default_factory=list)
    open_pulls: list[dict[str, object]] = field(default_factory=list)
    cz_next: dict[tuple[str, ...], tuple[int, str]] = field(default_factory=dict)
    log: list[tuple[str, str]] = field(default_factory=list)
    head: str = BASE
    fail_on: str | None = None
    status: str = ""
    staged: str = "pyproject.toml\n"
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
        if any(word.endswith("-checkout") for word in command):
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
            "diff": lambda _: Completed(0, self.staged),
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


@dataclass(frozen=True)
class FakeCommit:
    """One first-parent commit of ``main`` in :class:`FakeTagHost`: its sha, version and manifest."""

    sha: str
    version: str
    manifest: str | None = None


@dataclass
class FakeTagHost:
    """git and ``gh`` for ``release.py tag``: a first-parent history, tags and CI jobs.

    ``history`` is newest first and every commit touches ``pyproject.toml``;
    ``parents`` overrides a commit's first parent (else the next commit in
    ``history``). ``remote_tags`` and ``local_tags`` map a tag to its commit;
    ``lightweight`` names local tags that are not annotated. ``jobs`` is the
    ``gh run view --json jobs`` text of the release commit's CI run.
    """

    history: list[FakeCommit]
    parents: dict[str, str] = field(default_factory=dict)
    remote_tags: dict[str, str] = field(default_factory=dict)
    local_tags: dict[str, str] = field(default_factory=dict)
    lightweight: set[str] = field(default_factory=set)
    jobs: str = '{"jobs": []}'
    fail_on: str | None = None
    commands: list[list[str]] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
    ) -> Completed:
        command = list(argv)
        self.commands.append(command)
        if self.fail_on is not None and f" {self.fail_on}" in f" {' '.join(command)}":
            return Completed(1, "", f"{self.fail_on} failed")
        if command[0] == "gh":
            return self._gh(command[1:])
        handlers: dict[str, Callable[[list[str]], Completed]] = {
            "rev-parse": self._rev_parse,
            "show": self._show,
            "log": lambda _: Completed(0, "".join(f"{c.sha}\n" for c in self.history)),
            "ls-remote": self._ls_remote,
            "cat-file": self._cat_file,
            "tag": self._tag,
            "push": self._push,
        }
        handler = handlers.get(command[1])
        return handler(command[2:]) if handler else Completed(0)

    def ran(self, *words: str) -> bool:
        """Whether some command held ``words`` in this order, contiguously."""
        needle = list(words)
        return any(
            command[i : i + len(needle)] == needle
            for command in self.commands
            for i in range(len(command))
        )

    def _commit(self, sha: str) -> FakeCommit | None:
        return next((c for c in self.history if c.sha == sha), None)

    def _rev_parse(self, args: list[str]) -> Completed:
        ref = args[-1].removesuffix("^{commit}")
        if ref.startswith("refs/tags/"):
            target = self.local_tags.get(ref.removeprefix("refs/tags/"))
            return Completed(0, f"{target}\n") if target else Completed(1)
        if ref.endswith("^1"):
            return self._parent(ref.removesuffix("^1"))
        return Completed(0, f"{self.history[0].sha}\n")

    def _parent(self, sha: str) -> Completed:
        if sha in self.parents:
            return Completed(0, f"{self.parents[sha]}\n")
        shas = [c.sha for c in self.history]
        index = shas.index(sha) + 1
        return Completed(0, f"{shas[index]}\n") if index < len(shas) else Completed(128)

    def _show(self, args: list[str]) -> Completed:
        sha, _, path = args[-1].partition(":")
        commit = self._commit(sha)
        if commit is None:
            return Completed(128, "", f"bad revision {sha}")
        if path == "pyproject.toml":
            return Completed(0, f'[project]\nname = "x"\nversion = "{commit.version}"\n')
        if commit.manifest is not None and path.endswith("/manifest.toml"):
            return Completed(0, commit.manifest)
        return Completed(128, "", f"path {path} does not exist in {sha}")

    def _ls_remote(self, args: list[str]) -> Completed:
        """Like real git: only the refs a pattern names exactly, the peeled one only if asked."""
        patterns = {arg for arg in args if arg.startswith("refs/")}
        lines = []
        for tag, target in self.remote_tags.items():
            ref = f"refs/tags/{tag}"
            if ref in patterns:
                lines.append(f"{'7a9' * 13}\t{ref}\n")  # the annotated tag object
            if f"{ref}^{{}}" in patterns:
                lines.append(f"{target}\t{ref}^{{}}\n")
        return Completed(0, "".join(lines))

    def _cat_file(self, args: list[str]) -> Completed:
        tag = args[-1].removeprefix("refs/tags/")
        return Completed(0, "commit\n" if tag in self.lightweight else "tag\n")

    def _tag(self, args: list[str]) -> Completed:
        self.local_tags[args[-2]] = args[-1]
        return Completed(0)

    def _push(self, args: list[str]) -> Completed:
        tag = args[-1].partition(":")[0].removeprefix("refs/tags/")
        self.remote_tags[tag] = self.local_tags[tag]
        return Completed(0)

    def _gh(self, args: list[str]) -> Completed:
        if args[:2] == ["run", "list"]:
            return Completed(0, "4242\n")  # `--jq .[].databaseId`
        return Completed(0, self.jobs)


@dataclass
class FakeForgeOverRealGit:
    """The real git (and every other command) with only ``playbook forge pr`` faked.

    ``open_pulls`` is what ``pr list`` prints; ``pr create`` prints ``PR_URL``.
    """

    open_pulls: list[dict[str, object]] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None = None
    ) -> Completed:
        command = list(argv)
        self.commands.append(command)
        if "forge" in command:
            listing = "list" in command
            return Completed(0, json.dumps(self.open_pulls) if listing else f"{PR_URL}\n")
        return run_process(command, cwd=cwd, env=env)

    def created(self) -> list[list[str]]:
        """Every ``forge pr create`` command run."""
        return [c for c in self.commands if "forge" in c and "create" in c]
