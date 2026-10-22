"""``detect_smells.py`` on classes: methods that could be functions, namespace
classes, and the cross-module class index behind the override checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.design_patterns._scripts import hits_of, line_of, scan_smells

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog

SELFLESS_METHODS = """
    import typing
    from abc import ABC, abstractmethod
    from typing import Protocol, overload, override


    class Invoice:
        def __init__(self, lines):
            self.lines = lines

        def total(self):
            return sum(self.lines)

        def currency_symbol(self):  # selfless
            return "EUR"

        @staticmethod
        def round_cents(amount):
            return round(amount, 2)

        @classmethod
        def empty(cls):
            return cls([])

        @property
        def kind(self):
            return "invoice"

        def __repr__(self):
            return "Invoice"

        def refresh(self):
            return super().refresh()

        def placeholder(self):
            raise NotImplementedError

        @overload
        def scale(self, factor: int) -> int: ...


    class Exporter(ABC):
        @abstractmethod
        def export(self, rows):
            return list(rows)

        def header(self):  # abc-helper
            return "id,name"

        def footer(self):
            return ""


    class CsvExporter(Exporter):
        def export(self, rows):
            return [",".join(row) for row in rows]

        def footer(self):
            return "--"

        @override
        def flush(self):
            return None

        @typing.override
        def close(self):
            return None

        def banner(self):  # subclass-helper
            return "csv"


    class Webhook(ExternalHandler):
        def handle(self, event):
            return event


    class Renderer(Protocol):
        def render(self, page):
            return page


    class TestInvoice:
        def test_symbol(self):
            assert True
"""


def test_method_could_be_function_skips_overrides_hooks_and_interfaces(
    detect: ModuleType, tmp_path: Path
) -> None:
    found = hits_of(scan_smells(detect, tmp_path, SELFLESS_METHODS), "method-could-be-function")
    assert found == [
        (line_of(SELFLESS_METHODS, "selfless"), "'Invoice.currency_symbol' never uses 'self'"),
        (line_of(SELFLESS_METHODS, "abc-helper"), "'Exporter.header' never uses 'self'"),
        (line_of(SELFLESS_METHODS, "subclass-helper"), "'CsvExporter.banner' never uses 'self'"),
    ]


def test_method_could_be_function_resolves_bases_across_scanned_files(
    detect: ModuleType, tmp_path: Path
) -> None:
    (tmp_path / "base.py").write_text(
        "class Hooks:\n    def on_start(self):\n        return self\n", encoding="utf-8"
    )
    child = tmp_path / "child.py"
    child.write_text(
        "from base import Hooks\n\n\nclass Child(Hooks):\n"
        "    def on_start(self):\n        return 1\n\n"
        "    def helper(self):\n        return 2\n",
        encoding="utf-8",
    )
    whole = hits_of(detect.scan([tmp_path]), "method-could-be-function")
    assert whole == [(8, "'Child.helper' never uses 'self'")]
    # Scanned alone, Child's base is unknown, so any of its methods may be an override.
    assert hits_of(detect.scan([child]), "method-could-be-function") == []


NAMESPACES = """
    from dataclasses import dataclass


    class Geometry:  # namespace
        UNIT = "cm"

        @staticmethod
        def area(radius):
            return radius * radius

        @staticmethod
        def perimeter(radius):
            return 2 * radius


    class Mixed:
        @staticmethod
        def parse(text):
            return text

        def render(self):
            return self


    class Constants:
        UNIT = "cm"


    @dataclass
    class Report:
        rows: list

        @staticmethod
        def blank():
            return Report([])


    class Fields:
        rows: list

        @staticmethod
        def blank():
            return None


    class Derived(Base):
        @staticmethod
        def build():
            return None
"""


def test_namespace_class_only_for_plain_staticmethod_holders(
    detect: ModuleType, tmp_path: Path
) -> None:
    found = hits_of(scan_smells(detect, tmp_path, NAMESPACES), "namespace-class")
    assert found == [
        (line_of(NAMESPACES, "namespace"), "class 'Geometry' only holds staticmethods (2)")
    ]


def test_ancestor_methods_is_none_for_an_unscanned_base(detect: ModuleType) -> None:
    index = detect.ClassIndex({"Base": {"run"}}, {"Base": {"Remote"}})
    assert index.ancestor_methods(["ABC", "ValueError"]) == set()
    assert index.ancestor_methods(["Remote"]) is None
    assert index.ancestor_methods(["Base"]) is None
