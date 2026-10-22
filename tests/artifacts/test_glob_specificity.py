"""``glob_specificity``: the skill nudge's rank key, read with the path-glob token walk (D41)."""

from __future__ import annotations

import pytest

from coding_agent_playbook.artifacts.path_globs import GlobSpecificity, glob_specificity


@pytest.mark.parametrize(
    ("patterns", "expected"),
    [
        (["**/*.py", "**/conftest.py"], ["**/conftest.py", "**/*.py"]),
        (["**/*.py", "src/app.py"], ["src/app.py", "**/*.py"]),
        (["src/**/*.py", "**/*.py"], ["src/**/*.py", "**/*.py"]),
        (["src/[ab]pp.py", "src/app.py"], ["src/app.py", "src/[ab]pp.py"]),
        (["**/?.py", "**/*.py"], ["**/?.py", "**/*.py"]),
        (["**/*.py", "**/tests/**/*.py"], ["**/tests/**/*.py", "**/*.py"]),
        (["src/", "src/**/*.py"], ["src/**/*.py", "src/"]),
    ],
    ids=[
        "longer-literal",
        "no-wildcard",
        "dir-literal",
        "class",
        "tie-order",
        "any-dirs-weigh-least",
        "trailing-slash-is-a-wildcard",
    ],
)
def test_glob_specificity_orders_fewer_wildcards_then_longer_literal(
    patterns: list[str], expected: list[str]
) -> None:
    assert sorted(patterns, key=glob_specificity) == expected


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("src/", GlobSpecificity(wildcards=1, neg_literal=-4, any_dirs=0)),
        ("src/***", GlobSpecificity(wildcards=1, neg_literal=-4, any_dirs=0)),
        ("*.py", GlobSpecificity(wildcards=1, neg_literal=-3, any_dirs=1)),
        ("**/*.py", GlobSpecificity(wildcards=1, neg_literal=-3, any_dirs=1)),
        ("**/tests/**/*.py", GlobSpecificity(wildcards=1, neg_literal=-9, any_dirs=2)),
        ("a[b", GlobSpecificity(wildcards=0, neg_literal=-3, any_dirs=1)),
    ],
    ids=["trailing-slash", "star-run", "basename", "any-depth", "tests-dir", "unclosed-class"],
)
def test_glob_specificity_counts_tokens_as_the_matcher_reads_them(
    pattern: str, expected: GlobSpecificity
) -> None:
    """A run of stars is one token, a trailing ``/`` is ``/**``, a bare name is ``**/``."""
    assert glob_specificity(pattern) == expected
