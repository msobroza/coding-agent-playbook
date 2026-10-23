"""What only the design-patterns skill's scripts promise (prU D2, D25).

The contract every core skill's scripts keep (shebang, usage docstring, Python 3.10
grammar, standard library only, ``mypy --strict``) is checked for every skill by
``tests/core_skills/test_script_contract.py``. This module pins the skill's script
set, that both scripts share one definition of their helpers, and an isolated run.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Final

import pytest

from tests.core_skills._script_contract import helper_files, run_isolated_copy, script_files
from tests.core_skills.design_patterns._scripts import SCRIPTS_DIR, SmellHit

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog

#: The two python_design scripts the skill took over (D2); a new script joins by existing.
EXPECTED_SCRIPTS: Final = frozenset({"detect_smells.py", "lcom4_clusters.py"})
SCRIPTS: Final = sorted(EXPECTED_SCRIPTS | set(script_files(SCRIPTS_DIR)))


def test_skill_ships_the_two_scripts() -> None:
    assert set(script_files(SCRIPTS_DIR)) == EXPECTED_SCRIPTS


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


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_runs_isolated_from_a_copy_and_leaves_no_bytecode(
    script: str, tmp_path: Path
) -> None:
    """The helpers still import under ``python -I``; the copy stays free of __pycache__."""
    (tmp_path / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    proc, copied = run_isolated_copy(SCRIPTS_DIR, script, [str(tmp_path / "mod.py")], tmp_path)
    assert (proc.returncode, proc.stdout.strip()) == (0, "[]"), proc.stderr
    assert copied == sorted(SCRIPTS + helper_files(SCRIPTS_DIR))
