"""The prompt that opened the current turn, read from the end of a Claude transcript (specs/prK-hook-pack.md §E.3).

The active-prompt record (``active_prompt``) is derived when a consumer first
needs it in a turn, so no ``user_prompt_submit`` process runs for it (review
finding #6). :func:`last_prompt_boundary` reads ``transcript_path`` backwards
to the newest entry a user turn opens with: a main-thread user entry (not
``isMeta``, a sidechain, a compact summary or a tool result) whose text is not
a harness echo (local-command output, ``!`` shell echoes, hook output, an
interruption). Its slash is what :func:`slash_of_prompt` finds: a typed
``/review-core`` or the harness's ``<command-name>`` wrapper.

Reads are bounded: windows of 64 KiB, 1 MiB, then 8 MiB from the end, and only
lines naming the ``"user"`` role are decoded. A user line that is not JSON
(other than the one still being written) or has an unknown shape, an
unreadable file, or no boundary inside the bound is *unknown* (``None``), and
the consumers then see no active prompt: uncertain detection fails open. Only
the slash and the entry's uuid leave this module; no prompt text is kept.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, BinaryIO, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    type Opener = Callable[[str], BinaryIO]

__all__ = ["WINDOWS", "PromptBoundary", "last_prompt_boundary", "slash_of_prompt"]

#: The read windows from the end of the transcript, each tried only when the last found nothing.
WINDOWS: Final = (64 * 1024, 1024 * 1024, 8 * 1024 * 1024)
#: Text the harness writes in the user's name that is no new prompt (commands are: see below).
_ECHOES: Final = (
    "<local-command-",
    "<bash-",
    "<user-prompt-submit-hook>",
    "<system-reminder>",
    "[Request interrupted by user",
    "Caveat: The messages below were generated",
)
#: Entry flags that mark anything but the user typing in the main thread.
_NOT_TYPED: Final = ("isMeta", "isSidechain", "isCompactSummary", "isVisibleInTranscriptOnly")
#: Only the head of a prompt is searched for the command wrapper.
_SCAN_CHARS: Final = 4096
_NAME: Final = r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"
_RAW: Final = re.compile(rf"/({_NAME})(?:\s|$)")
_WRAPPER: Final = re.compile(rf"<command-name>\s*/?({_NAME})\s*</command-name>")


class _Unknown(Exception):
    """A user line this reader cannot classify: the boundary is unknown."""


@dataclass(frozen=True, slots=True)
class PromptBoundary:
    """The entry that opened the turn: its transcript ``uuid`` and the slash it ran, if any.

    Example: ``PromptBoundary("u-0007", "review-core")`` for a ``/review-core`` turn.
    """

    uuid: str | None
    slash: str | None


def slash_of_prompt(text: str) -> str | None:
    """The slash a prompt invokes, raw or inside the command wrapper; else ``None``.

    Only a prompt that *starts* with the command counts: ``please /review-core``
    is prose, not an invocation, and an unrecognized wrapper is no command.

    Example::

        >>> slash_of_prompt("/security-review-core src/app.py")
        'security-review-core'
        >>> slash_of_prompt("fix it") is None
        True
    """
    head = text[:_SCAN_CHARS].lstrip()
    raw = _RAW.match(head)
    if raw is not None:
        return raw.group(1)
    if not head.startswith("<command-"):
        return None
    wrapped = _WRAPPER.search(head)
    return wrapped.group(1) if wrapped is not None else None


def last_prompt_boundary(
    path: str | None, *, windows: Sequence[int] = WINDOWS, opener: Opener | None = None
) -> PromptBoundary | None:
    """The newest turn-opening entry of the transcript at ``path``; ``None`` when unknown.

    Example::

        >>> last_prompt_boundary("/home/u/.claude/projects/p/s.jsonl")  # doctest: +SKIP
        PromptBoundary(uuid='u-0007', slash='review')
    """
    if not path:
        return None
    try:
        with (opener or _open_binary)(path) as handle:
            return _scan(handle, windows)
    except (OSError, _Unknown):
        return None


def _scan(handle: BinaryIO, windows: Sequence[int]) -> PromptBoundary | None:
    """Each window from the end, newest line first, skipping lines a smaller window examined."""
    size = handle.seek(0, os.SEEK_END)
    examined = size
    for window in windows:
        start = max(0, size - window)
        handle.seek(start)
        lines = _whole_lines(handle.read(size - start), start)
        for offset, line in reversed(lines):
            found = _boundary(line) if offset < examined else None
            if found is not None:
                return found
        if start == 0:
            return None
        examined = lines[0][0] if lines else examined
    return None


def _whole_lines(data: bytes, base: int) -> list[tuple[int, bytes]]:
    """``(offset, line)`` of every complete line; a window's cut first line and a torn last go."""
    pieces = data.split(b"\n")[:-1]  # after the last newline: nothing, or a line being written
    lines: list[tuple[int, bytes]] = []
    offset = base
    for index, piece in enumerate(pieces):
        if piece.strip() and (base == 0 or index > 0):
            lines.append((offset, piece))
        offset += len(piece) + 1
    return lines


def _boundary(line: bytes) -> PromptBoundary | None:
    """The boundary ``line`` is, ``None`` for any other entry; raises :class:`_Unknown`."""
    if b'"user"' not in line or b'"toolUseResult":' in line:
        return None  # not a user entry, or a tool result: never decoded
    try:
        record = json.loads(line)
    except ValueError:
        raise _Unknown from None
    if not isinstance(record, dict) or record.get("type") != "user" or "toolUseResult" in record:
        return None
    if any(record.get(flag) is True for flag in _NOT_TYPED):
        return None
    text = _text(record.get("message"))
    if text is None or text.lstrip().startswith(_ECHOES):
        return None
    uuid = record.get("uuid")
    return PromptBoundary(uuid if isinstance(uuid, str) and uuid else None, slash_of_prompt(text))


def _text(message: Any) -> str | None:
    """A user message's text (its ``text`` blocks joined); ``None`` for a tool result."""
    if not isinstance(message, dict) or message.get("role") != "user":
        raise _Unknown
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise _Unknown
    blocks = [block for block in content if isinstance(block, dict)]
    if any(block.get("type") == "tool_result" for block in blocks):
        return None
    texts = [block.get("text") for block in blocks if block.get("type") == "text"]
    return "\n".join(text for text in texts if isinstance(text, str))


def _open_binary(path: str) -> BinaryIO:
    return open(path, "rb")
