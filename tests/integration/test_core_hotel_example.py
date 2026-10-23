"""Regression checks for web-application's hotel example app (prU D48).

The example is the service agents copy, so its code must keep the persistence
and boundary decisions it demonstrates: the double-booking race is closed by a
partial unique index, the driver error that index raises becomes a domain error
inside the repository (a leak would answer 500 instead of 409), nothing builds
an engine or reads the environment at import time, and FastAPI stays at the
edge. The engine's test environment has neither FastAPI nor SQLAlchemy (the
example runs its own tests in its own CI job), so the modules are read with
``ast`` rather than imported.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from typing import TYPE_CHECKING, Final

import pytest

from tests._catalog import REPO_ROOT, core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

EXAMPLE: Final = core_skill_root("web-application") / "examples" / "fastapi-hotel-api"
#: Every file the example ships (mapping-web-application.md, the example table).
EXPECTED_FILES: Final = frozenset(
    {
        "README.md",
        "pyproject.toml",
        "app/settings.py",
        "app/main.py",
        "app/asgi.py",
        "app/deps.py",
        "app/domain/model.py",
        "app/domain/errors.py",
        "app/operations/ports.py",
        "app/operations/room.py",
        "app/operations/customer.py",
        "app/operations/booking.py",
        "app/db/models.py",
        "app/db/repositories.py",
        "app/routers/schemas.py",
        "app/routers/rooms.py",
        "app/routers/customers.py",
        "app/routers/bookings.py",
        "tests/conftest.py",
        "tests/fakes.py",
        "tests/test_operations.py",
        "tests/test_repositories.py",
        "tests/test_api.py",
    }
)
#: Calls that build an engine or read the environment: never at import time.
_IMPORT_TIME_CALLS: Final = frozenset({"create_engine", "create_async_engine", "Settings"})
#: python-architecture's import-direction checker; it lands with that skill's lane.
LAYER_MAP: Final = core_skill_root("python-architecture") / "scripts" / "layer_map.py"
#: The modules agents copy names from: each public name documents itself (python-docstrings).
_DOCUMENTED_MODULES: Final = ("app/", "tests/conftest.py", "tests/fakes.py")
#: The layers below the routes, which must not know FastAPI.
_INNER_LAYERS: Final = ("app/domain/", "app/operations/", "app/db/")


def _shipped_files(root: Path) -> set[str]:
    """Every file under ``root``, relative and POSIX, tool caches and envs aside."""
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not any(
            part.startswith(".") or part == "__pycache__" for part in path.relative_to(root).parts
        )
    }


@pytest.fixture(scope="module")
def modules() -> dict[str, ast.Module]:
    """Each Python module of the example, parsed (a syntax error fails here)."""
    return {
        rel: ast.parse((EXAMPLE / rel).read_text(encoding="utf-8"), filename=rel)
        for rel in sorted(_shipped_files(EXAMPLE))
        if rel.endswith(".py")
    }


def _find_class(tree: ast.Module, name: str) -> ast.ClassDef:
    found = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name]
    assert len(found) == 1, f"expected one class {name!r}, found {len(found)}"
    return found[0]


def _find_async_method(tree: ast.Module, class_name: str, name: str) -> ast.AsyncFunctionDef:
    body = _find_class(tree, class_name).body
    found = [node for node in body if isinstance(node, ast.AsyncFunctionDef) and node.name == name]
    assert len(found) == 1, f"expected one async method {class_name}.{name}, found {len(found)}"
    return found[0]


def _called_name(node: ast.AST | None) -> str:
    """``Index(...)`` -> ``Index``; ``self.x.commit()`` -> ``commit``; anything else -> ``""``."""
    if not isinstance(node, ast.Call):
        return ""
    if isinstance(node.func, ast.Name):
        return node.func.id
    return node.func.attr if isinstance(node.func, ast.Attribute) else ""


def _calls_to(scope: ast.AST, name: str) -> list[ast.Call]:
    """Every ``<name>(...)`` or ``<obj>.<name>(...)`` call inside ``scope``."""
    calls = (node for node in ast.walk(scope) if isinstance(node, ast.Call))
    return [call for call in calls if _called_name(call) == name]


def _raises(scope: ast.AST, error: str) -> list[ast.Raise]:
    """Every ``raise <error>(...)`` inside ``scope``."""
    found = (node for node in ast.walk(scope) if isinstance(node, ast.Raise))
    return [node for node in found if _called_name(node.exc) == error]


def _import_time_nodes(tree: ast.Module) -> list[ast.AST]:
    """Every node that runs on import: module and class bodies, never function bodies."""
    pending: list[ast.AST] = list(tree.body)
    found: list[ast.AST] = []
    while pending:
        node = pending.pop()
        found.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue  # its body runs only when called
        pending.extend(ast.iter_child_nodes(node))
    return found


def _imported_modules(tree: ast.Module) -> set[str]:
    """Every module ``tree`` imports, by its dotted name."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_the_example_ships_exactly_its_mapped_files() -> None:
    assert _shipped_files(EXAMPLE) == EXPECTED_FILES


