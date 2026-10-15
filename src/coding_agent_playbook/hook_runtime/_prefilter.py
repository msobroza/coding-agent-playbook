"""The shell-guard prefilter: no guard code runs without a matching argv0 (specs/prK-hook-pack.md §E.4).

A guard declares the commands it inspects (``register_hook_handler(argv0s=...)``,
``mkfs*`` being a prefix) and may name a config key whose row tables add an
``argv0`` each (destructive-command-guard's overlay ``extra_rows``). On a shell
tool call, the dispatcher computes the argv0 set of the command's segments (a
set over at most 256 basenames: cheaper than caching it) and calls a declaring
guard only when one of its argv0s is in it.

The prefilter never hides a command it cannot read: a command the parser could
not follow (``parse_error``) or a PowerShell one (no segments) passes, so the
guard takes its own conservative branch. A handler that declares no
``argv0s``, and every non-shell call, is never filtered.
"""

from __future__ import annotations

import posixpath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerDeclaration
    from coding_agent_playbook.hook_runtime.shell import ShellCommand

__all__ = ["argv0_matches", "command_argv0s", "skips_call"]


def command_argv0s(command: ShellCommand) -> frozenset[str] | None:
    """The basename of every segment's argv0; ``None`` when the command cannot be trusted.

    Example::

        >>> from coding_agent_playbook.hook_runtime.shell import parse_shell
        >>> sorted(command_argv0s(parse_shell("cd a && /bin/rm -rf b | tee x", "posix", "/r")))
        ['cd', 'rm', 'tee']
    """
    if command.parse_error is not None or command.kind != "posix":
        return None
    return frozenset(posixpath.basename(s.argv[0]) for s in command.segments if s.argv)


def argv0_matches(names: Iterable[str], patterns: Iterable[str]) -> bool:
    """Whether any of ``names`` is one of ``patterns`` (a trailing ``*`` is a prefix).

    Example::

        >>> argv0_matches(["mkfs.ext4"], ["rm", "mkfs*"]), argv0_matches(["ls"], ["rm"])
        (True, False)
    """
    wanted = list(patterns)
    exact = {p for p in wanted if not p.endswith("*")}
    prefixes = tuple(p[:-1] for p in wanted if p.endswith("*"))
    return any(name in exact or (prefixes and name.startswith(prefixes)) for name in names)


def skips_call(
    declaration: HandlerDeclaration | None, ev: CanonicalEvent, config: Mapping[str, Any]
) -> bool:
    """Whether the dispatcher may skip ``declaration``'s handler on ``ev`` (module docstring).

    Example: a guard declaring ``argv0s={"git"}`` is skipped on ``Bash: ls``.
    """
    if declaration is None or declaration.argv0s is None:
        return False
    command = ev.tool.command if ev.tool is not None else None
    if command is None:
        return False
    names = command_argv0s(command)
    if names is None:
        return False
    patterns = [*declaration.argv0s, *_row_argv0s(config, declaration.argv0_rows)]
    return not argv0_matches(names, patterns)


def _row_argv0s(config: Mapping[str, Any], key: str | None) -> list[str]:
    """The ``argv0`` of each row table under config ``key``."""
    rows = config.get(key) if key is not None else None
    if not isinstance(rows, list | tuple):
        return []
    found = (row.get("argv0") for row in rows if isinstance(row, dict))
    return [name for name in found if isinstance(name, str) and name]
