"""Regression checks for ``python-architecture/references/worked-example.md``.

The worked example is the template agents copy, so its code must follow the
skill's own persistence rules: the open-loan race is closed by a partial unique
index, and the driver error that index raises is translated into the domain
error inside the repository (a leak would answer 500 instead of 409). The repo's
test environment has neither SQLAlchemy nor FastAPI, so the ``# <path>`` code
blocks are read with ``ast`` rather than run.
"""

from __future__ import annotations

import ast
import re

import pytest

from tests._content import plugin_root

EXAMPLE = (
    plugin_root("python_design") / "skills" / "python-architecture/references/worked-example.md"
)
#: A fenced Python block whose first line names the module it holds.
_MODULE_BLOCK_RE = re.compile(r"```python\n# (?P<path>\S+\.py)\n(?P<body>.*?)```", re.S)
EXPECTED_MODULES = frozenset(
    {
        "tool_library/domain/model.py",
        "tool_library/services/lending.py",
        "tool_library/db/sql.py",
        "tool_library/api/routes.py",
        "tool_library/deps.py",
        "tool_library/main.py",
        "tests/fakes.py",
        "tests/test_lending.py",
    }
)


@pytest.fixture(scope="module")
def modules() -> dict[str, ast.Module]:
    """Each module block of the example, parsed (a syntax error fails here)."""
    text = EXAMPLE.read_text(encoding="utf-8")
    return {
        match["path"]: ast.parse(match["body"], filename=match["path"])
        for match in _MODULE_BLOCK_RE.finditer(text)
    }


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    found = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name]
    assert len(found) == 1, f"expected one class {name!r}, found {len(found)}"
    return found[0]


def _method(tree: ast.Module, class_name: str, name: str) -> ast.FunctionDef:
    body = _class(tree, class_name).body
    found = [node for node in body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(found) == 1, f"expected one method {class_name}.{name}, found {len(found)}"
    return found[0]


def _called_name(node: ast.AST | None) -> str:
    """``Index(...)`` -> ``Index``; anything but a call to a plain name -> ``""``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def _calls_to(scope: ast.AST, name: str) -> list[ast.Call]:
    """Every ``<name>(...)`` call inside ``scope``."""
    calls = (node for node in ast.walk(scope) if isinstance(node, ast.Call))
    return [call for call in calls if _called_name(call) == name]


def _raises(scope: ast.AST, error: str) -> list[ast.Raise]:
    """Every ``raise <error>(...)`` inside ``scope``."""
    found = (node for node in ast.walk(scope) if isinstance(node, ast.Raise))
    return [node for node in found if _called_name(node.exc) == error]


def test_every_module_of_the_tree_ships_as_a_parseable_block(
    modules: dict[str, ast.Module],
) -> None:
    assert set(modules) == EXPECTED_MODULES


def test_loan_table_declares_the_partial_unique_open_loan_index(
    modules: dict[str, ast.Module],
) -> None:
    # Regression: the prose relied on this index but the mapping never declared it.
    loan_row = _class(modules["tool_library/db/sql.py"], "LoanRow")
    table_args = [
        stmt.value
        for stmt in loan_row.body
        if isinstance(stmt, ast.Assign)
        and [ast.unparse(target) for target in stmt.targets] == ["__table_args__"]
    ]
    indexes = [call for arg in table_args for call in _calls_to(arg, "Index")]
    assert len(indexes) == 1, "LoanRow.__table_args__ must declare the open-loan index"
    keywords = {kw.arg: ast.unparse(kw.value) for kw in indexes[0].keywords}
    assert keywords["unique"] == "True"
    where = "text('returned_on IS NULL')"
    assert (keywords["sqlite_where"], keywords["postgresql_where"]) == (where, where)


def test_loan_repository_translates_the_index_violation(modules: dict[str, ast.Module]) -> None:
    # Regression: IntegrityError escaped SqlLoanRepository.add and answered 500, not 409.
    add = _method(modules["tool_library/db/sql.py"], "SqlLoanRepository", "add")
    handlers = [
        handler
        for node in ast.walk(add)
        if isinstance(node, ast.Try)
        for handler in node.handlers
        if handler.type is not None and ast.unparse(handler.type) == "IntegrityError"
    ]
    assert len(handlers) == 1, "add() must catch IntegrityError around the flush"
    raised = _raises(handlers[0], "ToolOnLoanError")
    assert len(raised) == 1 and raised[0].cause is not None, "raise the domain error `from` it"


def test_fake_loan_repository_refuses_a_second_open_loan_too(
    modules: dict[str, ast.Module],
) -> None:
    # A fake raises the same domain errors as the real implementation (testability.md).
    add = _method(modules["tests/fakes.py"], "InMemoryLoanRepository", "add")
    assert _raises(add, "ToolOnLoanError")
