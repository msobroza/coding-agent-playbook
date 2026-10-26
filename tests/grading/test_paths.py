"""Shared path-glob constants of the metrics tools (specs/prK-hook-pack.md §F.0.3 item 5, §F.1.1).

:data:`TEST_PATH_GLOBS` and :data:`EVAL_FIXTURE_GLOBS` are one source shared
with the hooks (gate-weakening-guard and the ``eval_fixture`` path class), and
:func:`matches_any_glob` keeps the hook glob grammar: ``*`` stays inside one
segment, a leading ``**/`` also matches zero directories.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.artifacts import path_classes
from coding_agent_playbook.grading.paths import (
    EVAL_FIXTURE_GLOBS,
    TEST_PATH_GLOBS,
    is_test_path,
    matches_any_glob,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/a.py", True),
        ("pkg/tests/x.py", True),
        ("test/helpers.py", True),
        ("test_x.py", True),
        ("src/pkg/test_mod.py", True),
        ("src/x_test.py", True),
        ("conftest.py", True),
        ("src/pkg/conftest.py", True),
        ("src/mod.py", False),
        ("src/testing.py", False),
        ("src/latest_tests.py", False),
    ],
)
def test_test_path_globs_table(path: str, expected: bool) -> None:
    assert is_test_path(path) is expected


def test_eval_fixture_glob_matches_engine_and_consumer_setup_trees() -> None:
    engine = "src/coding_agent_playbook/resources/eval_samples/refactor/fix-bug/setup/app.py"
    consumer = "eval_samples/review/t1/setup/pkg/mod.py"

    assert matches_any_glob(engine, EVAL_FIXTURE_GLOBS)
    assert matches_any_glob(consumer, EVAL_FIXTURE_GLOBS)
    assert not matches_any_glob("eval_samples/review/t1/sample.toml", EVAL_FIXTURE_GLOBS)
    assert not matches_any_glob("eval_samples/review/t1/solution/app.py", EVAL_FIXTURE_GLOBS)


def test_constants_are_the_hooks_single_source() -> None:
    assert EVAL_FIXTURE_GLOBS is path_classes.FIXTURE_GLOBS
    assert TEST_PATH_GLOBS is path_classes.TEST_PATH_GLOBS


@pytest.mark.parametrize(
    ("path", "globs", "expected"),
    [
        ("src/a.py", ("src/*.py",), True),
        ("src/pkg/a.py", ("src/*.py",), False),  # '*' never crosses '/'
        ("a.py", ("**/a.py",), True),  # '**/' also matches zero directories
        ("x/y/a.py", ("**/a.py",), True),
        ("gen/deep/x.py", ("gen/**",), True),
        ("src/gen.py", ("gen/**",), False),
        ("src/a.py", (), False),
    ],
)
def test_matches_any_glob_grammar(path: str, globs: tuple[str, ...], expected: bool) -> None:
    assert matches_any_glob(path, globs) is expected
