"""Which ``stop_gate.verify_commands`` a shell command ran (specs/prK-lifecycle-hooks.md §D.6.3).

The ledger tags a ``post_tool_use`` (green) or ``post_tool_use_failure``
(red) shell call with the id of each verify command one of its segments ran,
never the command itself; verify-claim reads the tags back at Stop.

A segment matches a row when both reduce to the same core: the launchers are
stripped with ``guard_config.shell``, the very unwrapping the guards judge a
command by (the configured ``wrapper_prefixes``, the ``runner_wrappers`` such
as ``uv run --frozen`` and the built-in ``env``/``sudo``/``timeout``/...
table, ``shell.wrappers``), then a leading ``python -m``. The program must be
the same and every remaining word of the row must appear in the segment:
``proxy uv run pytest -q tests/x.py`` ran ``pytest`` once ``proxy`` is a
configured wrapper; ``ruff check src`` ran ``ruff check``. The command is
parsed with ``cfg.shell`` here, whatever config the caller's ``ToolCall``
carried, so tagging can never disagree with the guards.
"""

from __future__ import annotations

import posixpath
import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.shell.tokens import ScanError, Word
from coding_agent_playbook.hook_runtime.shell.wrappers import DEFAULT_SHELL_CONFIG, unwrap

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.event import ToolCall
    from coding_agent_playbook.hook_runtime.shell.parse import ShellCommand
    from coding_agent_playbook.hook_runtime.shell.wrappers import ShellConfig

__all__ = ["verify_ids"]

_PYTHON: Final = re.compile(r"python(?:\d+(?:\.\d+)?)?(?:\.exe)?")


def verify_ids(tool: ToolCall, cfg: GuardConfig) -> list[str]:
    """The ids of the verify commands ``tool``'s shell segments ran, in row order, once each.

    Example::

        >>> verify_ids(bash("proxy uv run pytest -q"), cfg)  # doctest: +SKIP
        ['tests']
    """
    rows = _rows(cfg)
    command = _command(tool, cfg.shell) if rows else None
    if command is None:
        return []
    cores = [_core(segment.argv, cfg.shell) for segment in command.segments]
    return [verify_id for verify_id, row in rows if any(_runs(core, row) for core in cores)]


def _command(tool: ToolCall, shell: ShellConfig) -> ShellCommand | None:
    """``tool``'s command parsed with ``shell``; the memoized parse when it already is."""
    if tool.shell is None:
        return None
    if (tool.shell.config or DEFAULT_SHELL_CONFIG) != shell:
        tool = tool.with_shell_config(shell)
    return tool.command


def _rows(cfg: GuardConfig) -> list[tuple[str, list[str]]]:
    found: list[tuple[str, list[str]]] = []
    for command in cfg.tables.stop_gate().verify_commands:
        core = _core(command.argv, cfg.shell)
        if core:
            found.append((command.id, core))
    return found


def _core(argv: Sequence[str], shell: ShellConfig) -> list[str]:
    """``argv`` without its launchers and a leading ``python -m``, the program a basename.

    A parsed segment is already unwrapped; unwrapping it again is a no-op, and
    it covers the raw words of a command the parser could not follow. A
    launcher that cannot be read (an unbalanced ``env -S``) names no program.
    """
    try:
        words = [word.value for word in unwrap([Word(value) for value in argv], shell).argv]
    except ScanError:
        return []  # the ledger write must never raise (_post_write)
    if len(words) >= 2 and _PYTHON.fullmatch(posixpath.basename(words[0])) and words[1] == "-m":
        words = words[2:]
    return [posixpath.basename(words[0]), *words[1:]] if words else []


def _runs(core: Sequence[str], row: Sequence[str]) -> bool:
    return bool(core) and core[0] == row[0] and set(row[1:]) <= set(core[1:])
