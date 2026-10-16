"""Claude session transcripts for the active-prompt tests (specs/prK-hook-pack.md §E.3).

The active-prompt record is derived from ``transcript_path`` when a consumer
first needs it in a turn (review finding #6), so a test writes the transcript
Claude would: :class:`SessionTranscript` appends JSONL entries in Claude's
shape (a typed prompt, the slash-command wrapper plus its ``isMeta`` body, a
tool round) and numbers the turns, whose ``prompt_id`` the payloads carry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["SessionTranscript", "command_wrapper"]


def command_wrapper(slash: str, args: str = "") -> str:
    """The user entry Claude writes for a typed ``/<slash> <args>``.

    Example: ``command_wrapper("review", "src/app.py").startswith("<command-message>")``.
    """
    return (
        f"<command-message>{slash} is running…</command-message>\n"
        f"<command-name>/{slash}</command-name>\n<command-args>{args}</command-args>"
    )


@dataclass
class SessionTranscript:
    """A Claude JSONL transcript a test appends to; ``turn`` is the current ``prompt_id``.

    Example::

        transcript = SessionTranscript(tmp_path / "s.jsonl")
        transcript.command("review", "src/app.py")
        payload = repo.tool_payload("Edit", edit, **transcript.fields())
    """

    path: Path
    turns: int = 0
    entries: int = 0

    @property
    def turn(self) -> str:
        """The current turn's ``prompt_id``."""
        return f"pr_{self.turns}"

    def fields(self) -> dict[str, str]:
        """The payload fields that point a dispatch at this transcript and turn."""
        return {"transcript_path": str(self.path), "prompt_id": self.turn}

    def typed(self, text: str) -> str:
        """The user types ``text``: a new turn. Returns its ``prompt_id``."""
        self.turns += 1
        self.append(self.user(text))
        return self.turn

    def command(self, slash: str, args: str = "") -> str:
        """The user runs ``/<slash>``: the wrapper entry, then the expanded body as ``isMeta``."""
        self.turns += 1
        self.append(self.user(command_wrapper(slash, args)))
        self.append(self.user(f"# {slash}\nDo the {slash} task.", isMeta=True))
        return self.turn

    def tool_round(self, output: str = "ok") -> None:
        """One assistant tool call and its result: entries, but no new turn."""
        tool_id = f"toolu_{self.entries:04d}"
        use = {"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": "ls"}}
        self.append({"type": "assistant", "message": {"role": "assistant", "content": [use]}})
        result = {"type": "tool_result", "tool_use_id": tool_id, "content": output}
        self.append(self.user([result], toolUseResult={"stdout": output}))

    def user(self, content: object, **flags: Any) -> dict[str, Any]:
        """A main-thread user entry holding ``content`` (``flags``: ``isMeta`` and the like)."""
        return {
            "type": "user",
            "uuid": f"u-{self.entries:04d}",
            "isSidechain": False,
            "userType": "external",
            "message": {"role": "user", "content": content},
            **flags,
        }

    def append(self, entry: dict[str, Any] | str) -> None:
        """Append one entry (a raw ``str`` is written as is, for malformed-line cases)."""
        line = entry if isinstance(entry, str) else json.dumps(entry, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self.entries += 1
