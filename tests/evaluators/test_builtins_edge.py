"""Edge-case coverage for the static builtins (SPEC prM §B/§I).

Drives each builtin through the ``Metric`` layer (``get_metric(name).measure``).
"""

from __future__ import annotations

from coding_agent_playbook.evaluators.metric import get_metric
from coding_agent_playbook.evaluators.parse import parse_module
from coding_agent_playbook.evaluators.types import EvalContext


def _ctx(source: str, label: str = "t.py") -> EvalContext:
    return EvalContext(module=parse_module(source, label), source=source, label=label)


def _values(name: str, source: str) -> dict[str, float]:
    m = get_metric(name)
    return {meas.scope_key: meas.value for meas in m.measure(_ctx(source))}


def test_builtins_return_empty_without_module() -> None:
    empty = EvalContext(module=None, source="", label="x")
    for name in ("cyclomatic_complexity", "wmc", "lcom4", "dit", "cbo"):
        assert get_metric(name).measure(empty) == []


def test_cbo_counts_base_class_and_attribute_annotation() -> None:
    src = (
        "class Widget(framework.Base):\n"
        "    handler: EventHandler\n"
        "    def run(self):\n"
        "        return Helper()\n"
    )
    # Base attr 'Base' (from framework.Base), EventHandler (AnnAssign), Helper (call).
    values = _values("cbo", src)
    assert values["t.py::Widget"] == 3


def test_cbo_unwraps_subscript_and_tuple_annotations() -> None:
    src = (
        "class Store:\n"
        "    def get(self, key: str) -> dict[KeyType, ValueType]:\n"
        "        return {}\n"
        "    def pair(self) -> tuple[Left, Right]:\n"
        "        return Left(), Right()\n"
    )
    # Annotation types: KeyType, ValueType, Left, Right (str is a builtin, dropped).
    values = _values("cbo", src)
    assert values["t.py::Store"] == 4


def test_lcom4_empty_class_is_zero_components() -> None:
    src = "class Empty:\n    x = 1\n"
    assert _values("lcom4", src)["t.py::Empty"] == 0


def test_dit_diamond_takes_longest_chain() -> None:
    src = (
        "class A:\n    pass\n"
        "class B(A):\n    pass\n"
        "class C(A):\n    pass\n"
        "class D(B, C):\n    pass\n"
    )
    values = _values("dit", src)
    # D -> B -> A and D -> C -> A both depth 2.
    assert values["t.py::D"] == 2


def test_cyclomatic_assert_and_match_guard() -> None:
    src = (
        "def f(x):\n"
        "    assert x\n"
        "    match x:\n"
        "        case 1:\n"
        "            return 1\n"
        "        case _ if x > 5:\n"
        "            return 2\n"
        "    return 0\n"
    )
    # 1 base + assert + guarded case = 3 (bare `case 1` adds nothing).
    assert _values("cyclomatic_complexity", src)["t.py::f"] == 3
