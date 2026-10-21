"""What one forge CLI or ``playbook forge`` command line does, read from its words (specs/prF-forge-adapter.md §8).

The guards recognise every forge CLI in every repo, whatever the repo's own
forge (Q7), from the same tables ``playbook forge`` runs (Q35):
``forge.dialects`` for ``gh`` and ``glab``, ``forge.operations`` for
``playbook forge <operation>``. :func:`forge_call` is offline and pure: it
never runs a subprocess, never reads ``[forge]`` (Q48) and never resolves a
host name.

A :class:`ForgeCall` says which local files the command sends to the forge
(body, description, attachment, release-asset, template, ``api`` and
CI-trigger file inputs), whether it publishes them as a gist or snippet,
whether it sends data at all (those files, or a body, description, message,
comment, notes or API field given inline or on stdin; for ``playbook forge``,
an operation of kind ``sends_data``), whether it reads forge-hosted content
(a forge CLI command that prints it, or a ``playbook forge`` read operation
that runs one; untrusted: §14's ``taint:forge``), whether it
pushes ``HEAD``'s branch (§8.3), opens a pull request, adds or repoints a git
remote, and which hosts its words or environment name: ``-R/--repo
HOST/OWNER/REPO`` or a URL, ``--hostname``, the forge's host env vars and
``GH_REPO`` (in the segment's env prefix, then the hook's environment).
Empty ``hosts`` leaves the fallback to the caller (the session's remotes
snapshot). A ``--help`` run does nothing on the forge. :func:`credential_flags`
names the flags whose value is a credential (``glab auth login --token``),
for the activity record. The forge tables load on the first forge CLI or
``playbook forge`` command line only, so a plain shell call never pays for them.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.judges.cli_words import split_words
from coding_agent_playbook.hook_runtime.judges.hosts import url_host

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.forge.dialects import CliCommand, Forge
    from coding_agent_playbook.hook_runtime.judges.cli_words import CliWords
    from coding_agent_playbook.hook_runtime.shell.parse import Segment

__all__ = ["FORGE_ARGV0S", "ForgeCall", "credential_flags", "forge_call"]

#: The engine's own command names: ``playbook forge`` runs the forge CLIs.
_PLAYBOOK: Final = ("playbook", "coding-agent-playbook")
#: Every program :func:`forge_call` reads (a guard's argv0 prefilter share).
FORGE_ARGV0S: Final = ("gh", "glab", *_PLAYBOOK)
_FORGE_SUBCOMMAND: Final = "forge"
#: A value that names stdin, not a file.
_STDIN: Final = frozenset({"-", "@-"})
#: First words that never reach the forge: help, version and local config.
_LOCAL: Final = frozenset({"help", "version", "completion", "config", "alias", "--version"})
_HELP: Final = frozenset({"-h", "--help"})
#: Per forge CLI: its value-taking flags, built on first use.
_VALUES: dict[str, frozenset[str]] = {}


@dataclass(frozen=True, slots=True)
class ForgeCall:
    """One forge CLI or ``playbook forge`` command line: what it sends, pushes, opens and where.

    ``forge`` is ``None`` for ``playbook forge``, whose forge is the push
    remote's; ``changes_remote``: it adds or repoints a git remote. ``hosts`` are the hosts the command or its environment names
    (empty: the caller falls back to the session's remotes). ``reads``: it prints
    forge-hosted content, one of the forge's ``reads`` commands (for ``playbook
    forge``, a read operation some forge runs as one of them). ``sends_data``:
    it sends ``files``, a ``texts`` flag's value (inline or ``-``) or a body
    file on stdin; for ``playbook forge``, its operation's kind is ``sends_data``.

    Example: ``ForgeCall("glab snippet create", GITLAB, files=("notes.md",), snippet=True)``.
    """

    command: str
    forge: Forge | None
    files: tuple[str, ...] = ()
    snippet: bool = False
    pushes: bool = False
    opens_pull_request: bool = False
    changes_remote: bool = False
    creates_repository: bool = False
    hosts: tuple[str, ...] = ()
    contacts_forge: bool = True
    reads: bool = False
    sends_data: bool = False


def forge_call(segment: Segment, env: Mapping[str, str] | None = None) -> ForgeCall | None:
    """What the forge CLI or ``playbook forge`` command ``segment`` runs does, else ``None``.

    ``env`` is the hook's environment; the segment's own ``NAME=value``
    prefix wins over it.

    Example::

        >>> forge_call(parse_shell("glab snippet create notes.md", "posix", "/r").segments[0])
        ... # doctest: +SKIP
        ForgeCall(command='glab snippet create', forge=GITLAB, files=('notes.md',), snippet=True, ...)
    """
    argv = segment.argv
    if not argv or 0 in segment.dynamic:
        return None
    if _program(argv[0]) in _PLAYBOOK:
        return _playbook(argv[2:]) if argv[1:2] == (_FORGE_SUBCOMMAND,) else None
    forge = _forge_of(argv[0])
    return None if forge is None else _cli(forge, argv[1:], {**(env or {}), **dict(segment.env)})


def credential_flags(argv: Sequence[str]) -> frozenset[str]:
    """The flags of ``argv``'s forge CLI command whose value is a credential.

    Example::

        >>> sorted(credential_flags(["glab", "auth", "login", "-t", "x"]))
        ['--job-token', '--token', '-j', '-t']
    """
    forge = _forge_of(argv[0]) if argv else None
    row = None if forge is None else forge.command(list(argv[1:]))
    return frozenset() if row is None else row.secrets


def _program(argv0: str) -> str:
    return posixpath.basename(argv0).removesuffix(".exe")


def _forge_of(argv0: str) -> Forge | None:
    """The forge whose CLI ``argv0`` runs; the tables load only for a forge CLI's name."""
    program = _program(argv0)
    if program not in FORGE_ARGV0S or program in _PLAYBOOK:
        return None
    from coding_agent_playbook.forge.dialects import by_cli

    return by_cli(program)


