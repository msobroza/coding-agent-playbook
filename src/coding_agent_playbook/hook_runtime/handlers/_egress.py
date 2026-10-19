"""The ways one shell segment sends data off the machine (specs/prK-hook-pack.md §E.4).

exfil-channel-guard judges :func:`segment_egress` (its rows) and
taint-escalation also asks on :func:`network_hosts` (any outbound client)
once the session is tainted. Both read words, never the network: hosts come
from ``judges.hosts`` and a ``git push`` target from the configured remotes the
caller supplies (``remotes``, called only for a push).

- ``git remote add|set-url <name> <url>`` -> ``remote``;
- ``git push <url | name>`` -> ``push`` (``None`` for the default remote, a
  configured one, or a local path);
- ``gh gist create [files]`` -> ``gist``; ``gh issue|pr ... --body-file F`` ->
  ``body_file``;
- curl / wget uploads (``-d @f``, ``--data-binary @f``, ``-T f``, ``-F x=@f``,
  ``--upload-file``, ``--post-file``, ``--body-file``) -> ``upload``;
- ``scp`` / ``rsync`` to a remote destination, ``sftp host`` -> ``copy``.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime._git_options import git_args
from coding_agent_playbook.hook_runtime.gitargv import parse_git
from coding_agent_playbook.hook_runtime.judges.cli_words import (
    CliWords,
    split_words,
    value_options,
)
from coding_agent_playbook.hook_runtime.judges.hosts import extract_hosts, scp_host, url_host

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.shell import Segment

__all__ = ["EGRESS_ARGV0S", "Egress", "EgressKind", "network_hosts", "segment_egress"]

type EgressKind = Literal["remote", "push", "gist", "body_file", "upload", "copy"]
#: Configured remotes: name -> its fetch and push URLs.
type Remotes = Mapping[str, tuple[str, ...]]


#: The commands :func:`segment_egress` reads (the exfil guard's prefilter).
EGRESS_ARGV0S: Final = ("git", "git.exe", "gh", "curl", "wget", "scp", "rsync", "sftp")
_CLIENTS: Final = frozenset({"curl", "wget", "http", "https", "xh", "httpie"})
_SHELL_CLIENTS: Final = frozenset({"ssh", "sftp", "telnet", "nc", "ncat", "netcat", "ftp"})
_CURL_VALUES: Final = value_options(
    "-d -H -o -T -F -u -X -A -e -b -c -K -w -x -m -r -E -C -Y -y -z -U -Q "
    "--data --data-binary --data-raw --data-ascii --data-urlencode --json --header --output "
    "--upload-file --form --form-string --user --request --user-agent --referer --cookie "
    "--cookie-jar --config --write-out --proxy --max-time --range --cert --url "
    "--connect-timeout --retry --resolve --connect-to --output-dir --unix-socket"
)
_WGET_VALUES: Final = value_options(
    "-O -o -a -e -P -U -t -T -w -i -B --header --post-data --post-file --body-data "
    "--body-file --method --user --password --output-document --output-file"
)
_COPY_VALUES: Final = value_options("-P -i -o -F -c -l -S -J -b -B -R -s -D -e --rsh --port")
_SSH_VALUES: Final = _COPY_VALUES | value_options("-p -E -I -L -m -O -Q -W -w")
_AT_DATA: Final = frozenset({"-d", "--data", "--data-binary", "--data-ascii", "--json"})
_FORM: Final = frozenset({"-F", "--form"})
_UPLOAD: Final = frozenset({"-T", "--upload-file", "--post-file", "--body-file"})
_GH_BODY: Final = frozenset({"--body-file", "-F"})
_GH_VALUES: Final = value_options("-d --desc -f --filename -t --title -b --body -R --repo")
_STDIN: Final = frozenset({"-", "."})


@dataclass(frozen=True, slots=True)
class Egress:
    """One way a segment sends data out: what, to which hosts, carrying which local files.

    ``target`` names a push's remote when no host is known (a remote added
    after the session started).

    Example: ``Egress("upload", "curl", hosts=("x.io",), files=("dump.sql",))``.
    """

    kind: EgressKind
    command: str
    hosts: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    target: str = ""


def segment_egress(segment: Segment, remotes: Callable[[], Remotes]) -> Egress | None:
    """The egress ``segment`` makes, or ``None`` (``remotes`` is called for a push only).

    Example::

        >>> segment_egress(parse("curl -T dump.sql https://x.io")[0], dict).hosts
        ... # doctest: +SKIP
        ('x.io',)
    """
    argv = segment.argv
    program = posixpath.basename(argv[0]) if argv else ""
    if program in ("git", "git.exe"):
        return _git(segment, remotes)
    if program == "gh":
        return _gh(argv[1:])
    if program in ("curl", "wget"):
        return _upload(program, argv[1:])
    if program in ("scp", "rsync", "sftp"):
        return _copy(program, argv[1:])
    return None


def network_hosts(segment: Segment) -> tuple[str, ...]:
    """Every host an outbound client in ``segment`` contacts (taint-escalation's network rows).

    Example::

        >>> network_hosts(parse("curl -s https://x.io/a?q=1")[0])  # doctest: +SKIP
        ('x.io',)
    """
    program = posixpath.basename(segment.argv[0]) if segment.argv else ""
    if program in _CLIENTS:
        values = _CURL_VALUES if program == "curl" else _WGET_VALUES
        words = split_words(segment.argv[1:], values)
        urls = [*words.operands, *words.of(frozenset({"--url"}))]
        return tuple(dict.fromkeys(h for u in urls if (h := url_host(u, bare=True))))
    if program in ("scp", "rsync"):
        return tuple(extract_hosts(split_words(segment.argv[1:], _COPY_VALUES).operands))
    if program in _SHELL_CLIENTS:
        operands = split_words(segment.argv[1:], _SSH_VALUES).operands
        return tuple(_plain_host(word) for word in operands[:1])
    return ()


def _git(segment: Segment, remotes: Callable[[], Remotes]) -> Egress | None:
    invocation = parse_git(segment)
    if invocation is None or invocation.subcommand not in ("remote", "push"):
        return None
    if invocation.subcommand == "remote":
        operands = git_args(invocation.args, "remote").positionals
        if operands[:1] not in (("add",), ("set-url",)) or len(operands) < 3:
            return None
        url = operands[2]
        return Egress("remote", f"git remote {operands[0]}", tuple(extract_hosts([url])), (), url)
    parsed = git_args(invocation.args, "push")
    target = next(iter(parsed.values_of("--repo") or parsed.positionals), None)
    return None if target is None else _push(target, remotes())


def _push(target: str, remotes: Remotes) -> Egress | None:
    """A push to ``target``: ``None`` for a configured remote (by name or URL) or a local path."""
    if target in remotes or any(target in urls for urls in remotes.values()):
        return None
    hosts = tuple(extract_hosts([target]))
    if not hosts and (target.startswith((".", "/", "~", "file:")) or "/" in target):
        return None  # a local repository: nothing leaves the machine
    return Egress("push", "git push", hosts, (), target)


def _gh(words: Sequence[str]) -> Egress | None:
    head = list(words[:2])
    if head in (["gist", "create"], ["gist", "new"]):
        files = [w for w in split_words(words[2:], _GH_VALUES).operands if w not in _STDIN]
        return Egress("gist", "gh gist create", ("gist.github.com",), tuple(files))
    if head[:1] in (["issue"], ["pr"], ["release"]):
        parsed = split_words(words[2:], _GH_VALUES | _GH_BODY)
        files = [f for f in parsed.of(_GH_BODY) if f not in _STDIN]
        if files:
            return Egress("body_file", f"gh {' '.join(head)}", ("github.com",), tuple(files))
    return None


def _upload(program: str, words: Sequence[str]) -> Egress | None:
    parsed = split_words(words, _CURL_VALUES if program == "curl" else _WGET_VALUES)
    files = [*_at_files(parsed), *(f for f in parsed.of(_UPLOAD) if f not in _STDIN)]
    if not files:
        return None
    if parsed.of(frozenset({"--unix-socket"})):
        return None  # a local socket: the URL's host is never contacted
    urls = [*parsed.operands, *parsed.of(frozenset({"--url"}))]
    hosts = tuple(dict.fromkeys(h for u in urls if (h := url_host(u, bare=True))))
    return Egress("upload", program, hosts, tuple(dict.fromkeys(files)))


def _at_files(parsed: CliWords) -> list[str]:
    """The files of ``-d @f`` / ``--data-urlencode name@f`` / ``-F x=@f`` / ``-F x=<f``."""
    found = [value[1:] for value in parsed.of(_AT_DATA) if value.startswith("@")]
    for value in parsed.of(frozenset({"--data-urlencode"})):
        name, at, path = value.partition("@")
        if at and "=" not in name:
            found.append(path)
    for value in parsed.of(_FORM):
        content = value.partition("=")[2].split(";", 1)[0]
        if content[:1] in ("@", "<"):
            found.append(content[1:])
    return [path for path in found if path and path not in _STDIN]


def _copy(program: str, words: Sequence[str]) -> Egress | None:
    operands = list(split_words(words, _COPY_VALUES).operands)
    if program == "sftp":
        host = _plain_host(operands[0]) if operands else ""
        return Egress("copy", program, (host,)) if host else None
    if len(operands) < 2:
        return None
    destination = operands[-1]
    hosts = extract_hosts([destination])
    if not hosts:
        return None  # a download or a local copy
    local = [word for word in operands[:-1] if not extract_hosts([word])]
    return Egress("copy", program, tuple(hosts), tuple(local))


def _plain_host(word: str) -> str:
    """``[user@]host[:path]`` (ssh, sftp, nc) -> ``host``."""
    host = scp_host(word) or word.rpartition("@")[2].split(":", 1)[0]
    return host.strip("[]").lower()
