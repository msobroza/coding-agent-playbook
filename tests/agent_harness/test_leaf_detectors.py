"""Tests for harness.leaf_detectors (Track H1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.leaf_detectors import (
    is_harness_leaf,
    leaf_type,
    parse_leaf_detectors,
    routing_file_name,
)

if TYPE_CHECKING:
    from pathlib import Path

# --- parse_leaf_detectors --------------------------------------------------


def test_parse_simple_rule() -> None:
    assert parse_leaf_detectors("skill=SKILL.md") == {"skill": "SKILL.md"}


def test_parse_strips_whitespace_around_both_sides() -> None:
    assert parse_leaf_detectors("  skill  =  SKILL.md  ") == {"skill": "SKILL.md"}


def test_parse_skips_blank_lines_and_comments() -> None:
    text = "# a comment\n\nskill=SKILL.md\n   \n# trailing comment\n"
    assert parse_leaf_detectors(text) == {"skill": "SKILL.md"}


def test_parse_without_trailing_newline() -> None:
    assert parse_leaf_detectors("skill=SKILL.md") == {"skill": "SKILL.md"}


def test_parse_splits_on_first_equals_only() -> None:
    # An '=' inside the path must stay in the value.
    assert parse_leaf_detectors("weird=nested/a=b.md") == {"weird": "nested/a=b.md"}


def test_parse_multiple_rules() -> None:
    text = "skill=SKILL.md\nagent=AGENT.md\n"
    assert parse_leaf_detectors(text) == {"skill": "SKILL.md", "agent": "AGENT.md"}


def test_parse_empty_returns_empty_dict() -> None:
    assert parse_leaf_detectors("") == {}
    assert parse_leaf_detectors("# only a comment\n") == {}


def test_parse_ignores_lines_without_equals() -> None:
    assert parse_leaf_detectors("not a rule\nskill=SKILL.md\n") == {"skill": "SKILL.md"}


# --- routing_file_name -----------------------------------------------------


def test_routing_file_name_uppercases_and_appends_md() -> None:
    assert routing_file_name("skills") == "SKILLS.md"
    assert routing_file_name("tools") == "TOOLS.md"


def test_routing_file_name_top_level_segment_only() -> None:
    # The name derives from the TOP-LEVEL ancestor and propagates down: a deep
    # dir under tools/ still routes to TOOLS.md, never DB.md or RELATIONAL.md.
    top = "tools"
    assert routing_file_name(top) == "TOOLS.md"


# --- is_harness_leaf -------------------------------------------------------


def test_is_harness_leaf_true_when_marker_present(tmp_path: Path) -> None:
    (tmp_path / ".harnessleaf").write_text("", encoding="utf-8")
    assert is_harness_leaf(tmp_path) is True


def test_is_harness_leaf_false_when_absent(tmp_path: Path) -> None:
    assert is_harness_leaf(tmp_path) is False


# --- leaf_type -------------------------------------------------------------


def test_leaf_type_harnessleaf_takes_precedence(tmp_path: Path) -> None:
    # Both a .harnessleaf AND a detector file present -> "leaf" wins.
    (tmp_path / ".harnessleaf").write_text("", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    assert leaf_type(tmp_path, {"skill": "SKILL.md"}) == "leaf"


def test_leaf_type_detector_match(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    assert leaf_type(tmp_path, {"skill": "SKILL.md"}) == "skill"


def test_leaf_type_none_for_grouping_dir(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    assert leaf_type(tmp_path, {"skill": "SKILL.md"}) is None


def test_leaf_type_no_detectors_returns_none(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    assert leaf_type(tmp_path, {}) is None


def test_leaf_type_detector_relative_path_subdir(tmp_path: Path) -> None:
    # A detector whose relative_path points into a subdir matches when present.
    nested = tmp_path / "meta"
    nested.mkdir()
    (nested / "AGENT.md").write_text("x", encoding="utf-8")
    assert leaf_type(tmp_path, {"agent": "meta/AGENT.md"}) == "agent"