def test_the_example_pyproject_is_a_virtual_project_with_its_own_tool_tables() -> None:
    with (EXAMPLE / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    assert "build-system" not in config, "uv must treat the example as a virtual project"
    assert config["project"]["requires-python"] == ">=3.10"
    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert config["tool"]["mypy"]["strict"] is True
    assert config["tool"]["ruff"]["target-version"] == "py310"


def test_room_night_table_declares_the_partial_unique_booking_index(
    modules: dict[str, ast.Module],
) -> None:
    room_night = _find_class(modules["app/db/models.py"], "RoomNightRow")
    table_args = [
        stmt.value
        for stmt in room_night.body
        if isinstance(stmt, (ast.Assign, ast.AnnAssign))
        and stmt.value is not None
        and "__table_args__" in ast.unparse(stmt)
    ]
    indexes = [call for arg in table_args for call in _calls_to(arg, "Index")]
    assert len(indexes) == 1, "RoomNightRow.__table_args__ must declare the booking index"
    assert ast.unparse(indexes[0].args[0]) == "'one_active_booking_per_room_night'"
    keywords = {kw.arg: ast.unparse(kw.value) for kw in indexes[0].keywords}
    assert keywords["unique"] == "True"
    where = "text('cancelled_on IS NULL')"
    assert (keywords["sqlite_where"], keywords["postgresql_where"]) == (where, where)


@pytest.mark.parametrize(
    ("repository", "domain_error"),
    [
        ("SqlBookingRepository", "RoomUnavailableError"),
        ("SqlCustomerRepository", "DuplicateEmailError"),
    ],
    ids=["booking-index", "unique-email"],
)
def test_sql_repository_translates_the_constraint_violation(
    modules: dict[str, ast.Module], repository: str, domain_error: str
) -> None:
    # Regression: an IntegrityError escaping add() answers 500 instead of 409.
    add = _find_async_method(modules["app/db/repositories.py"], repository, "add")
    guarded = [
        (node, handler)
        for node in ast.walk(add)
        if isinstance(node, ast.Try)
        for handler in node.handlers
        if handler.type is not None and ast.unparse(handler.type) == "IntegrityError"
    ]
    assert len(guarded) == 1, f"{repository}.add must catch IntegrityError around the flush"
    body, handler = guarded[0]
    assert any(_calls_to(stmt, "flush") for stmt in body.body), "the flush sits in the try"
    raised = _raises(handler, domain_error)
    assert len(raised) == 1 and raised[0].cause is not None, "raise the domain error `from` it"


def test_fake_booking_repository_refuses_an_overlap_too(modules: dict[str, ast.Module]) -> None:
    # A fake raises the same domain errors as its SQL twin.
    add = _find_async_method(modules["tests/fakes.py"], "InMemoryBookingRepository", "add")
    assert _raises(add, "RoomUnavailableError")


def test_nothing_builds_an_engine_or_reads_settings_at_import_time(
    modules: dict[str, ast.Module],
) -> None:
    found = {
        (rel, _called_name(node))
        for rel, tree in modules.items()
        if rel.startswith("app/")
        for node in _import_time_nodes(tree)
        if _called_name(node) in _IMPORT_TIME_CALLS
    }
    assert found == {("app/asgi.py", "Settings")}
    assert len(_calls_to(modules["app/asgi.py"], "Settings")) == 1


def test_the_inner_layers_import_nothing_from_fastapi(modules: dict[str, ast.Module]) -> None:
    leaks = sorted(
        (rel, name)
        for rel, tree in modules.items()
        if rel.startswith(_INNER_LAYERS)
        for name in _imported_modules(tree)
        if name == "fastapi" or name.startswith(("fastapi.", "starlette"))
    )
    assert leaks == []


def test_the_unit_of_work_holds_the_only_commit_under_db(modules: dict[str, ast.Module]) -> None:
    db_modules = {rel: tree for rel, tree in modules.items() if rel.startswith("app/db/")}
    commits = [call for tree in db_modules.values() for call in _calls_to(tree, "commit")]
    commit = _find_async_method(modules["app/db/repositories.py"], "SqlHotelUnitOfWork", "commit")
    assert commits == _calls_to(commit, "commit")
    assert len(commits) == 1


def test_endpoint_tests_never_use_the_fakes(modules: dict[str, ast.Module]) -> None:
    # D27(3): endpoint tests run on the real engine in a rolled-back transaction.
    imported = _imported_modules(modules["tests/test_api.py"])
    assert not {name for name in imported if name.startswith("tests.fakes")}
    assert "fakes" not in {
        alias.name
        for node in ast.walk(modules["tests/test_api.py"])
        if isinstance(node, ast.ImportFrom) and node.module == "tests"
        for alias in node.names
    }


def _public_definitions(
    tree: ast.Module,
) -> list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]:
    """The module's top-level classes and functions whose names do not start with ``_``."""
    kinds = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return [n for n in tree.body if isinstance(n, kinds) and not n.name.startswith("_")]


