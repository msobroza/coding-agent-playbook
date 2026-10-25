"""``catalog.skill_rules.iter_md_files`` pinned against its code before the dot-dir check changed.

The walk used to find a file's names below ``root`` with ``path.relative_to(root)``,
which walks the parents of both paths on every call; it now slices the parts
``rglob`` already built. ``tests._link_scan_reference.reference_iter_md_files``
is the old code, verbatim: these tests compare the two, in order, on every
directory of the catalog, with and without ``skip``, on roots spelled
relative, with ``..`` or below a dot directory, and on generated trees.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from coding_agent_playbook.catalog.prompt_sets import prompt_set_dirs
from coding_agent_playbook.catalog.skill_rules import iter_md_files
from tests._catalog import CATALOG_ROOT, CORE_ROOT
from tests._link_scan_reference import reference_iter_md_files


def _assert_unchanged(root: Path, skip: tuple[Path, ...] = ()) -> list[Path]:
    found = list(iter_md_files(root, skip=skip))
    assert found == list(reference_iter_md_files(root, skip=skip)), root
    return found


def _catalog_dirs(max_depth: int) -> list[Path]:
    """``catalog/`` and its directories down to ``core/skills/<skill>`` (depth 3)."""
    return [
        CATALOG_ROOT,
        *(
            path
            for path in sorted(CATALOG_ROOT.rglob("*"))
            if path.is_dir() and len(path.relative_to(CATALOG_ROOT).parts) <= max_depth
        ),
    ]


@pytest.mark.catalog
def test_catalog_directories_list_exactly_as_before() -> None:
    roots = _catalog_dirs(max_depth=3)

    listed = sum(len(_assert_unchanged(root)) for root in roots)

    assert len(roots) > 40, "the catalog walk found too few directories to compare"
    assert listed > 1000, "too few markdown files listed: the comparison would be vacuous"


@pytest.mark.catalog
def test_the_core_prompts_root_with_its_skipped_sets_lists_exactly_as_before() -> None:
    prompts = CORE_ROOT / "prompts"

    assert _assert_unchanged(prompts, prompt_set_dirs(prompts))


@pytest.mark.catalog
def test_a_relative_root_lists_exactly_as_before() -> None:
    relative = Path(os.path.relpath(CORE_ROOT / "rules"))

    assert _assert_unchanged(relative)


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")


def test_roots_with_dot_dot_or_inside_a_dot_directory_list_as_before(tmp_path: Path) -> None:
    layer = tmp_path / ".cache" / "layer"
    for name in ("a.md", "sub/b.md.j2", ".hidden/c.md", "sub/.d.md", "e.mdx", "f.md.bak"):
        _write(layer / name)

    assert [path.name for path in _assert_unchanged(layer)] == ["a.md", "b.md.j2"]
    assert _assert_unchanged(layer / "sub" / "..")
    assert _assert_unchanged(layer, skip=(layer / "sub",)) == [layer / "a.md"]


_DIRS = ("a", "b", ".git", ".x", "skills", "_y")
_FILES = ("r.md", "s.md.j2", "t.mdx", "u.md.bak", ".v.md", "w.MD", "x.md.j2.bak", "README.md")


@pytest.mark.parametrize("seed", range(30))
def test_generated_trees_list_exactly_as_before(tmp_path: Path, seed: int) -> None:
    rng = random.Random(seed)
    root = tmp_path / "root"
    root.mkdir()
    for _ in range(rng.randint(0, 25)):
        dirs = [rng.choice(_DIRS) for _ in range(rng.randint(0, 3))]
        _write(root.joinpath(*dirs, rng.choice(_FILES)))
    skip = tuple(root / rng.choice(_DIRS) for _ in range(rng.randint(0, 2)))

    _assert_unchanged(root)
    _assert_unchanged(root, skip)
