"""Sample trees, move maps and fakes for the module-path rewrite script's tests.

A test builds a small ``tmp_path`` repository with ``repo_with``: an engine package in
the target layout plus the files that still name the old layout, and loads a map
with ``load_test_map``. ``FakeFormatter`` and ``FakeRuffRun`` stand in for ruff
(R-FORMAT), so no test runs a binary. The script never opens this file (it names
old paths on purpose).
"""

from __future__ import annotations

import subprocess
import textwrap
from typing import TYPE_CHECKING

from tests.architecture.module_moves import load_map

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from tests.architecture.module_moves import MoveMap

#: N1: the pilot rename ``_toml`` -> ``toml_writer``.
N1_MAP = """
[[module]]
pr = "N1"
old = "coding_agent_playbook._toml"
new = "coding_agent_playbook.toml_writer"
"""
#: N2's same-name conversion: config.py becomes config/model.py, ConfigError leaves for schema.
N2_MAP = """
[[module]]
pr = "N2"
old = "coding_agent_playbook.config"
new = "coding_agent_playbook.config.model"

[[names]]
pr = "N2"
old = "coding_agent_playbook.config"
new = "coding_agent_playbook.config.schema"
names = ["ConfigError"]
"""
N2_TREE = {
    "src/coding_agent_playbook/config/__init__.py": '"""The two consumer config files."""\n',
    "src/coding_agent_playbook/config/model.py": "class Config: ...\n",
    "src/coding_agent_playbook/config/schema.py": "class ConfigError(Exception): ...\n",
}
#: N12: a package move, ``harness/`` -> ``agent_harness/``.
N12_MAP = """
[[module]]
pr = "N12"
old = "coding_agent_playbook.harness"
new = "coding_agent_playbook.agent_harness"
package = true
"""
N12_TREE = {
    "src/coding_agent_playbook/agent_harness/__init__.py": '"""The Agent Harness format."""\n',
    "src/coding_agent_playbook/agent_harness/models.py": "class HarnessTree: ...\n",
    "src/coding_agent_playbook/agent_harness/parser.py": "def parse() -> None: ...\n",
}
#: N3 and N4: same-name conversions, ``catalog.py`` -> ``catalog/roots.py`` and
#: ``detector.py`` -> ``detector/facts.py``, each leaving a docstring-only package.
N3_N4_MAP = """
[[module]]
pr = "N3"
old = "coding_agent_playbook.catalog"
new = "coding_agent_playbook.catalog.roots"

[[module]]
pr = "N4"
old = "coding_agent_playbook.detector"
new = "coding_agent_playbook.detector.facts"
"""
N3_N4_TREE = {
    "src/coding_agent_playbook/catalog/__init__.py": '"""The catalog."""\n',
    "src/coding_agent_playbook/catalog/roots.py": "_PACKAGE_DIR = None\n",
    "src/coding_agent_playbook/detector/__init__.py": '"""The detector."""\n',
    "src/coding_agent_playbook/detector/facts.py": "def detect() -> None: ...\n",
}
#: AH-1: the Agent Harness adapter joins the ``agent_harness`` package. The pair is
#: move-map sample data for a ``tmp_path`` tree, not a pin on the installed engine
#: (the new name must not resolve today), so it stays out of ``engine_module`` and
#: out of the module-constant position test_module_pins.py rejects (D0-4).
AH1_OLD, AH1_NEW = (
    "coding_agent_playbook.adapters.agent_harness_adapter",
    "coding_agent_playbook.agent_harness.adapter",
)
AH1_TREE = {
    "src/coding_agent_playbook/adapters/__init__.py": "",
    "src/coding_agent_playbook/agent_harness/__init__.py": "",
    "src/coding_agent_playbook/agent_harness/adapter.py": "class AgentHarnessAdapter: ...\n",
}
#: The record rows of MIGRATION.md (5.3.8): old paths that no move rewrites.
MIGRATION_RECORD_ROWS = (
    "| `coding_agent_playbook.bundled_content` | `coding_agent_playbook.catalog` |",
    "| `src/coding_agent_playbook/resources/precommit/config.yaml.j2` |",
    "from coding_agent_playbook.evaluators.registry import Evaluator, register_evaluator",
    "from coding_agent_playbook.evaluators.scope import Scope, ValueKind, Determinism",
    '[project.entry-points."coding_agent_playbook.evaluators"]',
    "from coding_agent_playbook.evaluators.grade import grade",
    "report = grade(candidate, baseline, policy, extra_evaluators={name: inst})",
    "`Evaluator`, `evaluators/registry.py`, `evaluators/grade.py` (`grade()`),",
    "`evaluators/expected.py`, `evaluators/judged.py` (`JudgedCriterion`),",
    "fields, and `evals/task.py::evaluators_for_task` are **removed**. Their",
)


