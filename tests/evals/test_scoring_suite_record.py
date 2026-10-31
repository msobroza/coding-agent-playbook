"""Regression tests: the scoring suite's result is pytest's own, not what agent code wrote.

The agent's tree is the suite's cwd, so a planted ``pytest.py`` ran in place of
pytest, a ``conftest.py`` could rewrite the junit report (whose path argv names)
or the exit status, and ``pytest.exit()`` left a partial report that read as all
passed. Eval scoring now runs ``python -P`` with an engine plugin that records the
session (:mod:`coding_agent_playbook.grading.execution_metrics.suite_record_plugin`),
and a session that disagrees with its reports gives no result.
"""

from __future__ import annotations

import textwrap
from contextlib import ExitStack
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evals.run.scoring_suite import open_suite_handle
from tests.evals.test_harness_runner import (
    _REFACTORED,
    _TEST_OK,
    _check,
    _run_suite_green,
)

if TYPE_CHECKING:
    from pathlib import Path

_FAILING_TEST = "def test_new():\n    assert False\n"

#: A stand-in for pytest: it writes an all-pass junit report and a full coverage
#: report where argv says, and exits 0, whatever the tests do.
_FAKE_PYTEST = textwrap.dedent(
    """\
    import sys

    args = sys.argv[1:]
    junit = next(a.split("=", 1)[1] for a in args if a.startswith("--junitxml="))
    cov = next(a.split(":", 1)[1] for a in args if a.startswith("--cov-report=xml:"))
    with open(junit, "w") as fh:
        fh.write('<testsuite tests="1"><testcase name="t"/></testsuite>')
    with open(cov, "w") as fh:
        fh.write('<coverage line-rate="1"><packages/></coverage>')
    sys.exit(0)
    """
)

#: Rewrites the junit report as two passes once pytest wrote it (``{when}`` picks the hook).
_REWRITE_JUNIT = textwrap.dedent(
    """\
    import os
    import pytest

    _PASSES = '<testsuite tests="2"><testcase name="a"/><testcase name="b"/></testsuite>'


    def _rewrite(config):
        with open(config.option.xmlpath, "w") as fh:
            fh.write(_PASSES)
    """
)


def _gate_detail(files: dict[str, str], tmp_path: Path) -> tuple[bool, str, bool]:
    """``(tests_pass passed, its detail, trial passed)`` for an agent writing ``files``."""
    result = _run_suite_green(tmp_path, files)
    check = _check(result.report, "threshold:test_pass_rate")
    return check.passed, check.detail, result.passed


@pytest.mark.parametrize(
    "planted",
    [
        {"pytest.py": _FAKE_PYTEST},
        {"pytest/__init__.py": "", "pytest/__main__.py": _FAKE_PYTEST},
    ],
    ids=["module", "package"],
)
def test_a_planted_pytest_cannot_fake_the_scoring_suite(
    tmp_path: Path, planted: dict[str, str]
) -> None:
    """Regression: ``python -m pytest`` in the tree ran the agent's ``pytest`` before the real one."""
    files = {"mod.py": _REFACTORED, "test_new.py": _FAILING_TEST, **planted}

    passed, detail, trial = _gate_detail(files, tmp_path)

    # The real pytest ran and measured the failing test: a graded failure, not "no result".
    assert (passed, trial) == (False, False)
    assert "gave no result" not in detail


def test_a_conftest_that_rewrites_the_junit_report_fails_tests_pass(tmp_path: Path) -> None:
    """Regression: a ``conftest.py`` rewrote the report argv names, and a failing suite read as green."""
    conftest = _REWRITE_JUNIT + (
        "\n\n@pytest.hookimpl(trylast=True)\ndef pytest_unconfigure(config):\n    _rewrite(config)\n"
    )
    files = {"mod.py": _REFACTORED, "test_new.py": _FAILING_TEST, "conftest.py": conftest}

    passed, detail, trial = _gate_detail(files, tmp_path)

    assert (passed, trial) == (False, False)
    assert detail == "the test suite gave no result: its junit report hides 1 failed test(s)"


