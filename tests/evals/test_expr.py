"""Tests for the boolean-expression interpreter (Track C4).

The interpreter compiles a tiny boolean expression over *handle names*
(e.g. ``"build and (fast or sec)"``) into a ``compose.py`` check tree over a
provided ``name -> Check`` map. These tests drive the tokenizer, the
recursive-descent parser (precedence ``not`` > ``and`` > ``or`` + parens), the
compiler (flattening + identity mapping into ``AllOf``/``AnyOf``/``Not``), the
``names`` helper, and the ``ExprError`` cases.
"""

from __future__ import annotations

import pytest

from coding_agent_playbook.evals.compile._expr import (
    And,
    ExprError,
    Name,
    Not,
    Or,
    compile_expr,
    eval_bool,
    names,
    parse,
)
from coding_agent_playbook.evaluators.check import Check, MeasurementSet
from coding_agent_playbook.evaluators.checks.compose import AllOf, AnyOf
from coding_agent_playbook.evaluators.checks.compose import Not as NotCheck
from coding_agent_playbook.evaluators.scope import CostTier, Determinism
from coding_agent_playbook.evaluators.types import CheckResult, EvalContext


class _StubCheck(Check):
    """A minimal leaf ``Check`` used as a handle value in the tests.

    It never actually grades here - the tests only assert on the *structure* of
    the compiled tree (node types + child identity), not on grading behavior.
    """

    determinism = Determinism.DETERMINISTIC
    cost = CostTier.DETERMINISTIC

    def __init__(self, name: str) -> None:
        self.id = name
        self.weight = 0.0
        self.required = True

    def grade(
        self, ctx: EvalContext, measurements: MeasurementSet
    ) -> CheckResult:  # pragma: no cover - structural tests never grade
        return CheckResult(
            check_id=self.id,
            passed=True,
            score=1.0,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
        )


def _handles(*ids: str) -> dict[str, Check]:
    return {i: _StubCheck(i) for i in ids}


# --------------------------------------------------------------------------- #
# parse: precedence + parens + flattening (AST level)
# --------------------------------------------------------------------------- #


def test_parse_precedence_or_over_and() -> None:
    # "not" > "and" > "or": "a or b and c" => Or(Name(a), And(Name(b), Name(c)))
    node = parse("a or b and c")
    assert node == Or((Name("a"), And((Name("b"), Name("c")))))


def test_parse_precedence_not_over_and() -> None:
    # "not a and b" => And(Not(Name(a)), Name(b)) - not binds tighter than and.
    node = parse("not a and b")
    assert node == And((Not(Name("a")), Name("b")))


def test_parse_parens_override_precedence() -> None:
    # "(a or b) and c" => And(Or(a, b), c)
    node = parse("(a or b) and c")
    assert node == And((Or((Name("a"), Name("b"))), Name("c")))


def test_parse_flattens_chained_and() -> None:
    # "a and b and c" => one And with three children (not nested And(And(a,b),c)).
    node = parse("a and b and c")
    assert node == And((Name("a"), Name("b"), Name("c")))


def test_parse_flattens_chained_or() -> None:
    node = parse("a or b or c")
    assert node == Or((Name("a"), Name("b"), Name("c")))


def test_parse_single_name() -> None:
    assert parse("a") == Name("a")


def test_parse_keywords_case_insensitive() -> None:
    assert parse("a AND b") == And((Name("a"), Name("b")))
    assert parse("NOT a OR b") == Or((Not(Name("a")), Name("b")))


def test_parse_double_not() -> None:
    assert parse("not not a") == Not(Not(Name("a")))


# --------------------------------------------------------------------------- #
# compile_expr: maps names to handle checks + builds the compose.py tree
# --------------------------------------------------------------------------- #


def test_compile_single_name_is_handle_itself() -> None:
    # A bare single Name compiles to the handle check itself (no wrapper).
    handles = _handles("a")
    compiled = compile_expr("a", handles, id="gate")
    assert compiled is handles["a"]


def test_compile_and_builds_allof() -> None:
    handles = _handles("a", "b")
    root = compile_expr("a and b", handles, id="gate")
    assert isinstance(root, AllOf)
    assert root.id == "gate"
    # children map identically to the provided handle checks, in order.
    assert root._children == (handles["a"], handles["b"])


def test_compile_or_builds_anyof() -> None:
    handles = _handles("a", "b")
    root = compile_expr("a or b", handles, id="rubric")
    assert isinstance(root, AnyOf)
    assert root.id == "rubric"
    assert root._children == (handles["a"], handles["b"])


def test_compile_not_builds_not() -> None:
    handles = _handles("a")
    root = compile_expr("not a", handles, id="g")
    assert isinstance(root, NotCheck)
    assert root.id == "g"
    assert root._child is handles["a"]


