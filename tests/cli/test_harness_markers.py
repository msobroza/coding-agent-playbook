"""``playbook check`` prints the advisory Harnesses section (D79 part 2, L0-26).

The marker table and the hint wording are unit-tested in
tests/detector/test_harness_markers.py; these run the command end to end.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.commands import sync as _sync

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


def _write(repo: Path, rel: str, text: str = "x\n") -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


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
