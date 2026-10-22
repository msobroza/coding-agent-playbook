"""Tests for ``scripts/layer_map.py`` in the core python-architecture skill (prU D2, D25).

The script is a standalone stdlib tool an agent runs inside a consumer repo, so it is
loaded by file path and never imported from the engine. Each test writes the small
project tree it needs into ``tmp_path`` (a bike-rental service, ``rentals``). Most
cases call ``main()`` in-process with the tree as the working directory; a few run
the file as a subprocess to pin the real exit statuses and stderr.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog

SCRIPT = core_skill_root("python-architecture") / "scripts" / "layer_map.py"

ROOT_FILE_NAMES = (
    "main.py",
    "app.py",
    "__main__.py",
    "deps.py",
    "dependencies.py",
    "container.py",
    "bootstrap.py",
    "wiring.py",
)

# A layered service that follows the default rules: routers -> services -> domain,
# the store implements a port the service declares, main.py wires everything.
CLEAN_TREE: dict[str, str] = {
    "rentals/__init__.py": "",
    "rentals/main.py": """
        from rentals.db.bikes import SqlBikeStore
        from rentals.routers import bikes
        """,
    "rentals/routers/__init__.py": "",
    "rentals/routers/bikes.py": """
        from rentals.domain.bike import Bike
        from rentals.services.booking import book_bike
        """,
    "rentals/services/__init__.py": "",
    "rentals/services/booking.py": """
        from rentals.domain.bike import Bike
        """,
    "rentals/domain/__init__.py": "",
    "rentals/domain/bike.py": """
        from dataclasses import dataclass
        """,
    "rentals/db/__init__.py": "",
    "rentals/db/bikes.py": """
        from rentals.domain.bike import Bike
        from rentals.services.booking import BikeStore
        """,
}

# The same service with an endpoint reaching straight into the ORM module (line 3).
ROUTER_IMPORTS_ORM: dict[str, str] = {
    **CLEAN_TREE,
    "rentals/routers/bikes.py": '''
        """Bike endpoints."""

        from rentals.db.bikes import BikeRow
        ''',
}

ORM_VIOLATION = {
    "importer": "rentals.routers.bikes",
    "imported": "rentals.db.bikes",
    "from_layer": "interface",
    "to_layer": "infrastructure",
    "file": "rentals/routers/bikes.py",
    "line": 3,
}

# Two services that import each other at module level.
CYCLE_TREE: dict[str, str] = {
    "rentals/__init__.py": "",
    "rentals/services/__init__.py": "",
    "rentals/services/pricing.py": "from rentals.services import discounts\n",
    "rentals/services/discounts.py": "import rentals.services.pricing\n",
}

# A service packaged as one top-level `api/` package that holds every layer, so the
# package name is the project's name, not the interface layer.
API_PACKAGE_TREE: dict[str, str] = {
    "main.py": "from api.routers import orders\n",
    "api/__init__.py": "",
    "api/config.py": "",
    "api/routers/__init__.py": "",
    "api/routers/orders.py": "from api.services import pay\n",
    "api/services/__init__.py": "",
    "api/services/pay.py": "from api.db import session\n",
    "api/domain/__init__.py": "",
    "api/domain/order.py": "from api.routers import orders\nfrom api.db import session\n",
    "api/db/__init__.py": "",
    "api/db/session.py": "from api import config\n",
}

# Layer-first packages side by side at the top: each one is a layer, and
# db/models.py (ORM tables) stays infrastructure rather than domain.
LAYER_FIRST_TREE: dict[str, str] = {
    "main.py": "from api import routes\n",
    "api/__init__.py": "",
    "api/routes.py": "from services import lending\n",
    "services/__init__.py": "",
    "services/lending.py": "from db.models import LoanRow\n",
    "domain/__init__.py": "",
    "domain/loan.py": "",
    "db/__init__.py": "",
    "db/models.py": "from domain.loan import Loan\n",
}


def elif_chain_module(branches: int, final_import: str) -> str:
    """A function whose if/elif chain has BRANCHES tests and imports in its last branch."""
    lines = ["def dispatch(op):", "    if op == 0:", "        return 0"]
    for index in range(1, branches):
        lines += [f"    elif op == {index}:", f"        return {index}"]
    lines += ["    else:", f"        {final_import}", ""]
    return "\n".join(lines)


def plus_chain_module(terms: int, import_line: str) -> str:
    """A module-level `+` chain of TERMS string literals, then IMPORT_LINE."""
    chain = " + ".join(f"'s{index}'" for index in range(terms))
    return f"LABEL = {chain}\n{import_line}\n"


@dataclass(frozen=True)
class Outcome:
    """Exit status and captured streams of one layer_map run."""

    code: int
    out: str
    err: str

    def report(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.out)
        return loaded


def write_tree(root: Path, files: dict[str, str]) -> None:
    """Write FILES (relative path -> dedented source) under ROOT."""
    for rel, source in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")


def run_script(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the script as an agent would: a fresh interpreter, no stdin."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(scope="module")
def layer_map() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("layer_map_under_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    # No scripts/__pycache__ in the pack source tree (sync skips it anyway).
    writes_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = writes_bytecode
    yield module
    sys.modules.pop(spec.name, None)


@pytest.fixture
def run_map(
    layer_map: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Callable[..., Outcome]:
    """Call ``main(args)`` in-process with ``tmp_path`` as the working directory."""
    monkeypatch.chdir(tmp_path)

    def run(*args: str) -> Outcome:
        try:
            code = int(layer_map.main(list(args)))
        except SystemExit as exit_:
            code = int(exit_.code or 0)
        captured = capsys.readouterr()
        return Outcome(code, captured.out, captured.err)

    return run


# --- violations ---------------------------------------------------------------------


def test_router_importing_orm_module_is_a_named_violation(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map("--json")
    assert outcome.code == 1
    assert outcome.report()["violations"] == [ORM_VIOLATION]


def test_text_report_names_violation_with_file_and_line(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map()
    assert outcome.code == 1
    assert "Rule violations: 1" in outcome.out
    assert (
        "rentals/routers/bikes.py:3  rentals.routers.bikes [interface] imports "
        "rentals.db.bikes [infrastructure]"
    ) in outcome.out
    assert "interface -> infrastructure: 1  (breaks a rule)" in outcome.out


def test_clean_layered_tree_exits_zero(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert report["cycles"] == []
    assert report["layers"] == {
        "rentals.db": "infrastructure",
        "rentals.db.bikes": "infrastructure",
        "rentals.domain": "domain",
        "rentals.domain.bike": "domain",
        "rentals.routers": "interface",
        "rentals.routers.bikes": "interface",
        "rentals.services": "application",
        "rentals.services.booking": "application",
    }
    assert report["unlayered"] == ["rentals", "rentals.main"]
    assert report["composition_roots"] == ["rentals.main"]


def test_clean_text_report_says_nothing_found(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map()
    assert outcome.code == 0
    assert outcome.out.rstrip().endswith("No rule violations or import cycles found.")
    assert "domain         -> nothing" in outcome.out


def test_flows_count_distinct_module_pairs_in_layer_order(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    returns = """
        from rentals.services.booking import book_bike
        from rentals.services.booking import cancel_booking
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/returns.py": returns})
    assert run_map("--json").report()["flows"] == [
        ["interface", "application", 2],
        ["interface", "domain", 1],
        ["application", "domain", 1],
        ["infrastructure", "application", 1],
        ["infrastructure", "domain", 1],
    ]


