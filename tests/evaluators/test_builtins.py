"""Per-evaluator value tests for the five static builtins (SPEC prM §B)."""

from __future__ import annotations

from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.registry import get_evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import EvalContext, Measurement


def _ctx(source: str, label: str = "t.py") -> EvalContext:
    return EvalContext(module=parse_module(source, label), source=source, label=label)


def _by_scope(measurements: list[Measurement]) -> dict[str, float]:
    return {m.scope_key: m.value for m in measurements}


# --- cyclomatic_complexity ---------------------------------------------------

_HIGH_CC = """
def hot(x):
    if x > 0 and x < 10:
        return 1
    for i in range(x):
        if i:
            while i:
                i -= 1
    try:
        return 1 / x
    except ZeroDivisionError:
        return 0
"""


def test_cyclomatic_defaults() -> None:
    ev = get_evaluator("cyclomatic_complexity")
    assert ev.scope is Scope.FUNCTION
    assert ev.value_kind is ValueKind.NUMERIC
    assert ev.determinism is Determinism.DETERMINISTIC
    assert ev.higher_is_worse is True
    assert ev.default_absolute.warn == 10
    assert ev.default_absolute.fail == 20
    assert ev.default_regression.max_worsening == 0.0
    assert ev.requires is None


def test_cyclomatic_measures_each_function() -> None:
    ev = get_evaluator("cyclomatic_complexity")
    ctx = _ctx(_HIGH_CC)
    values = _by_scope(ev.evaluate(ctx))
    # 1 + if + and + for + if + while + except = 7
    assert values["t.py::hot"] == 7


def test_cyclomatic_emits_methods_too() -> None:
    src = "class C:\n    def m(self, x):\n        return 1 if x else 0\n"
    ev = get_evaluator("cyclomatic_complexity")
    values = _by_scope(ev.evaluate(_ctx(src)))
    assert values["t.py::C.m"] == 2


# --- wmc ---------------------------------------------------------------------

_GOD_CLASS = """
class God:
    def a(self, x):
        if x: return 1
        return 0
    def b(self, x):
        for _ in range(x):
            if x: pass
        return x
    def c(self):
        return 1
"""


def test_wmc_defaults() -> None:
    ev = get_evaluator("wmc")
    assert ev.scope is Scope.CLASS
    assert ev.higher_is_worse is True
    assert ev.default_absolute.fail == 50
    assert ev.requires is None


def test_wmc_sums_method_complexity() -> None:
    ev = get_evaluator("wmc")
    values = _by_scope(ev.evaluate(_ctx(_GOD_CLASS)))
    # a: 1+if=2 ; b: 1+for+if=3 ; c: 1 -> 6
    assert values["t.py::God"] == 6


# --- lcom4 -------------------------------------------------------------------

_TWO_COMPONENT = """
class Split:
    def set_x(self, v):
        self.x = v
    def get_x(self):
        return self.x
    def set_y(self, v):
        self.y = v
    def get_y(self):
        return self.y
"""

_ONE_COMPONENT = """
class Cohesive:
    def set_xy(self, a, b):
        self.x = a
        self.y = b
    def total(self):
        return self.x + self.y
"""


def test_lcom4_defaults() -> None:
    ev = get_evaluator("lcom4")
    assert ev.scope is Scope.CLASS
    assert ev.higher_is_worse is True
    assert ev.default_absolute.warn == 2


def test_lcom4_two_connected_components() -> None:
    ev = get_evaluator("lcom4")
    values = _by_scope(ev.evaluate(_ctx(_TWO_COMPONENT)))
    assert values["t.py::Split"] == 2


def test_lcom4_single_component_is_one() -> None:
    ev = get_evaluator("lcom4")
    values = _by_scope(ev.evaluate(_ctx(_ONE_COMPONENT)))
    assert values["t.py::Cohesive"] == 1


def test_lcom4_method_call_links_components() -> None:
    src = (
        "class Linked:\n"
        "    def a(self):\n"
        "        return self.x\n"
        "    def b(self):\n"
        "        return self.a()\n"  # calls self.a -> linked even without shared attr
    )
    ev = get_evaluator("lcom4")
    values = _by_scope(ev.evaluate(_ctx(src)))
    assert values["t.py::Linked"] == 1


# --- dit ---------------------------------------------------------------------

_CHAIN = """
class A:
    pass
class B(A):
    pass
class C(B):
    pass
"""


def test_dit_defaults() -> None:
    ev = get_evaluator("dit")
    assert ev.scope is Scope.CLASS
    assert ev.higher_is_worse is True
    assert ev.default_absolute.warn == 5


def test_dit_three_deep_chain() -> None:
    ev = get_evaluator("dit")
    values = _by_scope(ev.evaluate(_ctx(_CHAIN)))
    # A has no resolvable base => depth 0; C(B(A)) => depth 2.
    assert values["t.py::A"] == 0
    assert values["t.py::B"] == 1
    assert values["t.py::C"] == 2


def test_dit_external_base_is_depth_one() -> None:
    src = "class E(SomethingExternal):\n    pass\n"
    ev = get_evaluator("dit")
    values = _by_scope(ev.evaluate(_ctx(src)))
    assert values["t.py::E"] == 1


# --- cbo (approximate) -------------------------------------------------------

_CBO_CLASS = """
class Service:
    def handle(self, req: Request) -> Response:
        client = HttpClient()
        logger = Logger()
        return Response(client.send(req), logger)
"""


def test_cbo_defaults_and_approximate() -> None:
    ev = get_evaluator("cbo")
    assert ev.scope is Scope.CLASS
    assert ev.higher_is_worse is True
    assert ev.default_absolute.warn == 14


def test_cbo_counts_distinct_external_types() -> None:
    ev = get_evaluator("cbo")
    values = _by_scope(ev.evaluate(_ctx(_CBO_CLASS)))
    # Distinct external referenced types: Request, Response, HttpClient, Logger.
    assert values["t.py::Service"] == 4
