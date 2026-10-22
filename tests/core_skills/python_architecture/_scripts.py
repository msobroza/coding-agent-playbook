"""Shared helpers for the ``layer_map.py`` tests: loading, project trees, runs.

The script is a standalone stdlib tool an agent runs inside a consumer repo, so it is
loaded by file path and never imported from the engine. Each test writes the small
project tree it needs into ``tmp_path`` (a bike-rental service, ``rentals``). Most
cases call ``main()`` in-process with the tree as the working directory (the
``run_map`` fixture); a few run the file as a subprocess to pin the real exit
statuses and stderr.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from tests._catalog import core_skill_root
from tests.core_skill_pins.python_architecture import PINS

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

SCRIPTS_DIR: Final = core_skill_root("python-architecture") / "scripts"
LAYER_MAP: Final = SCRIPTS_DIR / "layer_map.py"

#: The composition-root file names, read from the arch-composition-root rule's pinned
#: globs; test_script_contract checks that the script's ROOT_FILE_NAMES is the same set.
ROOT_FILE_NAMES: Final = tuple(
    glob.removeprefix("**/") for glob in PINS.rules["arch-composition-root"].globs
)

# A layered service that follows the default rules: routers -> services -> domain,
# the store implements a port the service declares, main.py wires everything.
CLEAN_TREE: Final[dict[str, str]] = {
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
ROUTER_IMPORTS_ORM: Final[dict[str, str]] = {
    **CLEAN_TREE,
    "rentals/routers/bikes.py": '''
        """Bike endpoints."""

        from rentals.db.bikes import BikeRow
        ''',
}

ORM_VIOLATION: Final = {
    "importer": "rentals.routers.bikes",
    "imported": "rentals.db.bikes",
    "from_layer": "interface",
    "to_layer": "infrastructure",
    "file": "rentals/routers/bikes.py",
    "line": 3,
}

# Two services that import each other at module level.
CYCLE_TREE: Final[dict[str, str]] = {
    "rentals/__init__.py": "",
    "rentals/services/__init__.py": "",
    "rentals/services/pricing.py": "from rentals.services import discounts\n",
    "rentals/services/discounts.py": "import rentals.services.pricing\n",
}

# A service packaged as one top-level `api/` package that holds every layer, so the
# package name is the project's name, not the interface layer.
API_PACKAGE_TREE: Final[dict[str, str]] = {
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
LAYER_FIRST_TREE: Final[dict[str, str]] = {
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


@dataclass(frozen=True)
class Outcome:
    """Exit status and captured streams of one layer_map run."""

    code: int
    out: str
    err: str

    def report(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.out)
        return loaded


def load_script(path: Path, module_name: str) -> ModuleType:
    """The script at ``path`` loaded as a module (registered first: dataclasses look it up).

    Loading runs the script's own ``sys.path`` setup, so its helper modules import
    the same way they do when the script runs.
    """
    spec = importlib.util.spec_from_file_location(module_name, path)
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


def write_tree(root: Path, files: dict[str, str]) -> None:
    """Write FILES (relative path -> dedented source) under ROOT."""
    for rel, source in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")


def run_script(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the script as an agent would: a fresh interpreter, no stdin."""
    return subprocess.run(
        [sys.executable, str(LAYER_MAP), *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


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
