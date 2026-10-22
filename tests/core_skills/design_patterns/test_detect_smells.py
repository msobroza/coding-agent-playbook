"""Contract tests for ``design-patterns/scripts/detect_smells.py``.

The script ships inside a skill and must run standalone, so it is loaded by path
(never imported as a package module) for the per-smell fixtures and run as a
subprocess for the CLI contract: JSON on stdout, exit 0 with or without hits,
exit 2 on a usage error, unparseable files named on stderr and skipped. Every
fixture is written to ``tmp_path``; line expectations come from ``# <marker>``
comments so the fixtures can be edited without renumbering.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

pytestmark = pytest.mark.catalog

SCRIPT = core_skill_root("design-patterns") / "scripts" / "detect_smells.py"
HIT_KEYS = {"smell", "file", "line", "evidence"}


@pytest.fixture(scope="module")
def detect() -> ModuleType:
    """The script loaded as a module (registered first: dataclasses look it up)."""
    spec = importlib.util.spec_from_file_location("design_patterns_detect_smells", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # No scripts/__pycache__ in the pack source tree (sync skips it anyway).
    writes_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = writes_bytecode
    return module


def _dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def _line(source: str, marker: str) -> int:
    """1-based line of the single line of ``source`` carrying ``# <marker>``."""
    lines = _dedent(source).splitlines()
    matches = [number for number, text in enumerate(lines, 1) if f"# {marker}" in text]
    assert len(matches) == 1, f"marker {marker!r} must appear exactly once"
    return matches[0]


def _scan(detect: ModuleType, tmp_path: Path, source: str) -> list[dict[str, Any]]:
    path = tmp_path / "sample.py"
    path.write_text(_dedent(source), encoding="utf-8")
    found: list[dict[str, Any]] = detect.scan([path])
    assert all(hit["file"] == path.as_posix() for hit in found)
    return found