def _cli(forge: Forge, words: Sequence[str], env: Mapping[str, str]) -> ForgeCall:
    lead = split_words(words, _all_values(forge)).operands  # flags may precede the verb
    row = forge.command(lead)
    path = _row_path(row, lead) if row is not None else tuple(lead[:1])
    shown = " ".join((forge.cli, *path, *_verb(forge, path, lead)))
    common = forge.repo_flags | forge.hostname_flags
    parsed = split_words(words, common if row is None else row.values | common)
    del parsed.operands[: len(path)]
    if not lead or lead[0] in _LOCAL or _HELP & parsed.flags:
        return ForgeCall(shown, forge, contacts_forge=False)  # help, version, local config
    reads = _reads(forge, lead)
    if row is None:
        return ForgeCall(shown, forge, hosts=_hosts(forge, parsed, env), reads=reads)
    files = _files(row, parsed)
    return ForgeCall(
        command=shown,
        forge=forge,
        files=files,
        snippet=row.snippet,
        pushes=_pushes(row, parsed),
        opens_pull_request=row.opens_pull_request,
        changes_remote=row.adds_remote or _given(row.remotes, parsed),
        creates_repository=row.creates_repository,
        hosts=_hosts(forge, parsed, env),
        reads=reads,
        sends_data=bool(files) or _sends_text(row, parsed),
    )


def _sends_text(row: CliCommand, parsed: CliWords) -> bool:
    """A text flag given (inline or ``-``), or a body file read from stdin (``--body-file -``)."""
    if parsed.of(row.texts):
        return True
    return any(value in _STDIN for value in parsed.of(row.files))


def _reads(forge: Forge, words: Sequence[str]) -> bool:
    """Whether ``words`` (argv after argv0, flags dropped) run one of ``forge``'s read commands."""
    return any(tuple(words[: len(path)]) == path for path in forge.reads)


def _all_values(forge: Forge) -> frozenset[str]:
    """Every value-taking flag of ``forge``'s CLI, so a flag before the verb skips its value."""
    found = _VALUES.get(forge.cli)
    if found is None:
        found = frozenset().union(
            forge.repo_flags, forge.hostname_flags, *(row.values for row in forge.commands)
        )
        _VALUES[forge.cli] = found
    return found


def _verb(forge: Forge, path: tuple[str, ...], lead: Sequence[str]) -> tuple[str, ...]:
    """The verb after a noun row's noun (``pr`` of ``gh pr view``), for the command shown."""
    verb = lead[len(path) : len(path) + 1]
    nouns = {p[0] for row in forge.commands for p in row.paths if len(p) > 1}
    if len(path) == 1 and path[0] in nouns and verb and verb[0].isalpha() and verb[0].islower():
        return tuple(verb)
    return ()


def _row_path(row: CliCommand, words: Sequence[str]) -> tuple[str, ...]:
    """The path of ``row`` that ``words`` start with (an alias as typed)."""
    return next(path for path in row.paths if tuple(words[: len(path)]) == path)


