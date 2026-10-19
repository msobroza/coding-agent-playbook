"""The user's own prompts in a Claude transcript, by reference (specs/prK-hook-pack.md §E.5).

precompact-checkpoint must never persist prompt text, so at ``pre_compact`` it
keeps only an :class:`EntryRef` (the entry ``uuid`` and the byte offset of its
JSONL line) per **genuine** human prompt, and re-reads the text after
compaction. Genuine means typed by the user: a ``type: "user"`` entry that is
not ``isMeta`` (system reminders), not a sidechain (a subagent's prompt), not
a compact summary, not a ``tool_result`` and not a wrapper the harness writes
in the user's name (slash-command and ``!`` shell echoes, hook output).
Re-injecting any of those as "the user said" would launder prompt injection
(principle 15).

The transcript format is Claude-internal and unversioned, so any surprise (a
line that is not a JSON object, an entry without a string ``type``, a user
entry whose ``message`` is not a user message) raises
:class:`TranscriptShapeError` and the caller fails open: no checkpoint, no
injection. Reads are bounded: the selection reads the last
:data:`MAX_TAIL_BYTES`, the re-read seeks to each offset and reads one line.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, BinaryIO, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    type Opener = Callable[[str], BinaryIO]

__all__ = [
    "MAX_ENTRY_BYTES",
    "MAX_TAIL_BYTES",
    "WRAPPER_MARKERS",
    "EntryRef",
    "TranscriptShapeError",
    "human_prompt_text",
    "read_prompts",
    "select_human_prompts",
    "tail_lines",
]

#: The selection reads at most this much of the transcript's end.
MAX_TAIL_BYTES: Final = 8 * 1024 * 1024
#: A prompt line longer than this is not re-read (a huge paste is no constraint).
MAX_ENTRY_BYTES: Final = 1024 * 1024
#: Text the harness writes in the user's name; an entry holding one is not genuine.
WRAPPER_MARKERS: Final = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<user-prompt-submit-hook>",
    "<system-reminder>",
    "[Request interrupted by user",
    "Caveat: The messages below were generated",
)
#: Entry flags that mark anything but the user typing in the main thread.
_NOT_TYPED: Final = ("isMeta", "isSidechain", "isCompactSummary", "isVisibleInTranscriptOnly")
_UUID: Final = re.compile(r"[A-Za-z0-9-]{1,64}")


class TranscriptShapeError(Exception):
    """The transcript is not in a shape this reader knows; never names its content.

    Example::

        >>> str(TranscriptShapeError("the line at byte 0 is not JSON"))
        'the line at byte 0 is not JSON'
    """


@dataclass(frozen=True, slots=True)
class EntryRef:
    """Where a genuine prompt lives: its entry ``uuid`` and its line's byte offset.

    Example: ``EntryRef("u-0001", 1024).to_json() == {"uuid": "u-0001", "offset": 1024}``.
    """

    uuid: str
    offset: int

    def to_json(self) -> dict[str, object]:
        """The checkpoint form: ids and offsets only."""
        return {"uuid": self.uuid, "offset": self.offset}

    @classmethod
    def from_json(cls, raw: object) -> EntryRef | None:
        """The ref a checkpoint row holds, or ``None`` for a malformed (hand-edited) row."""
        if not isinstance(raw, dict):
            return None
        uuid, offset = raw.get("uuid"), raw.get("offset")
        if not isinstance(uuid, str) or not _UUID.fullmatch(uuid):
            return None
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            return None
        return cls(uuid, offset)


def human_prompt_text(record: object) -> str | None:
    """The text the user typed in ``record``, or ``None`` when it is no genuine prompt.

    Raises :class:`TranscriptShapeError` for an entry of unknown shape.

    Example::

        >>> human_prompt_text({"type": "user", "uuid": "u1",
        ...                    "message": {"role": "user", "content": "do not push"}})
        'do not push'
    """
    if not isinstance(record, dict) or not isinstance(record.get("type"), str):
        raise TranscriptShapeError("an entry is not an object with a string 'type'")
    if record["type"] != "user" or "toolUseResult" in record:
        return None
    if any(record.get(flag) is True for flag in _NOT_TYPED):
        return None
    message = record.get("message")
    if not isinstance(message, dict) or message.get("role") != "user":
        raise TranscriptShapeError("a user entry has no user 'message' object")
    text = _content_text(message.get("content"))
    if text is None or not text.strip() or any(m in text for m in WRAPPER_MARKERS):
        return None
    return text


def _content_text(content: object) -> str | None:
    """A message's text: the string, or its ``text`` blocks; ``None`` for a tool result."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise TranscriptShapeError("a user message's content is neither text nor blocks")
    texts: list[str] = []
    for block in content:
        kind = block.get("type") if isinstance(block, dict) else None
        if not isinstance(kind, str):
            raise TranscriptShapeError("a content block has no string 'type'")
        if kind == "tool_result":
            return None
        if kind == "text":
            texts.append(_block_text(block))
    return "\n".join(texts) if texts else None


