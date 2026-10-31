"""Regression tests: tests hidden by skips, xfails or collection do not pass ``tests_pass``.

A junit pass rate leaves skipped and xfailed tests out, and an empty suite scores
1.0, so an agent could skip, xfail, deselect or never collect the tests that
fail. Eval scoring now compares the candidate's session record with the
``setup/`` baseline's (:mod:`coding_agent_playbook.evals.run.suite_integrity`).
Each test runs the ``suite_green`` sample over the fixture ``setup/`` (``mod.py``
and a passing ``test_mod.py::test_small``).
"""

from __future__ import annotations

import textwrap
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from coding_agent_playbook.evals.run import scoring
from coding_agent_playbook.evals.run.fake_runner import FakeRunner, write_files
from coding_agent_playbook.evals.run.harness_runner import Candidate
from coding_agent_playbook.evals.run.setup_baseline import SetupBaseline, SetupSnapshot
from coding_agent_playbook.grading.execution_metrics.suite_record import (
    RecordedOutcome,
    RecordedTest,
    SuiteRecord,
)
from tests.evals.test_harness_runner import (
    _REFACTORED,
    _TEST_OK,
    _check,
    _make_sample,
    _make_setup,
    _suite_green_gate,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle

_BROKEN = 'def classify(n):\n    return "WRONG"\n'
_FAILING_TEST = "def test_new():\n    assert False\n"
_PASSING_TEST = (
    "from mod import classify\n\n\ndef test_other():\n    assert classify(5) == 'small'\n"
)
_DOES_NOT_COUNT = "the test suite result does not count: "


def _grade(
    tmp_path: Path,
    agent: Callable[[Path], None],
    *,
    setup_test: str = _TEST_OK,
    setup_test_name: str = "test_mod.py",
) -> tuple[bool, str, bool]:
    """``(tests_pass passed, its detail, trial passed)`` for ``agent`` over the fixture setup/."""
    sample_dir = tmp_path / "sample"
    _make_setup(sample_dir, test_source=setup_test)
    (sample_dir / "setup" / "test_mod.py").rename(sample_dir / "setup" / setup_test_name)
    sample = _make_sample(sample_dir, gate=_suite_green_gate())
    result = FakeRunner(agent).run_sample(sample, tmp_path / "scratch")
    check = _check(result.report, "threshold:test_pass_rate")
    return check.passed, check.detail, result.passed


def _writes(files: dict[str, str]) -> Callable[[Path], None]:
    return write_files({name: textwrap.dedent(body) for name, body in files.items()})


@pytest.mark.parametrize(
    ("files", "reason"),
    [
        (
            {"test_new.py": "import pytest\npytestmark = pytest.mark.skip\n" + _FAILING_TEST},
            "test(s) skipped: test_new.py::test_new",
        ),
        (
            {"test_new.py": "import pytest\n\n\n@pytest.mark.skip\n" + _FAILING_TEST},
            "test(s) skipped: test_new.py::test_new",
        ),
        (
            {"test_new.py": "import pytest\npytest.importorskip('no_such_mod')\n" + _FAILING_TEST},
            "test(s) skipped: test_new.py",
        ),
    ],
    ids=["module-pytestmark", "skip-marker", "module-importorskip"],
)
def test_a_new_skip_fails_tests_pass(tmp_path: Path, files: dict[str, str], reason: str) -> None:
    """Regression: a skipped failing test left the denominator, and the suite scored 1.0."""
    passed, detail, trial = _grade(tmp_path, _writes({"mod.py": _REFACTORED, **files}))

    assert (passed, detail, trial) == (False, _DOES_NOT_COUNT + reason, False)


def test_a_conftest_collect_ignore_of_a_new_test_file_fails_tests_pass(tmp_path: Path) -> None:
    files = {"conftest.py": "collect_ignore = ['test_new.py']\n", "test_new.py": _FAILING_TEST}

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "test file(s) define tests that never ran: test_new.py",
    )


_NAIVE_DESELECT = """\
def pytest_collection_modifyitems(items):
    items[:] = [item for item in items if item.name != "test_new"]
"""

_WRAPPER_DESELECT = """\
import pytest


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_collection_modifyitems(items):
    result = yield
    items[:] = [item for item in items if item.name != "test_new"]
    return result
"""


@pytest.mark.parametrize("conftest", [_NAIVE_DESELECT, _WRAPPER_DESELECT], ids=["naive", "wrapper"])
def test_a_conftest_that_deselects_a_failing_test_fails_tests_pass(
    tmp_path: Path, conftest: str
) -> None:
    files = {"conftest.py": conftest, "test_new.py": _FAILING_TEST}

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "test(s) deselected during collection: test_new.py::test_new",
    )


