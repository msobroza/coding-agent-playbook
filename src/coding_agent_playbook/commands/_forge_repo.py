"""Which forge ``playbook forge`` talks to: the push remote, its host, its forge (spec prF §5.1, §5.2).

:func:`locate` reads git config on every call, offline: the work tree, the
current branch, the push remote (``branch.<b>.pushRemote`` → ``remote.pushDefault``
→ ``branch.<b>.remote`` → ``origin``; on a detached ``HEAD`` ``remote.pushDefault``
then ``origin``), and its URL (``pushurl`` before ``url``, read raw; ``git remote
get-url --push``, which applies ``insteadOf``, only when the raw host does not
map). An SSH host is resolved with ``ssh -G`` (aliases), then the host maps to
its forge through :func:`coding_agent_playbook.forge.hosts.forge_for_host`
with the committed ``[forge]`` table. Errors name the host, never the URL.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._forge_stop import (
    ForgeStop,
    local_remote,
    outside_repo,
    unknown_forge,
)
from coding_agent_playbook.config.files import CONFIG_FILENAME, ConfigFiles
from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.config.tables.forge import parse_forge_table
from coding_agent_playbook.forge.hosts import forge_for_host, remote_host

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.forge.dialects import Forge
    from coding_agent_playbook.forge.hosts import ForgeHost

__all__ = ["ForgeRemote", "locate", "repo_path"]

_GIT_TIMEOUT_S: Final = 30
_SSH_TIMEOUT_S: Final = 10
#: The forges' SSH-over-HTTPS-port hosts (``ssh -G`` may name them): the forge CLI talks
#: to the web host instead.
_SSH_PORT_443_HOSTS: Final = {"altssh.gitlab.com": "gitlab.com", "ssh.github.com": "github.com"}
_URL_PATH: Final = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*(/[^?#]*)?")
_SCP_PATH: Final = re.compile(r"^(?:[^@/\[\]]*@)?(?:\[[^\]/]+\]|[^:/@\[\]]+):(.*)$")


@dataclass(frozen=True)
class ForgeRemote:
    """The push remote of the work tree at ``top``, and the forge it is on.

    ``host`` is the remote's host (SSH aliases resolved), ``api_host`` the host
    the forge CLI talks to (the ``[forge]`` entry's ``api_host``, else ``host``),
    ``repo`` the remote's repository path (``acme/app``), ``branch`` the current
    branch (``None`` on a detached ``HEAD``).

    Example: ``ForgeRemote(GITHUB, "github.com", "github.com", "origin", "acme/app", "main", top)``.
    """

    forge: Forge
    host: str
    api_host: str
    remote: str
    repo: str
    branch: str | None
    top: Path

    def pushed_branch(self) -> str | None:
        """The current branch's name on the push remote when the remote has it, else ``None``.

        Offline: the branch's push destination (``%(push)``, which honours
        ``push.default`` and ``branch.<b>.merge``) when it is on this remote,
        else the same name, must exist as a remote-tracking ref.
        """
        if self.branch is None:
            return None
        prefix = f"refs/remotes/{self.remote}/"
        push = _git(self.top, "for-each-ref", "--format=%(push)", f"refs/heads/{self.branch}")
        ref = push if push and push.startswith(prefix) else prefix + self.branch
        if _git(self.top, "rev-parse", "--verify", "--quiet", ref) is None:
            return None
        return ref.removeprefix(prefix)

    def which(self) -> dict[str, str]:
        """What ``playbook forge which`` prints: ``{forge, cli, host, api_host, repo, remote}``."""
        return {
            "forge": self.forge.name,
            "cli": self.forge.cli,
            "host": self.host,
            "api_host": self.api_host,
            "repo": self.repo,
            "remote": self.remote,
        }


def locate(start: Path, env: Mapping[str, str]) -> ForgeRemote:
    """The push remote of the work tree holding ``start`` and its forge, else a :class:`ForgeStop`.

    Exit 2 outside a work tree, for a push remote without a URL or with a local
    path, and for a host no §5.2 rule maps; a malformed ``[forge]`` table or
    committed config also exits 2 (a human fixes the file).

    Example::

        >>> locate(Path("."), os.environ).forge.name  # doctest: +SKIP
        'github'
    """
    top_text = _git(start, "rev-parse", "--show-toplevel") if start.is_dir() else None
    if not top_text:
        raise outside_repo(env)
    top = Path(top_text)
    config = _git_config(top)
    branch = _git(top, "symbolic-ref", "-q", "--short", "HEAD") or None
    remote = _push_remote(config, branch)
    url = _first(config, f"remote.{remote}.pushurl") or _first(config, f"remote.{remote}.url")
    if not url:
        raise ForgeStop(2, f"no remote `{remote}`: add it with `git remote add {remote} <url>`")
    hosts = _forge_hosts(top)
    found = _forge_of(url, hosts, env)
    if found is None:
        rewritten = _git(top, "remote", "get-url", "--push", remote)
        if rewritten and rewritten != url:
            found = _forge_of(rewritten, hosts, env)
            url = rewritten if found is not None else url
    if found is None:
        remote_url = remote_host(url)
        if remote_url is None:
            raise local_remote(remote)
        raise unknown_forge(remote_url.host)
    return ForgeRemote(
        forge=found.forge,
        host=found.host,
        api_host=found.api_host,
        remote=remote,
        repo=repo_path(url),
        branch=branch,
        top=top,
    )


def repo_path(url: str) -> str:
    """The repository path a remote URL names, without leading ``/`` or trailing ``.git``.

    Example::

        >>> repo_path("ssh://git@gitlab.example:2222/group/sub/app.git")
        'group/sub/app'
    """
    text = url.strip()
    match = _URL_PATH.match(text) or _SCP_PATH.match(text)
    path = (match.group(1) or "") if match is not None else ""
    path = path.strip("/")
    return path.removesuffix(".git").strip("/")


def _git(cwd: Path, *args: str) -> str | None:
    """``git -C cwd <args>``'s stripped stdout, or ``None`` when it fails."""
    try:
        done = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _git_config(top: Path) -> dict[str, list[str]]:
    """Every git config entry visible in ``top``: ``key -> values``, in git's order.

    git prints section and variable names lower-cased and keeps the subsection
    (a remote or branch name) as written.
    """
    text = _git(top, "config", "--null", "--list") or ""
    entries: dict[str, list[str]] = {}
    for item in text.split("\0"):
        key, _, value = item.partition("\n")
        if key:
            entries.setdefault(key, []).append(value)
    return entries


