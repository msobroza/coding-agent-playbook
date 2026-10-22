"""``detect_smells.py`` on function signatures and bodies: mutable defaults,
isinstance ladders, long parameter lists, boolean flags, nesting and length.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.design_patterns._scripts import hits_of, line_of, scan_smells

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog

# --- one fixture per smell, positives and near misses ------------------------------------

MUTABLE_DEFAULTS = """
    from collections import defaultdict


    def add_tag(tag, tags=[]):  # list-default
        return tags


    def index(*, seen={}, groups=defaultdict(list)):  # kw-defaults
        return seen, groups


    def squares(table={n: n * n for n in range(3)}):  # comprehension-default
        return table


    def safe(tags=None, size=(1, 2), label="x", frozen=frozenset()):
        return tags, size, label, frozen
"""


def test_mutable_default_argument(detect: ModuleType, tmp_path: Path) -> None:
    found = hits_of(scan_smells(detect, tmp_path, MUTABLE_DEFAULTS), "mutable-default-argument")
    kw_line = line_of(MUTABLE_DEFAULTS, "kw-defaults")
    assert found == [
        (
            line_of(MUTABLE_DEFAULTS, "list-default"),
            "parameter 'tags' of 'add_tag' defaults to []",
        ),
        (kw_line, "parameter 'groups' of 'index' defaults to defaultdict(list)"),
        (kw_line, "parameter 'seen' of 'index' defaults to {}"),
        (
            line_of(MUTABLE_DEFAULTS, "comprehension-default"),
            "parameter 'table' of 'squares' defaults to {n: n * n for n in range(3)}",
        ),
    ]


ISINSTANCE_CHAINS = """
    def describe(shape):
        if isinstance(shape, Circle):  # ladder
            return "round"
        elif isinstance(shape, Square):
            return "boxy"
        elif isinstance(shape, Triangle):
            return "pointy"
        return "?"


    def two_branches(shape):
        if isinstance(shape, Circle):
            return "round"
        elif isinstance(shape, Square):
            return "boxy"
        return "?"


    def separate_ifs(shape):
        if isinstance(shape, Circle):
            return 1
        if isinstance(shape, Square):
            return 2
        if isinstance(shape, Triangle):
            return 3
        return 0


    def combined(token):
        if isinstance(token, int) or isinstance(token, float):  # combined-ladder
            return "number"
        elif isinstance(token, str):
            return "text"
        return "other"
"""


def test_isinstance_ladder_needs_three_tests_in_one_chain(
    detect: ModuleType, tmp_path: Path
) -> None:
    found = hits_of(scan_smells(detect, tmp_path, ISINSTANCE_CHAINS), "isinstance-ladder")
    assert found == [
        (
            line_of(ISINSTANCE_CHAINS, "ladder"),
            "3 isinstance() tests in one if/elif chain on shape",
        ),
        (
            line_of(ISINSTANCE_CHAINS, "combined-ladder"),
            "3 isinstance() tests in one if/elif chain on token",
        ),
    ]


LONG_PARAMETERS = """
    def book_freight(origin, destination, weight, volume, carrier, insured):  # six
        return origin


    def five(origin, destination, weight, volume, carrier):
        return origin


    class Planner:
        def plan(self, origin, destination, weight, volume, carrier):
            return origin

        def plan_more(self, origin, destination, weight, volume, *, carrier, insured):  # kw-six
            return origin

        @classmethod
        def build(cls, origin, destination, weight, volume, carrier):
            return cls()

        def variadic(self, origin, destination, weight, volume, carrier, *rest, **extra):
            return origin
"""


def test_long_parameter_list_excludes_receiver_and_catch_alls(
    detect: ModuleType, tmp_path: Path
) -> None:
    found = hits_of(scan_smells(detect, tmp_path, LONG_PARAMETERS), "long-parameter-list")
    assert found == [
        (line_of(LONG_PARAMETERS, "six"), "'book_freight' takes 6 parameters (more than 5)"),
        (line_of(LONG_PARAMETERS, "kw-six"), "'plan_more' takes 6 parameters (more than 5)"),
    ]


BOOLEAN_FLAGS = """
    def ship(parcel, express: bool):  # annotated
        if express:
            return "air"
        return "ground"


    def label(parcel, fragile=False):  # defaulted
        return "careful" if fragile else "normal"


    def notify(
        user,
        urgent: "bool" = False,  # multiline
    ):
        if urgent and user:
            return 1
        return 0


    def log(parcel, verbose: bool = False):
        return parcel, verbose


    def route(parcel, mode: str = "air"):
        if mode == "air":
            return 1
        return 2


    class Parcel:
        @property
        def sealed(self):
            return self._sealed

        @sealed.setter
        def sealed(self, value: bool):
            if value:
                self._sealed = True
"""


def test_boolean_flag_parameter_must_drive_a_branch(detect: ModuleType, tmp_path: Path) -> None:
    found = hits_of(scan_smells(detect, tmp_path, BOOLEAN_FLAGS), "boolean-flag-parameter")
    assert found == [
        (line_of(BOOLEAN_FLAGS, "annotated"), "'ship' branches on flag 'express'"),
        (line_of(BOOLEAN_FLAGS, "defaulted"), "'label' branches on flag 'fragile'"),
        (line_of(BOOLEAN_FLAGS, "multiline"), "'notify' branches on flag 'urgent'"),
    ]


NESTING = """
    def route(orders, lock):
        for order in orders:
            if order.paid:
                with lock:
                    if order.urgent:  # fourth
                        while order.retry:
                            send(order)


    def chain(kind, items, lock):
        for item in items:
            if kind == 1:
                pass
            elif kind == 2:
                pass
            elif kind == 3:
                with lock:
                    send(item)


    def outer(rows):
        for row in rows:
            if row:
                def inner(cells):
                    for cell in cells:
                        if cell:
                            with cell:
                                return cell
                inner(row)


    def guarded(rows):
        try:
            for row in rows:
                if row:
                    pass
        except ValueError:
            for row in rows:
                if row:
                    pass
"""


def test_deep_nesting_counts_blocks_not_elifs_or_nested_functions(
    detect: ModuleType, tmp_path: Path
) -> None:
    found = hits_of(scan_smells(detect, tmp_path, NESTING), "deep-nesting")
    assert found == [
        (line_of(NESTING, "fourth"), "'route' nests blocks 5 levels deep (more than 3)")
    ]


def _function_source(name: str, statements: int, *, docstring: bool = False) -> str:
    body = ['    """Docs."""'] if docstring else []
    body += [f"    step{i} = {i}" for i in range(statements)]
    return f"def {name}():\n" + "\n".join(body) + "\n"


def test_long_function_counts_statement_lines(detect: ModuleType, tmp_path: Path) -> None:
    tall_statement = "def tall():\n    return [\n" + "        1,\n" * 70 + "    ]\n"
    source = "\n\n".join(
        [
            _function_source("long_one", 51),
            _function_source("fifty", 50, docstring=True),
            tall_statement,
        ]
    )
    found = hits_of(scan_smells(detect, tmp_path, source), "long-function")
    assert found == [(1, "'long_one' spans 51 statement lines (more than 50)")]