def test_a_pyproject_python_files_that_collects_nothing_fails_tests_pass(tmp_path: Path) -> None:
    pyproject = "[tool.pytest.ini_options]\npython_files = ['nothing_*.py']\n"
    files = {"mod.py": _BROKEN, "pyproject.toml": pyproject, "test_new.py": _FAILING_TEST}

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "setup/ test(s) did not run: test_mod.py::test_small",
    )


def test_a_setup_test_file_left_unchanged_but_ignored_fails_tests_pass(tmp_path: Path) -> None:
    files = {
        "mod.py": _BROKEN,
        "conftest.py": "collect_ignore = ['test_mod.py']\n",
        "test_other.py": "def test_other():\n    pass\n",
    }

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "setup/ test(s) did not run: test_mod.py::test_small",
    )


def test_a_setup_test_xfailed_by_conftest_fails_tests_pass(tmp_path: Path) -> None:
    conftest = """\
        import pytest


        def pytest_collection_modifyitems(items):
            for item in items:
                item.add_marker(pytest.mark.xfail(strict=False))
        """
    files = {"mod.py": _BROKEN, "conftest.py": conftest, "test_other.py": "def test_x(): pass\n"}

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "setup/ test(s) now skip or xfail: test_mod.py::test_small",
    )


@pytest.mark.parametrize(
    "test_new",
    [
        "import pytest\n\n\n@pytest.mark.xfail\n" + _FAILING_TEST,
        "import pytest\n\n\n@pytest.mark.xfail(strict=True)\n"
        "def test_new():\n    pytest.xfail('later')\n",
    ],
    ids=["marker", "imperative"],
)
def test_a_non_strict_xfail_fails_tests_pass(tmp_path: Path, test_new: str) -> None:
    """Policy: a non-strict xfail passes whatever the code does, so it hides a failure."""
    passed, detail, _ = _grade(tmp_path, _writes({"mod.py": _REFACTORED, "test_new.py": test_new}))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "test(s) xfailed without strict=True: test_new.py::test_new",
    )


def test_a_suite_where_no_test_passed_fails_tests_pass(tmp_path: Path) -> None:
    passed, detail, _ = _grade(tmp_path, lambda scratch: (scratch / "test_mod.py").unlink())

    assert (passed, detail) == (False, _DOES_NOT_COUNT + "no test ran and passed")


# --------------------------------------------------------------------------- #
# Honest suites keep passing
# --------------------------------------------------------------------------- #


def test_a_strict_xfail_pinning_a_known_bug_passes_tests_pass(tmp_path: Path) -> None:
    """characterize/legacy-pricing pins a bug as xfail(strict=True): that still counts."""
    pin = "import pytest\n\n\n@pytest.mark.xfail(strict=True)\n" + _FAILING_TEST

    passed, detail, trial = _grade(tmp_path, _writes({"mod.py": _REFACTORED, "test_pin.py": pin}))

    assert (passed, detail, trial) == (True, "", True)


def _delete_setup_test(scratch: Path) -> None:
    (scratch / "test_mod.py").unlink()
    (scratch / "test_other.py").write_text(_PASSING_TEST, encoding="utf-8")


def _rename_setup_test(scratch: Path) -> None:
    (scratch / "test_mod.py").write_text(_TEST_OK.replace("test_small", "test_renamed"), "utf-8")


@pytest.mark.parametrize(
    "agent", [_delete_setup_test, _rename_setup_test], ids=["deleted", "edited"]
)
def test_a_deleted_or_edited_setup_test_does_not_count_as_missing(
    tmp_path: Path, agent: Callable[[Path], None]
) -> None:
    passed, detail, trial = _grade(tmp_path, agent)

    assert (passed, detail, trial) == (True, "", True)


def _rename_setup_test_file(scratch: Path) -> None:
    (scratch / "test_mod.py").rename(scratch / "test_classify.py")


def _move_setup_test_file(scratch: Path) -> None:
    (scratch / "tests").mkdir()
    (scratch / "test_mod.py").rename(scratch / "tests" / "test_mod.py")


def _replace_setup_test_file(scratch: Path) -> None:
    (scratch / "test_mod.py").unlink()
    (scratch / "test_new.py").write_text(_TEST_OK, encoding="utf-8")