def _first(config: Mapping[str, list[str]], key: str) -> str:
    values = config.get(key)
    return values[0].strip() if values else ""


def _last(config: Mapping[str, list[str]], key: str) -> str:
    values = config.get(key)
    return values[-1].strip() if values else ""


def _push_remote(config: Mapping[str, list[str]], branch: str | None) -> str:
    """The §5.1 push remote: the first of the config keys that names a remote, else ``origin``."""
    keys = (
        (f"branch.{branch}.pushremote", "remote.pushdefault", f"branch.{branch}.remote")
        if branch is not None
        else ("remote.pushdefault",)
    )
    for key in keys:
        name = _last(config, key)
        if name and name != ".":  # "." is the local repository, not a remote
            return name
    return "origin"


def _forge_hosts(top: Path) -> Mapping[str, object]:
    """The committed ``[forge] hosts`` table of the work tree, checked (exit 2 when malformed)."""
    try:
        return parse_forge_table(ConfigFiles(top).committed_table("forge")).hosts
    except ConfigError as error:  # names the file itself
        raise ForgeStop(2, str(error)) from None
    except ValueError as error:
        raise ForgeStop(2, f"{CONFIG_FILENAME}: {error}") from None


def _forge_of(url: str, hosts: Mapping[str, object], env: Mapping[str, str]) -> ForgeHost | None:
    remote = remote_host(url)
    if remote is None:
        return None
    host = _ssh_host(remote.host) if remote.ssh else remote.host
    try:
        return forge_for_host(host, hosts, env)
    except ValueError as error:  # pragma: no cover - parse_forge_table checked every entry
        raise ForgeStop(2, f"{CONFIG_FILENAME}: {error}") from None


def _ssh_host(alias: str) -> str:
    """The host ``ssh -G`` resolves ``alias`` to (offline: ssh reads its config only)."""
    try:
        done = subprocess.run(
            ["ssh", "-G", alias],
            capture_output=True,
            text=True,
            timeout=_SSH_TIMEOUT_S,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return alias
    for line in done.stdout.splitlines() if done.returncode == 0 else ():
        key, _, value = line.strip().partition(" ")
        if key.lower() == "hostname" and value.strip():
            host = value.strip().lower()
            return _SSH_PORT_443_HOSTS.get(host, host)
    return alias
