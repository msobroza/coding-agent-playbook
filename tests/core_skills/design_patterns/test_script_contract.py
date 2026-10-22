"""The shape every script of the design-patterns skill keeps (prU D2, D25).

The scripts run in consumer repos on Python 3.10 or later, outside this package,
so each one is an executable ``python3`` program that names itself in its usage
docstring. The ``_``-prefixed helper modules beside them hold code the scripts
share (one home per piece of logic) and are imported, never run. Every file
parses as Python 3.10, imports only the standard library and its sibling helpers,
and passes ``mypy --strict`` for Python 3.10 under an empty config (never the repo's).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from tests.core_skills.design_patterns._scripts import SCRIPTS_DIR, SmellHit

if TYPE_CHECKING:
    from types import ModuleType

pytestmark = pytest.mark.catalog

#: The two python_design scripts the skill took over (D2); a new script joins by existing.
EXPECTED_SCRIPTS: Final = frozenset({"detect_smells.py", "lcom4_clusters.py"})
#: The helper modules the scripts import; a file name starting with ``_`` marks one.
HELPERS: Final = sorted(p.name for p in SCRIPTS_DIR.glob("_*.py"))
SCRIPTS: Final = sorted(EXPECTED_SCRIPTS | {p.name for p in SCRIPTS_DIR.glob("[!_]*.py")})
SHEBANG: Final = "#!/usr/bin/env python3"


def test_skill_ships_the_two_scripts() -> None:
    assert {p.name for p in SCRIPTS_DIR.glob("[!_]*.py")} == EXPECTED_SCRIPTS


@pytest.mark.parametrize("helper", HELPERS)
def test_every_helper_is_imported_by_a_script(helper: str) -> None:
    importers = [
        name for name in SCRIPTS + HELPERS if Path(helper).stem in _imported_names(_tree(name))
    ]
    assert importers, f"{helper} is imported by no script or helper: delete it or use it"


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_is_an_executable_python3_program(script: str) -> None:
    path = SCRIPTS_DIR / script
    assert path.read_text(encoding="utf-8").split("\n", 1)[0] == SHEBANG
    if os.name != "nt":  # Windows has no executable bit to check
        assert os.access(path, os.X_OK), f"{script} is not executable (chmod +x)"


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_names_itself_in_its_usage_docstring(script: str) -> None:
    assert script in (ast.get_docstring(_tree(script)) or ""), "the docstring needs a usage line"


@pytest.mark.parametrize("name", SCRIPTS + HELPERS)
def test_file_parses_as_310_and_imports_only_stdlib_and_helpers(name: str) -> None:
    helpers = {Path(helper).stem for helper in HELPERS}
    outside = [n for n in _imported_names(_tree(name)) if n.split(".")[0] not in helpers]
    assert sorted(n for n in outside if n.split(".")[0] not in sys.stdlib_module_names) == []


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


def test_both_scripts_share_one_stub_and_file_walk_definition(
    detect: ModuleType, lcom4: ModuleType, tmp_path: Path
) -> None:
    """One home per helper: the scripts agree on stub methods and on which files they read."""
    assert lcom4.is_stub_body is sys.modules["_smell_detectors"].is_stub_body
    assert lcom4.load_modules is detect.load_modules
    # A literal after the docstring is behaviour for both, not a stub.
    path = tmp_path / "flags.py"
    source = "class Flags:\n    def on(self):\n        return self.state\n\n"
    source += '    def default(self):\n        """Docs."""\n        0\n'
    path.write_text(source, encoding="utf-8")
    smells: list[SmellHit] = detect.scan([path])
    assert [(hit["smell"], hit["line"]) for hit in smells] == [("method-could-be-function", 5)]
    assert [item["clusters"] for item in lcom4.scan([path])] == [[["on"], ["default"]]]


@pytest.fixture(scope="module")
def mypy_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A neutral cwd + empty config + shared cache, so the repo config never applies."""
    workdir = tmp_path_factory.mktemp("mypy-scripts")
    (workdir / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
    return workdir


@pytest.mark.parametrize("script", SCRIPTS + HELPERS)
def test_script_passes_strict_mypy_for_python_310(script: str, mypy_workdir: Path) -> None:
    command = [sys.executable, "-m", "mypy", "--strict", "--python-version", "3.10"]
    command += ["--config-file", str(mypy_workdir / "mypy.ini")]
    command += ["--cache-dir", str(mypy_workdir / "cache"), str(SCRIPTS_DIR / script)]
    proc = subprocess.run(
        command, cwd=mypy_workdir, capture_output=True, text=True, timeout=300, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_runs_isolated_from_a_copy_and_leaves_no_bytecode(
    script: str, tmp_path: Path
) -> None:
    """``python -I`` drops the script's directory from sys.path; the helpers still import.

    The copy stands in for a synced skill directory, which must stay free of __pycache__.
    """
    skill_scripts = tmp_path / "scripts"
    skill_scripts.mkdir()
    for name in SCRIPTS + HELPERS:
        shutil.copy2(SCRIPTS_DIR / name, skill_scripts / name)
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", str(skill_scripts / script), str(tmp_path / "mod.py")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
        check=False,
    )
    assert (proc.returncode, proc.stdout.strip()) == (0, "[]"), proc.stderr
    assert sorted(p.name for p in skill_scripts.iterdir()) == sorted(SCRIPTS + HELPERS)
