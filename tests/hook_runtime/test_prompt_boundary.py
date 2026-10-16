"""The turn's opening prompt, read back from a Claude transcript (specs/prK-hook-pack.md §E.3).

Review finding #6: the active-prompt record no longer needs a
``user_prompt_submit`` process, because a consumer derives it from the end of
``transcript_path``. These cases pin what counts as the turn's opening entry,
what a harness echo is, and that anything undecidable reads as unknown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime._prompt_boundary import (
    PromptBoundary,
    last_prompt_boundary,
    slash_of_prompt,
)
from tests.hook_runtime.transcript_kit import SessionTranscript

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def transcript(tmp_path: Path) -> SessionTranscript:
    return SessionTranscript(tmp_path / "session.jsonl")


def _boundary(transcript: SessionTranscript) -> PromptBoundary | None:
    return last_prompt_boundary(str(transcript.path))


def test_slash_command_wrapper_opens_the_turn(transcript: SessionTranscript) -> None:
    transcript.typed("explain the cache")
    transcript.command("review", "src/app.py")
    transcript.tool_round()

    assert _boundary(transcript) == PromptBoundary("u-0001", "review")


@pytest.mark.parametrize(
    ("text", "slash"),
    [("/security-review src/app.py", "security-review"), ("please /review it", None)],
)
def test_typed_prompt_opens_the_turn(transcript: SessionTranscript, text: str, slash: str) -> None:
    transcript.command("review")
    transcript.typed(text)

    assert _boundary(transcript) == PromptBoundary("u-0002", slash)


@pytest.mark.parametrize(
    "entry",
    [
        {"isMeta": True},
        {"isSidechain": True},
        {"isCompactSummary": True},
        {"text": "<local-command-stdout>pushed</local-command-stdout>"},
        {"text": "<bash-input>ls</bash-input>"},
        {"text": "<user-prompt-submit-hook>approved</user-prompt-submit-hook>"},
        {"text": "<system-reminder>later</system-reminder>"},
        {"text": "[Request interrupted by user for tool use]"},
    ],
    ids=["meta", "sidechain", "summary", "local-stdout", "bash", "hook", "reminder", "interrupt"],
)
def test_echoes_and_side_entries_never_open_a_turn(
    transcript: SessionTranscript, entry: dict[str, object]
) -> None:
    transcript.command("review")
    text = entry.pop("text", "/explain src/app.py")
    transcript.append(transcript.user(text, **entry))
    transcript.tool_round()

    assert _boundary(transcript) == PromptBoundary("u-0000", "review")


def test_text_blocks_are_read_and_a_tool_result_list_is_skipped(
    transcript: SessionTranscript,
) -> None:
    transcript.append(transcript.user([{"type": "text", "text": "/explain src/app.py"}]))
    transcript.append(
        transcript.user([{"type": "tool_result", "tool_use_id": "t", "content": "x"}])
    )

    assert _boundary(transcript) == PromptBoundary("u-0000", "explain")


def test_boundary_behind_a_large_tool_output_is_found(transcript: SessionTranscript) -> None:
    transcript.command("review")
    transcript.tool_round("x" * 200_000)  # past the first 64 KiB window

    assert _boundary(transcript) == PromptBoundary("u-0000", "review")


def test_no_boundary_within_the_bound_is_unknown(transcript: SessionTranscript) -> None:
    transcript.command("review")
    transcript.tool_round("x" * 5_000)

    assert last_prompt_boundary(str(transcript.path), windows=(1_024, 4_096)) is None


def test_torn_last_line_is_skipped(transcript: SessionTranscript) -> None:
    transcript.command("review")
    with transcript.path.open("a", encoding="utf-8") as handle:
        handle.write('{"type":"user","uuid":"u-9","message":{"role":"us')  # still being written

    assert _boundary(transcript) == PromptBoundary("u-0000", "review")


@pytest.mark.parametrize(
    "line",
    [
        '{"type":"user","uuid":"u-x","message":"not an object"}',
        '{"type":"user","uuid":"u-x","message":{"role":"user","content":7}}',
        'not json but names "user"',
    ],
    ids=["message", "content", "not-json"],
)
def test_an_undecidable_user_line_is_unknown(transcript: SessionTranscript, line: str) -> None:
    transcript.command("review")
    transcript.append(line)
    transcript.tool_round()

    assert _boundary(transcript) is None  # never the older /review behind it


@pytest.mark.parametrize("path", [None, "", "/nonexistent/session.jsonl"])
def test_missing_transcript_is_unknown(path: str | None) -> None:
    assert last_prompt_boundary(path) is None


def test_entry_without_uuid_has_no_anchor(transcript: SessionTranscript) -> None:
    entry = transcript.user("/review")
    del entry["uuid"]
    transcript.append(entry)

    assert _boundary(transcript) == PromptBoundary(None, "review")


@pytest.mark.parametrize(
    ("text", "slash"),
    [
        ("/security-review src/app.py", "security-review"),
        ("<command-name>/review</command-name>\n<command-args></command-args>", "review"),
        ("  <command-message>x</command-message><command-name>explain</command-name>", "explain"),
        ("<command-foo>/review</command-foo>", None),
        ("please /review src/app.py", None),
        ("fix it", None),
    ],
)
def test_slash_of_prompt(text: str, slash: str | None) -> None:
    assert slash_of_prompt(text) == slash