@pytest.mark.parametrize(
    "agent",
    [_rename_setup_test_file, _move_setup_test_file, _replace_setup_test_file],
    ids=["renamed", "moved-into-tests", "deleted-and-copied"],
)
def test_a_setup_test_file_moved_away_does_not_count_as_missing(
    tmp_path: Path, agent: Callable[[Path], None]
) -> None:
    """Regression: git paired the move as a rename and left the old path out of changed_files."""
    passed, detail, trial = _grade(tmp_path, agent)

    assert (passed, detail, trial) == (True, "", True)


def test_an_edited_setup_test_file_with_a_non_ascii_name_does_not_count_as_missing(
    tmp_path: Path,
) -> None:
    """Regression: git quoted the non-ASCII path, so it never matched the record's path."""
    name = "test_\u00e9.py"
    edited = _TEST_OK.replace("test_small", "test_five")

    passed, detail, trial = _grade(tmp_path, _writes({name: edited}), setup_test_name=name)

    assert (passed, detail, trial) == (True, "", True)


def test_a_new_non_ascii_test_file_whose_tests_never_ran_fails_tests_pass(tmp_path: Path) -> None:
    name = "test_\u00e9.py"
    files = {"conftest.py": f"collect_ignore = [{name!r}]\n", name: _FAILING_TEST}

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + f"test file(s) define tests that never ran: {name}",
    )


def test_a_skip_already_in_setup_is_not_a_new_skip(tmp_path: Path) -> None:
    skipping = _TEST_OK + "\n\nimport pytest\n\n\n@pytest.mark.skip\ndef test_later():\n    pass\n"

    passed, detail, trial = _grade(tmp_path, _writes({"mod.py": _REFACTORED}), setup_test=skipping)

    assert (passed, detail, trial) == (True, "", True)


# --------------------------------------------------------------------------- #
# The rules judge the test files as the agent left them, not as the suite did
# --------------------------------------------------------------------------- #


def test_a_setup_test_file_touched_during_the_run_still_counts_as_unchanged(
    tmp_path: Path,
) -> None:
    """Regression: a ``conftest.py`` that edits an ignored setup test file made it look edited."""
    conftest = """\
        collect_ignore = ["test_mod.py"]


        def pytest_sessionfinish(session):
            with open("test_mod.py", "a") as fh:
                fh.write("# touched\\n")
        """
    files = {"mod.py": _BROKEN, "conftest.py": conftest, "test_other.py": "def test_x(): pass\n"}

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "setup/ test(s) did not run: test_mod.py::test_small",
    )


def test_a_test_file_emptied_during_the_run_still_defines_its_tests(tmp_path: Path) -> None:
    """Regression: a ``conftest.py`` that blanks an ignored test file after the run hid it."""
    conftest = """\
        collect_ignore = ["test_new.py"]


        def pytest_sessionfinish(session):
            with open("test_new.py", "w") as fh:
                fh.write("x = 1\\n")
        """
    files = {"conftest.py": conftest, "test_new.py": _FAILING_TEST}

    passed, detail, _ = _grade(tmp_path, _writes(files))

    assert (passed, detail) == (
        False,
        _DOES_NOT_COUNT + "test file(s) define tests that never ran: test_new.py",
    )


# --------------------------------------------------------------------------- #
# A missing session record never lets a result count
# --------------------------------------------------------------------------- #


class _RecordlessHandle:
    """A suite handle whose run left no session record (``_project`` always asks for one)."""

    def run(self) -> SimpleNamespace:
        return SimpleNamespace(record=None)


@pytest.mark.parametrize("missing", ["candidate", "baseline"])
def test_a_suite_with_no_session_record_does_not_count(tmp_path: Path, missing: str) -> None:
    """Fail closed: with no record to check, no rule could catch a hidden test."""
    record = _record_of_one_pass()
    handle = _RecordlessHandle() if missing == "candidate" else _RecordedHandle(record)
    baseline = SetupBaseline(
        "t-fixture",
        tmp_path,
        SetupSnapshot({}, "digest"),
        record=None if missing == "baseline" else record,
    )

    reason = scoring._suite_violation(
        cast("ProjectHandle", handle), baseline, Candidate(tmp_path, "", ""), {}
    )

    assert reason == "the suite left no session record to check"


class _RecordedHandle:
    def __init__(self, record: SuiteRecord) -> None:
        self._record = record

    def run(self) -> SimpleNamespace:
        return SimpleNamespace(record=self._record)


def _record_of_one_pass() -> SuiteRecord:
    test = RecordedTest("test_mod.py::test_small", "test_mod.py")
    return SuiteRecord(
        pid=1,
        ppid=0,
        exitstatus=0,
        collected=(test,),
        selected=(test,),
        outcomes={test.nodeid: RecordedOutcome("passed")},
        finished=frozenset({test.nodeid}),
    )
