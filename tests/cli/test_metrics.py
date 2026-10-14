"""Tests for ``playbook metrics`` (PR-M Track M3 — standalone static gate).

The standalone gate measures static metrics (cyclomatic complexity, MI, ...)
over Python files, optionally diffing against a baseline, and exits non-zero on
a breach (mirroring ``playbook check``). These tests pin the CLI surface:
absolute vs regression mode, ``--strict``, JSON output, and the usage-error
exit codes.

T5b cut the gate over from the retired ``grade()`` to the
:class:`~coding_agent_playbook.evaluators.rubric.Rubric` stack (one metric-backed
:class:`~coding_agent_playbook.evaluators.check.Check` per gated metric, folded
into one :class:`~coding_agent_playbook.evaluators.types.EvaluationReport`). The
verdicts asserted here — gate pass/fail, which metric breaches, the ``0/1/2``
exit codes, and the JSON ``findings`` contract — are *identical* to the
pre-cutover output (the only sanctioned diff is the multi-scope composite value,
now a mean-of-scope-ramps per check, so the tests assert the gate + breaching
metric, not an exact composite). One test pins the new ``report.checks`` →
``subresults`` internal shape directly.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import metrics as _metrics
from coding_agent_playbook.evaluators.metrics_gate import (
    CONFIG_FILENAME,
    MetricsGateDeps,
    build_rubric,
)
from tests.fakes import FakeBaselineGit

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

# A moderate function used as a regression-mode baseline. CC 2 -> normalized
# score 1.0 (at/under the RampNormalizer(good=5, bad=20) good anchor). The
# candidate variant below climbs to CC 8 (score 0.8), a *drop* in normalized
# goodness that regression mode flags - while staying above the absolute warn
# cutoff (0.5), so the same file graded all-new still passes absolute.
_BASELINE_SOURCE = """\
def classify(value):
    if value > 0:
        return "positive"
    return "non-positive"
"""

_WORSE_SOURCE = """\
def classify(value):
    if value == 0:
        return "v0"
    if value == 1:
        return "v1"
    if value == 2:
        return "v2"
    if value == 3:
        return "v3"
    if value == 4:
        return "v4"
    if value == 5:
        return "v5"
    if value == 6:
        return "v6"
    return "other"
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
        "run_tests": False,
        "test_cmd": None,
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
    """A function whose normalized CC score lands in the warn band (< warn=0.5,
    >= fail=0.25) passes by default but fails under ``--strict``.

    13 ifs => CC 14 => score (20-14)/15 = 0.4, a warn. The MI floor is relaxed via
    config so the only finding is the CC *warn*, isolating the strict behaviour
    from the (coupled) maintainability metric.
    """
    warn_source = (
        "def f(x):\n"
        + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(13))
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
# report.checks → subresults shape (the new Rubric stack)
# --------------------------------------------------------------------------- #


def test_report_has_per_check_subresults_shape(tmp_path):
    """The gate is a Rubric: one metric-backed check per gated metric, each
    carrying its per-scope ``ScopeDetail`` leaves as ``subresults``.

    Drives the command's internals (not the CLI) to assert the
    ``report.checks``/``subresults`` structure directly: the high-CC function is a
    failing ``threshold:cyclomatic_complexity`` check whose subresult flags the
    function scope as ``fail``.
    """
    from coding_agent_playbook.evaluators import MetricConfig, parse_module
    from coding_agent_playbook.evaluators.check import MeasurementSet
    from coding_agent_playbook.evaluators.metric import static_metrics
    from coding_agent_playbook.evaluators.types import EvalContext, ScopeDetail

    static = static_metrics()
    source = _HIGH_CC_SOURCE
    module = parse_module(source, "tangled.py")
    ctx = EvalContext(module=module, source=source, label="tangled.py")
    candidate = []
    for metric in static:
        if metric.available(ctx):
            candidate.extend(metric.measure(ctx))

    config = MetricConfig(mode="absolute")
    rubric = build_rubric(static, config)
    grading_ctx = EvalContext(module=parse_module("", "metrics"), source="", label="metrics")
    report = rubric.evaluate(grading_ctx, MeasurementSet(candidate, None), fail_fast=False)

    assert report.passed is False
    # One check per static metric; the gate breach lives on the CC check.
    check_ids = {c.check_id for c in report.checks}
    assert "threshold:cyclomatic_complexity" in check_ids
    cc_check = next(c for c in report.checks if c.check_id == "threshold:cyclomatic_complexity")
    assert cc_check.passed is False
    fail_leaves = [
        s for s in cc_check.subresults if isinstance(s, ScopeDetail) and s.level == "fail"
    ]
    assert fail_leaves  # the tangled function scope failed absolute


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


