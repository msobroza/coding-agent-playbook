"""Unit tests for spelling-proof file membership (``generated_output/file_identity.py``)."""

from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.generated_output.file_identity import FileSet, file_identity
from tests.generated_output.link_zoo import (
    build_link_zoo,
    link_zoo_queries,
    random_link_tree,
    random_tree_queries,
    relink_directory,
    relinkable_outputs,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")


@dataclass
class _FileSetBeforeBatch:
    """``FileSet`` as of 8eb43dff (one ``os.path.realpath`` per path), kept as the oracle."""

    paths: set[Path] = field(default_factory=set)
    identities: set[tuple[int, int]] = field(default_factory=set)

    @classmethod
    def of(cls, files: Iterable[Path]) -> _FileSetBeforeBatch:
        members = cls()
        for path in files:
            members.add(path)
        return members

    def add(self, path: Path) -> None:
        self.paths.add(Path(os.path.realpath(path)))
        identity = file_identity(path)
        if identity is not None:
            self.identities.add(identity)

    def holds(self, path: Path) -> bool:
        if Path(os.path.realpath(path)) in self.paths:
            return True
        identity = file_identity(path)
        return identity is not None and identity in self.identities


def _assert_same_file_set(members: list[Path], queries: list[Path]) -> None:
    new, old = FileSet.of(iter(members)), _FileSetBeforeBatch.of(members)
    assert (new.paths, new.identities) == (old.paths, old.identities)
    assert [new.holds(query) for query in queries] == [old.holds(query) for query in queries]


@posix_only
def test_file_set_of_matches_the_per_path_implementation_over_every_link_shape(
    tmp_path: Path,
) -> None:
    build_link_zoo(tmp_path)
    queries = link_zoo_queries(tmp_path)
    for members in (queries, queries[::-1], queries[::3]):
        _assert_same_file_set(members, queries)


@posix_only
@pytest.mark.parametrize("seed", range(3))
def test_file_set_of_matches_the_per_path_implementation_on_random_trees(
    tmp_path: Path, seed: int
) -> None:
    rng = random.Random(seed)
    queries = random_tree_queries(random_link_tree(tmp_path, rng), rng)
    _assert_same_file_set(rng.sample(queries, len(queries) // 2), queries)


@posix_only
def test_file_set_of_resolves_afresh_on_every_call(tmp_path: Path) -> None:
    """Pins the batch's scope, one per ``of`` call and never module-level: a directory
    relinked between two calls is seen by the second, as with per-path realpath."""
    written = relinkable_outputs(tmp_path)
    first = FileSet.of(written).paths
    relink_directory(tmp_path / "out", tmp_path / "other")

    second, old = FileSet.of(written), _FileSetBeforeBatch.of(written)

    assert (second.paths, second.identities) == (old.paths, old.identities)
    assert second.paths != first


def test_file_identity_is_none_for_a_missing_path(tmp_path: Path) -> None:
    assert file_identity(tmp_path / "missing") is None


def test_file_set_holds_members_by_resolved_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.md").write_text("a")
    members = FileSet.of([tmp_path / "a.md", tmp_path / "not-yet-written.md"])
    monkeypatch.chdir(tmp_path)
    assert members.holds(tmp_path / "a.md")
    assert members.holds(Path("a.md"))  # relative spelling
    assert members.holds(tmp_path / "not-yet-written.md")  # absent: by path only
    assert not members.holds(tmp_path / "b.md")


def test_file_set_holds_another_name_of_the_same_file(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a")
    os.link(tmp_path / "a.md", tmp_path / "alias.md")
    (tmp_path / "other.md").write_text("a")  # equal bytes, different file
    members = FileSet.of([tmp_path / "a.md"])
    assert members.holds(tmp_path / "alias.md")
    assert not members.holds(tmp_path / "other.md")


def test_file_set_add_extends_membership(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a")
    members = FileSet()
    assert not members.holds(tmp_path / "a.md")
    members.add(tmp_path / "a.md")
    assert members.holds(tmp_path / "a.md")
