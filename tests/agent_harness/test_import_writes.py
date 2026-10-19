"""Tests for agent_harness._import_writes — the importer's file helpers (AH-2, #143).

``restore_recorded_exec_bits`` is the one exec-bit restore that the lossless
skill reader and ``read_hook_sidecar`` now share; ``read_harness_md`` is the
frontmatter split both import tiers use.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.agent_harness._import_writes import (
    read_harness_md,
    restore_recorded_exec_bits,
)
from coding_agent_playbook.agent_harness.manifest import ManifestEntry, ScriptEntry
from coding_agent_playbook.generated_output.sentinel import SENTINEL

if TYPE_CHECKING:
    from pathlib import Path

_EXEC_BITS = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def _skill_entry(scripts: list[ScriptEntry]) -> ManifestEntry:
    return ManifestEntry(kind="skill", path="skills/db/SKILL.md", id="db", scripts=scripts)


def _script(root: Path, name: str) -> Path:
    """A ``skills/db/scripts/<name>`` file whose exec bits a transport dropped (0o644)."""
    path = root / "skills" / "db" / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o644)
    return path


@pytest.mark.skipif(os.name != "posix", reason="exec bits are restored on POSIX only")
def test_restore_recorded_exec_bits_restores_only_recorded_executables(tmp_path: Path) -> None:
    run, data = _script(tmp_path, "run.sh"), _script(tmp_path, "data.txt")
    entry = _skill_entry(
        [
            ScriptEntry("skills/db/scripts/run.sh", executable=True),
            ScriptEntry("skills/db/scripts/data.txt", executable=False),
        ]
    )

    restore_recorded_exec_bits(tmp_path / entry.path, entry)

    assert run.stat().st_mode & _EXEC_BITS == _EXEC_BITS
    assert data.stat().st_mode & _EXEC_BITS == 0


def test_restore_recorded_exec_bits_skips_a_script_missing_on_disk(tmp_path: Path) -> None:
    entry = _skill_entry([ScriptEntry("skills/db/scripts/gone.sh", executable=True)])

    restore_recorded_exec_bits(tmp_path / entry.path, entry)

    assert not (tmp_path / "skills" / "db" / "scripts" / "gone.sh").exists()


def test_read_harness_md_strips_the_sentinel_after_the_frontmatter(tmp_path: Path) -> None:
    leaf = tmp_path / "SKILL.md"
    leaf.write_text(
        f"---\nname: DB\ndescription: Database work.\n---\n<!-- {SENTINEL} -->\n\nBody.\n",
        encoding="utf-8",
    )

    assert read_harness_md(leaf) == ({"name": "DB", "description": "Database work."}, "Body.\n")


def test_read_harness_md_without_frontmatter_returns_the_whole_text(tmp_path: Path) -> None:
    content = tmp_path / "50-style.md"
    content.write_text("Plain foreign content.\n", encoding="utf-8")

    assert read_harness_md(content) == ({}, "Plain foreign content.\n")
