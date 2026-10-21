"""A git remote's host, and the forge that host is on (specs/prF-forge-adapter.md §5.1, §5.2).

Pure functions over strings: the ``[forge] hosts`` table and the environment
come in as arguments, and nothing here reads a file, runs a subprocess or
looks a name up (a lookup is itself egress).

- :func:`remote_host`: the host of a remote URL in any of git's forms
  (scp-like ``git@host:path``, ``ssh://user@host:port/path``,
  ``https://user:token@host:port/path``), lower-cased, never its userinfo;
- :func:`forge_for_host`: the host's forge through the §5.2 chain
  (``[forge] hosts``, the public hosts, a host name holding a forge's name, a
  forge host env var), else ``None``, which ``playbook forge`` reports as an
  unknown forge (exit 2);
- :func:`host_entry`: one ``[forge] hosts`` value, checked.

``playbook forge`` resolves an SSH alias (``ssh -G``, a subprocess) between the
first two, so they stay separate. Errors name the host, never the URL.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.forge.dialects import FORGES, by_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.forge.dialects import Forge

__all__ = [
    "ForgeHost",
    "HostEntry",
    "MatchedBy",
    "RemoteHost",
    "forge_for_host",
    "host_entry",
    "remote_host",
]

#: What mapped a host to its forge, in §5.2 order: a ``[forge] hosts`` entry, the
#: forge's public host, a host name holding the forge's name, a forge host env var.
type MatchedBy = Literal["table", "exact", "name", "env"]

#: ``scheme://authority``; the authority ends at the first ``/ ? #``.
_URL: Final = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#]*)")
#: git's scp-like ``[user@]host:path``: no ``/`` before the first ``:``.
_SCP: Final = re.compile(r"^(?:[^@/\[\]]*@)?(?:\[([^\]/]+)\]|([^:/@\[\]]+)):")
_AUTHORITY_END: Final = re.compile(r"[/?#]")
#: An ``api_host``: a host name or a bracketed IPv6 address, then an optional port.
_API_HOST: Final = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?|\[[0-9a-f:.]+\])(?::[0-9]{1,5})?$"
)
_ENTRY_KEYS: Final = frozenset({"forge", "api_host"})


@dataclass(frozen=True, slots=True)
class RemoteHost:
    """The host a remote URL names, and whether git reaches it over SSH.

    ``ssh`` tells ``playbook forge`` to resolve an SSH alias (``ssh -G``) first.

    Example: ``RemoteHost("github.com", ssh=True)`` for ``git@github.com:a/b.git``.
    """

    host: str
    ssh: bool


def remote_host(url: str) -> RemoteHost | None:
    """The host of the remote ``url``, or ``None`` for a local path or a URL without one.

    Example::

        >>> remote_host("https://ci:tok@GitLab.example:8443/g/app.git")
        RemoteHost(host='gitlab.example', ssh=False)
    """
    text = url.strip()
    match = _URL.match(text)
    if match is not None:
        scheme = match.group(1).lower()
        host = _authority_host(match.group(2))
        if scheme == "file" or not host:
            return None
        return RemoteHost(host, ssh="ssh" in scheme.split("+"))
    scp = _SCP.match(text)
    if scp is None:
        return None
    host = scp.group(1) or scp.group(2)
    if scp.group(2) and len(host) == 1 and "@" not in text.partition(":")[0]:
        return None  # a Windows drive (C:\repo), not a host
    return RemoteHost(_clean(host), ssh=True)


@dataclass(frozen=True, slots=True)
class HostEntry:
    """One ``[forge] hosts`` value (§5.4): the forge, and the API host when it differs.

    Example: ``HostEntry(GITLAB, "gitlab.acme.com")`` for
    ``{ forge = "gitlab", api_host = "gitlab.acme.com" }``.
    """

    forge: Forge
    api_host: str | None


@dataclass(frozen=True, slots=True)
class ForgeHost:
    """A remote host mapped to its forge, with the host its forge CLI talks to.

    ``api_host`` is the ``[forge]`` entry's ``api_host``, else ``host``.

    Example: ``ForgeHost(GITLAB, "ssh.acme.com", "gitlab.acme.com", "table")``.
    """

    forge: Forge
    host: str
    api_host: str
    matched_by: MatchedBy


def forge_for_host(
    host: str, hosts: Mapping[str, object], env: Mapping[str, str]
) -> ForgeHost | None:
    """The forge of ``host`` through the §5.2 chain, first match wins; ``None``: unknown forge.

    Example::

        >>> forge_for_host("GitHub.com", {}, {}).forge.name
        'github'
    """
    name = _clean(host)
    if not name:
        return None
    entry = _table_entry(name, hosts)
    if entry is not None:
        return ForgeHost(entry.forge, name, entry.api_host or name, "table")
    rules: tuple[tuple[MatchedBy, Callable[[Forge], bool]], ...] = (
        ("exact", lambda forge: forge.host == name),
        ("name", lambda forge: forge.name in name),
        ("env", lambda forge: name in {_host_name(env.get(var, "")) for var in forge.host_env}),
    )
    for matched_by, matches in rules:
        found = [forge for forge in FORGES if matches(forge)]
        if len(found) == 1:  # a host two forges claim is evidence for neither
            return ForgeHost(found[0], name, name, matched_by)
    return None


def host_entry(value: object) -> HostEntry:
    """Read one ``[forge] hosts`` value: a forge name, or a table with ``forge`` and ``api_host``.

    Raises ``ValueError`` naming what is wrong, so ``playbook validate`` and
    ``playbook forge`` reject the same values.

    Example::

        >>> host_entry({"forge": "gitlab", "api_host": "gitlab.acme.com"}).api_host
        'gitlab.acme.com'
    """
    if isinstance(value, str):
        return HostEntry(_named_forge(value), None)
    if not isinstance(value, Mapping):
        raise ValueError(f"expected a forge name or a table, got {type(value).__name__}")
    unknown = sorted(str(key) for key in value if key not in _ENTRY_KEYS)
    if unknown:
        raise ValueError(f"unknown key {unknown[0]!r} (expected forge, api_host)")
    if "forge" not in value:
        raise ValueError("a table entry needs forge")
    forge = value["forge"]
    if not isinstance(forge, str):
        raise ValueError("'forge' must be a string")
    api_host = value.get("api_host")
    if api_host is None:
        return HostEntry(_named_forge(forge), None)
    if not isinstance(api_host, str) or _API_HOST.match(api_host.strip().lower()) is None:
        # the value is not echoed: a URL put here may carry a token
        raise ValueError("api_host must be a host name with an optional port")
    return HostEntry(_named_forge(forge), api_host.strip().lower())


def _named_forge(name: str) -> Forge:
    forge = by_name(name)
    if forge is None:
        names = ", ".join(forge.name for forge in FORGES)
        raise ValueError(f"{name!r} is not a forge (expected one of {names})")
    return forge


def _table_entry(name: str, hosts: Mapping[str, object]) -> HostEntry | None:
    for key, value in hosts.items():
        if _clean(key) == name:
            try:
                return host_entry(value)
            except ValueError as error:
                raise ValueError(f"[forge] hosts entry for {name!r}: {error}") from None
    return None


def _host_name(value: str) -> str:
    """``value`` as a host name: scheme, userinfo, port and path stripped, lower-cased."""
    text = value.strip()
    match = _URL.match(text)
    authority = match.group(2) if match is not None else _AUTHORITY_END.split(text, 1)[0]
    return _authority_host(authority)


def _authority_host(authority: str) -> str:
    hostport = authority.rpartition("@")[2]
    if hostport.startswith("["):
        return _clean(hostport[1:].partition("]")[0])
    return _clean(hostport.partition(":")[0])


def _clean(host: str) -> str:
    return host.strip().lower().rstrip(".")
