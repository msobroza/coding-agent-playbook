"""``write_targets``: the files one shell segment writes (specs/prK-lifecycle-hooks.md §D.2.5).

This is the shared extractor the §E file guards read: redirect targets,
``tee`` operands, ``sed -i`` / ``perl -i`` files, ``cp``/``mv``/``install``
destinations, and ``rm``/``truncate``/``dd of=`` operands. Sources are never
returned, so ``cp AGENTS.md /tmp/x`` yields only ``/tmp/x``. Targets are raw
strings; the caller normalizes them against ``Segment.cwd``. Ambiguous option
syntax resolves toward returning more targets, which is the safe direction
for a guard.
"""

from __future__ import annotations

import posixpath
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._shell_options import OptionSpec, long_names, option_arity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.hook_runtime._shell_segments import Redirect, Segment

_FILE_WRITE_OPS = frozenset({">", ">>", ">|", "&>", "&>>", "<>"})
_FD_TARGET = re.compile(r"\d+|-")
_FLAGS_ONLY = OptionSpec()


def write_targets(segment: Segment) -> list[str]:
    """The files ``segment`` writes, in order: redirect targets, then argv operands.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell import parse_shell
        >>> write_targets(parse_shell("cp AGENTS.md /tmp/x", "posix", "/r").segments[0])
        ['/tmp/x']
    """
    targets = [r.target for r in segment.redirects if r.target is not None and _writes(r)]
    if segment.argv:
        extract = _ARGV_WRITERS.get(posixpath.basename(segment.argv[0]))
        if extract is not None:
            targets.extend(extract(list(segment.argv[1:])))
    return targets


def _writes(redirect: Redirect) -> bool:
    """Whether a redirect opens a file for writing (``2>&1`` and ``>&-`` only dup or close)."""
    if redirect.op == ">&":
        return redirect.target is not None and not _FD_TARGET.fullmatch(redirect.target)
    return redirect.op in _FILE_WRITE_OPS


def operands(args: list[str], spec: OptionSpec = _FLAGS_ONLY) -> list[str]:
    """The non-option arguments; GNU tools take options anywhere, and ``--`` ends them.

    Example::

        >>> operands(["-s", "0", "f", "-c"], OptionSpec("s"))
        ['f']
    """
    found: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            return found + args[index + 1 :]
        if arg.startswith("-") and arg != "-":
            index += 1 + option_arity(arg, spec)
            continue
        found.append(arg)
        index += 1
    return found


def _in_place_files(args: list[str], script_letters: str, arg_letters: str) -> list[str]:
    """Files edited by ``sed -i`` / ``perl -i``: the operands, minus the script without ``-e``.

    The rest of an ``-i`` cluster is the backup suffix (``-i.bak``); a letter in
    ``script_letters`` supplies the script, and it or one in ``arg_letters``
    takes the rest of its cluster or the next word as its argument.
    """
    in_place = has_script = False
    found: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--":
            found.extend(args[index:])
            break
        if arg.startswith("--"):
            name = arg.partition("=")[0]
            in_place |= name == "--in-place"
            has_script |= name in ("--expression", "--file")
            index += int("=" not in arg and name in ("--expression", "--file", "--line-length"))
            continue
        if not arg.startswith("-") or arg == "-":
            found.append(arg)
            continue
        for offset, letter in enumerate(arg[1:], 1):
            if letter == "i":
                in_place = True
                # BSD sed spells "no backup" as a separate empty suffix: `sed -i '' ...`.
                index += int(arg == "-i" and args[index : index + 1] == [""])
                break
            if letter in script_letters or letter in arg_letters:
                has_script |= letter in script_letters
                index += int(offset == len(arg) - 1)
                break
    if not in_place:
        return []
    return found if has_script else found[1:]


def _sed_files(args: list[str]) -> list[str]:
    return _in_place_files(args, "ef", "l")


def _perl_files(args: list[str]) -> list[str]:
    return _in_place_files(args, "eE", "IMm")


def _destination(spec: OptionSpec) -> Callable[[list[str]], list[str]]:
    """``cp``/``mv``: the ``-t DIR`` target directory, else the last of two or more operands."""

    def extract(args: list[str]) -> list[str]:
        directory = _target_directory(args)
        if directory is not None:
            return [directory]
        found = operands(args, spec)
        return found[-1:] if len(found) >= 2 else []

    return extract


def _target_directory(args: list[str]) -> str | None:
    """The ``-t DIR`` / ``--target-directory=DIR`` value, wherever ``t`` sits in a cluster."""
    for index, arg in enumerate(args):
        following = args[index + 1] if index + 1 < len(args) else None
        if arg == "--":
            return None
        if arg == "--target-directory":
            return following
        if arg.startswith("--target-directory="):
            return arg.partition("=")[2]
        if arg[:1] == "-" and arg[:2] != "--":
            cluster = arg[1:].partition("S")[0]  # S takes the rest of the cluster
            if "t" in cluster:
                return arg[arg.index("t") + 1 :] or following
    return None


def _install_files(args: list[str]) -> list[str]:
    """``install -d`` creates every operand; otherwise it copies like ``cp``."""
    if "--directory" in args or any(a[:1] == "-" and a[:2] != "--" and "d" in a for a in args):
        return operands(args, _INSTALL)
    return _destination(_INSTALL)(args)


def _dd_files(args: list[str]) -> list[str]:
    return [arg[len("of=") :] for arg in args if arg.startswith("of=")]


_INSTALL = OptionSpec("moStgZ", long_names("mode owner group suffix"))
_COPY = OptionSpec("tS", long_names("target-directory suffix"))
_TRUNCATE = OptionSpec("sr", long_names("size reference"))

_ARGV_WRITERS: Final[Mapping[str, Callable[[list[str]], list[str]]]] = MappingProxyType(
    {
        "tee": operands,
        "sed": _sed_files,
        "perl": _perl_files,
        "cp": _destination(_COPY),
        "mv": _destination(_COPY),
        "install": _install_files,
        "rm": operands,
        "truncate": lambda args: operands(args, _TRUNCATE),
        "dd": _dd_files,
    }
)