def test_function_local_import_still_breaks_a_rule(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    lazy = """
        def list_bikes():
            from rentals.db.bikes import BikeRow
            return BikeRow
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": lazy})
    outcome = run_map("--json")
    assert outcome.code == 1
    assert [v["line"] for v in outcome.report()["violations"]] == [2]


# --- type-only imports --------------------------------------------------------------


def test_type_checking_import_is_type_only_not_a_violation(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        import typing
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from rentals.db.bikes import BikeRow

        if typing.TYPE_CHECKING:
            import rentals.db.bikes
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": router})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert report["type_only"] == [
        {**ORM_VIOLATION, "line": 5},
        {**ORM_VIOLATION, "line": 8},
    ]


def test_else_branch_of_type_checking_runs_and_is_checked(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from rentals.domain.bike import Bike
        else:
            from rentals.db.bikes import BikeRow
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": router})
    outcome = run_map("--json")
    assert outcome.code == 1
    assert outcome.report()["violations"] == [{**ORM_VIOLATION, "line": 6}]
    assert outcome.report()["type_only"] == []


# --- composition roots --------------------------------------------------------------


@pytest.mark.parametrize("filename", ROOT_FILE_NAMES)
def test_composition_root_files_may_import_any_layer(
    tmp_path: Path, run_map: Callable[..., Outcome], filename: str
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path, {**CLEAN_TREE, f"rentals/routers/{filename}": wiring})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert f"rentals.routers.{filename.removesuffix('.py')}" in report["composition_roots"]
    # A root keeps its directory's layer for the modules that import it.
    assert report["layers"][f"rentals.routers.{filename.removesuffix('.py')}"] == "interface"


@pytest.mark.parametrize(
    "flag_value",
    ["rentals.routers.setup", "routers.setup", "setup", "rentals/routers/setup.py"],
)
def test_root_module_flag_adds_a_composition_root(
    tmp_path: Path, run_map: Callable[..., Outcome], flag_value: str
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/setup.py": wiring})
    assert run_map("--json").code == 1
    outcome = run_map(".", "--root-module", flag_value, "--json")
    assert outcome.code == 0
    assert outcome.report()["composition_roots"] == ["rentals.main", "rentals.routers.setup"]


def test_root_imports_are_left_out_of_flows(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/deps.py": wiring})
    flows = run_map("--json").report()["flows"]
    assert ["interface", "infrastructure", 1] not in flows


@pytest.mark.parametrize(
    "flag_value",
    [
        "src/rentals/routers/setup.py",
        "./src/rentals/routers/setup.py",
        "rentals/routers/setup.py",
        "ABSOLUTE",
    ],
)
def test_root_module_accepts_the_file_path_the_report_prints(
    tmp_path: Path, run_map: Callable[..., Outcome], flag_value: str
) -> None:
    # Regression: in a src layout the printed `file` is src/..., which used to match
    # nothing and leave the wiring module's imports reported as violations.
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path / "src", {**CLEAN_TREE, "rentals/routers/setup.py": wiring})
    printed = run_map("--json").report()["violations"][0]["file"]
    assert printed == "src/rentals/routers/setup.py"
    value = str(tmp_path / printed) if flag_value == "ABSOLUTE" else flag_value
    outcome = run_map(".", "--root-module", value, "--json")
    assert outcome.code == 0, outcome.err
    assert outcome.report()["composition_roots"] == ["rentals.main", "rentals.routers.setup"]


def test_root_module_path_is_also_read_relative_to_root(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    wiring = "from rentals.db.bikes import SqlBikeStore\n"
    write_tree(tmp_path / "proj" / "src", {**CLEAN_TREE, "rentals/routers/setup.py": wiring})
    for value in ("src/rentals/routers/setup.py", "proj/src/rentals/routers/setup.py"):
        outcome = run_map("proj", "--root-module", value, "--json")
        assert outcome.code == 0, (value, outcome.err)
        assert "rentals.routers.setup" in outcome.report()["composition_roots"]


@pytest.mark.parametrize(
    "flag_value", ["nowhere", "rentals.routers.nowhere", "src/rentals/routers/nowhere.py"]
)
def test_root_module_matching_no_scanned_module_is_a_usage_error(
    tmp_path: Path, run_map: Callable[..., Outcome], flag_value: str
) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map(".", "--root-module", flag_value, "--json")
    assert outcome.code == 2
    assert outcome.out == ""
    assert flag_value in outcome.err
    assert "matches no scanned module" in outcome.err


# --- imports of composition roots ---------------------------------------------------


def test_non_interface_code_importing_a_composition_root_is_a_violation(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: a top-level deps.py has no layer, so a use case reaching into it for
    # a session (a service locator) was never checked.
    booking = """
        def book_bike():
            from rentals.deps import get_session
            return get_session()
        """
    files = {
        **CLEAN_TREE,
        "rentals/deps.py": "from rentals.db.bikes import SqlBikeStore\n",
        "rentals/services/booking.py": booking,
        "rentals/domain/bike.py": "import rentals.main\n",
        "rentals/db/bikes.py": "from rentals import deps\n",
    }
    write_tree(tmp_path, files)
    outcome = run_map("--json")
    assert outcome.code == 1
    found = {(v["importer"], v["imported"], v["to_layer"]) for v in outcome.report()["violations"]}
    assert found == {
        ("rentals.services.booking", "rentals.deps", None),
        ("rentals.domain.bike", "rentals.main", None),
        ("rentals.db.bikes", "rentals.deps", None),
    }


def test_interface_code_may_import_the_provider_module(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = "from rentals.deps import Booking\nfrom rentals.services.booking import book_bike\n"
    files = {
        **CLEAN_TREE,
        "rentals/deps.py": "from rentals.db.bikes import SqlBikeStore\n",
        "rentals/routers/bikes.py": router,
    }
    write_tree(tmp_path, files)
    outcome = run_map("--json")
    assert outcome.code == 0
    assert outcome.report()["violations"] == []


def test_root_import_text_names_the_composition_root_and_type_only_is_not_failing(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    booking = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from rentals import deps\n"
    files = {
        **CLEAN_TREE,
        "rentals/deps.py": "",
        "rentals/services/booking.py": booking,
        "rentals/db/bikes.py": "from rentals.deps import get_session\n",
    }
    write_tree(tmp_path, files)
    outcome = run_map()
    assert outcome.code == 1
    assert (
        "rentals/db/bikes.py:1  rentals.db.bikes [infrastructure] imports "
        "rentals.deps [composition root]"
    ) in outcome.out
    report = run_map("--json").report()
    assert [v["importer"] for v in report["type_only"]] == ["rentals.services.booking"]


# --- container packages -------------------------------------------------------------


def test_top_level_package_named_like_a_layer_does_not_swallow_its_layers(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: every module under a top-level api/ package used to be interface,
    # so domain -> interface and domain/application -> db imports passed with exit 0.
    write_tree(tmp_path, API_PACKAGE_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["container_packages"] == ["api"]
    assert report["layers"] == {
        "api.db": "infrastructure",
        "api.db.session": "infrastructure",
        "api.domain": "domain",
        "api.domain.order": "domain",
        "api.routers": "interface",
        "api.routers.orders": "interface",
        "api.services": "application",
        "api.services.pay": "application",
    }
    assert report["unlayered"] == ["api", "api.config", "main"]
    found = {(v["importer"], v["imported"]) for v in report["violations"]}
    assert found == {
        ("api.services.pay", "api.db.session"),
        ("api.domain.order", "api.routers.orders"),
        ("api.domain.order", "api.db.session"),
    }


def test_container_packages_are_listed_in_the_text_report(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, API_PACKAGE_TREE)
    outcome = run_map()
    assert "container packages (named like a layer, holding other layers): api" in outcome.out
    assert "Rule violations: 3" in outcome.out


def test_enclosing_package_above_root_does_not_swallow_its_layers(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: with services/__init__.py present, ROOT=services/billing named every
    # module services.billing.*, so all of them were application code.
    files = {
        "services/__init__.py": "",
        "services/billing/__init__.py": "",
        "services/billing/domain/__init__.py": "",
        "services/billing/domain/invoice.py": "from services.billing.db import store\n",
        "services/billing/db/__init__.py": "",
        "services/billing/db/store.py": "",
    }
    write_tree(tmp_path, files)
    outcome = run_map("services/billing", "--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["container_packages"] == ["services"]
    assert report["layers"]["services.billing.domain.invoice"] == "domain"
    assert [(v["from_layer"], v["to_layer"]) for v in report["violations"]] == [
        ("domain", "infrastructure")
    ]


def test_layer_first_top_level_packages_stay_layers(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, LAYER_FIRST_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["container_packages"] == []
    assert report["layers"]["db.models"] == "infrastructure"
    assert [(v["importer"], v["imported"]) for v in report["violations"]] == [
        ("services.lending", "db.models")
    ]


def test_a_multi_part_layer_name_overrules_a_container(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # The documented escape hatch: api/models/ holding request schemas stays interface.
    write_tree(tmp_path, {**API_PACKAGE_TREE, "api/models/__init__.py": "", "api/models/io.py": ""})
    assert run_map("--json").report()["layers"]["api.models.io"] == "domain"
    names = "interface=api,routers,routes,endpoints,views,cli,api/models"
    report = run_map(".", "--layer", names, "--json").report()
    assert report["layers"]["api.models.io"] == "interface"
    assert report["layers"]["api.db.session"] == "infrastructure"


def test_container_packages_need_other_layers_inside_and_no_layered_sibling(
    layer_map: ModuleType,
) -> None:
    rules = layer_map.build_rules([], [], [])
    containers = layer_map.container_packages
    packaged = ["api.routers.orders", "api.db.session", "api.services.pay", "setup"]
    assert containers(packaged, rules) == {("api",)}
    # A layer-first sibling makes the top level the layer axis.
    assert containers(["api.db.session", "services.lending"], rules) == frozenset()
    # Nothing inside names another layer: api/ is just the interface layer.
    assert containers(["api.routes", "api.schemas", "core.rules"], rules) == frozenset()
    # One other layer inside is not enough either: api/models/ may hold request schemas.
    assert containers(["api.routes", "api.models.io", "core.rules"], rules) == frozenset()
    # Nested: rentals/api/ alone beside unlayered packages holds two other layers.
    nested = ["rentals.api.db.rows", "rentals.api.services.loans", "rentals.core"]
    assert containers(nested, rules) == {("rentals", "api")}
    # One other layer inside is not enough: db/models.py (ORM tables) stays in db.
    orm = ["shop.db.models", "shop.db.repositories", "shop.core.rules"]
    assert containers(orm, rules) == frozenset()
    assert layer_map.classify("shop.db.models", rules, containers(orm, rules)) == "infrastructure"


# --- import resolution --------------------------------------------------------------


def test_relative_imports_resolve_to_scanned_modules(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        from ..services import booking
        from ..db.bikes import BikeRow
        from .. import domain
        from .... import beyond_the_top
        """
    package_init = "from .bikes import router\n"
    write_tree(
        tmp_path,
        {
            **CLEAN_TREE,
            "rentals/routers/bikes.py": router,
            "rentals/routers/__init__.py": package_init,
        },
    )
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["violations"] == [{**ORM_VIOLATION, "line": 2}]
    assert ["interface", "application", 1] in report["flows"]
    assert ["interface", "domain", 1] in report["flows"]


def test_src_layout_scans_src_only(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    write_tree(tmp_path / "src", ROUTER_IMPORTS_ORM)
    outside = {"tools/routers/seed.py": "from db import fixtures\n", "db/fixtures.py": ""}
    write_tree(tmp_path, outside)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["scanned"] == "src"
    assert report["violations"] == [{**ORM_VIOLATION, "file": "src/rentals/routers/bikes.py"}]
    assert all(module.startswith("rentals") for module in report["layers"])


def test_src_without_python_files_falls_back_to_root(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: a maturin src/lib.rs (or a JS src/) used to be scanned instead of
    # the Python package beside it, giving 0 modules and a clean exit 0.
    write_tree(tmp_path, {**ROUTER_IMPORTS_ORM, "src/lib.rs": "fn main() {}\n"})
    write_tree(tmp_path, {"src/tests/test_lib.py": "import rentals\n"})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["scanned"] == "."
    assert report["violations"] == [ORM_VIOLATION]


@pytest.mark.parametrize(
    "files",
    [{}, {"src/lib.rs": "fn main() {}\n"}, {"tests/test_bikes.py": "import rentals\n"}],
    ids=["empty", "rust-src-only", "tests-only"],
)
def test_nothing_to_scan_is_a_usage_error(
    tmp_path: Path, run_map: Callable[..., Outcome], files: dict[str, str]
) -> None:
    write_tree(tmp_path, files)
    outcome = run_map("--json")
    assert outcome.code == 2
    assert outcome.out == ""
    assert "found no Python module to scan" in outcome.err


def test_root_inside_a_package_keeps_the_package_prefix(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map("rentals", "--json")
    assert outcome.code == 1
    assert outcome.report()["violations"][0]["importer"] == "rentals.routers.bikes"


def test_third_party_and_unknown_imports_are_ignored(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    router = """
        import os
        import sqlalchemy.orm
        from fastapi import APIRouter
        import models
        from db import Session
        from rentals.payments.gateway import charge
        """
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/routers/bikes.py": router})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    assert report["violations"] == []
    assert [flow for flow in report["flows"] if flow[0] == "interface"] == []


def test_test_code_and_hidden_or_vendored_dirs_are_not_scanned(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    reach_in = "from rentals.db.bikes import SqlBikeStore\n"
    extra = {
        "tests/routers/test_bikes.py": reach_in,
        "rentals/routers/conftest.py": reach_in,
        "rentals/routers/test_payloads.py": reach_in,
        "rentals/routers/payloads_test.py": reach_in,
        ".venv/lib/routers/client.py": "from db import pool\n",
        "node_modules/views/page.py": "from db import pool\n",
    }
    write_tree(tmp_path, {**CLEAN_TREE, **extra})
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 0
    scanned = set(report["layers"]) | set(report["unlayered"])
    assert all(module.startswith("rentals") for module in scanned)
    assert not any("test" in module for module in scanned)


# --- cycles -------------------------------------------------------------------------


def test_import_cycle_between_two_modules_fails_and_is_listed(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, CYCLE_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["violations"] == []
    assert report["cycles"] == [["rentals.services.discounts", "rentals.services.pricing"]]


def test_text_report_lists_the_cycle(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    write_tree(tmp_path, CYCLE_TREE)
    outcome = run_map()
    assert outcome.code == 1
    assert "  rentals.services.discounts, rentals.services.pricing" in outcome.out
    assert "Found 0 rule violations and 1 import cycle." in outcome.out


@pytest.mark.parametrize(
    "discounts",
    [
        "import sys\nif sys.version_info >= (3, 10):\n    import rentals.services.pricing\n",
        "try:\n    from rentals.services.pricing import *\nexcept ImportError:\n    pass\n",
        "class Rules:\n    from rentals.services import pricing\n",
    ],
    ids=["plain-if", "star-import-in-try", "class-body"],
)
def test_module_level_imports_inside_blocks_still_form_cycles(
    tmp_path: Path, run_map: Callable[..., Outcome], discounts: str
) -> None:
    write_tree(tmp_path, {**CYCLE_TREE, "rentals/services/discounts.py": discounts})
    outcome = run_map("--json")
    assert outcome.code == 1
    assert outcome.report()["cycles"] == [
        ["rentals.services.discounts", "rentals.services.pricing"]
    ]


@pytest.mark.parametrize(
    "discounts",
    [
        "def load():\n    import rentals.services.pricing\n",
        "async def load():\n    import rentals.services.pricing\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import rentals.services.pricing\n",
    ],
    ids=["deferred", "deferred-async", "type-only"],
)
def test_deferred_and_type_only_imports_do_not_form_cycles(
    tmp_path: Path, run_map: Callable[..., Outcome], discounts: str
) -> None:
    write_tree(tmp_path, {**CYCLE_TREE, "rentals/services/discounts.py": discounts})
    outcome = run_map("--json")
    assert outcome.code == 0
    assert outcome.report()["cycles"] == []


def test_find_cycles_groups_each_strongly_connected_set(layer_map: ModuleType) -> None:
    graph = {
        "a": {"b"},
        "b": {"c"},
        "c": {"a", "x"},
        "x": {"y"},
        "y": {"x"},
        "z": {"a"},
    }
    assert layer_map.find_cycles(graph) == (("a", "b", "c"), ("x", "y"))


# --- overrides ----------------------------------------------------------------------


def test_layer_and_allow_overrides_change_classification_and_rules(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(
        tmp_path,
        {
            "rentals/http/handlers.py": "from rentals.store.tables import BikeTable\n",
            "rentals/store/tables.py": "",
        },
    )
    assert run_map("--json").report()["layers"] == {}
    layers = ("--layer", "interface=http", "--layer", "infrastructure=store")
    remapped = run_map(".", *layers, "--json")
    assert remapped.code == 1
    assert remapped.report()["layers"] == {
        "rentals.http.handlers": "interface",
        "rentals.store.tables": "infrastructure",
    }
    allowed = run_map(".", *layers, "--allow", "interface=infrastructure", "--json")
    assert allowed.code == 0
    assert allowed.report()["rules"]["interface"] == ["infrastructure"]


def test_layer_override_replaces_the_default_names(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map(".", "--layer", "interface=http", "--json")
    assert outcome.code == 0
    assert "rentals.routers.bikes" in outcome.report()["unlayered"]


def test_new_layer_with_a_path_pattern_may_import_only_itself(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/jobs/nightly.py": "import rentals.domain.bike\n"})
    outcome = run_map(".", "--layer", "worker=rentals/jobs", "--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["layers"]["rentals.jobs.nightly"] == "worker"
    assert report["rules"]["worker"] == []
    assert report["violations"][0]["to_layer"] == "domain"


def test_classify_prefers_the_outermost_matching_part(layer_map: ModuleType) -> None:
    rules = layer_map.build_rules([], [], [])
    assert layer_map.classify("rentals.api.models.payloads", rules) == "interface"
    assert layer_map.classify("rentals.domain.services.pricing", rules) == "domain"
    assert layer_map.classify("rentals.db", rules) == "infrastructure"
    assert layer_map.classify("rentals.billing", rules) is None


# --- output and usage ---------------------------------------------------------------


def test_json_output_schema(tmp_path: Path, run_map: Callable[..., Outcome]) -> None:
    admin = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import rentals.db.bikes\n"
    write_tree(tmp_path, {**ROUTER_IMPORTS_ORM, **CYCLE_TREE, "rentals/routers/admin.py": admin})
    report = run_map("--json").report()
    assert {"layers", "flows", "violations", "cycles", "type_only"} <= set(report)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in report["layers"].items())
    assert report["flows"]
    assert all([type(item) for item in flow] == [str, str, int] for flow in report["flows"])
    records = report["violations"] + report["type_only"]
    assert report["violations"]
    assert report["type_only"]
    for record in records:
        assert set(record) == {"importer", "imported", "from_layer", "to_layer", "file", "line"}
        assert isinstance(record["line"], int)
    assert report["cycles"]
    assert all(isinstance(m, str) for group in report["cycles"] for m in group)


@pytest.mark.parametrize(
    "args",
    [
        ["no-such-dir"],
        ["interface=api"],
        [".", "--layer", "interface"],
        [".", "--layer", "=api"],
        [".", "--allow", "interface=warehouse"],
        [".", "--allow", "warehouse=domain"],
        [".", "--root-module", "/"],
        [".", "--root-module", "nowhere"],
        [".", "--no-such-flag"],
    ],
)
def test_usage_errors_exit_2(
    tmp_path: Path, run_map: Callable[..., Outcome], args: list[str]
) -> None:
    write_tree(tmp_path, CLEAN_TREE)
    outcome = run_map(*args)
    assert outcome.code == 2
    assert outcome.out == ""
    assert "usage: layer_map.py" in outcome.err


def test_unparseable_file_is_reported_on_stderr_and_skipped(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/services/broken.py": "def oops(:\n"})
    outcome = run_map("--json")
    assert outcome.code == 0
    assert "rentals/services/broken.py" in outcome.err
    assert outcome.report()["violations"] == []


# --- the real command line ----------------------------------------------------------


def test_cli_exit_statuses(tmp_path: Path) -> None:
    clean, dirty = tmp_path / "clean", tmp_path / "dirty"
    write_tree(clean, CLEAN_TREE)
    write_tree(dirty, ROUTER_IMPORTS_ORM)
    assert run_script(clean).returncode == 0
    result = run_script(dirty, ".", "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["violations"] == [ORM_VIOLATION]
    usage = run_script(clean, ".", "--allow", "nowhere=domain")
    assert usage.returncode == 2
    assert "nowhere" in usage.stderr


def test_cli_reports_unparseable_files_on_stderr(tmp_path: Path) -> None:
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/db/legacy.py": "print 'old'\n"})
    result = run_script(tmp_path, ".", "--json")
    assert result.returncode == 0
    assert "skipped rentals/db/legacy.py" in result.stderr
    json.loads(result.stdout)


def test_cli_survives_a_long_elif_chain_and_a_deep_expression(tmp_path: Path) -> None:
    # Regression: the recursive import visitor overflowed the stack on ~330 elif
    # branches or a ~900-term `+` chain (both valid Python), killing the whole scan
    # with a traceback, empty stdout and exit 1. A fresh interpreter, as an agent runs it.
    files = {
        **CLEAN_TREE,
        "rentals/routers/dispatch.py": elif_chain_module(
            1000, "from rentals.db.bikes import BikeRow"
        ),
        "rentals/routers/labels.py": plus_chain_module(900, "import rentals.db.bikes"),
    }
    write_tree(tmp_path, files)
    result = run_script(tmp_path, ".", "--json")
    assert result.returncode == 1, result.stderr
    assert "RecursionError" not in result.stderr
    found = {(v["importer"], v["line"]) for v in json.loads(result.stdout)["violations"]}
    assert found == {("rentals.routers.dispatch", 2003), ("rentals.routers.labels", 2)}
