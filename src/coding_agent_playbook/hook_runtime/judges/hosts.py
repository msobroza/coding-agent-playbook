"""The hosts a command names, read as strings only: no DNS lookup, no connect probe (specs/prK-hook-pack.md §E.4).

exfil-channel-guard and taint-escalation (and network-egress-guard, §E.5)
decide whether data leaves the machine from a command's words alone. A name
lookup is itself egress (it leaks the name to a resolver; catalog principle
10), so nothing here imports ``socket``:

- :func:`extract_hosts`: the hosts of URL arguments (``--index-url=URL``,
  ``name @ URL`` and ``git+https://`` forms included), of scp-style
  ``[user@]host:path`` words, and of git remote names, which the caller
  resolves from ``git remote -v`` (``remotes``);
- :func:`url_host`: one URL's host; ``bare=True`` also reads curl's
  scheme-less ``host/path`` form;
- :func:`is_loopback`: ``localhost`` and loopback addresses only (``ipaddress``
  is imported for a word that looks like an IP, nothing else); RFC 1918
  ranges are not trusted, since a LAN host is still off the machine;
- :func:`host_matches`: the suffix match of an ``allowed_hosts`` row;
- :func:`without_userinfo`: a URL with its ``user:token@`` dropped, so a
  remote URL is stored and compared without a credential (prF Q56).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "extract_hosts",
    "host_matches",
    "is_loopback",
    "scp_host",
    "url_host",
    "without_userinfo",
]

#: ``scheme://[userinfo@]host``: an IPv6 literal in brackets, else up to ``/ : ? #``.
_URL: Final = re.compile(
    r"\b[A-Za-z][A-Za-z0-9+.-]*://(?:[^/@\s]*@)?(\[[0-9A-Fa-f:.]+\]|[^/:?#\s@\[\]]+)"
)
#: scp's ``[user@]host:path``; ``host::module`` is rsync's daemon form.
_SCP: Final = re.compile(r"^(?:[^@\s/:]+@)?(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9][A-Za-z0-9.-]*):(?!//)")
#: A scheme-less ``host[:port][/path]`` (curl reads one as ``http://``).
_BARE: Final = re.compile(
    r"^(?:[^@\s/:]+@)?([A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z0-9-]+)(?::\d+)?(?:/|$)"
)
_IP_LIKE: Final = re.compile(r"^[0-9.]+$|:")
_LOCALHOST: Final = frozenset({"localhost", "localhost.localdomain"})
#: ``scheme://`` then the userinfo up to the authority's last ``@``.
_USERINFO: Final = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/?#]*@")


def extract_hosts(words: Sequence[str], *, remotes: Mapping[str, str] | None = None) -> list[str]:
    """Every host ``words`` name, lower-cased and deduplicated, in order.

    A word equal to a key of ``remotes`` (git remote name -> URL) contributes
    its URL's host; scp-style words are read only when they hold no space and
    do not start with ``-`` (an option). Pure: nothing is resolved.

    Example::

        >>> extract_hosts(["push", "origin", "git@GitHub.com:a/b.git",
        ...                "--index-url=https://pypi.example/simple"],
        ...               remotes={"origin": "https://gitlab.example/x.git"})
        ['gitlab.example', 'github.com', 'pypi.example']
    """
    found: list[str] = []
    for word in words:
        if remotes and word in remotes:
            found.extend(_hosts_of(remotes[word]))
        else:
            found.extend(_hosts_of(word))
    return list(dict.fromkeys(found))


def url_host(word: str, *, bare: bool = False) -> str | None:
    """The host of the first URL in ``word``; ``bare`` also reads ``host.tld/path``.

    Example::

        >>> url_host("https://user:pw@[::1]:8000/x"), url_host("x.io/up", bare=True)
        ('::1', 'x.io')
    """
    match = _URL.search(word)
    if match is not None:
        return _clean(match.group(1))
    if bare:
        plain = _BARE.match(word)
        return None if plain is None else _clean(plain.group(1))
    return None


def scp_host(word: str) -> str | None:
    """The host of an scp/rsync-style ``[user@]host:path`` word, else ``None``.

    A one-letter "host" without ``user@`` is a Windows drive (``C:\\x``), not a host.

    Example::

        >>> scp_host("deploy@host:/srv"), scp_host("C:/x"), scp_host("./a:b")
        ('host', None, None)
    """
    if not word or word.startswith("-") or "://" in word or any(c.isspace() for c in word):
        return None
    match = _SCP.match(word)
    if match is None or (len(match.group(1)) == 1 and "@" not in word):
        return None
    return _clean(match.group(1))


def is_loopback(host: str) -> bool:
    """Whether ``host`` is this machine: ``localhost`` or a loopback address.

    Example::

        >>> is_loopback("127.0.0.2"), is_loopback("::1"), is_loopback("10.0.0.5")
        (True, True, False)
    """
    name = host.strip().strip("[]").lower().rstrip(".")
    if name in _LOCALHOST:
        return True
    if not name or _IP_LIKE.search(name) is None:
        return False
    import ipaddress  # branch-local (§D.1): only a word that looks like an address

    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_loopback or (mapped is not None and mapped.is_loopback)


def host_matches(host: str, suffixes: Iterable[str]) -> bool:
    """Whether ``host`` is one of ``suffixes`` or a subdomain of one (``*.`` / ``.`` ignored).

    Example::

        >>> host_matches("api.Example.com", ["example.com"]), host_matches("badexample.com",
        ...                                                                 ["example.com"])
        (True, False)
    """
    name = host.lower().rstrip(".")
    for raw in suffixes:
        suffix = raw.strip().lower().removeprefix("*").lstrip(".").rstrip(".")
        if suffix and (name == suffix or name.endswith("." + suffix)):
            return True
    return False


def without_userinfo(url: str) -> str:
    """``url`` without the ``user[:password]@`` of a ``scheme://`` URL (scp-like stays).

    Example::

        >>> without_userinfo("https://ci:tok@gitlab.example/g/app.git")
        'https://gitlab.example/g/app.git'
    """
    return _USERINFO.sub(r"\1", url, count=1)


def _hosts_of(word: str) -> list[str]:
    urls = [_clean(match.group(1)) for match in _URL.finditer(word)]
    if urls:
        return [host for host in urls if host]
    host = scp_host(word)
    return [] if host is None else [host]


def _clean(host: str) -> str:
    return host.strip("[]").lower().rstrip(".")
