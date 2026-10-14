"""Cross-adapter cleanup contract for the anchored sentinel (prK §P3).

Every built-in sentinel scanner (the ABC's directory scan used by Continue and
OpenCode, Claude Code's ``.claude/commands`` + ``CLAUDE.md`` scans, AGENTS.md's
single-file check and the agent_harness tree scan) recognises an
engine-generated file by ``_sentinel.has_sentinel``: a sentinel line on line 1,
or on the first body line after a leading YAML frontmatter block. A sentinel
anywhere else is user prose and never makes a file deletable. ``stale_outputs``
is the read-only twin ``sync --check`` uses: it reports exactly what
``cleanup_stale`` deletes and deletes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
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
    (ClaudeCodeAdapter, ".claude/CLAUDE.md"),
    (AgentHarnessAdapter, "references/playbook-notes.md"),
    (AgentHarnessAdapter, "rules/50-review.md"),
    (AgentHarnessAdapter, "HARNESS.md"),
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


@pytest.mark.parametrize(("make_adapter", "rel"), _SCANNED_OUTPUTS, ids=_IDS)
def test_stale_outputs_reports_without_deleting(
    tmp_path: Path, make_adapter: Callable[[], Adapter], rel: str
) -> None:
    """``sync --check`` asks ``stale_outputs``: same verdict, nothing deleted."""
    stale = _write(tmp_path, rel, _FRONTMATTER_SENTINEL_TEXT)
    _write(tmp_path, f"{rel}.user.md", _QUOTED_SENTINEL_TEXT)

    assert make_adapter().stale_outputs(set(), tmp_path) == [stale]
    assert stale.exists()


def test_harness_user_reference_quoting_the_sentinel_survives_sync_cleanup(
    tmp_path: Path,
) -> None:
    """Regression: agent_harness matched the sentinel *anywhere*, so a user's
    ``references/`` note quoting it in an indented code block was deleted."""
    note = _write(
        tmp_path,
        "references/playbook-notes.md",
        f"# Playbook notes\n\nGenerated files start with:\n\n    {sentinel_line('html')}\n",
    )

    assert AgentHarnessAdapter().cleanup_stale(set(), tmp_path) == []
    assert note.exists()


def test_quoted_sentinel_in_first_line_prose_is_kept(tmp_path: Path) -> None:
    """Only an exact sentinel line counts: prose on line 1 that mentions it is the user's."""
    readme = _write(
        tmp_path,
        ".continue/rules/README.md",
        f"Files whose first line is `{sentinel_line('html')}` are generated.\n\nMy notes.\n",
    )

    assert ContinueAdapter().cleanup_stale(set(), tmp_path) == []
    assert readme.exists()
