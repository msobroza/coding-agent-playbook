"""The CLI contract of ``detect_smells.py``, and scans that must survive pathological depth.

JSON on stdout, exit 0 with or without hits, exit 2 on a usage error,
unparseable files named on stderr and skipped; a module that nests too deeply
is skipped on its own without aborting the scan of every other file.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from tests.core_skills.design_patterns._scripts import (
    BARE,
    DETECT_SMELLS,
    hits_of,
    run_script,
    scan_smells,
    write_tree,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

pytestmark = pytest.mark.catalog

HIT_KEYS: Final = {"smell", "file", "line", "evidence"}

# --- pathological depth must not abort a scan --------------------------------------------

# More elif branches than the default recursion limit (1000) allows frames; every
# supported Python still parses it.
LONG_CHAIN_BRANCHES = 1500


def _elif_chain(branches: int, last_body: list[str]) -> str:
    """``dispatch`` with one ``if`` plus ``branches - 1`` elifs; ``last_body`` ends the chain."""
    lines = ["def dispatch(code, rows):", "    if code == 0:", "        pass"]
    for number in range(1, branches):
        lines += [f"    elif code == {number}:", "        pass"]
    return "\n".join(lines + last_body) + "\n"


def _sum_of(terms: int) -> str:
    return " + ".join(f"a{number}" for number in range(terms))


def test_deep_nesting_survives_an_elif_chain_longer_than_the_stack(
    detect: ModuleType, tmp_path: Path
) -> None:
    # Regression: block_levels recursed once per elif and raised RecursionError.
    nested = [
        "    elif code == -1:",
        "        for row in rows:",
        "            if row:",
        "                with row:  # fourth",
        "                    while row:",
        "                        pass",
    ]
    source = _elif_chain(LONG_CHAIN_BRANCHES, nested)
    found = hits_of(scan_smells(detect, tmp_path, source), "deep-nesting")
    fourth = source.splitlines().index("                with row:  # fourth") + 1
    assert found == [(fourth, "'dispatch' nests blocks 5 levels deep (more than 3)")]


def test_snippet_falls_back_for_an_expression_too_deep_to_unparse(smell_model: ModuleType) -> None:
    # Regression: ast.unparse recursed past the limit and aborted the whole scan.
    deep: ast.expr = ast.Name("a0")
    for number in range(1, 5 * sys.getrecursionlimit()):
        deep = ast.BinOp(deep, ast.Add(), ast.Name(f"a{number}"))
    assert smell_model.snippet(deep) == smell_model.TOO_DEEP_TO_PRINT
    assert smell_model.snippet(ast.parse("total + 1", mode="eval").body) == "total + 1"


def test_scan_skips_only_the_module_that_exhausts_the_stack(
    detect: ModuleType,
    smell_model: ModuleType,
    smell_detectors: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def stack_exhausting_detector(module: Any) -> Iterator[Any]:
        """Bare excepts, except in a module defining ``too_deep`` (stands in for any overflow)."""
        if "too_deep" in {fn.name for fn in smell_model.functions_in(module.tree)}:
            raise RecursionError("maximum recursion depth exceeded")
        yield from smell_detectors.detect_bare_excepts(module)

    write_tree(tmp_path, {"deep.py": BARE + "def too_deep():\n    pass\n", "ok.py": BARE})
    found = detect.scan([tmp_path], detectors=(stack_exhausting_detector,))
    assert [(hit["file"], hit["smell"]) for hit in found] == [
        ((tmp_path / "ok.py").as_posix(), "bare-except")
    ]
    stderr = capsys.readouterr().err
    assert f"skipped {(tmp_path / 'deep.py').as_posix()}: maximum recursion depth" in stderr


# --- CLI contract ------------------------------------------------------------------------


def test_cli_prints_sorted_json_and_exits_zero_with_hits(tmp_path: Path) -> None:
    write_tree(
        tmp_path,
        {
            "b.py": "def f(x=[], y_str=''):\n    global z\n",
            "a.py": BARE + "def g(items={}):\n    return items\n",
        },
    )
    first = run_script(DETECT_SMELLS, str(tmp_path / "b.py"), str(tmp_path))
    assert first.returncode == 0, first.stderr
    hits = json.loads(first.stdout)
    assert hits and all(set(hit) == HIT_KEYS for hit in hits)
    keys = [(hit["file"], hit["line"], hit["smell"]) for hit in hits]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys)), "a file named twice is scanned once"
    assert run_script(DETECT_SMELLS, str(tmp_path), str(tmp_path / "b.py")).stdout == first.stdout


def test_cli_default_path_recurses_and_skips_tool_dirs(tmp_path: Path) -> None:
    skipped = [".hidden", ".venv", "venv", "node_modules", "__pycache__", "lib/site-packages"]
    write_tree(tmp_path, {f"{folder}/mod.py": BARE for folder in skipped})
    write_tree(tmp_path, {"pkg/mod.py": BARE, "pkg/notes.txt": BARE})
    result = run_script(DETECT_SMELLS, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {
            "smell": "bare-except",
            "file": "pkg/mod.py",
            "line": 3,
            "evidence": "bare 'except:' also catches KeyboardInterrupt and SystemExit",
        }
    ]


def test_cli_clean_tree_prints_an_empty_array(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("VALUE = 1\n", encoding="utf-8")
    result = run_script(DETECT_SMELLS, str(tmp_path))
    assert (result.returncode, json.loads(result.stdout)) == (0, [])


def test_cli_unparseable_file_is_reported_and_skipped(tmp_path: Path) -> None:
    write_tree(tmp_path, {"broken.py": "def broken(:\n", "good.py": BARE})
    result = run_script(DETECT_SMELLS, str(tmp_path))
    assert result.returncode == 0
    assert "broken.py" in result.stderr
    assert [hit["file"] for hit in json.loads(result.stdout)] == [(tmp_path / "good.py").as_posix()]


def test_cli_deep_files_do_not_abort_a_multi_file_scan(tmp_path: Path) -> None:
    # Regression: one of these used to end the run with exit 1, a traceback and no JSON.
    terms = _sum_of(400)
    write_tree(
        tmp_path,
        {
            "chain.py": _elif_chain(LONG_CHAIN_BRANCHES, []),
            "default.py": f"def f(x=[{terms}]):\n    return x\n",
            "ladder.py": "def g(v):\n"
            + "".join(
                f"    {keyword} isinstance({terms}, {kind}):\n        return 1\n"
                for keyword, kind in [("if", "int"), ("elif", "str"), ("elif", "float")]
            ),
            "plain.py": BARE,
        },
    )
    result = run_script(DETECT_SMELLS, str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    found = {(Path(hit["file"]).name, hit["smell"]) for hit in json.loads(result.stdout)}
    assert found == {
        ("chain.py", "long-function"),
        ("default.py", "mutable-default-argument"),
        ("ladder.py", "isinstance-ladder"),
        ("plain.py", "bare-except"),
    }


@pytest.mark.parametrize(
    "args",
    [["does-not-exist.py"], ["--no-such-option"]],
    ids=["missing-path", "unknown-option"],
)
def test_cli_usage_errors_exit_2(tmp_path: Path, args: list[str]) -> None:
    result = run_script(DETECT_SMELLS, *args, cwd=tmp_path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "error" in result.stderr


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions enforced for a non-root user",
)
def test_cli_unreadable_path_exits_2(tmp_path: Path) -> None:
    locked = tmp_path / "locked.py"
    locked.write_text(BARE, encoding="utf-8")
    locked.chmod(0)
    try:
        result = run_script(DETECT_SMELLS, str(locked))
    finally:
        locked.chmod(0o644)
    assert result.returncode == 2
    assert "cannot read" in result.stderr


@pytest.mark.skipif(shutil.which("python3.10") is None, reason="python3.10 is not installed")
def test_cli_runs_on_python_310(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(BARE, encoding="utf-8")
    interpreter = shutil.which("python3.10")
    assert interpreter is not None
    result = subprocess.run(
        [interpreter, str(DETECT_SMELLS), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert [hit["smell"] for hit in json.loads(result.stdout)] == ["bare-except"]
