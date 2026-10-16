"""Byte-identity goldens for ``playbook metrics`` output (prK §F.0.3 item 1, P-D3).

The files under ``tests/cli/golden/metrics/`` were captured from the CLI before
the gate moved out of ``commands/metrics.py``; any change to one byte of the text
or JSON output is a contract break for pre-commit logs and machine consumers.
Every case runs with ``--repo-root`` at the fixture tree, so labels are
repo-relative and no tmp path reaches the output.

``maintainability_index`` measures only when radon is importable. The goldens
are the radon-free output CI produces, so the test skips when radon is present.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import metrics as _metrics
from tests.cli.test_metrics import (
    _BASELINE_SOURCE,
    _CLEAN_SOURCE,
    _HIGH_CC_SOURCE,
    _WORSE_SOURCE,
    _ns,
    _write,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable

GOLDEN_DIR = Path(__file__).parent / "golden" / "metrics"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("radon") is not None,
    reason="the goldens are the radon-free CI output (maintainability_index needs radon)",
)

_GIT_TIMEOUT_S = 30

# 13 ifs: CC 14 lands in the cyclomatic_complexity warn band (see test_metrics).
_WARN_SOURCE = (
    "def f(x):\n"
    + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(13))
    + "    return -1\n"
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, timeout=_GIT_TIMEOUT_S
    )


def _text_absolute(root: Path) -> argparse.Namespace:
    target = _write(root / "tangled.py", _HIGH_CC_SOURCE)
    return _ns(paths=[str(target)], mode="absolute", repo_root=str(root))


def _text_fallback_note(root: Path) -> argparse.Namespace:
    target = _write(root / "tangled.py", _HIGH_CC_SOURCE)
    return _ns(paths=[str(target)], repo_root=str(root))


def _regression_dir(root: Path, fmt: str) -> argparse.Namespace:
    _write(root / "baseline" / "mod.py", _BASELINE_SOURCE)
    target = _write(root / "mod.py", _WORSE_SOURCE)
    return _ns(
        paths=[str(target)],
        baseline=str(root / "baseline"),
        mode="regression",
        format=fmt,
        repo_root=str(root),
    )


def _text_git_head(root: Path) -> argparse.Namespace:
    _git(root, "init", "-q")
    _write(root / "mod.py", _BASELINE_SOURCE)
    _write(root / "new.py", _CLEAN_SOURCE)
    _git(root, "add", "mod.py")
    _git(root, "commit", "-q", "-m", "baseline")
    _write(root / "mod.py", _WORSE_SOURCE)
    return _ns(
        paths=[str(root / "mod.py"), str(root / "new.py")],
        baseline="git:HEAD",
        mode="regression",
        repo_root=str(root),
    )


def _text_strict(root: Path) -> argparse.Namespace:
    target = _write(root / "warn.py", _WARN_SOURCE)
    (root / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "absolute"\n[metrics.thresholds.maintainability_index]\nfail = 0\n',
        encoding="utf-8",
    )
    return _ns(paths=[str(target)], strict=True, repo_root=str(root))


def _text_weighted_composite(root: Path) -> argparse.Namespace:
    # Default weights are 0 (composite n/a); weights pin the composite formatting.
    _write(root / "pkg" / "tangled.py", _HIGH_CC_SOURCE)
    _write(root / "pkg" / "clean.py", _CLEAN_SOURCE)
    (root / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "absolute"\n[metrics.weights]\ncyclomatic_complexity = 2.0\nwmc = 1.0\n',
        encoding="utf-8",
    )
    return _ns(paths=[str(root / "pkg")], repo_root=str(root))


def _text_skipped_unparseable(root: Path) -> argparse.Namespace:
    _write(root / "pkg" / "broken.py", "def oops(:\n    pass\n")
    _write(root / "pkg" / "clean.py", _CLEAN_SOURCE)
    return _ns(paths=[str(root / "pkg")], mode="absolute", repo_root=str(root))


#: case name -> (fixture builder, expected exit code). The name's prefix is the
#: output format and picks the golden's suffix.
CASES: dict[str, tuple[Callable[[Path], argparse.Namespace], int]] = {
    "text-absolute": (_text_absolute, 1),
    "text-fallback-note": (_text_fallback_note, 1),
    "text-regression-dir": (lambda root: _regression_dir(root, "text"), 1),
    "json-regression": (lambda root: _regression_dir(root, "json"), 1),
    "text-git-head": (_text_git_head, 1),
    "text-strict": (_text_strict, 1),
    "text-skipped-unparseable": (_text_skipped_unparseable, 0),
    "text-weighted-composite": (_text_weighted_composite, 1),
}


def golden_path(case: str) -> Path:
    """The golden file for ``case``: ``<case>.json`` for JSON cases, else ``.txt``.

    Example::

        >>> golden_path("json-regression").name
        'json-regression.json'
    """
    suffix = ".json" if case.startswith("json-") else ".txt"
    return GOLDEN_DIR / f"{case}{suffix}"


@pytest.mark.usefixtures("hermetic_git_env")
@pytest.mark.parametrize("case", sorted(CASES))
def test_metrics_output_byte_identical_to_golden(
    case: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build, expected_rc = CASES[case]

    rc = _metrics.run(build(tmp_path))

    out = capsys.readouterr().out
    assert rc == expected_rc
    assert out.encode("utf-8") == golden_path(case).read_bytes()
