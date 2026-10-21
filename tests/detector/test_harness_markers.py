"""The harness-marker table, ``detected_adapters`` and ``adapter_hints`` (D79 part 2, L0-26).

The table reads repo files only (never PATH). A file the engine generated, per
the lockfile, never counts as a sign that a harness is in use.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.detector.harness_markers import (
    HARNESS_MARKERS,
    adapter_hints,
    detected_adapters,
)
from coding_agent_playbook.lockfile.model import LockEntry, Lockfile, generated_paths

if TYPE_CHECKING:
    from collections.abc import Iterator

_CONFIG = ".coding-agent-playbook.toml"

#: One literal case per marker: the file a user (or the harness) would write,
#: and the adapter it points to. Kept independent of the table on purpose.
_MARKER_CASES: list[tuple[str, str, str]] = [
    ("CLAUDE.md", "CLAUDE.md", "claude_code"),
    ("CLAUDE.local.md", "CLAUDE.local.md", "claude_code"),
    (".claude/", ".claude/settings.local.json", "claude_code"),
    ("opencode.json", "opencode.json", "opencode"),
    ("opencode.jsonc", "opencode.jsonc", "opencode"),
    (".opencode/", ".opencode/agent/reviewer.md", "opencode"),
    (".codex/", ".codex/config.toml", "shared_skills"),
    (".agents/", ".agents/skills/mine/SKILL.md", "shared_skills"),
    (".continue/", ".continue/config.yaml", "continue"),
]


def _write(repo: Path, rel: str, text: str = "x\n") -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _lockfile(*paths: str, scope: str = "") -> Lockfile:
    entries = [LockEntry(path=p, sha256="0" * 64, bytes=1, scope=scope) for p in paths]
    return Lockfile(schema_version=2, engine_version="0", rendered_at="", entries=entries)


def test_every_marker_in_the_table_has_a_case() -> None:
    assert sorted(m.path for m in HARNESS_MARKERS) == sorted(c[0] for c in _MARKER_CASES)


@pytest.mark.parametrize(
    ("marker", "written", "adapter"), _MARKER_CASES, ids=[c[0] for c in _MARKER_CASES]
)
def test_each_marker_detects_its_adapter(
    tmp_path: Path, marker: str, written: str, adapter: str
) -> None:
    _write(tmp_path, written)

    assert detected_adapters(tmp_path, frozenset()) == [adapter]


@pytest.mark.parametrize(
    ("marker", "written", "adapter"), _MARKER_CASES, ids=[c[0] for c in _MARKER_CASES]
)
def test_a_generated_marker_file_does_not_count_as_use(
    tmp_path: Path, marker: str, written: str, adapter: str
) -> None:
    _write(tmp_path, written)

    assert detected_adapters(tmp_path, generated_paths(_lockfile(written))) == []


def test_a_scoped_lock_entry_marks_its_file_as_generated(tmp_path: Path) -> None:
    """``.claude/settings.json`` holds engine-managed elements: the engine may have created it."""
    _write(tmp_path, ".claude/settings.json", "{}\n")

    lock = _lockfile(".claude/settings.json", scope="json:/x")
    assert detected_adapters(tmp_path, generated_paths(lock)) == []


def test_a_user_settings_file_the_engine_merged_into_is_skipped_and_the_hint_says_so(
    tmp_path: Path,
) -> None:
    """The unused hint names the skip, so a repo whose only Claude file is shared reads right."""
    _write(tmp_path, ".claude/settings.json", '{"model": "mine"}\n')
    lock = _lockfile(".claude/settings.json", scope="json:/hooks/Stop")

    hints = adapter_hints(tmp_path, ["claude_code"], generated_paths(lock), config_name=_CONFIG)

    assert hints == [
        "claude_code is enabled but the repo shows no Claude Code files beyond the "
        "engine's own output (looked for CLAUDE.md, CLAUDE.local.md, .claude/, skipping "
        "files the engine wrote or merged into): if no one uses Claude Code, remove "
        '"claude_code" from adapters_enabled in .coding-agent-playbook.toml, '
        "then run 'playbook sync'."
    ]


def test_an_unreadable_marker_tree_is_no_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, ".opencode/agent/reviewer.md")

    def _unreadable(self: Path, pattern: str) -> Iterator[Path]:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "rglob", _unreadable)

    assert detected_adapters(tmp_path, frozenset()) == []


def test_a_user_file_next_to_generated_ones_counts(tmp_path: Path) -> None:
    _write(tmp_path, ".opencode/command/review.md")
    _write(tmp_path, ".opencode/package.json")

    lock = _lockfile(".opencode/command/review.md")
    assert detected_adapters(tmp_path, generated_paths(lock)) == ["opencode"]


def test_an_empty_marker_directory_is_not_use(tmp_path: Path) -> None:
    (tmp_path / ".continue").mkdir()

    assert detected_adapters(tmp_path, frozenset()) == []


def test_detected_adapters_follow_table_order_without_duplicates(tmp_path: Path) -> None:
    for rel in (".continue/config.yaml", "opencode.json", ".opencode/x.md", "CLAUDE.md"):
        _write(tmp_path, rel)

    assert detected_adapters(tmp_path, frozenset()) == ["claude_code", "opencode", "continue"]


def test_hint_for_markers_whose_adapter_is_off_names_the_config_fix(tmp_path: Path) -> None:
    _write(tmp_path, "opencode.json", "{}\n")
    _write(tmp_path, "CLAUDE.md")

    hints = adapter_hints(tmp_path, ["claude_code"], frozenset(), config_name=_CONFIG)

    assert hints == [
        "OpenCode files found (opencode.json) but the opencode adapter is off: "
        'add "opencode" to adapters_enabled in .coding-agent-playbook.toml, '
        "then run 'playbook sync'."
    ]


def test_hint_for_an_enabled_adapter_with_only_generated_files(tmp_path: Path) -> None:
    _write(tmp_path, ".continue/rules/50-x.md")

    hints = adapter_hints(
        tmp_path,
        ["continue"],
        generated_paths(_lockfile(".continue/rules/50-x.md")),
        config_name=_CONFIG,
    )

    assert hints == [
        "continue is enabled but the repo shows no Continue files beyond the engine's "
        "own output (looked for .continue/, skipping files the engine wrote or merged "
        "into): if no one uses Continue, remove "
        '"continue" from adapters_enabled in .coding-agent-playbook.toml, '
        "then run 'playbook sync'."
    ]


def test_no_hint_when_adapters_and_markers_agree(tmp_path: Path) -> None:
    _write(tmp_path, "CLAUDE.md")

    assert (
        adapter_hints(tmp_path, ["claude_code", "custom_adapter"], frozenset(), config_name=_CONFIG)
        == []
    )