def test_malformed_config_exits_two(tmp_path, capsys):
    """A malformed ``.coding-agent-playbook.toml`` is a usage error (exit 2),
    not an uncaught :class:`tomllib.TOMLDecodeError` traceback."""
    target = _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        "[metrics]\nmode = \nthis is not = valid toml\n",
        encoding="utf-8",
    )
    rc = _metrics.run(_ns(paths=[str(target)], repo_root=str(tmp_path)))
    assert rc == 2
    err = capsys.readouterr().err
    assert "error" in err.lower()
    assert CONFIG_FILENAME in err


def test_invalid_config_mode_exits_two(tmp_path, capsys):
    """An invalid ``[metrics] mode`` in the repo config is a usage error (exit
    2), not an uncaught :class:`ValueError` traceback."""
    target = _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "nonsense"\n',
        encoding="utf-8",
    )
    rc = _metrics.run(_ns(paths=[str(target)], repo_root=str(tmp_path)))
    assert rc == 2
    err = capsys.readouterr().err
    assert "error" in err.lower()
    assert CONFIG_FILENAME in err


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


def test_hostile_candidates_are_skipped_with_exit_zero(tmp_path, capsys):
    """A NUL byte, a non-UTF-8 file, a file over the 1 MB cap and a parser-overflowing
    nest are each skipped with a note; the clean sibling still passes (exit 0)."""
    _write(tmp_path / "nul.py", "x = 1\0\n")
    (tmp_path / "latin1.py").write_bytes(b"x = '\xff'\n")
    _write(tmp_path / "huge.py", "#\n" * 500_001)
    _write(tmp_path / "deep.py", "-" * 200_000 + "1\n")
    _write(tmp_path / "clean.py", _CLEAN_SOURCE)

    rc = _metrics.run(_ns(paths=[str(tmp_path)], mode="absolute", repo_root=str(tmp_path)))

    assert rc == 0
    out = capsys.readouterr().out
    assert "  skipped huge.py: too large (1000002 bytes, over the 1000000-byte cap)" in out
    for label in ("nul.py", "latin1.py", "deep.py"):
        assert f"  skipped {label}: " in out
    assert "OK — 1 file(s) measured" in out


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


def test_git_baseline_outside_repo_root_treated_as_all_new(tmp_path, capsys):
    """A target *outside* ``repo_root`` must not be compared against a
    coincidental same-named file at the repo root via ``git show``.

    The repo commits a clean ``mod.py``; an unrelated, worse ``mod.py`` outside
    the repo shares the basename. With a ``git:HEAD`` baseline the outside file
    must be treated as all-new (graded absolutely), NOT diffed against the repo's
    committed ``mod.py``. Since the outside file is clean in absolute terms, the
    run passes.
    """
    import subprocess

    def _git(*cmd: str) -> None:
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)

    _git("init")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    # The repo's committed mod.py is the simple baseline (low complexity).
    _write(tmp_path / "mod.py", _BASELINE_SOURCE)
    _git("add", "mod.py")
    _git("commit", "-m", "baseline")

    # An unrelated mod.py OUTSIDE repo_root, more branchy than the baseline. If
    # the basename fallback wrongly resolved it against the repo's committed
    # mod.py, regression mode would flag it. Treated as all-new it passes.
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside = _write(outside_dir / "mod.py", _WORSE_SOURCE)
    try:
        rc = _metrics.run(
            _ns(
                paths=[str(outside)],
                baseline="git:HEAD",
                mode="regression",
                repo_root=str(tmp_path),
            )
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "regression" not in out.lower()
    finally:
        import shutil

        shutil.rmtree(outside_dir, ignore_errors=True)


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


@pytest.mark.parametrize(
    ("config", "seconds"),
    [(None, "10s"), ("[metrics]\ngit_timeout_s = 2.5\n", "2.5s")],
    ids=["default", "configured"],
)
def test_git_timeout_maps_to_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], config: str | None, seconds: str
) -> None:
    """A wedged git (lock contention, network FS) is a usage error, never a hang."""
    target = _write(tmp_path / "mod.py", _BASELINE_SOURCE)
    if config is not None:
        (tmp_path / CONFIG_FILENAME).write_text(config, encoding="utf-8")
    fake = FakeBaselineGit(timeout_on={"rev-parse"})

    def git_factory(timeout_s: float) -> FakeBaselineGit:
        fake.timeout_s = timeout_s
        return fake

    rc = _metrics.run(
        _ns(paths=[str(target)], baseline="git:HEAD", repo_root=str(tmp_path)),
        deps=MetricsGateDeps(git_factory=git_factory),
    )

    assert rc == 2
    assert f"error: git rev-parse timed out after {seconds}" in capsys.readouterr().err


