"""Tests for agent_harness.models — frozen dataclasses (Track H1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.agent_harness.models import (
    ContentFile,
    Harness,
    HarnessDirectory,
    LeafMarker,
    NotAHarnessError,
    RawAsset,
    ScriptFile,
    SkillLeaf,
)


def test_script_file_is_frozen() -> None:
    sf = ScriptFile(path=Path("scripts/run.py"), executable=True)
    assert sf.executable is True
    with pytest.raises(AttributeError):
        sf.executable = False  # type: ignore[misc]


def test_content_file_holds_description_and_markdown_flag() -> None:
    cf = ContentFile(
        filename="note.md",
        description="A note",
        path=Path("references/note.md"),
        is_markdown=True,
    )
    assert cf.description == "A note"
    assert cf.is_markdown is True


def test_raw_asset_carries_checksum() -> None:
    asset = RawAsset(path=Path("data/logo.png"), sha256="deadbeef")
    assert asset.sha256 == "deadbeef"


def test_leaf_marker_records_its_path() -> None:
    marker = LeafMarker(path=Path("evals"))
    assert marker.path == Path("evals")


def test_skill_leaf_defaults_collections() -> None:
    leaf = SkillLeaf(
        name="query-db",
        description="Run a query",
        body="body",
        path=Path("skills/query-db"),
        scripts=(),
        references=(),
    )
    assert leaf.scripts == ()
    assert leaf.references == ()


def test_harness_directory_construction() -> None:
    d = HarnessDirectory(
        name="skills",
        routing_file_name="SKILLS.md",
        description="Skills",
        path=Path("skills"),
        children=(),
        leaves=(),
        content=(),
    )
    assert d.routing_file_name == "SKILLS.md"


def test_harness_top_level() -> None:
    h = Harness(
        name="My Harness",
        description="desc",
        body="body",
        path=Path("/root"),
        directories=(),
    )
    assert h.name == "My Harness"
    assert h.directories == ()


def test_not_a_harness_error_is_exception() -> None:
    assert issubclass(NotAHarnessError, Exception)
    with pytest.raises(NotAHarnessError):
        raise NotAHarnessError("no HARNESS.md")
