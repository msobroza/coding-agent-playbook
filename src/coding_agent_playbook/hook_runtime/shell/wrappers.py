"""Wrapper unwrapping for ``parse.parse_shell`` (specs/prK-lifecycle-hooks.md §D.2.5).

``env FOO=1 sudo -u root timeout 5 rm -rf /`` runs ``rm``, so guards judge the
effective argv, not its launcher. ``unwrap`` strips launchers, matching each on
the basename of ``argv[0]``, up to ``MAX_UNWRAP`` times:

- the configured ``wrapper_prefixes`` (longest token prefix first, e.g. ``proxy run``);
- the ``runner_wrappers`` (``uv run``, ...), skipping their own options;
- the §D.2.5 table: ``env``, ``sudo``/``doas``, ``command``, ``exec``,
  ``nohup``, ``time``, ``nice``, ``ionice``, ``stdbuf``, ``timeout`` and ``xargs``.

A shell's ``-c SCRIPT`` and ``eval``'s arguments are reported in ``nested`` for a
recursive parse, and ``find -exec`` commands in ``find_execs``; those launchers
stay in the segment itself. More than ``MAX_UNWRAP`` launchers sets ``limit``.
"""

from __future__ import annotations

import posixpath
import shlex
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.shell._options import (
    OptionSpec,
    has_letter,
    long_names,
    option_arity,
    skip_options,
)
from coding_agent_playbook.hook_runtime.shell.tokens import ScanError, Word

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

MAX_UNWRAP: Final = 4
DEFAULT_RUNNER_WRAPPERS: Final = ("uv run", "uvx", "poetry run", "pdm run", "hatch run", "pipx run")

type SegmentOrigin = Literal["top", "subst", "bash_c", "eval", "xargs", "find_exec"]

_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_FIND_EXEC = frozenset({"-exec", "-execdir", "-ok", "-okdir"})


@dataclass(frozen=True, slots=True)
class ShellConfig:
    """The ``guard_config.shell`` knobs (§D.8.2); ``ShellConfig()`` is the engine default.

    Example::

        >>> ShellConfig(wrapper_prefixes=("proxy",)).runner_wrappers[0]
        'uv run'
    """

    wrapper_prefixes: tuple[str, ...] = ()
    runner_wrappers: tuple[str, ...] = DEFAULT_RUNNER_WRAPPERS


DEFAULT_SHELL_CONFIG: Final = ShellConfig()


@dataclass(slots=True)
class Unwrapped:
    """What ``unwrap`` found: the effective argv plus what each launcher contributed."""

    argv: list[Word]
    env: list[tuple[str, str]] = field(default_factory=list)
    wrappers: list[str] = field(default_factory=list)
    args_open: bool = False
    origin: SegmentOrigin | None = None
    nested: list[tuple[SegmentOrigin, str, Word]] = field(default_factory=list)
    find_execs: list[list[Word]] = field(default_factory=list)
    limit: bool = False


def unwrap(argv: list[Word], cfg: ShellConfig) -> Unwrapped:
    """Strip the launchers off ``argv``; see the module docstring for the order.

    Example::

        >>> [w.value for w in unwrap([Word("nohup"), Word("ls")], ShellConfig()).argv]
        ['ls']
    """
    result = Unwrapped(argv=list(argv))
    steps = 0
    while result.argv and _unwrap_once(result, cfg):
        steps += 1
        if steps > MAX_UNWRAP:
            result.limit = True
            return result
    _extract_inner(result)
    return result


def _unwrap_once(result: Unwrapped, cfg: ShellConfig) -> bool:
    if result.argv[0].dynamic:
        return False
    for prefix in _longest_first(cfg.wrapper_prefixes):
        if _strip_prefix(result, prefix, None):
            return True
    for runner in _longest_first(cfg.runner_wrappers):
        if _strip_prefix(result, runner, _RUNNER_OPTIONS.get(runner, OptionSpec())):
            return True
    handler = _WRAPPERS.get(posixpath.basename(result.argv[0].value))
    return handler is not None and handler(result)