def test_compile_flattens_chained_and_to_single_allof() -> None:
    # "a and b and c" => one AllOf with 3 children (not nested).
    handles = _handles("a", "b", "c")
    root = compile_expr("a and b and c", handles, id="gate")
    assert isinstance(root, AllOf)
    assert root._children == (handles["a"], handles["b"], handles["c"])
    # No nested composer among the children.
    assert all(child in handles.values() for child in root._children)


def test_compile_nested_tree_structure() -> None:
    # "build and (fast or sec)" => AllOf(build, AnyOf(fast, sec))
    handles = _handles("build", "fast", "sec")
    root = compile_expr("build and (fast or sec)", handles, id="gate")
    assert isinstance(root, AllOf)
    assert root.id == "gate"
    build, inner = root._children
    assert build is handles["build"]
    assert isinstance(inner, AnyOf)
    assert inner.id == "gate"
    assert inner._children == (handles["fast"], handles["sec"])


def test_compile_precedence_or_over_and() -> None:
    # "a or b and c" => AnyOf(a, AllOf(b, c))
    handles = _handles("a", "b", "c")
    root = compile_expr("a or b and c", handles, id="r")
    assert isinstance(root, AnyOf)
    a_compiled, and_compiled = root._children
    assert a_compiled is handles["a"]
    assert isinstance(and_compiled, AllOf)
    assert and_compiled._children == (handles["b"], handles["c"])


# --------------------------------------------------------------------------- #
# names: collect referenced identifiers without compiling
# --------------------------------------------------------------------------- #


def test_names_collects_referenced_identifiers() -> None:
    assert names("a and (b or not c)") == {"a", "b", "c"}


def test_names_single() -> None:
    assert names("a") == {"a"}


def test_names_dedupes() -> None:
    assert names("a and a or a") == {"a"}


# --------------------------------------------------------------------------- #
# eval_bool: evaluate the AST over a name -> bool environment
# --------------------------------------------------------------------------- #


def test_eval_bool_single_name() -> None:
    assert eval_bool(parse("a"), {"a": True}) is True
    assert eval_bool(parse("a"), {"a": False}) is False


def test_eval_bool_and_or_not() -> None:
    env = {"a": True, "b": False, "c": True}
    assert eval_bool(parse("a and c"), env) is True
    assert eval_bool(parse("a and b"), env) is False
    assert eval_bool(parse("a or b"), env) is True
    assert eval_bool(parse("b or not b"), env) is True
    assert eval_bool(parse("not a"), env) is False


def test_eval_bool_precedence_over_bool_env() -> None:
    # "not" > "and" > "or": "a or b and c" with a=False, b=True, c=False is
    # a or (b and c) = False or (True and False) = False.
    env = {"a": False, "b": True, "c": False}
    assert eval_bool(parse("a or b and c"), env) is False
    # flip c to True: a or (b and c) = False or (True and True) = True.
    assert eval_bool(parse("a or b and c"), {**env, "c": True}) is True
    # parens override: "(a or b) and c" = (False or True) and False = False.
    assert eval_bool(parse("(a or b) and c"), env) is False


def test_eval_bool_unknown_name_raises() -> None:
    with pytest.raises(ExprError) as exc:
        eval_bool(parse("a and missing"), {"a": True})
    assert "unknown handle" in str(exc.value)
    assert "'missing'" in str(exc.value)


# --------------------------------------------------------------------------- #
# ExprError cases
# --------------------------------------------------------------------------- #


def test_error_unknown_handle() -> None:
    handles = _handles("a")
    with pytest.raises(ExprError) as exc:
        compile_expr("a and b", handles, id="gate")
    msg = str(exc.value)
    assert "unknown handle" in msg
    assert "'b'" in msg
    # known handles are listed, sorted.
    assert "['a']" in msg


def test_error_empty_string() -> None:
    with pytest.raises(ExprError):
        parse("")


def test_error_whitespace_only() -> None:
    with pytest.raises(ExprError):
        parse("   ")


def test_error_unbalanced_open_paren() -> None:
    with pytest.raises(ExprError):
        parse("(a")


def test_error_unbalanced_close_paren() -> None:
    with pytest.raises(ExprError):
        parse("a)")


def test_error_trailing_junk() -> None:
    # "a b" - two adjacent atoms with no operator.
    with pytest.raises(ExprError):
        parse("a b")


def test_error_illegal_char() -> None:
    with pytest.raises(ExprError):
        parse("a & b")


def test_error_dangling_operator() -> None:
    with pytest.raises(ExprError):
        parse("a and")


def test_error_leading_operator() -> None:
    with pytest.raises(ExprError):
        parse("and a")


def test_error_dangling_not() -> None:
    with pytest.raises(ExprError):
        parse("not")


def test_error_empty_parens() -> None:
    with pytest.raises(ExprError):
        parse("()")


def test_compile_propagates_parse_error() -> None:
    with pytest.raises(ExprError):
        compile_expr("a &", _handles("a"), id="gate")
