"""What only the python-architecture skill's scripts promise (prU D2, D25).

The contract every core skill's scripts keep (shebang, usage docstring, Python 3.10
grammar, standard library only, ``mypy --strict``) is checked for every skill by
``tests/core_skills/test_script_contract.py``. This module pins the skill's script
set, that the script's composition-root files are the rule's globs, and an isolated run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from tests.core_skill_pins.python_architecture import PINS
from tests.core_skills._script_contract import helper_files, run_isolated_copy, script_files
from tests.core_skills.python_architecture._scripts import ROOT_FILE_NAMES, SCRIPTS_DIR

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog

#: The python_design script the skill took over (D2); a new script joins by existing.
EXPECTED_SCRIPTS: Final = frozenset({"layer_map.py"})


def test_skill_ships_the_layer_map_script() -> None:
    assert set(script_files(SCRIPTS_DIR)) == EXPECTED_SCRIPTS


def test_root_file_names_are_the_composition_root_rule_globs(layer_model: ModuleType) -> None:
    """One list of wiring files: the script and the arch-composition-root rule agree."""
    rule_globs = set(PINS.rules["arch-composition-root"].globs)
    assert {f"**/{name}" for name in layer_model.ROOT_FILE_NAMES} == rule_globs
    assert set(ROOT_FILE_NAMES) == set(layer_model.ROOT_FILE_NAMES)


def test_script_runs_isolated_from_a_copy_and_leaves_no_bytecode(tmp_path: Path) -> None:
    """The helpers still import under ``python -I``; the copy stays free of __pycache__."""
    project = tmp_path / "project"
    (project / "domain").mkdir(parents=True)
    (project / "domain" / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    args = [str(project), "--json"]
    proc, copied = run_isolated_copy(SCRIPTS_DIR, "layer_map.py", args, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert '"domain.model": "domain"' in proc.stdout
    assert copied == sorted(["layer_map.py", *helper_files(SCRIPTS_DIR)])