def test_invalid_git_timeout_exits_two(tmp_path, capsys):
    target = _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    (tmp_path / CONFIG_FILENAME).write_text("[metrics]\ngit_timeout_s = 0\n", encoding="utf-8")

    rc = _metrics.run(_ns(paths=[str(target)], repo_root=str(tmp_path)))

    assert rc == 2
    assert "git_timeout_s must be a positive number of seconds, got 0" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# [metrics] config in .coding-agent-playbook.toml
# --------------------------------------------------------------------------- #


def test_config_threshold_override_changes_verdict(tmp_path, capsys):
    """A stricter ``[metrics]`` threshold in the repo config turns a passing file
    into a failing one (config is read; CLI flags would override it).

    The override ``fail = 0.9`` is a ``0-1`` cutoff on the normalized score; the
    moderate ``classify`` (CC 8 -> score 0.8) clears the default ``fail=0.25`` but
    falls below the stricter ``0.9`` floor.
    """
    src = _write(tmp_path / "warn.py", _WORSE_SOURCE)  # CC 8 -> normalized 0.8
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "absolute"\n[metrics.thresholds.cyclomatic_complexity]\nfail = 0.9\n',
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


# --------------------------------------------------------------------------- #
# --run-tests (execution evaluators) — PR-M Track M4
# --------------------------------------------------------------------------- #

# A tiny project whose static metrics are clean (so the static gate never breaks
# the run) and whose suite either fully passes/covers or fails.
_RUN_MOD = "def add(a, b):\n    return a + b\n"
_RUN_TEST_PASS = "from mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
_RUN_TEST_FAIL = (
    "from mod import add\n\n\n"
    "def test_ok():\n    assert add(1, 2) == 3\n\n\n"
    "def test_bad():\n    assert add(1, 2) == 99\n"
)


def _run_project(root: Path, test_source: str) -> None:
    _write(root / "mod.py", _RUN_MOD)
    _write(root / "test_mod.py", test_source)


def test_run_tests_passing_suite_exits_zero(tmp_path, capsys):
    _run_project(tmp_path, _RUN_TEST_PASS)
    rc = _metrics.run(
        _ns(paths=[str(tmp_path)], mode="absolute", run_tests=True, repo_root=str(tmp_path))
    )
    assert rc == 0
    out = capsys.readouterr().out
    # The execution evaluators contributed measurements (visible in JSON below);
    # here we just assert the suite passed overall.
    assert "FAIL" not in out


