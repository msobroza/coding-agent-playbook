"""Shell parsing for the Bash guards (specs/prK-lifecycle-hooks.md §D.2.5).

``parse_shell`` turns command text into ``Segment``s, one per simple command
that will run: the effective argv after env prefixes and launchers are
stripped, plus its redirects, heredoc bodies (data only, never parsed as
commands), cwd and provenance. Command substitutions, shell ``-c`` scripts,
``eval`` and ``find -exec`` commands become segments of their own.
``write_targets`` lists the files one segment writes.

Degradation is explicit. A text the lexer cannot follow sets ``parse_error``
and falls back to a regex split; exceeding a limit (64 KiB of text, nesting
depth 4, 256 segments, 4 launchers) sets ``parse_error = "limit"``. Every
handler then treats the command as unknown and takes its conservative branch.
PowerShell is never shlex-parsed: its segments are empty and handlers apply
their PowerShell regex rows.

The work is split over private modules to keep each under §D.1's 300 lines:
``_shell_tokens`` / ``_shell_scan`` (lexer), ``_shell_options`` and
``_shell_wrappers`` (launchers), ``_shell_segments`` (assembly) and
``_shell_writes`` (``write_targets``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal

from coding_agent_playbook.hook_runtime._shell_scan import scan
from coding_agent_playbook.hook_runtime._shell_segments import (
    MAX_SEGMENTS,
    Redirect,
    Segment,
    build_segments,
)
from coding_agent_playbook.hook_runtime._shell_tokens import MAX_DEPTH, ScanError, ScanLimit
from coding_agent_playbook.hook_runtime._shell_wrappers import (
    DEFAULT_SHELL_CONFIG,
    SegmentOrigin,
    ShellConfig,
)
from coding_agent_playbook.hook_runtime._shell_writes import write_targets

__all__ = [
    "DEFAULT_SHELL_CONFIG",
    "LIMIT",
    "MAX_DEPTH",
    "MAX_SEGMENTS",
    "MAX_TEXT_BYTES",
    "Redirect",
    "Segment",
    "SegmentOrigin",
    "ShellCommand",
    "ShellConfig",
    "ShellKind",
    "parse_shell",
    "write_targets",
]

type ShellKind = Literal["posix", "powershell"]

MAX_TEXT_BYTES: Final = 64 * 1024
#: The ``parse_error`` value for every exceeded limit.
LIMIT: Final = "limit"

_FALLBACK_SPLIT = re.compile(r";|&&|\|\||\||\n")


@dataclass(frozen=True, slots=True)
class ShellCommand:
    """A parsed command text; ``parse_error`` set means handlers treat it as unknown.

    Example::

        >>> parse_shell("echo 'open", "posix", "/r").parse_error is not None
        True
    """

    text: str = field(repr=False)
    kind: ShellKind
    segments: tuple[Segment, ...]
    parse_error: str | None = None


def parse_shell(
    text: str, kind: ShellKind, cwd: str | None, cfg: ShellConfig = DEFAULT_SHELL_CONFIG
) -> ShellCommand:
    """Parse ``text`` into the segments that will run, starting in ``cwd``.

    ``cfg`` supplies the ``wrapper_prefixes`` and ``runner_wrappers``
    (``guard_config.shell``). The function is pure: it executes and expands
    nothing.

    Example::

        >>> parse_shell("cd sub && sudo rm -rf x", "posix", "/r").segments[1].argv
        ('rm', '-rf', 'x')
    """
    if kind == "powershell":
        return ShellCommand(text, kind, ())
    if len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
        return _degraded(text, cwd, LIMIT)
    try:
        segments = build_segments(scan(text), cwd, cfg)
    except ScanLimit:
        return _degraded(text, cwd, LIMIT)
    except ScanError as exc:
        return _degraded(text, cwd, str(exc))
    return ShellCommand(text, kind, segments)


def _degraded(text: str, cwd: str | None, reason: str) -> ShellCommand:
    """The best-effort regex split every handler treats as unknown."""
    pieces = (piece.split() for piece in _FALLBACK_SPLIT.split(text[:MAX_TEXT_BYTES]))
    segments = [Segment(argv=tuple(p), raw_argv=tuple(p), cwd=cwd) for p in pieces if p]
    return ShellCommand(text, "posix", tuple(segments[:MAX_SEGMENTS]), reason)
