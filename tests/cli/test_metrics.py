"""Tests for ``playbook metrics`` (PR-M Track M3 — standalone static gate).

The standalone gate measures static metrics (cyclomatic complexity, MI, ...)
over Python files, optionally diffing against a baseline, and exits non-zero on
a breach (mirroring ``playbook check``). These tests pin the CLI surface:
absolute vs regression mode, ``--strict``, JSON output, and the usage-error
exit codes.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import metrics as _metrics

if TYPE_CHECKING:
    from pathlib import Path

# A function with a long if-chain: cyclomatic complexity 23, well over the fail
# bound (20), so absolute mode must flag cyclomatic_complexity as ``fail``.
_HIGH_CC_SOURCE = (
    "def tangled(x):\n"
    + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(22))
    + "    return -1\n"
)

# A trivial, highly maintainable function: low CC, high MI.
_CLEAN_SOURCE = """\
def add(a, b):
    \"\"\"Return the sum of two numbers.\"\"\"
    return a + b
"""

# A moderate function used as a regression-mode baseline. Its candidate variant
# below adds branches (higher CC) without crossing the absolute fail bound, so
# only regression mode flags it.
_BASELINE_SOURCE = """\
def classify(value):
    if value > 0:
        return "positive"
    return "non-positive"
"""

_WORSE_SOURCE = """\
def classify(value):
    if value > 0:
        if value > 10:
            return "big"
        return "positive"
    if value < 0:
        if value < -10:
            return "very-negative"
        return "negative"
    return "zero"
"""

# An improvement: fewer branches than the baseline.
_IMPROVED_SOURCE = """\
def classify(value):
    return "positive" if value > 0 else "non-positive"
