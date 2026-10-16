"""Contract tests for ``python-design-review/scripts/lcom4_clusters.py``.

The script ships inside a skill and must run standalone, so it is loaded by path
for the graph fixtures and run as a subprocess for the CLI contract: a JSON
array of ``{"class", "file", "line", "lcom4", "clusters"}`` for classes with
lcom4 > 1 (every in-scope class with ``--all``), exit 0, and exit 2 on a usage
error. Fixtures are written to ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING, Any

import pytest

from tests._content import plugin_root

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

SCRIPT = plugin_root("python_design") / "skills" / "python-design-review/scripts/lcom4_clusters.py"
RESULT_KEYS = {"class", "file", "line", "lcom4", "clusters"}


@pytest.fixture(scope="module")
def lcom4() -> ModuleType:
    """The script loaded as a module (registered first: dataclasses look it up)."""
    spec = importlib.util.spec_from_file_location("python_design_lcom4_clusters", SCRIPT)
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


def _scan(
    lcom4: ModuleType, tmp_path: Path, source: str, *, include_cohesive: bool = False
) -> list[dict[str, Any]]:
    path = tmp_path / "sample.py"
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    found: list[dict[str, Any]] = lcom4.scan([path], include_cohesive=include_cohesive)
    assert all(set(item) == RESULT_KEYS and item["file"] == path.as_posix() for item in found)
    return found


def _clusters(found: list[dict[str, Any]]) -> dict[str, tuple[int, list[list[str]]]]:
    return {item["class"]: (item["lcom4"], item["clusters"]) for item in found}


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
        check=False,
    )


SHOP = """
    class Storefront:
        def __init__(self, inventory, mailer):
            self.inventory = inventory
            self.mailer = mailer

        def restock(self, sku, quantity):
            self.inventory[sku] = self.inventory.get(sku, 0) + quantity

        def in_stock(self, sku):
            return self.inventory.get(sku, 0) > 0

        def notify(self, message):
            self.mailer.send(message)

        def welcome(self, customer):
            self.notify(f"hello {customer}")

        def __repr__(self):
            return f"Storefront({self.inventory}, {self.mailer})"
"""


def test_two_cluster_class_reports_both_clusters(lcom4: ModuleType, tmp_path: Path) -> None:
    found = _scan(lcom4, tmp_path, SHOP)
    assert [(item["class"], item["line"], item["lcom4"]) for item in found] == [
        ("Storefront", 1, 2)
    ]
    # __init__ and __repr__ touch both attributes but stay out of the graph.
    assert found[0]["clusters"] == [["restock", "in_stock"], ["notify", "welcome"]]


COHESIVE = """
    class Thermostat:
        def __init__(self, target):
            self.target = target
            self.reading = target

        def record(self, value):
            self.reading = value

        def too_cold(self):
            return self.reading < self.target

        def adjust(self, delta):
            self.target += delta
"""


def test_cohesive_class_is_listed_only_with_all(lcom4: ModuleType, tmp_path: Path) -> None:
    assert _scan(lcom4, tmp_path, COHESIVE) == []
    found = _scan(lcom4, tmp_path, COHESIVE, include_cohesive=True)
    assert _clusters(found) == {"Thermostat": (1, [["record", "too_cold", "adjust"]])}


PROTOCOLS = """
    import typing
    from typing import Protocol, TypeVar

    T = TypeVar("T")


    class Clock(Protocol):
        def now(self) -> float: ...

        def sleep(self, seconds: float) -> None:
            \"\"\"Block for ``seconds``.\"\"\"

        def zone(self) -> str:
            raise NotImplementedError


    class Store(typing.Protocol[T]):
        def get(self, key: str) -> T:
            return self.cache[key]

        def put(self, key: str, value: T) -> None:
            self.other[key] = value
"""


def test_protocols_are_skipped(lcom4: ModuleType, tmp_path: Path) -> None:
    assert _scan(lcom4, tmp_path, PROTOCOLS, include_cohesive=True) == []


UNBOUND_AND_STUBS = """
    from abc import ABC, abstractmethod


    class Importer(ABC):
        def __init__(self, source, sink):
            self.source = source
            self.sink = sink

        def read(self):
            return self.source.read() + self.clean("")

        def write(self, rows):
            self.sink.write(rows, self.clean(""))

        @staticmethod
        def clean(text):
            return text.strip()

        @classmethod
        def default(cls):
            return cls(None, None)

        @abstractmethod
        def validate(self, rows):
            ...

        def hook(self):
            pass


    class Lonely:
        def run(self):
            return self.value

        @staticmethod
        def helper():
            return 1

        @classmethod
        def build(cls):
            return cls()
