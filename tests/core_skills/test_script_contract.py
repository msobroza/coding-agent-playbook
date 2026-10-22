"""The shape every core skill's scripts keep (prU D2, D25), checked for each skill.

Each script is an executable ``python3`` program that names itself in its usage
docstring. Every script and helper parses as Python 3.10, imports only the standard
library and its sibling helpers, and passes ``mypy --strict`` for Python 3.10 under
an empty config (never the repo's); every helper is imported by some file.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from tests._catalog import core_skill_root
from tests.core_skills._script_contract import (
    SHEBANG,
    helper_files,
    imported_names,
    parse_as_310,
    run_strict_mypy,
    script_files,
    skills_with_scripts,
)

pytestmark = pytest.mark.catalog


def _scripts_dir(skill: str) -> Path:
    return core_skill_root(skill) / "scripts"


SCRIPTS = [
    (skill, name) for skill in skills_with_scripts() for name in script_files(_scripts_dir(skill))
]
HELPERS = [
    (skill, name) for skill in skills_with_scripts() for name in helper_files(_scripts_dir(skill))
]


def _ids(cases: list[tuple[str, str]]) -> list[str]:
    return [f"{skill}/{name}" for skill, name in cases]


def test_the_skills_with_scripts_are_found() -> None:
    assert {"design-patterns", "python-architecture"} <= set(skills_with_scripts())


@pytest.mark.parametrize(("skill", "script"), SCRIPTS, ids=_ids(SCRIPTS))
def test_script_is_an_executable_python3_program(skill: str, script: str) -> None:
    path = _scripts_dir(skill) / script
    assert path.read_text(encoding="utf-8").split("\n", 1)[0] == SHEBANG
    if os.name != "nt":  # Windows has no executable bit to check
        assert os.access(path, os.X_OK), f"{script} is not executable (chmod +x)"


@pytest.mark.parametrize(("skill", "script"), SCRIPTS, ids=_ids(SCRIPTS))
def test_script_names_itself_in_its_usage_docstring(skill: str, script: str) -> None:
    docstring = ast.get_docstring(parse_as_310(_scripts_dir(skill) / script)) or ""
    assert script in docstring, "the docstring needs a usage line"


@pytest.mark.parametrize(("skill", "helper"), HELPERS, ids=_ids(HELPERS))
def test_every_helper_is_imported_by_a_script(skill: str, helper: str) -> None:
    scripts_dir = _scripts_dir(skill)
    files = script_files(scripts_dir) + helper_files(scripts_dir)
    importers = [
        name
        for name in files
        if Path(helper).stem in imported_names(parse_as_310(scripts_dir / name))
    ]
    assert importers, f"{helper} is imported by no script or helper: delete it or use it"


@pytest.mark.parametrize(("skill", "name"), SCRIPTS + HELPERS, ids=_ids(SCRIPTS + HELPERS))
def test_file_parses_as_310_and_imports_only_stdlib_and_helpers(skill: str, name: str) -> None:
    scripts_dir = _scripts_dir(skill)
    helpers = {Path(helper).stem for helper in helper_files(scripts_dir)}
    names = imported_names(parse_as_310(scripts_dir / name))
    outside = [n for n in names if n.split(".")[0] not in helpers]
    assert sorted(n for n in outside if n.split(".")[0] not in sys.stdlib_module_names) == []


@pytest.fixture(scope="module")
def mypy_workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A neutral cwd + empty config + shared cache, so the repo config never applies."""
    workdir = tmp_path_factory.mktemp("mypy-scripts")
    (workdir / "mypy.ini").write_text("[mypy]\n", encoding="utf-8")
    return workdir


@pytest.mark.parametrize(("skill", "name"), SCRIPTS + HELPERS, ids=_ids(SCRIPTS + HELPERS))
def test_file_passes_strict_mypy_for_python_310(skill: str, name: str, mypy_workdir: Path) -> None:
    proc = run_strict_mypy(_scripts_dir(skill) / name, mypy_workdir)
    assert proc.returncode == 0, proc.stdout + proc.stderr
