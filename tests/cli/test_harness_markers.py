"""The harness-marker table and the advisory ``playbook check`` hints (D79 part 2, L0-26).

The table reads repo files only (never PATH). A file the engine generated, per
the lockfile, never counts as a sign that a harness is in use.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.detector.harness_markers import (
    HARNESS_MARKERS,
    adapter_hints,
    detected_adapters,
)
from coding_agent_playbook.lockfile.model import LockEntry, Lockfile

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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

    assert detected_adapters(tmp_path, _lockfile(written).recorded_paths()) == []


def test_a_scoped_lock_entry_marks_its_file_as_generated(tmp_path: Path) -> None:
    """``.claude/settings.json`` holds engine-managed elements: the engine may have created it."""
    _write(tmp_path, ".claude/settings.json", "{}\n")

    assert (
        detected_adapters(
            tmp_path, _lockfile(".claude/settings.json", scope="json:/x").recorded_paths()
        )
        == []
    )


def test_a_user_file_next_to_generated_ones_counts(tmp_path: Path) -> None:
    _write(tmp_path, ".opencode/command/review.md")
    _write(tmp_path, ".opencode/package.json")

    lock = _lockfile(".opencode/command/review.md")
    assert detected_adapters(tmp_path, lock.recorded_paths()) == ["opencode"]


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
        _lockfile(".continue/rules/50-x.md").recorded_paths(),
        config_name=_CONFIG,
    )

    assert hints == [
        "continue is enabled but the repo shows no Continue files beyond the engine's "
        "own output (looked for .continue/): if no one uses Continue, remove "
        '"continue" from adapters_enabled in .coding-agent-playbook.toml, '
        "then run 'playbook sync'."
    ]


def test_no_hint_when_adapters_and_markers_agree(tmp_path: Path) -> None:
    _write(tmp_path, "CLAUDE.md")

    assert (
        adapter_hints(tmp_path, ["claude_code", "custom_adapter"], frozenset(), config_name=_CONFIG)
        == []
    )


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), refresh=False)


def test_check_prints_the_hints_and_still_exits_zero(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Default synthetic config enables continue, claude_code, opencode; sync writes only engine files."""
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    _sync.run(argparse.Namespace(repo_root=str(repo), check=False))
    _write(repo, ".codex/config.toml")
    capsys.readouterr()

    assert _check.run(_ns(repo)) == 0

    out = capsys.readouterr().out
    section = out.split("=== Harnesses ===\n", 1)[1].split("=== Drift ===", 1)[0]
    assert "Codex files found (.codex/) but the shared_skills adapter is off" in section
    for adapter in ("continue", "claude_code", "opencode"):
        assert f"  ! {adapter} is enabled but the repo shows no" in section


def test_check_reports_agreement_when_there_is_nothing_to_hint(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    for rel in ("CLAUDE.md", "opencode.json", ".continue/config.yaml"):
        _write(repo, rel)

    assert _check.run(_ns(repo)) == 0

    out = capsys.readouterr().out
    assert "=== Harnesses ===\n  Enabled adapters match the repo's harness files.\n" in out