"""


def _ns(**kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "paths": [],
        "baseline": None,
        "mode": None,
        "strict": False,
        "format": "text",
        "repo_root": None,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Absolute mode
# --------------------------------------------------------------------------- #


def test_absolute_mode_flags_high_complexity_file(tmp_path, capsys):
    target = _write(tmp_path / "tangled.py", _HIGH_CC_SOURCE)
    rc = _metrics.run(_ns(paths=[str(target)], mode="absolute"))
    assert rc == 1
    out = capsys.readouterr().out
    assert "cyclomatic_complexity" in out
    assert "fail" in out.lower()


def test_absolute_mode_clean_file_passes(tmp_path, capsys):
    target = _write(tmp_path / "clean.py", _CLEAN_SOURCE)
    rc = _metrics.run(_ns(paths=[str(target)], mode="absolute"))
    assert rc == 0


# --------------------------------------------------------------------------- #
# Regression mode (--baseline <dir>)
# --------------------------------------------------------------------------- #


def test_regression_unchanged_file_passes(tmp_path, capsys):
    baseline_dir = tmp_path / "baseline"
    cand = _write(tmp_path / "mod.py", _BASELINE_SOURCE)
    _write(baseline_dir / "mod.py", _BASELINE_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(cand)],
            baseline=str(baseline_dir),
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 0


def test_regression_worsened_file_fails(tmp_path, capsys):
    baseline_dir = tmp_path / "baseline"
    cand = _write(tmp_path / "mod.py", _WORSE_SOURCE)
    _write(baseline_dir / "mod.py", _BASELINE_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(cand)],
            baseline=str(baseline_dir),
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "regression" in out.lower()


def test_regression_improved_file_passes(tmp_path, capsys):
    baseline_dir = tmp_path / "baseline"
    cand = _write(tmp_path / "mod.py", _IMPROVED_SOURCE)
    _write(baseline_dir / "mod.py", _BASELINE_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(cand)],
            baseline=str(baseline_dir),
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 0


def test_regression_new_file_not_in_baseline_uses_absolute(tmp_path, capsys):
    """A file absent from the baseline dir is all-new: graded absolutely.

    A clean new file passes; a tangled new file fails on the absolute bound.
    """
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    clean = _write(tmp_path / "new_clean.py", _CLEAN_SOURCE)
    rc_clean = _metrics.run(
        _ns(
            paths=[str(clean)],
            baseline=str(baseline_dir),
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc_clean == 0

    tangled = _write(tmp_path / "new_tangled.py", _HIGH_CC_SOURCE)
    rc_tangled = _metrics.run(
        _ns(
            paths=[str(tangled)],
            baseline=str(baseline_dir),
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc_tangled == 1


# --------------------------------------------------------------------------- #
# --strict
# --------------------------------------------------------------------------- #


def test_strict_promotes_warning_to_failure(tmp_path, capsys):
    """A function whose CC is in the warn band (10..20) passes by default but
    fails under ``--strict``.

    The MI floor is relaxed via config so the only finding is the CC *warn*,
    isolating the strict behaviour from the (coupled) maintainability metric.
    """
    warn_source = (
        "def f(x):\n"
        + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(11))
        + "    return -1\n"
    )
    target = _write(tmp_path / "warn.py", warn_source)
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "absolute"\n[metrics.thresholds.maintainability_index]\nfail = 0\n',
        encoding="utf-8",
    )

    rc_default = _metrics.run(_ns(paths=[str(target)], repo_root=str(tmp_path)))
    assert rc_default == 0

    rc_strict = _metrics.run(_ns(paths=[str(target)], strict=True, repo_root=str(tmp_path)))
    assert rc_strict == 1


# --------------------------------------------------------------------------- #
# JSON output
# --------------------------------------------------------------------------- #


def test_json_format_emits_parseable_report(tmp_path, capsys):
    target = _write(tmp_path / "tangled.py", _HIGH_CC_SOURCE)
    rc = _metrics.run(_ns(paths=[str(target)], mode="absolute", format="json"))
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    assert payload["fail_count"] >= 1
    assert "composite" in payload
    assert isinstance(payload["findings"], list)
    first = payload["findings"][0]
    for key in ("evaluator", "scope_key", "value", "level", "kind"):
        assert key in first


def test_json_format_clean_file_passes(tmp_path, capsys):
    target = _write(tmp_path / "clean.py", _CLEAN_SOURCE)
    rc = _metrics.run(_ns(paths=[str(target)], mode="absolute", format="json"))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True


# --------------------------------------------------------------------------- #
# Directory recursion + default path
# --------------------------------------------------------------------------- #


def test_directory_path_recurses_and_skips_dotdirs(tmp_path, capsys):
    pkg = tmp_path / "pkg"
    _write(pkg / "ok.py", _CLEAN_SOURCE)
    _write(pkg / ".hidden" / "ignored.py", _HIGH_CC_SOURCE)
    rc = _metrics.run(_ns(paths=[str(pkg)], mode="absolute"))
    # Only the clean file is discovered; the dotdir is skipped -> pass.
    assert rc == 0


def test_default_path_uses_src_dir(tmp_path, capsys):
    src = tmp_path / "src"
    _write(src / "clean.py", _CLEAN_SOURCE)
    rc = _metrics.run(_ns(paths=[], mode="absolute", repo_root=str(tmp_path)))
    assert rc == 0


# --------------------------------------------------------------------------- #
# Usage errors (exit 2)
# --------------------------------------------------------------------------- #


def test_missing_path_exits_two(tmp_path, capsys):
    rc = _metrics.run(_ns(paths=[str(tmp_path / "does-not-exist.py")], mode="absolute"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_bad_baseline_dir_exits_two(tmp_path, capsys):
    target = _write(tmp_path / "mod.py", _BASELINE_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(target)],
            baseline=str(tmp_path / "no-such-baseline-dir"),
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_bad_baseline_git_ref_exits_two(tmp_path, capsys):
    """A ``git:`` baseline pointing at a non-existent ref (or non-git dir) is a
    usage error."""
    target = _write(tmp_path / "mod.py", _BASELINE_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(target)],
            baseline="git:definitely-not-a-real-ref-xyz",
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "error" in err.lower()


# --------------------------------------------------------------------------- #
# Unparseable file handled gracefully
# --------------------------------------------------------------------------- #


def test_unparseable_file_is_skipped_not_crashed(tmp_path, capsys):
    """A syntactically-broken file must not crash the run; it is reported as a
    skip and a sibling clean file is still measured (pass)."""
    _write(tmp_path / "broken.py", "def oops(:\n    pass\n")
    _write(tmp_path / "clean.py", _CLEAN_SOURCE)
    rc = _metrics.run(_ns(paths=[str(tmp_path)], mode="absolute"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "broken.py" in out
    assert "skip" in out.lower()


# --------------------------------------------------------------------------- #
# git: baseline (happy path)
# --------------------------------------------------------------------------- #


def test_git_baseline_detects_regression(tmp_path, capsys):
    """``--baseline git:HEAD`` reads the committed version of each file via
    ``git show`` and compares the working-tree candidate against it."""
    import subprocess

    def _git(*cmd: str) -> None:
        subprocess.run(
            ["git", *cmd],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    _git("init")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    rel = "mod.py"
    _write(tmp_path / rel, _BASELINE_SOURCE)
    _git("add", rel)
    _git("commit", "-m", "baseline")
    # Worsen the working tree.
    _write(tmp_path / rel, _WORSE_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(tmp_path / rel)],
            baseline="git:HEAD",
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "regression" in out.lower()


def test_git_baseline_new_file_treated_as_all_new(tmp_path, capsys):
    """A file not present in the git ref is all-new: graded absolutely. A clean
    new file passes."""
    import subprocess

    def _git(*cmd: str) -> None:
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)

    _git("init")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    _write(tmp_path / "seed.py", _CLEAN_SOURCE)
    _git("add", "seed.py")
    _git("commit", "-m", "seed")
    # A brand-new (uncommitted) clean file.
    new = _write(tmp_path / "fresh.py", _CLEAN_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(new)],
            baseline="git:HEAD",
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 0


# --------------------------------------------------------------------------- #
# [metrics] config in .coding-agent-playbook.toml
# --------------------------------------------------------------------------- #


def test_config_threshold_override_changes_verdict(tmp_path, capsys):
    """A stricter ``[metrics]`` threshold in the repo config turns a passing file
    into a failing one (config is read; CLI flags would override it)."""
    src = _write(tmp_path / "warn.py", _CLEAN_SOURCE)
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "absolute"\n[metrics.thresholds.cyclomatic_complexity]\nfail = 1\n',
        encoding="utf-8",
    )
    rc = _metrics.run(_ns(paths=[str(src)], repo_root=str(tmp_path)))
    assert rc == 1


def test_no_baseline_regression_falls_back_to_absolute_with_note(tmp_path, capsys):
    """The default mode is ``regression``; with no ``--baseline`` the gate
    degrades to absolute and prints an explanatory note."""
    target = _write(tmp_path / "tangled.py", _HIGH_CC_SOURCE)
    rc = _metrics.run(_ns(paths=[str(target)], repo_root=str(tmp_path)))
    assert rc == 1
    out = capsys.readouterr().out
    assert "falls back to 'absolute'" in out


def test_bad_format_exits_two(tmp_path, capsys):
    target = _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    rc = _metrics.run(_ns(paths=[str(target)], format="xml"))
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def test_bad_mode_exits_two(tmp_path, capsys):
    target = _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    rc = _metrics.run(_ns(paths=[str(target)], mode="sideways"))
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def test_unparseable_baseline_file_is_dropped(tmp_path, capsys):
    """A baseline file that does not parse contributes no measurements, so the
    candidate's scopes are graded as all-new (absolute). A clean candidate
    passes."""
    baseline_dir = tmp_path / "baseline"
    _write(baseline_dir / "mod.py", "def broken(:\n    pass\n")
    cand = _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    rc = _metrics.run(
        _ns(
            paths=[str(cand)],
            baseline=str(baseline_dir),
            mode="regression",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 0


def test_explicit_non_python_file_path_is_ignored(tmp_path, capsys):
    """An explicit non-``.py`` file is silently skipped (no targets => pass)."""
    note = _write(tmp_path / "README.txt", "not python\n")
    rc = _metrics.run(_ns(paths=[str(note)], mode="absolute"))
    assert rc == 0


def test_config_fail_on_breach_false_returns_zero(tmp_path, capsys):
    """``fail_on_breach = false`` reports findings but never sets a non-zero
    exit."""
    target = _write(tmp_path / "tangled.py", _HIGH_CC_SOURCE)
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "absolute"\nfail_on_breach = false\n',
        encoding="utf-8",
    )
    rc = _metrics.run(_ns(paths=[str(target)], repo_root=str(tmp_path)))
    assert rc == 0
