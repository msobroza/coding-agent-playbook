"""``BatchRealPaths`` (``generated_output/symlinks.py``) equals ``os.path.realpath`` exactly.

The batch memoizes directories and resolves a leaf as ``realpath(parent)/name``
after one lstat, so every link shape a user can build (``tests.generated_output.link_zoo``)
is pinned against the reference itself, the old ``real_path``: a symlinked leaf
or parent, chains, dangling links, loops (a file linking to itself too), ``..``
after a symlinked dir, case variants, nonexistent leaves and parents, relative
spellings, and seeded random trees. Exceptions must match too (type and message).
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.generated_output.symlinks import BatchRealPaths
from tests.generated_output.link_zoo import (
    build_link_zoo,
    link_zoo_queries,
    random_link_tree,
    random_tree_queries,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")

Outcome = tuple[str, object]


def _outcome(resolve: Callable[[Path], object], path: Path) -> Outcome:
    """What ``resolve(path)`` returns, or the type and message it raises."""
    try:
        return ("value", resolve(path))
    except Exception as exc:  # the parity check compares any exception
        return ("raised", (type(exc), str(exc)))


def _reference(path: Path) -> Path:
    """The old implementation: ``real_path`` (and ``FileSet``'s ``_real``) before the batch."""
    return Path(os.path.realpath(path))


def _assert_matches_realpath(queries: list[Path], batch: BatchRealPaths) -> None:
    for query in queries:
        assert _outcome(batch.real, query) == _outcome(_reference, query), query


def _orders(queries: list[Path], seed: int) -> Iterable[list[Path]]:
    shuffled = list(queries)
    random.Random(seed).shuffle(shuffled)
    return (queries, queries[::-1], shuffled)


def test_every_zoo_path_resolves_like_realpath_in_one_fresh_batch_each(tmp_path: Path) -> None:
    build_link_zoo(tmp_path)
    for query in link_zoo_queries(tmp_path):
        assert _outcome(BatchRealPaths().real, query) == _outcome(_reference, query), query


def test_one_shared_batch_resolves_the_zoo_like_realpath_in_any_order(tmp_path: Path) -> None:
    build_link_zoo(tmp_path)
    for order in _orders(link_zoo_queries(tmp_path), seed=7):
        _assert_matches_realpath(order, BatchRealPaths())


def test_relative_spellings_resolve_against_the_cwd_like_realpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_link_zoo(tmp_path)
    monkeypatch.chdir(tmp_path / "d1")
    queries = link_zoo_queries(tmp_path)
    relative = [Path(os.path.relpath(query, tmp_path / "d1")) for query in queries]
    _assert_matches_realpath([*relative, Path("."), Path(".."), Path("../x")], BatchRealPaths())


def test_case_variants_keep_their_spelling_like_realpath(tmp_path: Path) -> None:
    build_link_zoo(tmp_path)
    queries = [tmp_path / "upper" / "mixed.md", tmp_path / "UPPER" / "MIXED.MD"]
    queries += [tmp_path / "DIR_LINK" / "d3" / "FILE.txt", tmp_path / "D1" / "Back" / "x"]
    _assert_matches_realpath(queries, BatchRealPaths())


def test_an_embedded_nul_raises_like_realpath(tmp_path: Path) -> None:
    build_link_zoo(tmp_path)
    queries = [tmp_path / "a\0b", tmp_path / "loop_a" / "a\0b", tmp_path / "d1" / "a\0b" / "c"]
    _assert_matches_realpath(queries, BatchRealPaths())


@pytest.mark.parametrize("seed", range(10))
def test_random_link_trees_resolve_like_realpath(tmp_path: Path, seed: int) -> None:
    rng = random.Random(seed)
    queries = random_tree_queries(random_link_tree(tmp_path, rng), rng)
    for order in _orders(queries, seed):
        _assert_matches_realpath(order, BatchRealPaths())


class CountingLstat:
    """``os.lstat`` recording each path it is asked, so a test can count the batch's lstats."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, path: str) -> os.stat_result:
        self.calls.append(path)
        return os.lstat(path)


def test_a_sibling_of_a_resolved_path_costs_one_lstat(tmp_path: Path) -> None:
    deep = tmp_path.joinpath(*"abcdefgh")
    deep.mkdir(parents=True)
    lstat = CountingLstat()
    batch = BatchRealPaths(lstat=lstat)
    batch.real(deep / "one.md")
    lstat.calls.clear()

    assert batch.real(deep / "two.md") == _reference(deep / "two.md")
    assert lstat.calls == [os.path.realpath(deep) + "/two.md"]


def test_a_path_seen_before_costs_no_lstat(tmp_path: Path) -> None:
    lstat = CountingLstat()
    batch = BatchRealPaths(lstat=lstat)
    batch.real(tmp_path / "a" / "b.md")
    lstat.calls.clear()

    assert batch.real(tmp_path / "a" / "b.md") == _reference(tmp_path / "a" / "b.md")
    assert lstat.calls == []


def test_a_batch_never_sees_a_later_write_so_each_batch_is_fresh(tmp_path: Path) -> None:
    """Why a batch must not span a write: its memo is never invalidated."""
    (tmp_path / "real").mkdir()
    (tmp_path / "other").mkdir()
    spelled = tmp_path / "real" / "f.md"
    earlier = BatchRealPaths()
    assert earlier.real(spelled) == _reference(spelled)
    before = _reference(spelled)

    (tmp_path / "real").rmdir()
    (tmp_path / "real").symlink_to("other")

    assert earlier.real(spelled) == before  # stale: the memo kept the old answer
    assert BatchRealPaths().real(spelled) == _reference(spelled) != before