def _hits(found: list[dict[str, Any]], smell: str) -> list[tuple[int, str]]:
    return [(hit["line"], hit["evidence"]) for hit in found if hit["smell"] == smell]


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
        check=False,
    )


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
    found = _hits(_scan(detect, tmp_path, MUTABLE_DEFAULTS), "mutable-default-argument")
    kw_line = _line(MUTABLE_DEFAULTS, "kw-defaults")
    assert found == [
        (
            _line(MUTABLE_DEFAULTS, "list-default"),
            "parameter 'tags' of 'add_tag' defaults to []",
        ),
        (kw_line, "parameter 'groups' of 'index' defaults to defaultdict(list)"),
        (kw_line, "parameter 'seen' of 'index' defaults to {}"),
        (
            _line(MUTABLE_DEFAULTS, "comprehension-default"),
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
    found = _hits(_scan(detect, tmp_path, ISINSTANCE_CHAINS), "isinstance-ladder")
    assert found == [
        (
            _line(ISINSTANCE_CHAINS, "ladder"),
            "3 isinstance() tests in one if/elif chain on shape",
        ),
        (
            _line(ISINSTANCE_CHAINS, "combined-ladder"),
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
    found = _hits(_scan(detect, tmp_path, LONG_PARAMETERS), "long-parameter-list")
    assert found == [
        (_line(LONG_PARAMETERS, "six"), "'book_freight' takes 6 parameters (more than 5)"),
        (_line(LONG_PARAMETERS, "kw-six"), "'plan_more' takes 6 parameters (more than 5)"),
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
    found = _hits(_scan(detect, tmp_path, BOOLEAN_FLAGS), "boolean-flag-parameter")
    assert found == [
        (_line(BOOLEAN_FLAGS, "annotated"), "'ship' branches on flag 'express'"),
        (_line(BOOLEAN_FLAGS, "defaulted"), "'label' branches on flag 'fragile'"),
        (_line(BOOLEAN_FLAGS, "multiline"), "'notify' branches on flag 'urgent'"),
    ]


EXCEPT_HANDLERS = """
    import builtins


    def load():
        try:
            return read()
        except:  # bare
            pass


    def quiet():
        try:
            risky()
        except Exception:  # pass-body
            pass


    def drain(items):
        for item in items:
            try:
                risky(item)
            except (ValueError, BaseException):  # continue-body
                continue


    def dotted():
        try:
            risky()
        except builtins.Exception:  # ellipsis-body
            ...


    def logged():
        try:
            risky()
        except Exception:
            log.warning("failed")


    def narrow():
        try:
            risky()
        except ValueError:
            pass
"""


def test_bare_except(detect: ModuleType, tmp_path: Path) -> None:
    found = _hits(_scan(detect, tmp_path, EXCEPT_HANDLERS), "bare-except")
    assert found == [
        (
            _line(EXCEPT_HANDLERS, "bare"),
            "bare 'except:' also catches KeyboardInterrupt and SystemExit",
        )
    ]


def test_swallowed_exception_only_for_broad_silent_handlers(
    detect: ModuleType, tmp_path: Path
) -> None:
    found = _hits(_scan(detect, tmp_path, EXCEPT_HANDLERS), "swallowed-exception")
    assert found == [
        (
            _line(EXCEPT_HANDLERS, "pass-body"),
            "'except Exception' discards the error (body: pass)",
        ),
        (
            _line(EXCEPT_HANDLERS, "continue-body"),
            "'except (ValueError, BaseException)' discards the error (body: continue)",
        ),
        (
            _line(EXCEPT_HANDLERS, "ellipsis-body"),
            "'except builtins.Exception' discards the error (body: ...)",
        ),
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
    found = _hits(_scan(detect, tmp_path, NESTING), "deep-nesting")
    assert found == [(_line(NESTING, "fourth"), "'route' nests blocks 5 levels deep (more than 3)")]


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
    found = _hits(_scan(detect, tmp_path, source), "long-function")
    assert found == [(1, "'long_one' spans 51 statement lines (more than 50)")]


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
    found = _hits(_scan(detect, tmp_path, SELFLESS_METHODS), "method-could-be-function")
    assert found == [
        (_line(SELFLESS_METHODS, "selfless"), "'Invoice.currency_symbol' never uses 'self'"),
        (_line(SELFLESS_METHODS, "abc-helper"), "'Exporter.header' never uses 'self'"),
        (_line(SELFLESS_METHODS, "subclass-helper"), "'CsvExporter.banner' never uses 'self'"),
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
    whole = _hits(detect.scan([tmp_path]), "method-could-be-function")
    assert whole == [(8, "'Child.helper' never uses 'self'")]
    # Scanned alone, Child's base is unknown, so any of its methods may be an override.
    assert _hits(detect.scan([child]), "method-could-be-function") == []


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
    found = _hits(_scan(detect, tmp_path, NAMESPACES), "namespace-class")
    assert found == [
        (_line(NAMESPACES, "namespace"), "class 'Geometry' only holds staticmethods (2)")
    ]


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
    found = _hits(_scan(detect, tmp_path, TYPE_NAMES), "type-in-name")
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
        (_line(TYPE_NAMES, marker), f"'{name}' spells its type in its name")
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
    found = _hits(_scan(detect, tmp_path, GLOBALS), "module-level-mutable-global-rebound")
    assert found == [
        (_line(GLOBALS, "global"), "'bump' rebinds module global counter"),
        (_line(GLOBALS, "inner-global"), "'inner' rebinds module global counter, total"),
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
    assert _scan(detect, tmp_path, clean) == []


def test_ancestor_methods_is_none_for_an_unscanned_base(detect: ModuleType) -> None:
    index = detect.ClassIndex({"Base": {"run"}}, {"Base": {"Remote"}})
    assert index.ancestor_methods(["ABC", "ValueError"]) == set()
    assert index.ancestor_methods(["Remote"]) is None
    assert index.ancestor_methods(["Base"]) is None


def test_scanned_code_warnings_stay_silent(detect: ModuleType, tmp_path: Path) -> None:
    # An invalid escape makes the parser warn; pytest turns warnings into errors.
    found = _scan(detect, tmp_path, 'PATTERN = "\\d+"\n\ndef f(x=[]):\n    return x\n')
    assert [hit["smell"] for hit in found] == ["mutable-default-argument"]


# --- pathological depth must not abort a scan --------------------------------------------

# More elif branches than the default recursion limit (1000) allows frames; every
# supported Python still parses it.
LONG_CHAIN_BRANCHES = 1500


def _elif_chain(branches: int, last_body: list[str]) -> str:
    """``dispatch`` with one ``if`` plus ``branches - 1`` elifs; ``last_body`` ends the chain."""
    lines = ["def dispatch(code, rows):", "    if code == 0:", "        pass"]
    for number in range(1, branches):
        lines += [f"    elif code == {number}:", "        pass"]
    return "\n".join(lines + last_body) + "\n"


def _sum_of(terms: int) -> str:
    return " + ".join(f"a{number}" for number in range(terms))


def test_deep_nesting_survives_an_elif_chain_longer_than_the_stack(
    detect: ModuleType, tmp_path: Path
) -> None:
    # Regression: block_levels recursed once per elif and raised RecursionError.
    nested = [
        "    elif code == -1:",
        "        for row in rows:",
        "            if row:",
        "                with row:  # fourth",
        "                    while row:",
        "                        pass",
    ]
    source = _elif_chain(LONG_CHAIN_BRANCHES, nested)
    found = _hits(_scan(detect, tmp_path, source), "deep-nesting")
    fourth = source.splitlines().index("                with row:  # fourth") + 1
    assert found == [(fourth, "'dispatch' nests blocks 5 levels deep (more than 3)")]


def test_snippet_falls_back_for_an_expression_too_deep_to_unparse(detect: ModuleType) -> None:
    # Regression: ast.unparse recursed past the limit and aborted the whole scan.
    deep: ast.expr = ast.Name("a0")
    for number in range(1, 5 * sys.getrecursionlimit()):
        deep = ast.BinOp(deep, ast.Add(), ast.Name(f"a{number}"))
    assert detect.snippet(deep) == detect.TOO_DEEP_TO_PRINT
    assert detect.snippet(ast.parse("total + 1", mode="eval").body) == "total + 1"


def test_scan_skips_only_the_module_that_exhausts_the_stack(
    detect: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def stack_exhausting_detector(module: Any) -> Iterator[Any]:
        """Bare excepts, except in a module defining ``too_deep`` (stands in for any overflow)."""
        if "too_deep" in {fn.name for fn in detect.functions_in(module.tree)}:
            raise RecursionError("maximum recursion depth exceeded")
        yield from detect.detect_bare_excepts(module)

    _write_tree(tmp_path, {"deep.py": BARE + "def too_deep():\n    pass\n", "ok.py": BARE})
    found = detect.scan([tmp_path], detectors=(stack_exhausting_detector,))
    assert [(hit["file"], hit["smell"]) for hit in found] == [
        ((tmp_path / "ok.py").as_posix(), "bare-except")
    ]
    stderr = capsys.readouterr().err
    assert f"skipped {(tmp_path / 'deep.py').as_posix()}: maximum recursion depth" in stderr


# --- CLI contract ------------------------------------------------------------------------


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


BARE = "try:\n    pass\nexcept:\n    pass\n"


def test_cli_prints_sorted_json_and_exits_zero_with_hits(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "b.py": "def f(x=[], y_str=''):\n    global z\n",
            "a.py": BARE + "def g(items={}):\n    return items\n",
        },
    )
    first = _run(str(tmp_path / "b.py"), str(tmp_path))
    assert first.returncode == 0, first.stderr
    hits = json.loads(first.stdout)
    assert hits and all(set(hit) == HIT_KEYS for hit in hits)
    keys = [(hit["file"], hit["line"], hit["smell"]) for hit in hits]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys)), "a file named twice is scanned once"
    assert _run(str(tmp_path), str(tmp_path / "b.py")).stdout == first.stdout


def test_cli_default_path_recurses_and_skips_tool_dirs(tmp_path: Path) -> None:
    skipped = [".hidden", ".venv", "venv", "node_modules", "__pycache__", "lib/site-packages"]
    _write_tree(tmp_path, {f"{folder}/mod.py": BARE for folder in skipped})
    _write_tree(tmp_path, {"pkg/mod.py": BARE, "pkg/notes.txt": BARE})
    result = _run(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {
            "smell": "bare-except",
            "file": "pkg/mod.py",
            "line": 3,
            "evidence": "bare 'except:' also catches KeyboardInterrupt and SystemExit",
        }
    ]


def test_cli_clean_tree_prints_an_empty_array(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("VALUE = 1\n", encoding="utf-8")
    result = _run(str(tmp_path))
    assert (result.returncode, json.loads(result.stdout)) == (0, [])


def test_cli_unparseable_file_is_reported_and_skipped(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"broken.py": "def broken(:\n", "good.py": BARE})
    result = _run(str(tmp_path))
    assert result.returncode == 0
    assert "broken.py" in result.stderr
    assert [hit["file"] for hit in json.loads(result.stdout)] == [(tmp_path / "good.py").as_posix()]


def test_cli_deep_files_do_not_abort_a_multi_file_scan(tmp_path: Path) -> None:
    # Regression: one of these used to end the run with exit 1, a traceback and no JSON.
    terms = _sum_of(400)
    _write_tree(
        tmp_path,
        {
            "chain.py": _elif_chain(LONG_CHAIN_BRANCHES, []),
            "default.py": f"def f(x=[{terms}]):\n    return x\n",
            "ladder.py": "def g(v):\n"
            + "".join(
                f"    {keyword} isinstance({terms}, {kind}):\n        return 1\n"
                for keyword, kind in [("if", "int"), ("elif", "str"), ("elif", "float")]
            ),
            "plain.py": BARE,
        },
    )
    result = _run(str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    found = {(Path(hit["file"]).name, hit["smell"]) for hit in json.loads(result.stdout)}
    assert found == {
        ("chain.py", "long-function"),
        ("default.py", "mutable-default-argument"),
        ("ladder.py", "isinstance-ladder"),
        ("plain.py", "bare-except"),
    }


@pytest.mark.parametrize(
    "args",
    [["does-not-exist.py"], ["--no-such-option"]],
    ids=["missing-path", "unknown-option"],
)
def test_cli_usage_errors_exit_2(tmp_path: Path, args: list[str]) -> None:
    result = _run(*args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "error" in result.stderr


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions enforced for a non-root user",
)
def test_cli_unreadable_path_exits_2(tmp_path: Path) -> None:
    locked = tmp_path / "locked.py"
    locked.write_text(BARE, encoding="utf-8")
    locked.chmod(0)
    try:
        result = _run(str(locked))
    finally:
        locked.chmod(0o644)
    assert result.returncode == 2
    assert "cannot read" in result.stderr


@pytest.mark.skipif(shutil.which("python3.10") is None, reason="python3.10 is not installed")
def test_cli_runs_on_python_310(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(BARE, encoding="utf-8")
    interpreter = shutil.which("python3.10")
    assert interpreter is not None
    result = subprocess.run(
        [interpreter, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [hit["smell"] for hit in json.loads(result.stdout)] == ["bare-except"]
