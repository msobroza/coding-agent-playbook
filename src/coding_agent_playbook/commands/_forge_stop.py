"""How ``playbook forge`` stops early, with the exit code and one-line hint of spec prF §6.2.

:class:`ForgeStop` carries the exit code: ``1`` the call or the forge CLI
failed (read the error), ``2`` a human must fix something (the hint names the
step), ``3`` the forge or its plan lacks the operation (the skill applies its
text fallback). The hint builders name the human step and, with
``DOMINO_PROJECT_ID`` set, the Domino Data Lab way to take it (Q63). Hints
name hosts, never a remote URL (it may carry a token).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import CONFIG_FILENAME

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.forge.dialects import Forge

__all__ = [
    "MINIMUM_VERSIONS",
    "ForgeStop",
    "detached_head",
    "host_mismatch",
    "local_remote",
    "logged_out",
    "missing_cli",
    "not_pushed",
    "old_cli",
    "outside_repo",
    "unknown_forge",
    "unsupported",
]

#: The oldest forge CLI ``playbook forge`` runs, per forge name (Q38).
MINIMUM_VERSIONS: Final = {"github": (2, 94, 0), "gitlab": (1, 115, 0)}
_DOMINO: Final = "DOMINO_PROJECT_ID"
_DOMINO_ENV_STEP: Final = (
    "add {var} under Account Settings → User environment variables and start a new workspace"
)
_DOMINO_IMAGE_STEP: Final = "add {cli} to the compute environment's Dockerfile"
_PREFIX: Final = {1: "error", 2: "error", 3: "unsupported"}


class ForgeStop(Exception):
    """Stop ``playbook forge`` with exit ``code``: ``passthrough``, then ``message``, on stderr.

    ``passthrough`` is a failed forge CLI call's stderr, printed unchanged; an
    empty ``message`` prints no line of its own.

    Example::

        >>> ForgeStop(2, "detached HEAD").stderr
        'error: detached HEAD\n'
    """

    def __init__(self, code: int, message: str, *, passthrough: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.passthrough = passthrough

    @property
    def stderr(self) -> str:
        """What goes to stderr: the passed-through output, then ``error: …`` / ``unsupported: …``."""
        line = f"{_PREFIX.get(self.code, 'error')}: {self.message}\n" if self.message else ""
        return self.passthrough + line


def _on_domino(env: Mapping[str, str]) -> bool:
    return bool(env.get(_DOMINO, "").strip())


def _version(numbers: tuple[int, ...]) -> str:
    return ".".join(str(number) for number in numbers)


def outside_repo(env: Mapping[str, str]) -> ForgeStop:
    """Exit 2: not in a git work tree (§5.1 step 3)."""
    where = (
        "`/mnt/code` in a git-based project, `/repos/<name>` for an attached repository"
        if _on_domino(env)
        else "the repository, or pass `-C <path>`"
    )
    return ForgeStop(2, f"not in a git work tree: run `playbook forge` from {where}")


def detached_head(operation: str) -> ForgeStop:
    """Exit 2: ``operation`` needs a branch and ``HEAD`` is detached (§5.1 step 2)."""
    return ForgeStop(2, f"detached HEAD: run `git checkout -b <name>` before `{operation}`")


def local_remote(remote: str) -> ForgeStop:
    """Exit 2: the push remote is a local path, which no forge serves."""
    return ForgeStop(2, f"the push remote `{remote}` is a local path, not a forge: push to a forge")


def unknown_forge(host: str) -> ForgeStop:
    """Exit 2: no §5.2 rule maps ``host`` to a forge."""
    return ForgeStop(
        2,
        f"unknown forge for host `{host}`; add it to `[forge] hosts` in {CONFIG_FILENAME} "
        '(for example `hosts = { "' + host + '" = "gitlab" }`)',
    )


def missing_cli(forge: Forge, env: Mapping[str, str]) -> ForgeStop:
    """Exit 2: the forge CLI is not on ``PATH``."""
    minimum = _version(MINIMUM_VERSIONS[forge.name])
    step = (
        _DOMINO_IMAGE_STEP.format(cli=f"`{forge.cli}` {minimum} or later")
        if _on_domino(env)
        else f"install `{forge.cli}` {minimum} or later"
    )
    return ForgeStop(2, f"`{forge.cli}` is not installed: {step}")


def old_cli(forge: Forge, found: tuple[int, ...] | None, env: Mapping[str, str]) -> ForgeStop:
    """Exit 2: the forge CLI is older than the minimum, or its version is unreadable."""
    minimum = _version(MINIMUM_VERSIONS[forge.name])
    have = f"is {_version(found)}" if found is not None else "reports no version"
    step = (
        _DOMINO_IMAGE_STEP.format(cli=f"`{forge.cli}` {minimum} or later")
        if _on_domino(env)
        else f"upgrade `{forge.cli}` to {minimum} or later"
    )
    return ForgeStop(2, f"`{forge.cli}` {have}, older than {minimum}: {step}")


def logged_out(forge: Forge, host: str, env: Mapping[str, str]) -> ForgeStop:
    """Exit 2: the forge CLI has no login for ``host``."""
    if _on_domino(env):
        step = _DOMINO_ENV_STEP.format(var=f"`{forge.token_env[0]}`")
    else:
        # gh's other variables are its fallback and its Enterprise Server tokens
        names = forge.token_env[:1] if forge.cli == "gh" else forge.token_env
        tokens = " / ".join(f"`{name}`" for name in names)
        step = f"run `{forge.cli} auth login --hostname {host}` or set {tokens}"
    return ForgeStop(2, f"`{forge.cli}` is not logged in to {host}: {step}")


def host_mismatch(source: str, named: str, api_host: str) -> ForgeStop:
    """Exit 2: ``source`` points ``glab`` at ``named``, not the remote's API host (Q55)."""
    return ForgeStop(
        2,
        f"{source} names {named}, but the push remote's API host is {api_host}: unset it, "
        f"or set `api_host` for this host in `[forge] hosts` in {CONFIG_FILENAME}",
    )


def not_pushed(remote: str, branch: str) -> ForgeStop:
    """Exit 2: ``pr create`` never pushes and ``branch`` is not on ``remote`` (Q43)."""
    return ForgeStop(2, f"push the branch first (`git push -u {remote} {branch}`)")


def unsupported(operation: str, forge: Forge, why: str) -> ForgeStop:
    """Exit 3: the forge or its plan lacks ``operation``; the skill applies its fallback (Q30)."""
    return ForgeStop(3, f"`{operation}` is not available on {forge.name}: {why}")
