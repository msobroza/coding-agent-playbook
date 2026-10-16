"""The files a subagent edited, read from its transcript (specs/prK-hook-pack.md §E.2 subagent-stop-verify).

Claude's ``SubagentStop`` names the subagent's own JSONL transcript in
``agent_transcript_path``. :func:`edited_files` reads it **read-only** and
keeps only tool inputs: the ``file_path`` of each ``Edit``, ``Write`` and
``MultiEdit`` ``tool_use`` block, in first-seen order. Message text is never
looked at, stored or logged (D-10).

A missing path, an unreadable or oversized file, or a line that is not a JSON
object raises :class:`TranscriptError`: the caller fails open with
``NOT verified`` instead of guessing a scope. The opener is injectable so a
test can spy on every ``open``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, BinaryIO, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    type Opener = Callable[[str], BinaryIO]

__all__ = ["EDIT_TOOLS", "MAX_TRANSCRIPT_BYTES", "TranscriptError", "edited_files"]

#: The tools whose ``file_path`` input is an edit (Claude Code tool names).
EDIT_TOOLS: Final = frozenset({"Edit", "Write", "MultiEdit"})
#: A subagent transcript larger than this is not parsed (NOT verified instead).
MAX_TRANSCRIPT_BYTES: Final = 64 * 1024 * 1024


class TranscriptError(Exception):
    """The transcript cannot be read as JSONL; the message says why, never what it holds.

    Example::

        >>> str(TranscriptError("line 3 is not a JSON object"))
        'line 3 is not a JSON object'
    """


def edited_files(path: str | None, *, opener: Opener | None = None) -> tuple[str, ...]:
    """The ``file_path`` inputs of the transcript's Edit/Write/MultiEdit calls, as written.

    Raises :class:`TranscriptError` for a missing, unreadable, oversized or malformed file.

    Example::

        >>> edited_files("/home/u/.claude/projects/p/agent_42.jsonl")  # doctest: +SKIP
        ('/repo/src/a.py',)
    """
    if not path:
        raise TranscriptError("the event names no agent transcript")
    found: dict[str, None] = {}
    for number, record in enumerate(_records(path, opener or _open_binary), 1):
        if not isinstance(record, dict):
            raise TranscriptError(f"line {number} is not a JSON object")
        found.update(dict.fromkeys(_edit_paths(record)))
    return tuple(found)


def _records(path: str, opener: Opener) -> Iterator[Any]:
    """Each non-blank JSONL line of ``path``, decoded; bounded by :data:`MAX_TRANSCRIPT_BYTES`."""
    try:
        with opener(path) as handle:
            data = handle.read(MAX_TRANSCRIPT_BYTES + 1)
    except OSError as exc:
        raise TranscriptError(f"cannot read the agent transcript: {exc.strerror}") from None
    if len(data) > MAX_TRANSCRIPT_BYTES:
        raise TranscriptError(f"the agent transcript exceeds {MAX_TRANSCRIPT_BYTES} bytes")
    for number, line in enumerate(data.splitlines(), 1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except ValueError:  # JSONDecodeError and UnicodeDecodeError alike
            raise TranscriptError(f"line {number} is not JSON") from None


def _edit_paths(record: dict[str, Any]) -> Iterable[str]:
    """The edit ``file_path`` inputs of one transcript record's ``tool_use`` blocks."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    for block in content if isinstance(content, list) else ():
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        tool_input = block.get("input")
        if block.get("name") in EDIT_TOOLS and isinstance(tool_input, dict):
            file_path = tool_input.get("file_path")
            if isinstance(file_path, str) and file_path:
                yield file_path


def _open_binary(path: str) -> BinaryIO:
    return open(path, "rb")
