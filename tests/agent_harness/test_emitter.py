"""Tests for harness.emitter — pure emit helpers (Track H1)."""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.emitter import (
    copy_script,
    frontmatter_block,
    harnessleaf_path,
    input_variables_note,
    leaf_detectors_file,
    routing_file,
    with_sentinel_body,
)
from coding_agent_playbook.agent_harness.leaf_detectors import HARNESS_LEAF_MARKER
from coding_agent_playbook.generated_output.sentinel import SENTINEL

if TYPE_CHECKING:
    from pathlib import Path

# --- frontmatter_block -----------------------------------------------------


def test_frontmatter_block_wraps_in_fences() -> None:
    block = frontmatter_block({"name": "X", "description": "Y"})
    assert block.startswith("---\n")
    assert block.rstrip("\n").endswith("---")
    assert "name: X" in block
    assert "description: Y" in block


def test_frontmatter_block_preserves_key_order() -> None:
    block = frontmatter_block({"name": "X", "description": "Y"})
    assert block.index("name:") < block.index("description:")


# --- with_sentinel_body ----------------------------------------------------


def test_with_sentinel_frontmatter_stays_on_line_one() -> None:
    fm = frontmatter_block({"name": "X", "description": "Y"})
    out = with_sentinel_body(fm, "Body text\n")
    lines = out.splitlines()
    # Line 1 MUST be the frontmatter fence so a harness parser's ^--- matches.
    assert lines[0] == "---"


def test_with_sentinel_sentinel_is_first_body_line() -> None:
    fm = frontmatter_block({"name": "X", "description": "Y"})
    out = with_sentinel_body(fm, "Body text\n")
    lines = out.splitlines()
    # Find the closing fence; the line immediately after it is the sentinel.
    closing = next(i for i in range(1, len(lines)) if lines[i] == "---")
    assert lines[closing + 1] == f"<!-- {SENTINEL} -->"


def test_with_sentinel_blank_line_then_body() -> None:
    fm = frontmatter_block({"description": "Y"})
    out = with_sentinel_body(fm, "Hello body\n")
    assert f"<!-- {SENTINEL} -->\n\nHello body" in out


def test_with_sentinel_body_contains_sentinel_not_on_line_one() -> None:
    fm = frontmatter_block({"name": "X", "description": "Y"})
    out = with_sentinel_body(fm, "Body\n")
    assert not out.startswith(f"<!-- {SENTINEL} -->")
    assert SENTINEL in out


# --- routing_file ----------------------------------------------------------


def test_routing_file_has_description_only_frontmatter_and_sentinel() -> None:
    out = routing_file("A routing file", "Index body\n")
    lines = out.splitlines()
    assert lines[0] == "---"
    assert "description: A routing file" in out
    # No 'name:' in a routing file's frontmatter.
    assert "name:" not in out
    assert f"<!-- {SENTINEL} -->" in out


# --- leaf_detectors_file ---------------------------------------------------


def test_leaf_detectors_file_renders_rules() -> None:
    out = leaf_detectors_file({"skill": "SKILL.md"})
    assert "skill=SKILL.md" in out


def test_leaf_detectors_file_multiple_rules() -> None:
    out = leaf_detectors_file({"skill": "SKILL.md", "agent": "AGENT.md"})
    assert "skill=SKILL.md" in out
    assert "agent=AGENT.md" in out


# --- harnessleaf_path ------------------------------------------------------


def test_harnessleaf_path(tmp_path: Path) -> None:
    assert harnessleaf_path(tmp_path) == tmp_path / HARNESS_LEAF_MARKER


# --- copy_script -----------------------------------------------------------


def test_copy_script_preserves_bytes(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    dst = tmp_path / "out" / "dst.bin"
    payload = b"\x00\x01\x02not-utf8\xff\xfe"
    src.write_bytes(payload)
    copy_script(src, dst)
    assert dst.read_bytes() == payload


def test_copy_script_reports_executable_true(tmp_path: Path) -> None:
    src = tmp_path / "run.py"
    src.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    src.chmod(src.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    dst = tmp_path / "out" / "run.py"
    assert copy_script(src, dst) is True


def test_copy_script_reports_executable_false(tmp_path: Path) -> None:
    src = tmp_path / "_helper.py"
    src.write_text("x = 1\n", encoding="utf-8")
    src.chmod(0o644)
    dst = tmp_path / "out" / "_helper.py"
    assert copy_script(src, dst) is False


def test_copy_script_creates_parent_dirs(tmp_path: Path) -> None:
    src = tmp_path / "s.py"
    src.write_text("x\n", encoding="utf-8")
    dst = tmp_path / "deep" / "nested" / "s.py"
    copy_script(src, dst)
    assert dst.is_file()


def test_copy_script_copy2_preserves_exec_bit_on_disk(tmp_path: Path) -> None:
    src = tmp_path / "run.sh"
    src.write_text("echo hi\n", encoding="utf-8")
    src.chmod(0o755)
    dst = tmp_path / "out" / "run.sh"
    copy_script(src, dst)
    # copy2 carries the mode, so the destination is executable on disk too.
    assert os.access(dst, os.X_OK)


# --- prompt-leaf body helpers ----------------------------------------------


def test_input_variables_note_lists_names_and_descriptions() -> None:
    note = input_variables_note([{"name": "path", "description": " file "}, {"name": "n"}])

    assert note == "## Input variables\n\n- `path` — file\n- `n`\n"
    assert input_variables_note([]) == ""
