"""The shape every script of the design-patterns skill keeps (prU D2, D25).

The scripts run in consumer repos on Python 3.10 or later, outside this package,
so each one is an executable ``python3`` program that parses as Python 3.10,
imports only the standard library, names itself in its usage docstring and passes
``mypy --strict`` for Python 3.10 under an empty config (never the repo's).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Final

import pytest

from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

SCRIPTS_DIR: Final = core_skill_root("design-patterns") / "scripts"
#: The two python_design scripts the skill took over (D2); a new script joins by existing.
EXPECTED_SCRIPTS: Final = frozenset({"detect_smells.py", "lcom4_clusters.py"})
SCRIPTS: Final = sorted(EXPECTED_SCRIPTS | {p.name for p in SCRIPTS_DIR.glob("*.py")})
SHEBANG: Final = "#!/usr/bin/env python3"


def test_skill_ships_the_two_scripts() -> None:
    assert {p.name for p in SCRIPTS_DIR.glob("*.py")} == EXPECTED_SCRIPTS


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_is_an_executable_python3_program(script: str) -> None:
    path = SCRIPTS_DIR / script
    assert path.read_text(encoding="utf-8").split("\n", 1)[0] == SHEBANG
    if os.name != "nt":  # Windows has no executable bit to check
        assert os.access(path, os.X_OK), f"{script} is not executable (chmod +x)"


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_parses_as_310_and_imports_only_stdlib(script: str) -> None:
    path = SCRIPTS_DIR / script
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=script, feature_version=(3, 10))
    docstring = ast.get_docstring(tree) or ""
    assert path.name in docstring, "the module docstring must carry a usage line"
    assert _non_stdlib_imports(tree) == []


def _non_stdlib_imports(tree: ast.Module) -> list[str]:
    """Imported top-level names outside the stdlib; a relative import counts too."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level + (node.module or ""))
    return sorted(n for n in names if n.split(".")[0] not in sys.stdlib_module_names)


@pytest.fixture(scope="module")
def mypy_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A neutral cwd + empty config + shared cache, so the repo config never applies."""
    workdir = tmp_path_factory.mktemp("mypy-scripts")
    (workdir / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
    return workdir


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_passes_strict_mypy_for_python_310(script: str, mypy_workdir: Path) -> None:
    command = [sys.executable, "-m", "mypy", "--strict", "--python-version", "3.10"]
    command += ["--config-file", str(mypy_workdir / "mypy.ini")]
    command += ["--cache-dir", str(mypy_workdir / "cache"), str(SCRIPTS_DIR / script)]
    proc = subprocess.run(
        command, cwd=mypy_workdir, capture_output=True, text=True, timeout=300, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
