"""The rule-linked lint hooks' AST passes (specs/prK-hook-pack.md §E.3).

Pure functions over an ``ast.Module``: which signature lines are public API
(typing-lint-feedback's ``ANN001``/``ANN201`` filter) and pytest's opt-in
heuristics. The edited module is parsed, never imported or run.
"""

from __future__ import annotations

import ast
from typing import Final

from coding_agent_playbook.hook_runtime.handlers._lint_ast import (
    ASYNCIO_MARK,
    LOOP_ASSERT,
    UNITTEST_CLASS,
    parse_module,
    public_def_lines,
    pytest_ast_heuristics,
)

MODULE: Final = (
    "def api(\n"  # 1
    "    x,\n"  # 2
    "):\n"  # 3
    "    def inner(y):\n"  # 4: nested in a function: internal
    "        return y\n"  # 5
    "    return inner(x)\n"  # 6
    "class Box:\n"  # 7
    "    def __init__(self, v): self.v = v\n"  # 8: a dunder is public API
    "    def _hidden(self, v): pass\n"  # 9
    "    async def get(self): return self.v\n"  # 10
    "class _Private:\n"  # 11
    "    def method(self, v): pass\n"  # 12
)


def test_public_def_lines_cover_signatures_of_public_functions_and_methods() -> None:
    tree = parse_module(MODULE)

    assert tree is not None
    assert sorted(public_def_lines(tree)) == [1, 2, 3, 8, 10]


def test_unparsable_text_gives_no_tree() -> None:
    assert parse_module("def f(:\n") is None
    assert parse_module("x = 1\x00\n") is None


def test_heuristics_flag_each_case_on_its_own_line() -> None:
    source = (
        "import unittest\n"  # 1
        "class TestOld(unittest.TestCase):\n"  # 2
        "    pass\n"  # 3
        "def test_loop():\n"  # 4
        "    for v in [1]:\n"  # 5
        "        assert v\n"  # 6
        "async def test_io():\n"  # 7
        "    pass\n"  # 8
        "@pytest.mark.asyncio\n"  # 9
        "async def test_marked():\n"  # 10
        "    pass\n"  # 11
    )
    tree = ast.parse(source)

    found = pytest_ast_heuristics(tree, created_this_session=True, asyncio_marks=True)
    existing = pytest_ast_heuristics(tree, created_this_session=False)

    assert [(d.code, d.row) for d in found] == [
        (UNITTEST_CLASS, 2),
        (LOOP_ASSERT, 6),
        (ASYNCIO_MARK, 7),
    ]
    assert [d.code for d in existing] == [LOOP_ASSERT]  # an old file's TestCase is left alone
