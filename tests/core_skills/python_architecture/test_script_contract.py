"""The shape every script of the python-architecture skill keeps (prU D2, D25).

The scripts run in consumer repos on Python 3.10 or later, outside this package, so
each one is an executable ``python3`` program that names itself in its usage
docstring, parses as Python 3.10, imports only the standard library, and passes
``mypy --strict`` for Python 3.10 under an empty config (never the repo's).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Final

import pytest

from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

SCRIPTS_DIR: Final = core_skill_root("python-architecture") / "scripts"
#: The python_design script the skill took over (D2); a new script joins by existing.
EXPECTED_SCRIPTS: Final = frozenset({"layer_map.py"})
SCRIPTS: Final = sorted(EXPECTED_SCRIPTS | {p.name for p in SCRIPTS_DIR.glob("*.py")})
SHEBANG: Final = "#!/usr/bin/env python3"


def test_skill_ships_the_layer_map_script() -> None:
    assert {p.name for p in SCRIPTS_DIR.glob("*.py")} == EXPECTED_SCRIPTS


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_is_an_executable_python3_program(script: str) -> None:
    path = SCRIPTS_DIR / script
    assert path.read_text(encoding="utf-8").split("\n", 1)[0] == SHEBANG
    if os.name != "nt":  # Windows has no executable bit to check
        assert os.access(path, os.X_OK), f"{script} is not executable (chmod +x)"


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_names_itself_in_its_usage_docstring(script: str) -> None:
    assert script in (ast.get_docstring(_tree(script)) or ""), "the docstring needs a usage line"


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_parses_as_310_and_imports_only_stdlib(script: str) -> None:
    names = _imported_names(_tree(script))
    assert sorted(n for n in names if n.split(".")[0] not in sys.stdlib_module_names) == []


def _tree(name: str) -> ast.Module:
    """The file parsed with the Python 3.10 grammar (a newer construct fails here)."""
    source = (SCRIPTS_DIR / name).read_text(encoding="utf-8")
    return ast.parse(source, filename=name, feature_version=(3, 10))


def _imported_names(tree: ast.Module) -> list[str]:
    """Every imported module name; a relative import keeps its dots, so it never matches."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level + (node.module or ""))
    return names


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


def test_script_runs_isolated_from_a_copy_and_leaves_no_bytecode(tmp_path: Path) -> None:
    """``python -I`` from a copy stands in for a synced skill directory, kept free of __pycache__."""
    skill_scripts = tmp_path / "scripts"
    skill_scripts.mkdir()
    shutil.copy2(SCRIPTS_DIR / "layer_map.py", skill_scripts / "layer_map.py")
    project = tmp_path / "project"
    (project / "domain").mkdir(parents=True)
    (project / "domain" / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", str(skill_scripts / "layer_map.py"), str(project), "--json"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert '"domain.model": "domain"' in proc.stdout
    assert sorted(p.name for p in skill_scripts.iterdir()) == ["layer_map.py"]