def test_run_tests_failing_suite_exits_one(tmp_path, capsys):
    _run_project(tmp_path, _RUN_TEST_FAIL)
    rc = _metrics.run(
        _ns(paths=[str(tmp_path)], mode="absolute", run_tests=True, repo_root=str(tmp_path))
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "test_pass_rate" in out


def test_run_tests_emits_execution_findings_in_json(tmp_path, capsys):
    _run_project(tmp_path, _RUN_TEST_PASS)
    rc = _metrics.run(
        _ns(
            paths=[str(tmp_path)],
            mode="absolute",
            run_tests=True,
            format="json",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    evaluators = {f["evaluator"] for f in payload["findings"]}
    assert "test_pass_rate" in evaluators
    assert "coverage" in evaluators


def test_without_run_tests_no_execution_findings(tmp_path, capsys):
    """Default behaviour (no --run-tests) is static-only: no execution findings."""
    _run_project(tmp_path, _RUN_TEST_PASS)
    rc = _metrics.run(
        _ns(paths=[str(tmp_path)], mode="absolute", format="json", repo_root=str(tmp_path))
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    evaluators = {f["evaluator"] for f in payload["findings"]}
    assert "test_pass_rate" not in evaluators
    assert "coverage" not in evaluators


def test_run_tests_bad_test_cmd_exits_two(tmp_path, capsys):
    """A --test-cmd that cannot be launched is a usage error (exit 2)."""
    _run_project(tmp_path, _RUN_TEST_PASS)
    rc = _metrics.run(
        _ns(
            paths=[str(tmp_path)],
            mode="absolute",
            run_tests=True,
            test_cmd="definitely-not-a-real-program-xyz --version",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def test_run_tests_regression_coverage_drop_fails(tmp_path, capsys):
    """With --run-tests + a dir baseline, dropping coverage fails regression."""
    baseline_dir = tmp_path / "baseline"
    # Baseline fully covers a two-branch module.
    _write(baseline_dir / "mod.py", "def f(x):\n    if x:\n        return 1\n    return 0\n")
    _write(
        baseline_dir / "test_mod.py",
        "from mod import f\n\n\ndef test_f():\n    assert f(1) == 1\n    assert f(0) == 0\n",
    )
    # Candidate only covers one branch -> coverage drops.
    cand = tmp_path / "cand"
    _write(cand / "mod.py", "def f(x):\n    if x:\n        return 1\n    return 0\n")
    _write(cand / "test_mod.py", "from mod import f\n\n\ndef test_f():\n    assert f(1) == 1\n")
    rc = _metrics.run(
        _ns(
            paths=[str(cand)],
            baseline=str(baseline_dir),
            mode="regression",
            run_tests=True,
            repo_root=str(cand),
        )
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "coverage" in out


def test_run_tests_config_run_tests_true_enables_execution(tmp_path, capsys):
    """``run_tests = true`` in config enables execution without the CLI flag."""
    _run_project(tmp_path, _RUN_TEST_PASS)
    (tmp_path / ".coding-agent-playbook.toml").write_text(
        '[metrics]\nmode = "absolute"\nrun_tests = true\n',
        encoding="utf-8",
    )
    rc = _metrics.run(_ns(paths=[str(tmp_path)], format="json", repo_root=str(tmp_path)))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    evaluators = {f["evaluator"] for f in payload["findings"]}
    assert "test_pass_rate" in evaluators


def test_run_tests_custom_test_cmd_is_used(tmp_path, capsys):
    """``--test-cmd`` (shlex-split) overrides the default pytest invocation."""
    _run_project(tmp_path, _RUN_TEST_PASS)
    cmd = (
        "python -m pytest --junitxml=junit.xml "
        "--cov --cov-report=xml:coverage.xml -o addopts= -p no:cacheprovider -q"
    )
    rc = _metrics.run(
        _ns(
            paths=[str(tmp_path)],
            mode="absolute",
            run_tests=True,
            test_cmd=cmd,
            format="json",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "test_pass_rate" in {f["evaluator"] for f in payload["findings"]}


def test_run_tests_empty_test_cmd_after_shlex_exits_two(tmp_path, capsys):
    """A ``--test-cmd`` that shlex-splits to nothing is a usage error."""
    _run_project(tmp_path, _RUN_TEST_PASS)
    rc = _metrics.run(
        _ns(
            paths=[str(tmp_path)],
            mode="absolute",
            run_tests=True,
            test_cmd="   ",
            repo_root=str(tmp_path),
        )
    )
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def test_run_tests_git_worktree_baseline_detects_coverage_drop(tmp_path, capsys):
    """``--run-tests --baseline git:HEAD`` materialises the ref in a temp git
    worktree, runs its suite, and flags a coverage drop in the working tree."""
    import subprocess

    def _git(*cmd: str) -> None:
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)

    _git("init")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    # Committed baseline: two branches, fully covered.
    _write(tmp_path / "mod.py", "def f(x):\n    if x:\n        return 1\n    return 0\n")
    _write(
        tmp_path / "test_mod.py",
        "from mod import f\n\n\ndef test_f():\n    assert f(1) == 1\n    assert f(0) == 0\n",
    )
    _git("add", "mod.py", "test_mod.py")
    _git("commit", "-m", "baseline full coverage")

    # Working tree: drop one branch's coverage.
    _write(tmp_path / "test_mod.py", "from mod import f\n\n\ndef test_f():\n    assert f(1) == 1\n")
    rc = _metrics.run(
        _ns(
            paths=[str(tmp_path / "mod.py"), str(tmp_path / "test_mod.py")],
            baseline="git:HEAD",
            mode="regression",
            run_tests=True,
            repo_root=str(tmp_path),
        )
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "coverage" in out
    # The temporary worktree must be cleaned up (no leftover under .git/worktrees
    # pointing at a live dir, and no baseline-worktree dir left behind in tmp).
    leftovers = list(tmp_path.glob("**/baseline-worktree"))
    assert leftovers == []
