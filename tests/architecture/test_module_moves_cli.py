"""The module-path rewrite script's interface: map loading, resolution, reports, CLI, R-FORMAT.

The rules themselves are in ``test_module_moves.py`` (specs/prT-package-layout.md 5.4.4);
these tests pin what a move PR author meets around them.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

import pytest

from tests.architecture._module_moves_format import run_ruff
from tests.architecture.module_moves import ENTRY_POINT_GROUPS, check, main
from tests.architecture.module_moves_samples import (
    N1_MAP,
    N2_MAP,
    N2_TREE,
    FakeRuffRun,
    load_test_map,
    read,
    repo_with,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_N25_NOT_IDEMPOTENT = """
[[module]]
pr = "N25"
old = "coding_agent_playbook.evaluators"
new = "coding_agent_playbook.evaluators.grading"
package = true
"""
_N4_CONVERSION = """
[[module]]
pr = "N4"
old = "coding_agent_playbook.detector"
new = "coding_agent_playbook.detector.facts"
"""
_NOT_DOTTED = '[[module]]\npr = "X"\nold = "toml"\nnew = "coding_agent_playbook.toml_writer"\n'
_OVERLAY = '[[module]]\npr = "X"\nold = "coding_agent_playbook.plugins.x"\nnew = "coding_agent_playbook.y"\n'


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (
            {"n25": _N25_NOT_IDEMPOTENT},
            r"n25\.toml: .*'coding_agent_playbook\.evaluators' is not idempotent",
        ),
        (
            {"a": N1_MAP, "b": N1_MAP},
            r"b\.toml: .*'coding_agent_playbook\._toml' is also moved by a\.toml",
        ),
        ({"x": '[[modules]]\npr = "X"\n'}, r"x\.toml: unknown keys \['modules'\]"),
        ({"x": _NOT_DOTTED}, r"x\.toml: .*'toml' is not a dotted module name"),
        ({"x": _OVERLAY}, "is an overlay label, not a module"),
        ({"x": "[[module]\n"}, r"x\.toml: not valid TOML"),
    ],
    ids=[
        "not-idempotent",
        "doubly-moved",
        "unknown-kind",
        "not-dotted",
        "overlay-label",
        "bad-toml",
    ],
)
def test_load_map_refuses_invalid_entries(
    tmp_path: Path, files: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_test_map(tmp_path, **files)


def test_resolve_gives_the_current_spelling_or_none(tmp_path: Path) -> None:
    repo = repo_with(
        tmp_path, {"src/coding_agent_playbook/toml_writer.py": "def dumps() -> str: ...\n"}
    )
    moves = load_test_map(tmp_path, n01=N1_MAP)

    assert (
        moves.resolve("coding_agent_playbook._toml.dumps", repo)
        == "coding_agent_playbook.toml_writer.dumps"
    )
    assert moves.resolve("coding_agent_playbook.toml_writer", repo) is None  # current
    assert moves.resolve("coding_agent_playbook._toml.gone", repo) is None  # no current spelling
    assert moves.resolve("coding_agent_playbook.renderer", repo) is None  # not in the map
    assert moves.resolve_path("src/coding_agent_playbook/_toml.py", repo) == (
        "src/coding_agent_playbook/toml_writer.py"
    )


def test_a_name_spelled_like_a_submodule_in_another_case_is_not_current(tmp_path: Path) -> None:
    # Regression: on a case-insensitive file system (macOS APFS), detector/Facts.py
    # "existed" because detector/facts.py does, so detector.Facts looked current and
    # every `from coding_agent_playbook.detector import Facts` was left stale.
    tree = {
        "src/coding_agent_playbook/detector/__init__.py": '"""The detector."""\n',
        "src/coding_agent_playbook/detector/facts.py": "class Facts: ...\n",
        "tests/test_a.py": "from coding_agent_playbook.detector import Facts\n",
    }
    repo = repo_with(tmp_path, tree)
    moves = load_test_map(tmp_path, n04=_N4_CONVERSION)

    assert moves.resolve("coding_agent_playbook.detector.Facts", repo) == (
        "coding_agent_playbook.detector.facts.Facts"
    )
    assert moves.resolve_path("src/coding_agent_playbook/Detector/facts.py", repo) is None
    assert check(repo, moves) == [
        "tests/test_a.py:1: coding_agent_playbook.detector -> coding_agent_playbook.detector.facts"
    ]


def test_unparsable_python_is_reported_not_rewritten(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, {"tests/test_a.py": "from coding_agent_playbook._toml import (\n"})

    lines = check(repo, load_test_map(tmp_path, n01=N1_MAP))

    assert lines == [
        "review: tests/test_a.py:1: not parsed as Python ('(' was never closed); not checked"
    ]


def test_a_missing_migration_section_is_reported(tmp_path: Path) -> None:
    repo = repo_with(tmp_path, {**N2_TREE, "MIGRATION.md": "# Migration guide\n"})

    lines = check(repo, load_test_map(tmp_path, n02=N2_MAP))

    assert lines == [
        "review: MIGRATION.md:1: no <!-- module-moves:start --> section to list the 2 public module moves in"
    ]


def test_cli_check_prints_stale_lines_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = {
        "src/coding_agent_playbook/toml_writer.py": "",
        "tests/architecture/move_map/n01.toml": N1_MAP,
        "tests/test_a.py": "import coding_agent_playbook._toml as toml\n",
    }

    assert main(["check", "--repo", str(repo_with(tmp_path, tree))]) == 1
    assert capsys.readouterr().out == (
        "tests/test_a.py:1: import coding_agent_playbook._toml as toml"
        " -> import coding_agent_playbook.toml_writer as toml\n"
    )


def test_cli_apply_prints_the_changed_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = {
        "src/coding_agent_playbook/toml_writer.py": "def dumps() -> str: ...\n",
        "tests/architecture/move_map/n01.toml": N1_MAP,
        "pyproject.toml": '[project.scripts]\nx = "coding_agent_playbook._toml:dumps"\n',
    }
    repo = repo_with(tmp_path, tree)

    assert main(["apply", "--repo", str(repo)]) == 0
    assert capsys.readouterr().out == "pyproject.toml\n"
    assert (
        read(repo, "pyproject.toml")
        == '[project.scripts]\nx = "coding_agent_playbook.toml_writer:dumps"\n'
    )
    assert main(["check", "--repo", str(repo)]) == 0


def test_cli_reports_an_invalid_map_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = repo_with(tmp_path, {"tests/architecture/move_map/x.toml": "[[module]]\n"})

    assert main(["apply", "--repo", str(repo)]) == 2
    assert capsys.readouterr().err.startswith(
        "error: x.toml: [[module]] {} lacks ['new', 'old', 'pr']"
    )


def test_run_ruff_sorts_imports_then_formats_python_and_markdown(tmp_path: Path) -> None:
    run = FakeRuffRun()

    run_ruff(tmp_path, [tmp_path / "src/a.py", tmp_path / "SPEC.md"], run=run)

    ruff = [sys.executable, "-m", "ruff"]
    assert run.commands == [
        [*ruff, "check", "--fix", "--exit-zero", "--select", "I", "src/a.py"],
        [*ruff, "format", "src/a.py", "SPEC.md"],
    ]


def test_run_ruff_raises_when_ruff_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"ruff format SPEC\.md exited 2: bad input"):
        run_ruff(tmp_path, [tmp_path / "SPEC.md"], run=FakeRuffRun(returncode=2))


def _imported_modules(source: str) -> set[str]:
    """Every module an ``import`` or ``from`` statement of ``source`` names."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_module_moves_imports_only_the_stdlib() -> None:
    folder = _REPO_ROOT / "tests/architecture"
    script = [folder / "module_moves.py", *sorted(folder.glob("_module_moves_*.py"))]
    own = {f"tests.architecture.{path.stem}" for path in script}

    outside = [
        f"{path.name}: {name}"
        for path in script
        for name in sorted(_imported_modules(path.read_text(encoding="utf-8")))
        if name.split(".")[0] not in sys.stdlib_module_names and name not in own
    ]
    assert len(script) > 1
    assert outside == []


def test_entry_point_groups_match_pyproject() -> None:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    groups = sorted(group.split(".", 1)[1] for group in pyproject["project"]["entry-points"])
    assert groups == list(ENTRY_POINT_GROUPS)
