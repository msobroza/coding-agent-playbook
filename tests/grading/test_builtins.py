"""Per-metric value tests for the five static builtins (SPEC prM §B).

Drives each builtin through the ``Metric`` layer (``get_metric(name).measure``)
and asserts the measured value per scope. Descriptor checks (scope, direction)
live alongside; the threshold/regression policy lives on the ``Check`` layer and
is covered by ``test_check.py`` / ``test_policy.py``.
"""

from __future__ import annotations

from coding_agent_playbook.grading.metric import get_metric
from coding_agent_playbook.grading.parse import parse_module
from coding_agent_playbook.grading.scope import Scope
from coding_agent_playbook.grading.types import EvalContext, Measurement


def _ctx(source: str, label: str = "t.py") -> EvalContext:
    return EvalContext(module=parse_module(source, label), source=source, label=label)


def _by_scope(measurements: list[Measurement]) -> dict[str, float]:
    return {m.scope_key: m.value for m in measurements}


def _values(name: str, source: str) -> dict[str, float]:
    return _by_scope(get_metric(name).measure(_ctx(source)))


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


def test_cyclomatic_descriptors() -> None:
    m = get_metric("cyclomatic_complexity")
    assert m.scope is Scope.FUNCTION
    assert m.requires is None
    # RampNormalizer(good=5, bad=20): higher raw CC -> lower goodness.
    assert m.score(5) == 1.0
    assert m.score(20) == 0.0
    assert m.score(12.5) == 0.5


def test_cyclomatic_measures_each_function() -> None:
    # 1 + if + and + for + if + while + except = 7
    assert _values("cyclomatic_complexity", _HIGH_CC)["t.py::hot"] == 7


def test_cyclomatic_emits_methods_too() -> None:
    src = "class C:\n    def m(self, x):\n        return 1 if x else 0\n"
    assert _values("cyclomatic_complexity", src)["t.py::C.m"] == 2


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


def test_wmc_descriptors() -> None:
    m = get_metric("wmc")
    assert m.scope is Scope.CLASS
    assert m.requires is None
    # RampNormalizer(good=10, bad=60).
    assert m.score(10) == 1.0
    assert m.score(60) == 0.0
    assert m.score(35) == 0.5


def test_wmc_sums_method_complexity() -> None:
    # a: 1+if=2 ; b: 1+for+if=3 ; c: 1 -> 6
    assert _values("wmc", _GOD_CLASS)["t.py::God"] == 6


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


def test_lcom4_descriptors() -> None:
    m = get_metric("lcom4")
    assert m.scope is Scope.CLASS
    # RampNormalizer(good=1, bad=6).
    assert m.score(1) == 1.0
    assert m.score(6) == 0.0


def test_lcom4_two_connected_components() -> None:
    assert _values("lcom4", _TWO_COMPONENT)["t.py::Split"] == 2


def test_lcom4_single_component_is_one() -> None:
    assert _values("lcom4", _ONE_COMPONENT)["t.py::Cohesive"] == 1


def test_lcom4_method_call_links_components() -> None:
    src = (
        "class Linked:\n"
        "    def a(self):\n"
        "        return self.x\n"
        "    def b(self):\n"
        "        return self.a()\n"  # calls self.a -> linked even without shared attr
    )
    assert _values("lcom4", src)["t.py::Linked"] == 1


# --- dit ---------------------------------------------------------------------

_CHAIN = """
class A:
    pass
class B(A):
    pass
class C(B):
    pass
"""


def test_dit_descriptors() -> None:
    m = get_metric("dit")
    assert m.scope is Scope.CLASS
    # RampNormalizer(good=1, bad=8).
    assert m.score(1) == 1.0
    assert m.score(8) == 0.0


def test_dit_three_deep_chain() -> None:
    values = _values("dit", _CHAIN)
    # A has no resolvable base => depth 0; C(B(A)) => depth 2.
    assert values["t.py::A"] == 0
    assert values["t.py::B"] == 1
    assert values["t.py::C"] == 2


def test_dit_external_base_is_depth_one() -> None:
    src = "class E(SomethingExternal):\n    pass\n"
    assert _values("dit", src)["t.py::E"] == 1


# --- cbo (approximate) -------------------------------------------------------

_CBO_CLASS = """
class Service:
    def handle(self, req: Request) -> Response:
        client = HttpClient()
        logger = Logger()
        return Response(client.send(req), logger)
"""


def test_cbo_descriptors() -> None:
    m = get_metric("cbo")
    assert m.scope is Scope.CLASS
    # RampNormalizer(good=3, bad=25).
    assert m.score(3) == 1.0
    assert m.score(25) == 0.0


def test_cbo_counts_distinct_external_types() -> None:
    # Distinct external referenced types: Request, Response, HttpClient, Logger.
    assert _values("cbo", _CBO_CLASS)["t.py::Service"] == 4
