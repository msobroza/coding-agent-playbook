"""Tests for the shared AST parse layer (SPEC prM §A/§B)."""

from __future__ import annotations

import ast

import pytest

from coding_agent_playbook.evaluators.parse import (
    ModuleModel,
    parse_module,
    scope_key,
)
from coding_agent_playbook.evaluators.scope import Scope

_HIGH_CC = '''
def grade(x):
    """A high-CC function: many decision points."""
    if x > 0 and x < 10:
        return 1
    for i in range(x):
        if i % 2 == 0:
            continue
        while i > 0:
            i -= 1
    try:
        y = 1 / x
    except ZeroDivisionError:
        y = 0
    except ValueError:
        y = -1
    z = [n for n in range(x) if n > 1]
    return y if x else z
'''

_CLASSES = """
class Base:
    def m(self):
        return self.a

class Derived(Base):
    attr = 1
    def __init__(self):
        self.a = 1
    def method(self, x):
        if x:
            return self.a
        return 0
"""


def test_parse_module_collects_functions_and_classes() -> None:
    model = parse_module(_CLASSES, "mod.py")
    assert isinstance(model, ModuleModel)
    assert model.label == "mod.py"
    class_names = {c.qualname for c in model.classes}
    assert class_names == {"Base", "Derived"}


def test_function_scope_records_cyclomatic() -> None:
    model = parse_module(_HIGH_CC, "f.py")
    funcs = {f.qualname: f for f in model.functions}
    assert "grade" in funcs
    # 1 base + if + BoolOp(and) + for + if + while + 2 excepts + comp-if + IfExp = 10
    assert funcs["grade"].complexity == 10


def test_simple_function_complexity_is_one() -> None:
    model = parse_module("def f():\n    return 1\n", "s.py")
    assert model.functions[0].complexity == 1


def test_method_qualname_and_scope_kind() -> None:
    model = parse_module(_CLASSES, "mod.py")
    methods = {f.qualname: f for f in model.functions}
    assert "Derived.method" in methods
    assert methods["Derived.method"].scope is Scope.METHOD
    # module-level function would be Scope.FUNCTION; this is a method.


def test_class_scope_lists_its_methods() -> None:
    model = parse_module(_CLASSES, "mod.py")
    derived = next(c for c in model.classes if c.qualname == "Derived")
    method_names = {m.qualname for m in derived.methods}
    assert method_names == {"Derived.__init__", "Derived.method"}
    assert derived.bases == ["Base"]


def test_scope_key_for_qualname_and_file() -> None:
    assert scope_key("mod.py", "Derived.method") == "mod.py::Derived.method"
    assert scope_key("mod.py", None) == "mod.py"


def test_function_scope_exposes_scope_key() -> None:
    model = parse_module(_HIGH_CC, "f.py")
    assert model.functions[0].scope_key == "f.py::grade"


def test_class_scope_exposes_scope_key() -> None:
    model = parse_module(_CLASSES, "mod.py")
    base = next(c for c in model.classes if c.qualname == "Base")
    assert base.scope_key == "mod.py::Base"


def test_match_statement_counts_guards() -> None:
    src = (
        "def f(x):\n"
        "    match x:\n"
        "        case 1 if x > 0:\n"
        "            return 1\n"
        "        case _:\n"
        "            return 0\n"
    )
    model = parse_module(src, "m.py")
    # 1 base + match guard (the `if x > 0`) = 2; bare `case _` adds nothing.
    assert model.functions[0].complexity == 2


def test_parse_module_rejects_syntax_error() -> None:
    with pytest.raises(SyntaxError):
        parse_module("def (:\n", "bad.py")


def test_cyclomatic_helper_is_shared_single_source() -> None:
    # The helper must exist as a module-level callable so WMC and CC reuse it.
    from coding_agent_playbook.evaluators.parse import _cyclomatic

    tree = ast.parse("def f(x):\n    if x:\n        return 1\n    return 0\n")
    fn = tree.body[0]
    assert isinstance(fn, ast.FunctionDef)
    assert _cyclomatic(fn) == 2
