"""The base a CLI twin compares against (specs/prF-forge-adapter.md §10.2, Q53).

``resolve_merge_base`` is forge-neutral and fails closed: a base whose merge
base with ``HEAD`` is ``HEAD`` itself leaves nothing to check, so the twins
exit 2 instead of passing an empty range.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from coding_agent_playbook.commands import twins
from coding_agent_playbook.commands.twins._git_scope import (
    FETCH_DEPTH_HINT,
    GitBaseError,
    MergeBase,
    resolve_merge_base,
)
from coding_agent_playbook.hook_runtime import git as git_layer
from tests.hook_runtime.fakes import FakeGit

HEAD_SHA = "c0ffee00" * 5
FORK_SHA = "9f2c4100" * 5


def test_a_base_behind_head_resolves_to_its_merge_base() -> None:
    git = FakeGit(merge_bases={("origin/main", "HEAD"): FORK_SHA}, commits={"HEAD": HEAD_SHA})

    assert resolve_merge_base(git, "origin/main") == MergeBase("origin/main", FORK_SHA)


def test_a_base_equal_to_head_is_an_empty_range() -> None:
    git = FakeGit(merge_bases={(HEAD_SHA, "HEAD"): HEAD_SHA}, commits={"HEAD": HEAD_SHA})

    with pytest.raises(GitBaseError, match="empty") as caught:
        resolve_merge_base(git, HEAD_SHA)

    assert HEAD_SHA in str(caught.value)


def test_a_base_that_already_contains_head_is_an_empty_range() -> None:
    git = FakeGit(merge_bases={("origin/main", "HEAD"): HEAD_SHA}, commits={"HEAD": HEAD_SHA})

    with pytest.raises(GitBaseError, match=r"origin/main\.\.HEAD is empty"):
        resolve_merge_base(git, "origin/main")


def test_the_default_branch_at_head_is_an_empty_range_too() -> None:
    git = FakeGit(
        default_branch_name="origin/main",
        merge_bases={("origin/main", "HEAD"): HEAD_SHA},
        commits={"HEAD": HEAD_SHA},
    )

    with pytest.raises(GitBaseError, match="empty"):
        resolve_merge_base(git, None)


def test_an_unresolvable_head_fails_closed() -> None:
    git = FakeGit(merge_bases={("origin/main", "HEAD"): FORK_SHA})

    with pytest.raises(GitBaseError, match="HEAD"):
        resolve_merge_base(git, "origin/main")


def test_the_fetch_depth_hint_names_both_forges() -> None:
    assert "actions/checkout" in FETCH_DEPTH_HINT
    assert "fetch-depth: 0" in FETCH_DEPTH_HINT
    assert "GIT_DEPTH: 0" in FETCH_DEPTH_HINT
    assert 'git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"' in FETCH_DEPTH_HINT


def test_a_twin_that_diffs_the_working_tree_accepts_an_empty_commit_range() -> None:
    """check-deps compares the working tree, so uncommitted edits are still checked."""
    git = FakeGit(merge_bases={("main", "HEAD"): HEAD_SHA}, commits={"HEAD": HEAD_SHA})

    assert resolve_merge_base(git, "main", includes_worktree=True) == MergeBase("main", HEAD_SHA)


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_base_fails_closed_instead_of_falling_back(blank: str) -> None:
    """An unset CI variable expands to ``--base ""``: never silently the default branch."""
    git = FakeGit(default_branch_name="origin/main", commits={"HEAD": HEAD_SHA})

    with pytest.raises(GitBaseError, match="--base is empty"):
        resolve_merge_base(git, blank)

    assert ("default_branch", ()) not in git.calls


def _twin_and_git_strings() -> list[tuple[str, str]]:
    """Every string literal of the CI twins and the git layer they call, with its file."""
    found: list[tuple[str, str]] = []
    for package in (twins, git_layer):
        for module in sorted(Path(str(package.__file__)).parent.glob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            found += [
                (module.name, node.value)
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            ]
    return found


def test_no_twin_reads_a_forge_variable_or_fetches() -> None:
    """Q9/Q53: the base sits in the CI job's YAML; ``playbook ci`` never asks the forge."""
    strings = _twin_and_git_strings()

    assert [
        s for s in strings if "CI_MERGE_REQUEST_" in s[1] and s[1] not in FETCH_DEPTH_HINT
    ] == []
    assert [s for s in strings if s[1] == "fetch"] == []