def test_every_public_name_has_an_intent_line_and_a_usage_example(
    modules: dict[str, ast.Module],
) -> None:
    # python-docstrings: the example is the code agents copy, so it follows the rule it teaches.
    undocumented = sorted(
        f"{rel}:{node.name}"
        for rel, tree in modules.items()
        if rel.startswith(_DOCUMENTED_MODULES)
        for node in _public_definitions(tree)
        if "Example" not in (ast.get_docstring(node) or "")
    )
    assert undocumented == []


def test_every_module_docstring_is_one_line(modules: dict[str, ast.Module]) -> None:
    # Mapping drop row: each adapted module gets a one-line docstring of its own.
    long_or_missing = sorted(
        rel
        for rel, tree in modules.items()
        if len((ast.get_docstring(tree) or "\n").splitlines()) != 1
    )
    assert long_or_missing == []


def test_the_layer_map_finds_no_violation_and_no_cycle() -> None:
    # The README claims this result; the script ships with python-architecture, whose
    # lane depends on this example, so the check runs as soon as the script exists.
    if not LAYER_MAP.is_file():
        pytest.skip("python-architecture's scripts/layer_map.py has not landed yet")
    result = subprocess.run(
        [sys.executable, "-I", str(LAYER_MAP), str(EXAMPLE)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ci_installs_uv_with_the_setup_action_pinned_by_sha() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = workflow.partition("\n  core-examples:\n")[2].partition("\n  wheel-smoke:\n")[0]
    assert re.search(r"uses: astral-sh/setup-uv@[0-9a-f]{40}\b", job), job
    assert "pip install uv" not in job