def _files(row: CliCommand, parsed: CliWords) -> tuple[str, ...]:
    found = [value for value in parsed.of(row.files)]
    for value in parsed.of(row.field_files):
        content = value.partition("=")[2]
        if content.startswith("@"):
            found.append(content[1:])
    for value in parsed.of(row.keyed_files):
        found.append(value.partition(":")[2])
    found.extend(value for value in parsed.of(row.templates) if _is_path(value))
    if row.file_operands is not None:
        found.extend(word.partition("#")[0] for word in parsed.operands[row.file_operands :])
    return tuple(dict.fromkeys(path for path in found if path and path not in _STDIN))


def _is_path(value: str) -> bool:
    """A ``--template`` value that names a local file: absolute or with a separator (Q56)."""
    return value.startswith(("/", "~")) or "/" in value or "\\" in value


def _pushes(row: CliCommand, parsed: CliWords) -> bool:
    """Any pushing flag given, each unless ``=false`` (§8.3): ``--fill --push=false`` pushes.

    A short one counts inside a cluster of short flags too (``-yf``).
    """
    return bool(row.pushes) and parsed.given(row.pushes)


def _given(flags: frozenset[str], parsed: CliWords) -> bool:
    return bool(flags & parsed.flags) or bool(parsed.of(flags))


def _hosts(forge: Forge, parsed: CliWords, env: Mapping[str, str]) -> tuple[str, ...]:
    """The hosts the command names (``--hostname``, ``-R HOST/…``), else its env's.

    A ``-R`` value overrides the repository env var (``GH_REPO``), as the CLIs read it.
    """
    repos = parsed.of(forge.repo_flags)
    named = [*parsed.of(forge.hostname_flags)]
    named.extend(h for value in repos if (h := _repo_host(forge, value, env)))
    if not named:
        named.extend(_env_hosts(forge, env, repo_given=bool(repos)))
    return tuple(dict.fromkeys(host for word in named if (host := _host(word))))


def _env_hosts(forge: Forge, env: Mapping[str, str], *, repo_given: bool) -> Iterable[str]:
    repo_env = () if repo_given else forge.repo_env
    for name in (*repo_env, *forge.host_env, *forge.api_host_env):
        value = env.get(name, "").strip()
        if not value:
            continue
        yield (_repo_host(forge, value, env) or "") if name in forge.repo_env else value


def _repo_host(forge: Forge, value: str, env: Mapping[str, str]) -> str | None:
    """The host of a ``-R`` / ``GH_REPO`` value: a URL's, or ``HOST/OWNER/REPO``'s first part.

    ``glab`` reads ``GROUP/NAMESPACE/REPO`` too and takes a first part for a
    host when it is the forge's own, its host env vars' or a host it is logged
    in to (its config, unread here): a dotted first part counts as one too,
    the cautious reading.
    """
    host = url_host(value)
    if host is not None or "://" in value:
        return host
    if "@" in value.partition("/")[0] or ":" in value.partition("/")[0]:
        return url_host(f"ssh://{value.replace(':', '/', 1)}")  # git@host:group/repo
    parts = value.strip("/").split("/")
    if len(parts) < 3:
        return None
    first = parts[0].lower()
    if forge.repo_host_parts is not None:
        return first if len(parts) == forge.repo_host_parts else None
    named = {_host(env.get(name, "")) for name in forge.host_env}
    return first if first == forge.host or first in named or "." in first else None


def _host(word: str) -> str | None:
    text = word.strip()
    if not text:
        return None
    return url_host(text) or text.rpartition("@")[2].split("/", 1)[0].split(":", 1)[0].lower()


def _playbook(words: Sequence[str]) -> ForgeCall | None:
    from coding_agent_playbook.forge.dialects import by_name
    from coding_agent_playbook.forge.operations import BODY_FILES, operation_call

    call = operation_call(words)
    if call is None:
        return None
    operation = call.operation
    shown = f"playbook {_FORGE_SUBCOMMAND} {operation.name}"
    files: tuple[str, ...] = ()
    if operation.kind == "sends_data":
        parsed = split_words(call.args, operation.values)
        found = parsed.of(BODY_FILES)
        files = tuple(dict.fromkeys(f for f in found if f and f not in _STDIN))
    reaches = any(t is not None and t.argv for _, t in operation.translations)
    reads = operation.kind == "read" and any(
        t is not None and (forge := by_name(name)) is not None and _reads(forge, t.argv)
        for name, t in operation.translations
    )
    return ForgeCall(
        command=shown,
        forge=None,
        files=files,
        opens_pull_request=operation.opens_pull_request,
        contacts_forge=reaches,
        reads=reads,
        sends_data=operation.kind == "sends_data",
    )