def map_entry(kind: str, old: str, new: str, extra: str = "") -> str:
    """One ``[[kind]]`` table of a map file (PR ``T``), plus any ``extra`` key lines.

    Example: ``map_entry("path", "a/", "b/")`` is ``'[[path]]\\npr = "T"\\nold = "a/"\\nnew = "b/"\\n'``.
    """
    return f'[[{kind}]]\npr = "T"\nold = "{old}"\nnew = "{new}"\n{extra}'


_E = "coding_agent_playbook"
#: ``(id, entry, the frozen name the error names)``: every entry renames an L2 name.
FROZEN_ENTRIES = (
    ("runtime", map_entry("module", f"{_E}.hook_runtime", f"{_E}.x"), "hook_runtime'"),
    ("runtime-cli", map_entry("module", f"{_E}.hook_runtime.cli", f"{_E}.x"), "runtime.cli'"),
    ("cli", map_entry("module", f"{_E}.cli", f"{_E}.cli.parser"), "playbook.cli'"),
    ("base", map_entry("module", f"{_E}.adapters.base", f"{_E}.x"), "base'"),
    (
        "package-of-base",
        map_entry("module", f"{_E}.adapters", f"{_E}.x", "package = true"),
        "base'",
    ),
    ("group", map_entry("module", f"{_E}.checks", f"{_E}.x"), "playbook.checks'"),
    ("cli-main", map_entry("names", f"{_E}.cli", f"{_E}.y", 'names = ["main"]'), "cli:main"),
    ("path", map_entry("path", "hook_runtime/", "runtime/"), "hook_runtime/'"),
    ("dir", map_entry("path", "adapters/", "x/"), "adapters/base.py'"),
)


class FakeFormatter:
    """Records the files ``apply`` hands to the formatter instead of running ruff."""

    def __init__(self) -> None:
        self.calls: list[list[Path]] = []

    def __call__(self, repo_root: Path, paths: Sequence[Path]) -> None:
        self.calls.append(list(paths))


class FakeRuffRun:
    """Records the ruff commands ``run_ruff`` would start, and answers with ``returncode``."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        assert options["timeout"], "every ruff run is bounded"
        self.commands.append(command)
        return subprocess.CompletedProcess(command, self.returncode, "", "bad input")


def write_files(root: Path, files: Mapping[str, str]) -> Path:
    """Write each ``relative path: text`` (dedented) under ``root``; return ``root``.

    Example: ``write_files(tmp_path, {"SPEC.md": "x\\n"})`` writes ``tmp_path/SPEC.md``.
    """
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return root


def repo_with(tmp_path: Path, files: Mapping[str, str]) -> Path:
    """A working tree at ``tmp_path/repo`` holding the engine root package and ``files``.

    Example: ``repo_with(tmp_path, N12_TREE)`` is a tree where N12 has already moved.
    """
    return write_files(tmp_path / "repo", {"src/coding_agent_playbook/__init__.py": "", **files})


def load_test_map(tmp_path: Path, **files: str) -> MoveMap:
    """Load a move map made of one ``<keyword>.toml`` per keyword, under ``tmp_path/map``.

    Example: ``load_test_map(tmp_path, n01=N1_MAP)`` loads ``tmp_path/map/n01.toml``.
    """
    texts = {f"{name}.toml": textwrap.dedent(text) for name, text in files.items()}
    return load_map(write_files(tmp_path / "map", texts))


def read(repo: Path, relative: str) -> str:
    """The text of ``repo/relative``; example: ``read(repo, "SPEC.md")``."""
    return (repo / relative).read_text(encoding="utf-8")
