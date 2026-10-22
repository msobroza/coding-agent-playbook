"""Shared helpers for the design-patterns script tests: loading, fixtures, CLI runs.

The scripts ship inside a skill and must run standalone, so they are loaded by
path (never imported as package modules) and run as subprocesses. Fixture
sources are dedented, and line expectations come from ``# <marker>`` comments so
the fixtures can be edited without renumbering.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING, Final, TypedDict, cast

from tests._catalog import core_skill_root

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

SCRIPTS_DIR: Final = core_skill_root("design-patterns") / "scripts"
DETECT_SMELLS: Final = SCRIPTS_DIR / "detect_smells.py"
LCOM4_CLUSTERS: Final = SCRIPTS_DIR / "lcom4_clusters.py"
#: A module with one bare ``except:`` on line 3.
BARE: Final = "try:\n    pass\nexcept:\n    pass\n"


class SmellHit(TypedDict):
    """One ``detect_smells.py`` output object."""

    smell: str
    file: str
    line: int
    evidence: str


#: One ``lcom4_clusters.py`` output object (``class`` is a keyword, hence this form).
CohesionHit = TypedDict(
    "CohesionHit",
    {"class": str, "file": str, "line": int, "lcom4": int, "clusters": list[list[str]]},
)


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


def dedent(source: str) -> str:
    return textwrap.dedent(source).lstrip("\n")


def line_of(source: str, marker: str) -> int:
    """1-based line of the single line of ``source`` carrying ``# <marker>``."""
    lines = dedent(source).splitlines()
    matches = [number for number, text in enumerate(lines, 1) if f"# {marker}" in text]
    assert len(matches) == 1, f"marker {marker!r} must appear exactly once"
    return matches[0]


def scan_smells(detect: ModuleType, tmp_path: Path, source: str) -> list[SmellHit]:
    """``detect_smells.scan`` over ``source`` written to one file."""
    path = tmp_path / "sample.py"
    path.write_text(dedent(source), encoding="utf-8")
    found = cast("list[SmellHit]", detect.scan([path]))
    assert all(hit["file"] == path.as_posix() for hit in found)
    return found


def hits_of(found: list[SmellHit], smell: str) -> list[tuple[int, str]]:
    """(line, evidence) of every hit of one smell."""
    return [(hit["line"], hit["evidence"]) for hit in found if hit["smell"] == smell]


def write_tree(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def run_script(
    script: Path, *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
        check=False,
    )