@pytest.mark.parametrize(
    "ending",
    [
        "    session.exitstatus = 0\n",
        "    os._exit(0)\n",
    ],
    ids=["exitstatus-0", "os-exit-0"],
)
def test_a_conftest_that_also_forges_the_exit_status_fails_tests_pass(
    tmp_path: Path, ending: str
) -> None:
    """Regression: the rewritten report plus exit 0 matched every check scoring made."""
    conftest = _REWRITE_JUNIT + (
        "\n\n@pytest.hookimpl(trylast=True)\ndef pytest_sessionfinish(session):\n"
        "    _rewrite(session.config)\n" + ending
    )
    files = {"mod.py": _REFACTORED, "test_new.py": _FAILING_TEST, "conftest.py": conftest}

    passed, detail, trial = _gate_detail(files, tmp_path)

    assert (passed, trial) == (False, False)
    assert detail == "the test suite gave no result: it exited 0, but its pytest session ended 1"


_STOPS_IN_A_TEST = textwrap.dedent(
    """\
    import pytest


    def test_ok():
        pass


    def test_stop():
        pytest.exit("stop"{returncode})
    """
)


@pytest.mark.parametrize("returncode", ["", ", returncode=0"], ids=["exit-2", "exit-0"])
def test_a_suite_stopped_by_pytest_exit_fails_tests_pass(tmp_path: Path, returncode: str) -> None:
    """Regression: ``pytest.exit()`` mid-run left a partial report of passes that scored 1.0."""
    files = {
        "mod.py": _REFACTORED,
        "test_aa.py": _STOPS_IN_A_TEST.format(returncode=returncode),
        "test_zz.py": _FAILING_TEST,
    }

    passed, detail, trial = _gate_detail(files, tmp_path)

    assert (passed, trial) == (False, False)
    assert detail == "the test suite gave no result: it stopped after 1 of 4 tests"


def test_a_suite_stopped_during_collection_fails_tests_pass(tmp_path: Path) -> None:
    """Regression: ``pytest.exit(returncode=0)`` while collecting left an empty, all-passing report."""
    conftest = (
        "import pytest\n\n\ndef pytest_collection_modifyitems(items):\n"
        "    pytest.exit('x', returncode=0)\n"
    )
    files = {"mod.py": _REFACTORED, "test_new.py": _FAILING_TEST, "conftest.py": conftest}

    passed, detail, trial = _gate_detail(files, tmp_path)

    assert (passed, trial) == (False, False)
    assert detail == "the test suite gave no result: it stopped after 0 of 2 tests"


def test_a_collection_error_is_still_a_graded_failure(tmp_path: Path) -> None:
    """A run that stops on a collection error recorded its failure: graded, not "no result"."""
    passed, detail, trial = _gate_detail({"test_broken.py": "def test_x(:\n"}, tmp_path)

    assert (passed, trial) == (False, False)
    assert "gave no result" not in detail


def test_an_honest_test_package_without_init_still_imports_the_root(tmp_path: Path) -> None:
    """``-P`` drops the cwd from ``sys.path[0]``; the plugin appends it, so root imports still work."""
    files = {"mod.py": _REFACTORED, "tests/test_root.py": _TEST_OK}

    passed, detail, trial = _gate_detail(files, tmp_path)

    assert (passed, detail, trial) == (True, "", True)


def test_the_scoring_suite_reports_no_coverage_outside_the_candidate_tree(tmp_path: Path) -> None:
    """The record plugin runs from the engine's install: it must not enter the candidate's coverage."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "mod.py").write_text(_REFACTORED, encoding="utf-8")
    (tree / "test_mod.py").write_text(_TEST_OK, encoding="utf-8")

    with ExitStack() as stack:
        coverage = open_suite_handle(tree, stack).run().coverage

    assert not [name for name in coverage.per_file if "suite_record" in name]
    assert coverage.sources == (str(tree),)


def test_a_test_that_passes_despite_a_lenient_xfail_still_gives_a_result(tmp_path: Path) -> None:
    """Regression: junit counts a non-strict xpass as a pass; the record called that a forged pass."""
    xpass = "import pytest\n\n\n@pytest.mark.xfail(strict=False)\ndef test_new():\n    pass\n"

    _, detail, _ = _gate_detail({"mod.py": _REFACTORED, "test_new.py": xpass}, tmp_path)

    assert "gave no result" not in detail
