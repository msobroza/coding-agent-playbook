"""The network destinations one shell segment reaches (specs/prK-hook-pack.md §E.5).

network-egress-guard judges every outbound command, where exfil-channel-guard
(``_egress``) reads only the ways data is *sent*. Hosts are strings only, from
``judges.hosts`` (no DNS: a lookup is itself egress):

- clients (``curl``, ``wget``, ``http``, ``nc``, ``ssh``, ``scp``, ``sftp``,
  ``rsync``, ``ftp``, ``telnet``): ``_egress.network_hosts``; a client whose
  destination is a shell variable reaches a host nobody can read (``unknown``);
- ``git clone|fetch|pull|push|ls-remote``: the repository operand's URL or
  scp host, else the configured remote it names (``remotes``, called only
  then), else ``origin``; a local repository reaches nothing.
  ``git submodule add <url>`` reads the URL; ``git submodule update`` fetches
  from ``.gitmodules``, which is not read here (``unknown``);
- installs (``judges.install_commands.install_requests``): the hosts of the index and
  direct-URL words; an install naming none uses the configured index, which a
  hook cannot see (``unknown``). Lockfile installs (``uv sync``, ``npm ci``)
  request nothing: the lockfile pins their sources;
- ``docker pull IMAGE``: the image's registry (Docker Hub for a bare name);
- ``huggingface-cli download|upload|login|...``: ``HF_ENDPOINT``'s host, else
  ``huggingface.co``.

A private module: it registers no handler.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.gitargv import parse_git
from coding_agent_playbook.hook_runtime.handlers._egress import network_hosts
from coding_agent_playbook.hook_runtime.judges.cli_words import split_words, value_options
from coding_agent_playbook.hook_runtime.judges.hosts import extract_hosts, url_host
from coding_agent_playbook.hook_runtime.judges.install_commands import install_requests

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["NetKind", "NetTarget", "Remotes", "image_registry", "segment_target"]

type NetKind = Literal["client", "git", "install", "docker", "hub"]
#: Configured remotes: name -> its fetch and push URLs (``git remote -v``).
type Remotes = Mapping[str, tuple[str, ...]]

_CLIENTS: Final = frozenset(
    {"curl", "wget", "http", "https", "xh", "httpie", "nc", "ncat", "netcat", "ssh", "scp"}
    | {"sftp", "rsync", "ftp", "telnet"}
)
_GIT: Final = frozenset({"git", "git.exe"})
#: The git subcommands that contact a remote repository.
_GIT_REMOTE_SUBS: Final = frozenset({"fetch", "pull", "push", "ls-remote"})
#: Their value options, so ``--depth 1`` never reads ``1`` as the repository.
_GIT_VALUES: Final = value_options(
    "--depth --deepen --shallow-since --shallow-exclude -j --jobs --negotiation-tip "
    "--upload-pack --receive-pack --exec -o --server-option --push-option --refmap --filter "
    "--recurse-submodules-default --origin -b --branch --reference --reference-if-able "
    "--separate-git-dir --template -c --config --repo -u"
)
_DEFAULT_REMOTE: Final = "origin"
#: A repository operand that is a local path: nothing leaves the machine.
_LOCAL_REPO: Final = re.compile(r"^(?:\.{1,2}(?:/|$)|/|~|file:)")
_DOCKER_VALUES: Final = value_options("--platform")
_DOCKER_HUB: Final = "docker.io"
_HUB: Final = "huggingface-cli"
_HUB_HOST: Final = "huggingface.co"
_HUB_NETWORK: Final = frozenset(
    {"download", "upload", "upload-large-folder", "login", "whoami", "repo", "repo-files"}
)


@dataclass(frozen=True, slots=True)
class NetTarget:
    """Where one segment connects: the command, its hosts, or ``unknown`` when unreadable.

    Example: ``NetTarget("client", "curl", hosts=("pypi.org",))``.
    """

    kind: NetKind
    command: str
    hosts: tuple[str, ...] = ()
    unknown: bool = False


def segment_target(segment: Segment, remotes: Callable[[], Remotes]) -> NetTarget | None:
    """The network destination of ``segment``, or ``None`` when it reaches no network.

    ``remotes`` is called only for a git command whose repository is a remote name.

    Example::

        >>> segment_target(parse("curl -s https://pypi.org/simple/")[0], dict)  # doctest: +SKIP
        NetTarget(kind='client', command='curl', hosts=('pypi.org',), unknown=False)
    """
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    if program in _CLIENTS:
        return _client(segment, program)
    if program in _GIT:
        return _git(segment, remotes)
    if program == "docker":
        return _docker(segment.argv[1:])
    if program == _HUB:
        return _hub(segment)
    return _install(segment)


def image_registry(reference: str) -> str:
    """The registry host of a container image reference (Docker Hub for a bare name).

    Example::

        >>> image_registry("ubuntu:24.04"), image_registry("registry.corp:5000/team/app")
        ('docker.io', 'registry.corp')
    """
    first, slash, _ = reference.partition("/")
    if slash and ("." in first or ":" in first or first == "localhost"):
        return first.rsplit(":", 1)[0].lower() if ":" in first else first.lower()
    return _DOCKER_HUB


def _client(segment: Segment, program: str) -> NetTarget | None:
    hosts = tuple(host for host in network_hosts(segment) if host)
    if hosts:
        return NetTarget("client", program, hosts)
    if any(index > 0 for index in segment.dynamic):
        return NetTarget("client", program, unknown=True)  # ``curl "$URL"``: unreadable
    return None


def _git(segment: Segment, remotes: Callable[[], Remotes]) -> NetTarget | None:
    invocation = parse_git(segment)
    sub = None if invocation is None else invocation.subcommand
    if invocation is None or sub is None:
        return None
    operands = split_words(invocation.args, _GIT_VALUES).operands
    if sub == "clone":
        cloned = extract_hosts(operands[:1])  # the repository; the directory follows
        return NetTarget("git", "git clone", tuple(cloned)) if cloned else None
    if sub == "submodule":
        return _submodule(operands)
    if sub not in _GIT_REMOTE_SUBS:
        return None
    hosts = _repository_hosts(operands[:1], remotes)
    return None if hosts is None else NetTarget("git", f"git {sub}", hosts)


def _repository_hosts(
    repository: Sequence[str], remotes: Callable[[], Remotes]
) -> tuple[str, ...] | None:
    """The hosts of a fetch/pull/push repository operand; ``None`` for a local one.

    Only the first operand names the repository: the rest are refspecs, and
    ``main:release`` must never read as an scp host.
    """
    named = repository[0] if repository else _DEFAULT_REMOTE
    hosts = extract_hosts([named])
    if hosts:
        return tuple(hosts)
    if _LOCAL_REPO.match(named):
        return None
    configured = remotes()
    urls = configured.get(named) or configured.get(_DEFAULT_REMOTE) or ()
    found = extract_hosts(list(urls))
    return tuple(found) if found else None  # a remote on a local path reaches nothing


def _submodule(operands: Sequence[str]) -> NetTarget | None:
    action = operands[0] if operands else ""
    if action == "add" and len(operands) > 1:
        hosts = extract_hosts(operands[1:2])
        return NetTarget("git", "git submodule add", tuple(hosts)) if hosts else None
    if action == "update":
        return NetTarget("git", "git submodule update", unknown=True)  # .gitmodules: unread
    return None


def _docker(words: Sequence[str]) -> NetTarget | None:
    rest = list(words)
    if rest[:1] == ["image"]:  # ``docker image pull`` is ``docker pull``
        rest = rest[1:]
    if rest[:1] != ["pull"]:
        return None
    images = split_words(rest[1:], _DOCKER_VALUES).operands
    if not images:
        return None
    return NetTarget("docker", "docker pull", (image_registry(images[0]),))


def _hub(segment: Segment) -> NetTarget | None:
    if len(segment.argv) < 2 or segment.argv[1] not in _HUB_NETWORK:
        return None  # help, env, scan-cache: local
    endpoint = dict(segment.env).get("HF_ENDPOINT")
    host = (url_host(endpoint) if endpoint else None) or _HUB_HOST
    return NetTarget("hub", _HUB, (host,))


def _install(segment: Segment) -> NetTarget | None:
    requests = install_requests(segment)
    if not requests:
        return None
    hosts = tuple(dict.fromkeys(h for word in segment.raw_argv if (h := url_host(word))))
    return NetTarget("install", requests[0].tool, hosts, unknown=not hosts)
