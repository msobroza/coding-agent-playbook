"""The plumbing of ``scripts/release.py``: commands, git/commitizen/forge, and the publish path.

:class:`Tools` runs git, commitizen and ``playbook forge`` through a
:class:`Runner` (the tests pass named fakes). :func:`on_branch` and
:func:`commit_push_open` are the one way every release command (``prepare``,
``freeze``, ``unfreeze``) turns its file changes into a pull request: a fresh
local branch, one commit, a push with a lease and a PR opened or reused.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

#: The commitizen this script runs, and the range the playbook-ci job installs.
COMMITIZEN_REQUIREMENT: Final = "commitizen>=4.13,<5"
REMOTE: Final = "origin"
MAIN_BRANCH: Final = "main"
#: Bounds every shell-out: git, uv, commitizen and the forge CLI all run unattended.
COMMAND_TIMEOUT_SECONDS: Final = 600


class ReleaseError(Exception):
    """A refusal or a failed step; the message says what to do."""


@dataclass(frozen=True)
class Completed:
    """What a finished command returned."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class Runner(Protocol):
    """Runs one command; the tests pass a named fake.

    ``timeout`` (seconds) replaces :data:`COMMAND_TIMEOUT_SECONDS` for a command
    known to run longer: the eval recordings of ``prepare --eval``.
    """

    def __call__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Completed: ...


def run_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> Completed:
    """Run ``argv`` in ``cwd`` with a timeout (default 600 s); a missing program exits 127."""
    limit = COMMAND_TIMEOUT_SECONDS if timeout is None else timeout
    try:
        done = subprocess.run(
            list(argv),
            cwd=cwd,
            env=None if env is None else dict(env),
            capture_output=True,
            text=True,
            check=False,
            timeout=limit,
        )
    except FileNotFoundError:
        return Completed(127, "", f"{argv[0]}: command not found")
    except subprocess.TimeoutExpired:
        return Completed(124, "", f"{argv[0]}: timed out after {limit:g}s")
    return Completed(done.returncode, done.stdout, done.stderr)


@dataclass(frozen=True)
class Tools:
    """git, commitizen and ``playbook forge``, run in ``cwd`` through ``runner``."""

    runner: Runner
    cwd: Path

    def run(self, argv: Sequence[str]) -> Completed:
        return self.runner(argv, cwd=self.cwd)

    def checked(self, argv: Sequence[str]) -> str:
        """Run ``argv``; its stdout, or a :class:`ReleaseError` naming it and its stderr."""
        done = self.run(argv)
        if done.returncode != 0:
            detail = (done.stderr or done.stdout).strip()
            raise ReleaseError(f"`{' '.join(argv)}` exited {done.returncode}: {detail}")
        return done.stdout

    def git(self, *args: str) -> str:
        return self.checked(["git", *args])

    def cz(self, *args: str) -> Completed:
        return self.run(["uv", "tool", "run", "--from", COMMITIZEN_REQUIREMENT, "cz", *args])

    def forge(self, *args: str) -> str:
        cli = [sys.executable, "-m", "coding_agent_playbook.cli", "forge", "-C", str(self.cwd)]
        return self.checked([*cli, *args])


def on_branch(tools: Tools, base: str, branch: str, publish: Callable[[], str]) -> str:
    """Run ``publish`` on a fresh local ``branch``; back at ``base`` and no branch afterwards."""
    tools.git("switch", "--force-create", branch)
    try:
        return publish()
    finally:
        tools.run(["git", "switch", "--detach", "--discard-changes", base])
        tools.run(["git", "branch", "--delete", "--force", branch])


def commit_push_open(
    tools: Tools, branch: str, title: str, paths: Sequence[str], body_file: Path
) -> str:
    """Commit ``paths`` as ``title``, push ``branch`` with a lease, open (or reuse) its PR."""
    tools.git("add", "--all", "--", *paths)
    if not tools.git("diff", "--cached", "--name-only").strip():
        raise ReleaseError(f"nothing to commit for {title!r}: {MAIN_BRANCH} already has it")
    tools.git("commit", "--quiet", "--message", title)
    leftover = tools.git("status", "--porcelain").strip()
    if leftover:
        raise ReleaseError(f"the commit {title!r} left changes behind:\n{leftover}")
    tools.git("push", "--force-with-lease", REMOTE, f"HEAD:refs/heads/{branch}")
    pulls = json.loads(tools.forge("pr", "list", "--state", "open") or "[]")
    url = next((str(p.get("url")) for p in pulls if p.get("head") == branch), None)
    if url is not None:
        return url
    created = tools.forge(
        "pr", "create", "--base", MAIN_BRANCH, "--title", title, "--body-file", str(body_file)
    )
    return created.strip()


def refuse_foreign_engine(checkout: Path, inner: str) -> None:
    """Refuse unless the imported engine is ``checkout``'s own (``<checkout>/src``).

    The scratch checkout's step runs with that ``src`` first on ``PYTHONPATH``,
    but an engine installed elsewhere (a ``.pth`` file, an editable install) can
    still win the import, and then the manifest or the pin digests would come
    from that other engine.

    Example::

        >>> refuse_foreign_engine(Path("/tmp/elsewhere"), "freeze-checkout")  # doctest: +SKIP
        Traceback (most recent call last):
        ReleaseError: freeze-checkout imported the engine from ..., not /tmp/elsewhere
    """
    import coding_agent_playbook

    engine = Path(coding_agent_playbook.__file__).resolve()
    if not engine.is_relative_to((checkout / "src").resolve()):
        raise ReleaseError(f"{inner} imported the engine from {engine}, not {checkout}")
