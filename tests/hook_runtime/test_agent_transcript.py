"""The subagent transcript reader of subagent-stop-verify (specs/prK-hook-pack.md §E.2).

It reads ``agent_transcript_path`` read-only, keeps only the ``file_path``
inputs of Edit/Write/MultiEdit ``tool_use`` blocks, and raises on anything it
cannot parse so the hook fails open with ``NOT verified``. The opener seam
lets a spy see every ``open``.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any, BinaryIO

import pytest

from coding_agent_playbook.hook_runtime import _agent_transcript
from coding_agent_playbook.hook_runtime._agent_transcript import TranscriptError, edited_files

if TYPE_CHECKING:
    from pathlib import Path


def _use(name: str, **tool_input: Any) -> dict[str, Any]:
    content = [
        {"type": "text", "text": "editing"},
        {"type": "tool_use", "name": name, "input": tool_input},
    ]
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def _jsonl(*records: Any) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


class SpyOpener:
    """Serves one transcript's bytes and records every path and nothing else."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.opened: list[str] = []

    def __call__(self, path: str) -> BinaryIO:
        self.opened.append(path)
        return io.BytesIO(self.data)


def test_edit_write_multiedit_paths_in_first_seen_order() -> None:
    spy = SpyOpener(
        _jsonl(
            {"type": "user", "message": {"role": "user", "content": "Fix a.py"}},
            _use("Read", file_path="/r/c.py"),
            _use("Edit", file_path="/r/a.py", old_string="x", new_string="y"),
            _use("Write", file_path="/r/b.py", content="z"),
            _use("MultiEdit", file_path="/r/a.py", edits=[]),
            _use("Bash", command="echo hi > /r/d.py"),
        )
        + b"\n"
    )

    assert edited_files("/t/agent.jsonl", opener=spy) == ("/r/a.py", "/r/b.py")
    assert spy.opened == ["/t/agent.jsonl"]


@pytest.mark.parametrize(
    "data",
    [b"not json\n", b'{"type": "user"}\n[1]\n', b"\xff\xfe\n"],
)
def test_malformed_transcript_raises(data: bytes) -> None:
    with pytest.raises(TranscriptError, match="line"):
        edited_files("/t/agent.jsonl", opener=SpyOpener(data))


def test_missing_or_unnamed_transcript_raises(tmp_path: Path) -> None:
    with pytest.raises(TranscriptError, match="cannot read"):
        edited_files(str(tmp_path / "gone.jsonl"))
    with pytest.raises(TranscriptError, match="names no agent transcript"):
        edited_files(None)


def test_oversized_transcript_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_agent_transcript, "MAX_TRANSCRIPT_BYTES", 8)

    with pytest.raises(TranscriptError, match="exceeds 8 bytes"):
        edited_files("/t/agent.jsonl", opener=SpyOpener(_jsonl({"type": "user"})))


def test_real_file_is_read_read_only(tmp_path: Path) -> None:
    path = tmp_path / "agent.jsonl"
    path.write_bytes(_jsonl(_use("Edit", file_path="/r/a.py")))
    before = path.stat().st_mtime_ns

    assert edited_files(str(path)) == ("/r/a.py",)
    assert path.stat().st_mtime_ns == before
