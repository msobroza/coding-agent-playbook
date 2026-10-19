"""``playbook metrics`` selection, ``--changed``, snapshots and ``--no-run-tests`` (prK §F.0.3 items 2-6, 8).

Every case parses real argv with :func:`build_parser` and runs the command; the
repositories are real git repos under ``hermetic_git_env``. No suite ever runs:
the run-tests cases inject ``FakeProjectFactory`` and assert it was never asked.
The default output stays byte-identical (``test_metrics_golden.py``).
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import metrics as _metrics
from coding_agent_playbook.evaluators.metrics_gate import CONFIG_FILENAME, MetricsGateDeps
from tests.cli.test_metrics import _BASELINE_SOURCE, _CLEAN_SOURCE, _HIGH_CC_SOURCE, _WORSE_SOURCE
from tests.fakes import FakeProjectFactory, FakeRuffRunner, ruff_row

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.usefixtures("hermetic_git_env")

_GIT_TIMEOUT_S = 30


def _cli(*argv: str, deps: MetricsGateDeps | None = None) -> int:
    return _metrics.run(build_parser().parse_args(["metrics", *argv]), deps=deps)


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, timeout=_GIT_TIMEOUT_S
    )
    return done.stdout.strip()


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed ``a.py`` (clean) and ``tangled.py`` (fails absolute), nothing else."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _write(root / "a.py", _BASELINE_SOURCE)
    _write(root / "tangled.py", _HIGH_CC_SOURCE)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _files(out: str) -> set[str]:
    return {finding["scope_key"].split("::")[0] for finding in json.loads(out)["findings"]}


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_select_family_limits_findings(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = str(repo)
    tangled = str(repo / "tangled.py")

    assert _cli(tangled, "--mode", "absolute", "--select", "quality", "--repo-root", root) == 1
    ignored = _cli(
        tangled, "--mode", "absolute", "--ignore", "cyclomatic_complexity", "--repo-root", root
    )

    assert ignored == 0
    assert "cyclomatic_complexity" not in capsys.readouterr().out.split("=== Metrics ===")[-1]


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (["--select", "quality,complexity"], "error: unknown metric or family 'complexity'"),
        (["--extend-select", "coverage"], "error: execution metric(s) coverage selected without"),
        (["--select", "testing"], "selected without --run-tests"),
    ],
    ids=["unknown", "execution-by-name", "execution-by-family"],
)
def test_bad_selection_exits_two(
    repo: Path, capsys: pytest.CaptureFixture[str], flags: list[str], message: str
) -> None:
    assert _cli(str(repo / "a.py"), *flags, "--repo-root", str(repo)) == 2
    assert message in capsys.readouterr().err


def test_no_run_tests_overrides_config_run_tests_true(repo: Path) -> None:
    """The pre-commit twins pass ``--no-run-tests``: static only, whatever ``[metrics]`` says."""
    (repo / CONFIG_FILENAME).write_text(
        '[metrics]\nrun_tests = true\nselect = ["quality", "testing"]\n', encoding="utf-8"
    )
    factory = FakeProjectFactory()
    deps = MetricsGateDeps(project_factory=factory)

    rc = _cli(str(repo / "a.py"), "--no-run-tests", "--repo-root", str(repo), deps=deps)
    _cli(str(repo / "a.py"), "--repo-root", str(repo), deps=deps)

    assert rc == 0
    assert [root for root, _ in factory.calls] == [repo]  # only the run without the flag


# --------------------------------------------------------------------------- #
# --changed and [metrics] exclude
# --------------------------------------------------------------------------- #


def test_changed_restricts_to_diff_and_untracked(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(repo / "a.py", _WORSE_SOURCE)
    _write(repo / "fresh.py", _CLEAN_SOURCE)
    common = ["--baseline", "git:HEAD", "--format", "json", "--repo-root", str(repo)]

    rc = _cli("--changed", "--mode", "absolute", *common)

    # tangled.py fails absolute but is unchanged, so it is never measured.
    assert rc == 0
    assert _files(capsys.readouterr().out) == {"a.py", "fresh.py"}


def test_changed_intersects_explicit_paths(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo / "a.py", _WORSE_SOURCE)
    _write(repo / "fresh.py", _CLEAN_SOURCE)

    rc = _cli(
        str(repo / "fresh.py"),
        str(repo / "tangled.py"),
        "--changed",
        "--baseline",
        "git:HEAD",
        "--format",
        "json",
        "--repo-root",
        str(repo),
    )

    assert rc == 0
    assert _files(capsys.readouterr().out) == {"fresh.py"}


@pytest.mark.parametrize("baseline", [[], ["--baseline", "json:snap.json"]], ids=["none", "json"])
def test_changed_without_git_baseline_exits_two(
    repo: Path, capsys: pytest.CaptureFixture[str], baseline: list[str]
) -> None:
    assert _cli("--changed", *baseline, "--repo-root", str(repo)) == 2
    assert "error: --changed needs a git: baseline" in capsys.readouterr().err


def test_exclude_skips_eval_fixture_setup_even_when_passed_explicitly(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    needle = _write(repo / "eval_tasks" / "t1" / "setup" / "needle.py", _HIGH_CC_SOURCE)

    rc = _cli(str(needle), "--mode", "absolute", "--repo-root", str(repo))

    assert rc == 0
    assert "OK — 0 file(s) measured" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# --emit-measurements and --baseline json:
# --------------------------------------------------------------------------- #


def test_emit_measurements_then_json_baseline_round_trip(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = tmp_path / "snap.json"  # outside the repo: the worktree stays clean
    target = str(repo / "a.py")

    assert _cli(target, "--emit-measurements", str(snapshot), "--repo-root", str(repo)) == 0
    document = json.loads(snapshot.read_text(encoding="utf-8"))
    _write(repo / "a.py", _WORSE_SOURCE)
    capsys.readouterr()
    rc = _cli(target, "--baseline", f"json:{snapshot}", "--repo-root", str(repo))

    assert document["schema"] == 1
    assert document["tree"] == _git(repo, "rev-parse", "HEAD^{tree}")
    assert {"evaluator", "scope_key", "value"} == set(document["measurements"][0])
    assert rc == 1
    assert "(regression; baseline=" in capsys.readouterr().out


def test_emit_measurements_tree_is_null_for_a_dirty_worktree(repo: Path, tmp_path: Path) -> None:
    _write(repo / "a.py", _WORSE_SOURCE)
    snapshot = tmp_path / "snap.json"

    _cli(str(repo / "a.py"), "--emit-measurements", str(snapshot), "--repo-root", str(repo))

    assert json.loads(snapshot.read_text(encoding="utf-8"))["tree"] is None


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('{"schema": 2, "tree": null, "measurements": []}', "schema 2 is not supported"),
        ("not json", "not JSON"),
        (None, "cannot read measurement snapshot"),
    ],
    ids=["schema", "not-json", "missing"],
)
def test_json_baseline_bad_schema_exits_two(
    repo: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    content: str | None,
    message: str,
) -> None:
    snapshot = tmp_path / "snap.json"
    if content is not None:
        snapshot.write_text(content, encoding="utf-8")

    rc = _cli(str(repo / "a.py"), "--baseline", f"json:{snapshot}", "--repo-root", str(repo))

    assert rc == 2
    assert message in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# ruff_violations (prK §F.2.1): opt-in, ruff found on PATH, both sides on stdin
# --------------------------------------------------------------------------- #

_STUB_RUFF = "/stub/bin/ruff"


def _ruff_deps(runner: FakeRuffRunner) -> MetricsGateDeps:
    """``ruff`` "on PATH" is the stub path; its calls go to ``runner``, never a process."""
    return MetricsGateDeps(
        which=lambda name: _STUB_RUFF if name == "ruff" else None, tool_runner=runner
    )


def test_extend_select_ruff_violations_with_stub_ruff(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    grown = _BASELINE_SOURCE + "\n\ndef extra():\n    return 1\n"
    _write(repo / "a.py", grown)
    runner = FakeRuffRunner(answers={grown: [ruff_row("D103", 7, "Missing docstring")]})
    argv = ["--baseline", "git:HEAD", "--extend-select", "ruff_violations", "--format", "json"]

    rc = _cli(str(repo / "a.py"), *argv, "--repo-root", str(repo), deps=_ruff_deps(runner))

    findings = json.loads(capsys.readouterr().out)["findings"]
    ruff = {(f["scope_key"], f["level"]) for f in findings if f["evaluator"] == "ruff_violations"}
    assert rc == 1
    assert ruff == {("a.py::ruff:docstrings", "fail"), ("a.py::ruff:quality", "ok")}
    assert sorted(stdin for _, stdin, _, _ in runner.calls) == sorted([_BASELINE_SOURCE, grown])
    assert {(argv[0], cwd) for argv, _, cwd, _ in runner.calls} == {(_STUB_RUFF, repo)}


def test_ruff_violations_absent_from_default_output(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRuffRunner()

    rc = _cli(
        str(repo / "a.py"), "--format", "json", "--repo-root", str(repo), deps=_ruff_deps(runner)
    )

    evaluators = {f["evaluator"] for f in json.loads(capsys.readouterr().out)["findings"]}
    assert (rc, runner.calls) == (0, [])
    assert evaluators.isdisjoint({"ruff_violations", "file_sloc", "docstring_example"})