def _longest_first(prefixes: tuple[str, ...]) -> list[str]:
    return sorted(prefixes, key=lambda prefix: len(prefix.split()), reverse=True)


def _strip_prefix(result: Unwrapped, prefix: str, spec: OptionSpec | None) -> bool:
    tokens = prefix.split()
    values = [word.value for word in result.argv[: len(tokens)]]
    if not tokens or len(values) < len(tokens):
        return False
    if [posixpath.basename(values[0]), *values[1:]] != tokens:
        return False
    start, env = (len(tokens), []) if spec is None else skip_options(result.argv, len(tokens), spec)
    return _descend(result, prefix, start, env)


def _descend(result: Unwrapped, name: str, start: int, env: list[tuple[str, str]]) -> bool:
    """Make ``argv[start:]`` the command, unless nothing is left to run."""
    if start >= len(result.argv):
        return False
    result.argv = result.argv[start:]
    result.env.extend(env)
    result.wrappers.append(name)
    return True


def _plain(name: str, spec: OptionSpec) -> Callable[[Unwrapped], bool]:
    def handler(result: Unwrapped) -> bool:
        start, env = skip_options(result.argv, 1, spec)
        return _descend(result, name, start, env)

    return handler


def _privileged(name: str, spec: OptionSpec) -> Callable[[Unwrapped], bool]:
    """``sudo``/``doas``: ``-i``/``-s`` with no command is an interactive root shell."""

    def handler(result: Unwrapped) -> bool:
        start, env = skip_options(result.argv, 1, spec)
        options = result.argv[1:start]
        if start >= len(result.argv) and has_letter(options, "is", ("--login", "--shell")):
            result.argv, result.wrappers = [], [*result.wrappers, name]
            return True
        return _descend(result, name, start, env)

    return handler


def _unwrap_command(result: Unwrapped) -> bool:
    start, _ = skip_options(result.argv, 1, OptionSpec())
    if has_letter(result.argv[1:start], "vV"):
        return False  # `command -v x` looks x up; it runs nothing
    return _descend(result, "command", start, [])


def _unwrap_xargs(result: Unwrapped) -> bool:
    start, _ = skip_options(result.argv, 1, _XARGS)
    result.argv = result.argv[start:] or [Word("echo")]
    result.wrappers.append("xargs")
    result.args_open, result.origin = True, "xargs"
    return True


def _unwrap_env(result: Unwrapped) -> bool:
    argv = _env_argv(result.argv)
    start, env = skip_options(argv, 1, _ENV)
    if start >= len(argv):
        return False
    result.argv = argv
    return _descend(result, "env", start, env)


def _env_argv(argv: list[Word]) -> list[Word]:
    """``env``'s argv with each ``-S STRING`` split in place and a lone ``-`` read as ``-i``."""
    words, index = list(argv), 1
    while index < len(words) and words[index].value.startswith("-"):
        if words[index].value == "--":
            break
        split = _split_string(words, index)
        if split is not None:
            # GNU env re-reads the split words as options, assignments and the command.
            words[index : index + split[0]] = split[1]
            continue
        if words[index].value == "-":
            words[index] = Word("-i")
        index += 1 + option_arity(words[index].value, _ENV)
    return words


def _split_string(argv: list[Word], index: int) -> tuple[int, list[Word]] | None:
    """``env -S STRING``: how many words to replace, and the words STRING splits into."""
    value, dynamic = argv[index].value, argv[index].dynamic
    if value in ("-S", "--split-string"):
        used, text = (2, argv[index + 1].value) if index + 1 < len(argv) else (1, "")
    elif value.startswith("--split-string="):
        used, text = 1, value.partition("=")[2]
    elif value.startswith("-S"):
        used, text = 1, value[2:]
    else:
        return None
    try:
        return used, [Word(part, dynamic) for part in shlex.split(text)]
    except ValueError as exc:
        raise ScanError(f"env -S string {text!r}: {exc}") from None


