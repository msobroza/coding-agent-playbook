"""Redis stream commands, built as argument lists for an injected executor."""

from collections.abc import Callable
from typing import Any

Executor = Callable[..., Any]


class StreamCommands:
    """Builds stream commands and hands them to ``execute_command``."""

    def __init__(self, execute_command: Executor) -> None:
        self.execute_command = execute_command

    def xlen(self, name: str) -> Any:
        """Return the number of entries in the stream ``name``."""
        return self.execute_command("XLEN", name)

    def xtrim(
        self,
        name: str,
        maxlen: int | None = None,
        approximate: bool = True,
        minid: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """Trim old entries from the stream ``name``.

        maxlen: keep at most this many entries.
        approximate: let the server keep slightly more than maxlen, which is faster.
        minid: evict the entries whose id is lower than this one.
        limit: evict at most this many entries in one call.
        """
        pieces: list[Any] = []
        if maxlen is not None:
            pieces.append(b"MAXLEN")
        if minid is not None:
            pieces.append(b"MINID")
        if approximate:
            pieces.append(b"~")
        if maxlen is not None:
            pieces.append(maxlen)
        if minid is not None:
            pieces.append(minid)
        if limit is not None:
            pieces.append(b"LIMIT")
            pieces.append(limit)
        return self.execute_command("XTRIM", name, *pieces)
