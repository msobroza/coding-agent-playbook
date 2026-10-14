"""Cross-adapter cleanup contract for the anchored sentinel (prK §P3).

Every built-in sentinel scanner (the ABC ``_default_cleanup`` used by Continue
and OpenCode, Claude Code's directory + ``CLAUDE.md`` scans, and AGENTS.md's
single-file check) recognises an engine-generated file by
``_sentinel.has_sentinel``: the sentinel on line 1, or on the first body line
after a leading YAML frontmatter block. A sentinel anywhere else is user prose
and never makes a file deletable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter

_FRONTMATTER = "---\ndescription: Review the diff\ndisallowed-tools: Edit Write NotebookEdit\n---\n"

#: A generated file whose sentinel is the first body line after its frontmatter.
_FRONTMATTER_SENTINEL_TEXT = f"{_FRONTMATTER}{sentinel_line('html')}\n\n# Review\n"

#: A user file that merely *quotes* the sentinel below its first body line.
_QUOTED_SENTINEL_TEXT = f"{_FRONTMATTER}# Notes\n\nOur header reads:\n{sentinel_line('html')}\n"

_SCANNED_OUTPUTS: list[tuple[Callable[[], Adapter], str]] = [
    (ClaudeCodeAdapter, ".claude/commands/review.md"),
    (ClaudeCodeAdapter, ".claude/skills/demo/references/notes.md"),
    (ClaudeCodeAdapter, ".claude/CLAUDE.md"),
    (ContinueAdapter, ".continue/rules/50-review.md"),
    (ContinueAdapter, ".continue/prompts/review.md"),
    (OpenCodeAdapter, ".opencode/command/review.md"),
    (AgentsMdAdapter, "AGENTS.md"),
]
_IDS = [f"{factory.__name__}:{rel}" for factory, rel in _SCANNED_OUTPUTS]


def _write(repo_root: Path, rel: str, text: str) -> Path:
    target = repo_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_frontmatter_sentinel_file_is_cleaned(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    stale = _write(tmp_path, rel, _FRONTMATTER_SENTINEL_TEXT)

    deleted = make_adapter().cleanup_stale(set(), tmp_path)

    assert deleted == [stale]
    assert not stale.exists()


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_frontmatter_sentinel_file_in_written_paths_is_kept(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    current = _write(tmp_path, rel, _FRONTMATTER_SENTINEL_TEXT)

    deleted = make_adapter().cleanup_stale({current.resolve()}, tmp_path)

    assert deleted == []
    assert current.exists()


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_sentinel_quoted_below_first_body_line_is_kept(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    user_file = _write(tmp_path, rel, _QUOTED_SENTINEL_TEXT)

    deleted = make_adapter().cleanup_stale(set(), tmp_path)

    assert deleted == []
    assert user_file.exists()


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_binary_file_is_skipped_not_crashed_on(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\xfe\x00\x00binary garbage")

    deleted = make_adapter().cleanup_stale(set(), tmp_path)

    assert deleted == []
    assert target.exists()