def _extract_inner(result: Unwrapped) -> None:
    """Report the command lists a shell ``-c``, ``eval`` or ``find -exec`` will run."""
    argv = result.argv
    name = "" if not argv or argv[0].dynamic else posixpath.basename(argv[0].value)
    if name in _SHELLS:
        start, _ = skip_options(argv, 1, _SHELL_OPTIONS)
        if start < len(argv) and has_letter(argv[1:start], "c"):
            result.nested.append(("bash_c", name, argv[start]))
    elif name == "eval" and len(argv) > 1:
        script = Word(" ".join(w.value for w in argv[1:]), any(w.dynamic for w in argv[1:]))
        result.nested.append(("eval", "eval", script))
    elif name == "find":
        result.find_execs = _find_execs(argv)


def _find_execs(argv: list[Word]) -> list[list[Word]]:
    execs: list[list[Word]] = []
    index = 1
    while index < len(argv):
        if argv[index].value not in _FIND_EXEC:
            index += 1
            continue
        end = index + 1
        while end < len(argv) and not _ends_exec(argv, end):
            end += 1
        if end > index + 1:
            execs.append(argv[index + 1 : end])
        index = end + 1
    return execs


def _ends_exec(argv: list[Word], index: int) -> bool:
    value = argv[index].value
    return value == ";" or (value == "+" and argv[index - 1].value == "{}")


_ENV = OptionSpec(with_arg="uC", long_with_arg=long_names("unset chdir"), assignments=True)
_XARGS = OptionSpec(
    with_arg="ILnPsdEa",
    long_with_arg=long_names(
        "arg-file delimiter max-args max-procs max-chars max-lines process-slot-var"
    ),
)
_SHELL_OPTIONS = OptionSpec(with_arg="oO", long_with_arg=long_names("rcfile init-file"), plus=True)
_SUDO_LONG = "user group host prompt close-from chdir role type other-user command-timeout"

_WRAPPERS: Final[Mapping[str, Callable[[Unwrapped], bool]]] = MappingProxyType(
    {
        "env": _unwrap_env,
        "sudo": _privileged(
            "sudo", OptionSpec("ughpCDrtUT", long_names(_SUDO_LONG), assignments=True)
        ),
        "doas": _privileged("doas", OptionSpec("uC")),
        "command": _unwrap_command,
        "exec": _plain("exec", OptionSpec("a")),
        "nohup": _plain("nohup", OptionSpec()),
        "time": _plain("time", OptionSpec("fo", long_names("format output"))),
        "nice": _plain("nice", OptionSpec("n", long_names("adjustment"))),
        "ionice": _plain("ionice", OptionSpec("cnpPu", long_names("class classdata pid pgid uid"))),
        "stdbuf": _plain("stdbuf", OptionSpec("ioe", long_names("input output error"))),
        "timeout": _plain(
            "timeout", OptionSpec("sk", long_names("signal kill-after"), positional=1)
        ),
        "xargs": _unwrap_xargs,
    }
)

#: Every launcher the built-in table unwraps, and the shells whose ``-c`` is parsed (§D.2.5).
LAUNCHER_NAMES: Final = frozenset(_WRAPPERS)
SHELL_NAMES: Final = _SHELLS

_UV_LONG = (
    "python with with-editable with-requirements package extra group only-group no-group "
    "env-file directory project index default-index index-url extra-index-url find-links "
    "upgrade-package reinstall-package refresh-package no-binary-package no-build-package "
    "config-file config-setting cache-dir color resolution prerelease exclude-newer "
    "link-mode python-platform allow-insecure-host keyring-provider index-strategy from"
)
_RUNNER_OPTIONS: Final[Mapping[str, OptionSpec]] = MappingProxyType(
    {
        "uv run": OptionSpec("pPfiC", long_names(_UV_LONG)),
        "uvx": OptionSpec("pPfiC", long_names(_UV_LONG)),
        "poetry run": OptionSpec("CP", long_names("directory project")),
        "pdm run": OptionSpec("p", long_names("project venv")),
        "pipx run": OptionSpec("", long_names("spec python index-url pip-args")),
    }
)
