"""``playbook metrics --run-tests`` with ``diff_coverage`` on a tiny real project (prK §F.1.1).

Like the existing ``--run-tests`` cases in ``test_metrics.py``, the inner
pytest really runs (with this environment's pytest-cov) in a project under
``tmp_path``; the git repository is real and isolated by ``hermetic_git_env``.
:class:`SpyProjectFactory` wraps ``ProjectHandle.create`` to count the suite runs
and record what each handle was built with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import metrics as _metrics
from coding_agent_playbook.evaluators.execution.project import ProjectHandle
from coding_agent_playbook.evaluators.metrics_gate import MetricsGateDeps

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    import pytest

_MOD = "def add(a, b):\n    return a + b\n"
_MUL = "\n\ndef mul(a, b):\n    return a * b\n"
_TEST = "from pkg.mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


@dataclass
class SpyProjectFactory:
    """``ProjectHandle.create`` that records ``(diff_base, cov_sources)`` per handle it builds."""

    built: list[tuple[str | None, tuple[str, ...]]] = field(default_factory=list)

    def __call__(
        self,
        root: Path,
        report_dir: Path,
        test_cmd: list[str] | None = None,
        *,
        diff_base: str | None = None,
        timeout_s: float | None = None,
        cov_sources: Sequence[str] = (),
    ) -> ProjectHandle:
        self.built.append((diff_base, tuple(cov_sources)))
        return ProjectHandle.create(
            root,
            report_dir,
            test_cmd,
            diff_base=diff_base,
            timeout_s=timeout_s,
            cov_sources=cov_sources,
        )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _src_layout_project(root: Path, real_git: Callable[..., str]) -> None:
    """A committed src-layout package whose one test covers ``add``."""
    _write(root / "pytest.ini", "[pytest]\npythonpath = src\n")
    _write(root / "src" / "pkg" / "__init__.py", "")
    _write(root / "src" / "pkg" / "mod.py", _MOD)
    _write(root / "tests" / "test_mod.py", _TEST)
    real_git("init", "-q", cwd=root)
    real_git("add", "-A", cwd=root)
    real_git("commit", "-q", "-m", "base", cwd=root)


def _cli(root: Path, *argv: str, deps: MetricsGateDeps) -> int:
    args = build_parser().parse_args(["metrics", *argv, "--repo-root", str(root)])
    return _metrics.run(args, deps=deps)


def test_select_diff_coverage_runs_suite_once_with_git_baseline(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    """``mul`` is untested and ``extra.py`` never imported: 1 of 4 changed lines ran."""
    _src_layout_project(tmp_path, real_git)
    _write(tmp_path / "src" / "pkg" / "mod.py", _MOD + _MUL)  # lines 5-6 executable
    _write(tmp_path / "src" / "pkg" / "extra.py", "def f():\n    return 1\n")  # untracked
    _write(tmp_path / "tests" / "test_more.py", "def test_nothing():\n    pass\n")  # not scored
    spy = SpyProjectFactory()

    code = _cli(
        tmp_path,
        "--run-tests",
        "--select",
        "diff_coverage",
        "--baseline",
        "git:HEAD",
        "--format",
        "json",
        deps=MetricsGateDeps(project_factory=spy),
    )

    findings = json.loads(capsys.readouterr().out)["findings"]
    assert [(f["evaluator"], f["value"], f["kind"], f["level"]) for f in findings] == [
        ("diff_coverage", 25.0, "new", "fail")
    ]
    assert code == 1
    # One suite run, in coverage source mode, diffed against the baseline ref.
    assert spy.built == [("HEAD", ("src",))]


def test_select_testing_without_git_baseline_diff_coverage_vacuous(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    """No diff base: ``diff_coverage`` measures nothing and the command keeps a bare ``--cov``."""
    _src_layout_project(tmp_path, real_git)
    spy = SpyProjectFactory()

    code = _cli(
        tmp_path,
        "--run-tests",
        "--select",
        "testing",
        "--mode",
        "absolute",
        "--format",
        "json",
        deps=MetricsGateDeps(project_factory=spy),
    )

    findings = json.loads(capsys.readouterr().out)["findings"]
    assert code == 0
    assert {f["evaluator"] for f in findings} == {"test_pass_rate", "coverage"}
    assert {f["scope_key"] for f in findings if f["evaluator"] == "coverage"} >= {"src/pkg/mod.py"}
    assert spy.built == [(None, ())]