def _block_text(block: dict[str, Any]) -> str:
    text = block.get("text")
    if not isinstance(text, str):
        raise TranscriptShapeError("a text block has no string 'text'")
    return text


def select_human_prompts(lines: Iterable[tuple[int, object]], *, limit: int) -> list[EntryRef]:
    """Refs to the last ``limit`` genuine prompts among ``(offset, record)`` lines, oldest first.

    Pure. Raises :class:`TranscriptShapeError` for any entry of unknown shape.

    Example::

        >>> select_human_prompts([(0, prompt_entry), (90, tool_result_entry)], limit=10)
        ... # doctest: +SKIP
        [EntryRef(uuid='u-0001', offset=0)]
    """
    refs = [
        EntryRef(_uuid(record), offset)
        for offset, record in lines
        if human_prompt_text(record) is not None
    ]
    return refs[-limit:] if limit > 0 else []


def _uuid(record: object) -> str:
    uuid = record.get("uuid") if isinstance(record, dict) else None
    if not isinstance(uuid, str) or not _UUID.fullmatch(uuid):
        raise TranscriptShapeError("a user prompt entry has no well-formed 'uuid'")
    return uuid


def tail_lines(
    path: str, *, max_bytes: int = MAX_TAIL_BYTES, opener: Opener | None = None
) -> list[tuple[int, object]]:
    """``(byte offset, decoded record)`` of each whole line in the last ``max_bytes`` of ``path``.

    A final line still being written (no newline, not JSON yet) is skipped.
    Raises :class:`TranscriptShapeError` when the file cannot be read or a line
    is not JSON.

    Example::

        >>> tail_lines("/home/u/.claude/projects/p/s.jsonl")[0]  # doctest: +SKIP
        (0, {'type': 'summary', ...})
    """
    try:
        with (opener or _open_binary)(path) as handle:
            base = max(0, handle.seek(0, os.SEEK_END) - max_bytes)
            handle.seek(base)
            data = handle.read(max_bytes)
    except OSError as exc:
        raise TranscriptShapeError(f"cannot read the transcript: {exc.strerror}") from None
    if base > 0:  # the window starts mid-line: drop that partial line
        cut = data.find(b"\n") + 1
        base, data = base + cut, data[cut:] if cut else b""
    return list(_decoded(data, base))


def _decoded(data: bytes, base: int) -> Iterator[tuple[int, object]]:
    offset = 0
    lines = data.split(b"\n")
    for index, line in enumerate(lines):
        start, offset = offset, offset + len(line) + 1
        if not line.strip():
            continue
        try:
            yield base + start, json.loads(line)
        except ValueError:  # JSONDecodeError and UnicodeDecodeError alike
            if index == len(lines) - 1:
                return  # torn: the harness is still appending it
            raise TranscriptShapeError(f"the line at byte {base + start} is not JSON") from None


def read_prompts(path: str, refs: Sequence[EntryRef], *, opener: Opener | None = None) -> list[str]:
    """The genuine prompt texts ``refs`` point at, in order; a ref that no longer does is skipped.

    Raises :class:`TranscriptShapeError` when the file cannot be read or a
    referenced entry has an unknown shape.

    Example::

        >>> read_prompts("/home/u/.claude/projects/p/s.jsonl", [EntryRef("u-0001", 0)])
        ... # doctest: +SKIP
        ['do not push']
    """
    texts: list[str] = []
    try:
        with (opener or _open_binary)(path) as handle:
            for ref in refs:
                handle.seek(ref.offset)
                text = _prompt_at(handle.readline(MAX_ENTRY_BYTES + 1), ref)
                if text is not None:
                    texts.append(text)
    except OSError as exc:
        raise TranscriptShapeError(f"cannot read the transcript: {exc.strerror}") from None
    return texts


def _prompt_at(line: bytes, ref: EntryRef) -> str | None:
    """The prompt on ``line`` when it is still the entry ``ref`` names, else ``None``."""
    if len(line) > MAX_ENTRY_BYTES:
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None  # the offset no longer starts that line: the file was rewritten
    if not isinstance(record, dict) or record.get("uuid") != ref.uuid:
        return None
    return human_prompt_text(record)


def _open_binary(path: str) -> BinaryIO:
    return open(path, "rb")