"""


def test_classmethods_staticmethods_and_stubs_stay_out_of_the_graph(
    lcom4: ModuleType, tmp_path: Path
) -> None:
    found = _scan(lcom4, tmp_path, UNBOUND_AND_STUBS, include_cohesive=True)
    # Calling the same staticmethod helper does not link read and write, and
    # Lonely keeps a single graph method, so it is skipped even with --all.
    assert _clusters(found) == {"Importer": (2, [["read"], ["write"]])}


PROPERTIES = """
    class Ledger:
        def __init__(self):
            self._entries = []
            self._owner = ""

        @property
        def balance(self):
            return sum(self._entries)

        @balance.setter
        def balance(self, value):
            self._entries = [value]

        def report(self):
            return f"{self.balance}"

        def rename(self, owner):
            self._owner = owner

        def owner(self):
            return self._owner
"""


def test_property_counts_as_attribute_access_by_name(lcom4: ModuleType, tmp_path: Path) -> None:
    found = _scan(lcom4, tmp_path, PROPERTIES)
    # The getter and setter merge into one ``balance`` node; ``report`` reaches it by name.
    assert _clusters(found) == {"Ledger": (2, [["balance", "report"], ["rename", "owner"]])}


NESTED = """
    class Outer:
        class Inner:
            def left(self):
                return self.a

            def right(self):
                return self.b


    def build():
        class Local:
            def left(self):
                return self.a

            def right(self):
                return self.b

        return Local
"""


def test_nested_classes_get_qualified_names(lcom4: ModuleType, tmp_path: Path) -> None:
    found = _scan(lcom4, tmp_path, NESTED)
    assert [(item["class"], item["line"]) for item in found] == [
        ("Outer.Inner", 2),
        ("build.<locals>.Local", 11),
    ]


def test_receiver_need_not_be_named_self(lcom4: ModuleType, tmp_path: Path) -> None:
    source = """
        class Counter:
            def bump(this):
                this.count += 1

            def reset(this):
                this.count = 0
    """
    assert _clusters(_scan(lcom4, tmp_path, source, include_cohesive=True)) == {
        "Counter": (1, [["bump", "reset"]])
    }


def test_dunder_attributes_are_not_shared_state(lcom4: ModuleType, tmp_path: Path) -> None:
    source = """
        class Labels:
            def title(self):
                return self.__class__.__name__ + self.prefix

            def badge(self):
                return type(self).__name__ + self.__class__.__doc__ + self.suffix
    """
    assert _clusters(_scan(lcom4, tmp_path, source)) == {"Labels": (2, [["title"], ["badge"]])}


# --- CLI contract ------------------------------------------------------------------------

SPLIT = "class Split:\n    def a(self):\n        return self.x\n\n    def b(self):\n        return self.y\n"
WHOLE = "class Whole:\n    def a(self):\n        return self.x\n\n    def b(self):\n        return self.x\n"


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def test_cli_lists_split_classes_and_all_with_flag(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"b.py": SPLIT + "\n\n" + WHOLE, "a.py": WHOLE + "\n\n" + SPLIT})
    default = _run(str(tmp_path))
    assert default.returncode == 0, default.stderr
    assert [(item["file"], item["class"]) for item in json.loads(default.stdout)] == [
        ((tmp_path / "a.py").as_posix(), "Split"),
        ((tmp_path / "b.py").as_posix(), "Split"),
    ]
    every = _run(str(tmp_path), "--all")
    rows = [(item["file"], item["line"], item["class"]) for item in json.loads(every.stdout)]
    assert rows == sorted(rows) and len(rows) == 4
    assert _run("--all", str(tmp_path)).stdout == every.stdout


def test_cli_default_path_recurses_and_skips_tool_dirs(tmp_path: Path) -> None:
    skipped = [".hidden", ".venv", "venv", "node_modules", "__pycache__", "lib/site-packages"]
    _write_tree(tmp_path, {f"{folder}/mod.py": SPLIT for folder in skipped})
    _write_tree(tmp_path, {"pkg/mod.py": SPLIT, "pkg/notes.txt": SPLIT})
    result = _run(cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {"class": "Split", "file": "pkg/mod.py", "line": 1, "lcom4": 2, "clusters": [["a"], ["b"]]}
    ]


def test_cli_unparseable_file_is_reported_and_skipped(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"broken.py": "class Broken(:\n", "good.py": SPLIT})
    result = _run(str(tmp_path))
    assert result.returncode == 0
    assert "broken.py" in result.stderr
    assert [item["file"] for item in json.loads(result.stdout)] == [
        (tmp_path / "good.py").as_posix()
    ]


def test_cli_empty_result_is_an_empty_array(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(WHOLE, encoding="utf-8")
    result = _run(str(tmp_path))
    assert (result.returncode, json.loads(result.stdout)) == (0, [])


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


@pytest.mark.skipif(shutil.which("python3.10") is None, reason="python3.10 is not installed")
def test_cli_runs_on_python_310(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(SPLIT, encoding="utf-8")
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
    assert [item["class"] for item in json.loads(result.stdout)] == ["Split"]
