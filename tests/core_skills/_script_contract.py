"""Helpers for the contract every core skill's ``scripts/`` keeps (prU D2, D25).

A skill's scripts run in consumer repos on Python 3.10 or later, outside this package.
An executable ``python3`` program is a script; a ``_``-prefixed module beside it is a
helper the scripts import and never run. ``test_script_contract.py`` next to this
module checks every core skill's scripts with these helpers; each skill's own
``test_script_contract.py`` adds what only that skill knows (its script set and a run).
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Final

from tests._catalog import CORE_SKILLS_ROOT

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

SHEBANG: Final = "#!/usr/bin/env python3"


def skills_with_scripts() -> list[str]:
    """Every core skill id that ships a ``scripts/`` directory, sorted.

    Example: ``skills_with_scripts()`` -> ``["design-patterns", "python-architecture"]``.
    """
    return sorted(path.parent.name for path in CORE_SKILLS_ROOT.glob("*/scripts") if path.is_dir())


def script_files(scripts_dir: Path) -> list[str]:
    """The programs in ``scripts_dir``: ``.py`` files whose name does not start with ``_``."""
    return sorted(path.name for path in scripts_dir.glob("[!_]*.py"))


def helper_files(scripts_dir: Path) -> list[str]:
    """The helper modules in ``scripts_dir``: ``.py`` files whose name starts with ``_``."""
    return sorted(path.name for path in scripts_dir.glob("_*.py"))


def parse_as_310(path: Path) -> ast.Module:
    """The file parsed with the Python 3.10 grammar (a newer construct fails here)."""
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=path.name, feature_version=(3, 10))


def imported_names(tree: ast.Module) -> list[str]:
    """Every imported module name; a relative import keeps its dots, so it never matches.

    Example: ``imported_names(ast.parse("from . import x"))`` -> ``["."]``.
    """
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level + (node.module or ""))
    return names


def run_strict_mypy(path: Path, workdir: Path) -> subprocess.CompletedProcess[str]:
    """``mypy --strict`` for Python 3.10 on ``path`` from ``workdir``, under its empty config."""
    command = [sys.executable, "-m", "mypy", "--strict", "--python-version", "3.10"]
    command += ["--config-file", str(workdir / "mypy.ini")]
    command += ["--cache-dir", str(workdir / "cache"), str(path)]
    return subprocess.run(
        command, cwd=workdir, capture_output=True, text=True, timeout=300, check=False
    )


def run_isolated_copy(
    scripts_dir: Path, script: str, args: Sequence[str], tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run a copy of ``scripts_dir``'s ``script`` under ``python -I`` from ``tmp_path``.

    ``-I`` drops the script's directory from sys.path, so the helpers must still
    import; the copy stands in for a synced skill directory. Returns the run and the
    copied directory's file names afterwards, to check that no __pycache__ appeared.
    """
    copied = tmp_path / "scripts"
    copied.mkdir()
    for name in script_files(scripts_dir) + helper_files(scripts_dir):
        shutil.copy2(scripts_dir / name, copied / name)
    proc = subprocess.run(
        [sys.executable, "-I", str(copied / script), *args],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
        check=False,
    )
    return proc, sorted(path.name for path in copied.iterdir())
