"""``detect_smells.py`` on names and module state: type-in-name and ``global``
rebinding, plus a clean module and the scanned code's own warnings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.design_patterns._scripts import hits_of, line_of, scan_smells

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog

TYPE_NAMES = """
    def render(name_str, count: int, items_list=None):  # params
        total_int = 0  # assign
        for price_str in []:  # loop
            total_int += 1
        dict_of_codes = {}  # prefix
        total_int = 5
        description, (first_bool, *rest_list) = "", (True, 1)  # unpack
        if (size_int := 3):  # walrus
            pass
        __dict__ = {}
        _ = None
        return total_int, description, dict_of_codes, size_int


    class Box:
        default_tuple = ()  # class-attr

        def __init__(self):
            self.label_str = "x"  # self-attr
            self.size = 1
"""


def test_type_in_name_reports_first_binding_per_scope(detect: ModuleType, tmp_path: Path) -> None:
    found = hits_of(scan_smells(detect, tmp_path, TYPE_NAMES), "type-in-name")
    expected = [
        ("params", "items_list"),
        ("params", "name_str"),
        ("assign", "total_int"),
        ("loop", "price_str"),
        ("prefix", "dict_of_codes"),
        ("unpack", "first_bool"),
        ("unpack", "rest_list"),
        ("walrus", "size_int"),
        ("class-attr", "default_tuple"),
        ("self-attr", "label_str"),
    ]
    assert found == [
        (line_of(TYPE_NAMES, marker), f"'{name}' spells its type in its name")
        for marker, name in expected
    ]


GLOBALS = """
    counter = 0


    def bump():
        global counter  # global
        counter += 1


    def read():
        return counter


    def nested():
        def inner():
            global counter, total  # inner-global
            counter = 1
        return inner
"""


def test_global_statement(detect: ModuleType, tmp_path: Path) -> None:
    found = hits_of(scan_smells(detect, tmp_path, GLOBALS), "module-level-mutable-global-rebound")
    assert found == [
        (line_of(GLOBALS, "global"), "'bump' rebinds module global counter"),
        (line_of(GLOBALS, "inner-global"), "'inner' rebinds module global counter, total"),
    ]


def test_clean_module_has_no_candidates(detect: ModuleType, tmp_path: Path) -> None:
    clean = """
        class Meter:
            def __init__(self, reading: float) -> None:
                self.reading = reading

            def advance(self, delta: float) -> float:
                if delta < 0:
                    raise ValueError(f"delta must be >= 0, got {delta}")
                self.reading += delta
                return self.reading
    """
    assert scan_smells(detect, tmp_path, clean) == []


def test_scanned_code_warnings_stay_silent(detect: ModuleType, tmp_path: Path) -> None:
    # An invalid escape makes the parser warn; pytest turns warnings into errors.
    found = scan_smells(detect, tmp_path, 'PATTERN = "\\d+"\n\ndef f(x=[]):\n    return x\n')
    assert [hit["smell"] for hit in found] == ["mutable-default-argument"]
