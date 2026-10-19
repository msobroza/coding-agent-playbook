"""Tests for agent_harness.parser — parse_harness (Track H1)."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

from coding_agent_playbook.agent_harness.models import (
    ContentFile,
    HarnessDirectory,
    HarnessTree,
    LeafMarker,
    NotAHarnessError,
    RawAsset,
    SkillLeaf,
)
from coding_agent_playbook.agent_harness.parser import parse_harness

FIXTURES = Path(__file__).parent / "fixtures"


def _copy_full(tmp_path: Path) -> Path:
    """Copy the ``full`` fixture into ``tmp_path`` and re-apply the script exec bit.

    git does not always preserve the executable bit across checkouts, so we set
    it explicitly here — the on-disk bit is exactly what the parser reads.
    """
    dest = tmp_path / "full"
    shutil.copytree(FIXTURES / "full", dest)
    run_query = dest / "skills" / "query-database" / "scripts" / "run_query.py"
    run_query.chmod(run_query.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    helper = dest / "skills" / "query-database" / "scripts" / "_db.py"
    helper.chmod(0o644)
    return dest


def _dir_named(harness_dirs: tuple[HarnessDirectory, ...], name: str) -> HarnessDirectory:
    return next(d for d in harness_dirs if d.name == name)


# --- root requirements -----------------------------------------------------


def test_missing_harness_md_raises(tmp_path: Path) -> None:
    with pytest.raises(NotAHarnessError):
        parse_harness(tmp_path)


def test_minimal_harness_parses_name_description_body() -> None:
    harness = parse_harness(FIXTURES / "minimal")
    # AH-2 (#143): the parsed tree is a HarnessTree, never CONTEXT's Harness (a runtime).
    assert isinstance(harness, HarnessTree)
    assert harness.name == "Minimal Harness"
    assert harness.description == "A bare harness with only a root file"
    assert "minimal harness" in harness.body.lower()
    assert harness.directories == ()


# --- top-level traversal + dotfile skipping --------------------------------


def test_walks_every_top_level_dir(tmp_path: Path) -> None:
    harness = parse_harness(_copy_full(tmp_path))
    names = {d.name for d in harness.directories}
    assert names == {"skills", "tools", "references", "evals"}


def test_skips_dot_dirs(tmp_path: Path) -> None:
    harness = parse_harness(_copy_full(tmp_path))
    assert ".hidden" not in {d.name for d in harness.directories}


# --- routing file name propagation -----------------------------------------


def test_routing_name_from_top_level_segment() -> None:
    harness = parse_harness(FIXTURES / "full")
    tools = _dir_named(harness.directories, "tools")
    assert tools.routing_file_name == "TOOLS.md"


def test_routing_name_propagates_through_deep_subtree() -> None:
    harness = parse_harness(FIXTURES / "full")
    tools = _dir_named(harness.directories, "tools")
    db = _dir_named(tools.children, "db")
    relational = _dir_named(db.children, "relational")
    # Every level under tools/ routes to TOOLS.md, not DB.md / RELATIONAL.md.
    assert db.routing_file_name == "TOOLS.md"
    assert relational.routing_file_name == "TOOLS.md"


def test_grouping_dir_reads_routing_description() -> None:
    harness = parse_harness(FIXTURES / "full")
    tools = _dir_named(harness.directories, "tools")
    assert tools.description == "Tooling index"


# --- skill leaf parsing ----------------------------------------------------


def test_skill_leaf_parsed_with_name_description_body() -> None:
    harness = parse_harness(FIXTURES / "full")
    skills = _dir_named(harness.directories, "skills")
    [leaf] = [leaf for leaf in skills.leaves if isinstance(leaf, SkillLeaf)]
    assert leaf.name == "query-database"
    assert leaf.description == "Run a parameterized SQL query"
    assert "run_query.py" in leaf.body


def test_skill_leaf_is_not_recursed_as_grouping_dir() -> None:
    # The skill dir is a leaf, so it must not appear as a child grouping dir.
    harness = parse_harness(FIXTURES / "full")
    skills = _dir_named(harness.directories, "skills")
    assert "query-database" not in {c.name for c in skills.children}


def test_skill_scripts_capture_exec_bit(tmp_path: Path) -> None:
    harness = parse_harness(_copy_full(tmp_path))
    skills = _dir_named(harness.directories, "skills")
    [leaf] = [leaf for leaf in skills.leaves if isinstance(leaf, SkillLeaf)]
    by_name = {s.path.name: s for s in leaf.scripts}
    assert by_name["run_query.py"].executable is True
    assert by_name["_db.py"].executable is False


def test_skill_references_captured_as_content_files() -> None:
    harness = parse_harness(FIXTURES / "full")
    skills = _dir_named(harness.directories, "skills")
    [leaf] = [leaf for leaf in skills.leaves if isinstance(leaf, SkillLeaf)]
    ref_names = {ref.filename for ref in leaf.references}
    assert "sql-style.md" in ref_names


def test_scripts_capture_is_non_recursive(tmp_path: Path) -> None:
    # Add a nested file under scripts/ — it must NOT be enumerated.
    root = _copy_full(tmp_path)
    nested = root / "skills" / "query-database" / "scripts" / "pkg"
    nested.mkdir()
    (nested / "deep.py").write_text("x\n", encoding="utf-8")
    harness = parse_harness(root)
    skills = _dir_named(harness.directories, "skills")
    [leaf] = [leaf for leaf in skills.leaves if isinstance(leaf, SkillLeaf)]
    assert "deep.py" not in {s.path.name for s in leaf.scripts}


# --- .harnessleaf precedence + over-traversal protection -------------------


def test_harnessleaf_dir_becomes_leaf_marker() -> None:
    harness = parse_harness(FIXTURES / "full")
    evals = _dir_named(harness.directories, "evals")
    assert any(isinstance(leaf, LeafMarker) for leaf in evals.leaves)


def test_does_not_recurse_into_harnessleaf_dir() -> None:
    harness = parse_harness(FIXTURES / "full")
    evals = _dir_named(harness.directories, "evals")
    # The opaque leaf is terminal: no children walked, so the inner directory
    # (should_not_be_walked/) never appears in the model.
    assert evals.children == ()


# --- content vs raw classification -----------------------------------------


def test_markdown_with_description_becomes_content_file() -> None:
    harness = parse_harness(FIXTURES / "full")
    references = _dir_named(harness.directories, "references")
    pooling = next(
        c for c in references.content if isinstance(c, ContentFile) and c.filename == "pooling.md"
    )
    assert pooling.description == "Connection pooling guide"
    assert pooling.is_markdown is True


def test_routing_file_itself_is_not_content() -> None:
    harness = parse_harness(FIXTURES / "full")
    references = _dir_named(harness.directories, "references")
    filenames = {c.filename for c in references.content if isinstance(c, ContentFile)}
    assert "REFERENCES.md" not in filenames


def test_markdown_without_description_has_none_description() -> None:
    harness = parse_harness(FIXTURES / "full")
    tools = _dir_named(harness.directories, "tools")
    db = _dir_named(tools.children, "db")
    relational = _dir_named(db.children, "relational")
    notes = next(
        c for c in relational.content if isinstance(c, ContentFile) and c.filename == "notes.md"
    )
    assert notes.description is None


def test_non_markdown_file_becomes_raw_asset_with_sha256() -> None:
    harness = parse_harness(FIXTURES / "full")
    tools = _dir_named(harness.directories, "tools")
    db = _dir_named(tools.children, "db")
    relational = _dir_named(db.children, "relational")
    blob = next(c for c in relational.content if isinstance(c, RawAsset))
    assert blob.path.name == "blob.bin"
    assert len(blob.sha256) == 64  # sha256 hex digest


def test_raw_asset_does_not_assume_utf8(tmp_path: Path) -> None:
    # A raw file containing invalid UTF-8 must parse without raising.
    root = _copy_full(tmp_path)
    bad = root / "tools" / "binary.dat"
    bad.write_bytes(b"\xff\xfe\x00garbage")
    harness = parse_harness(root)  # must not raise UnicodeDecodeError
    tools = _dir_named(harness.directories, "tools")
    assert any(isinstance(c, RawAsset) and c.path.name == "binary.dat" for c in tools.content)


# --- harness with no .leaf-detectors ---------------------------------------


def test_harness_md_missing_name_raises(tmp_path: Path) -> None:
    root = tmp_path / "h"
    root.mkdir()
    (root / "HARNESS.md").write_text(
        "---\ndescription: only a description\n---\nbody\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="name"):
        parse_harness(root)


def test_skill_without_scripts_or_references(tmp_path: Path) -> None:
    root = tmp_path / "h"
    (root / "skills" / "bare").mkdir(parents=True)
    (root / "HARNESS.md").write_text("---\nname: H\ndescription: D\n---\nbody\n", encoding="utf-8")
    (root / ".leaf-detectors").write_text("skill=SKILL.md\n", encoding="utf-8")
    (root / "skills" / "bare" / "SKILL.md").write_text(
        "---\nname: bare\ndescription: no side files\n---\nbody\n", encoding="utf-8"
    )
    harness = parse_harness(root)
    skills = _dir_named(harness.directories, "skills")
    [leaf] = [leaf for leaf in skills.leaves if isinstance(leaf, SkillLeaf)]
    assert leaf.scripts == ()
    assert leaf.references == ()


def test_nested_harnessleaf_subdir_inside_grouping_dir(tmp_path: Path) -> None:
    # A .harnessleaf subdir nested under a non-leaf grouping dir → LeafMarker,
    # and the grouping dir is not recursed into it.
    root = tmp_path / "h"
    (root / "tools" / "opaque").mkdir(parents=True)
    (root / "HARNESS.md").write_text("---\nname: H\ndescription: D\n---\nbody\n", encoding="utf-8")
    (root / "tools" / "opaque" / ".harnessleaf").write_text("", encoding="utf-8")
    (root / "tools" / "opaque" / "inner.md").write_text("inner\n", encoding="utf-8")
    harness = parse_harness(root)
    tools = _dir_named(harness.directories, "tools")
    assert any(isinstance(leaf, LeafMarker) for leaf in tools.leaves)
    assert "opaque" not in {c.name for c in tools.children}


def test_routing_file_with_malformed_frontmatter_yields_none_description(
    tmp_path: Path,
) -> None:
    root = tmp_path / "h"
    (root / "tools").mkdir(parents=True)
    (root / "HARNESS.md").write_text("---\nname: H\ndescription: D\n---\nbody\n", encoding="utf-8")
    # TOOLS.md without a frontmatter fence — split_frontmatter raises ValueError.
    (root / "tools" / "TOOLS.md").write_text("no frontmatter here\n", encoding="utf-8")
    harness = parse_harness(root)
    tools = _dir_named(harness.directories, "tools")
    assert tools.description is None


def test_no_leaf_detectors_means_skill_dirs_are_grouping(tmp_path: Path) -> None:
    # Without .leaf-detectors, a SKILL.md dir is not a typed leaf — it is a
    # grouping dir (best-effort import handles structural inference separately).
    root = _copy_full(tmp_path)
    (root / ".leaf-detectors").unlink()
    harness = parse_harness(root)
    skills = _dir_named(harness.directories, "skills")
    # query-database is now a recursed child, not a SkillLeaf.
    assert "query-database" in {c.name for c in skills.children}
    assert not any(isinstance(leaf, SkillLeaf) for leaf in skills.leaves)
