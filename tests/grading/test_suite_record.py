"""Tests of the scoring suite's session record: the reader, the disagreement rules, the handle opt-in."""

from __future__ import annotations

import json
import os
import sys
import textwrap
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.grading.execution_metrics.junit import JunitSummary
from coding_agent_playbook.grading.execution_metrics.project import (
    NoSuiteResultError,
    ProjectHandle,
    default_test_cmd,
)
from coding_agent_playbook.grading.execution_metrics.suite_record import (
    SUITE_RECORD_COVERAGE_OMIT,
    SUITE_RECORD_ENV,
    SUITE_RECORD_PLUGIN,
    RecordedOutcome,
    RecordedTest,
    SuiteRecord,
    read_suite_record,
    session_disagreement,
)

if TYPE_CHECKING:
    from pathlib import Path

_ENGINE = os.getpid()


def _record(outcomes: dict[str, str], **fields: Any) -> SuiteRecord:
    """An honest record of ``outcomes`` (``{nodeid: outcome}``), every test finished."""
    tests = tuple(RecordedTest(nodeid, nodeid.split("::")[0]) for nodeid in outcomes)
    base = SuiteRecord(
        pid=1,
        ppid=_ENGINE,
        exitstatus=0,
        collected=tests,
        selected=tests,
        outcomes={n: RecordedOutcome(o) for n, o in outcomes.items()},
        finished=frozenset(outcomes),
    )
    return replace(base, **fields)


def _junit(passed: int = 0, failed: int = 0, errors: int = 0, skipped: int = 0) -> JunitSummary:
    return JunitSummary(passed, failed, errors, skipped, passed + failed + errors + skipped)


# --------------------------------------------------------------------------- #
# read_suite_record
# --------------------------------------------------------------------------- #


_PLUGIN_JSON: dict[str, Any] = {
    "pid": 10,
    "ppid": 9,
    "exitstatus": 1,
    "collected": [{"nodeid": "t.py::a", "path": "t.py"}, {"nodeid": "t.py::b", "path": "t.py"}],
    "selected": [{"nodeid": "t.py::a", "path": "t.py"}],
    "outcomes": {"t.py::a": {"outcome": "xfailed", "xfail_strict": True}},
    "finished": ["t.py::a"],
    "collector_skips": [{"nodeid": "s.py", "path": "s.py"}],
    "collection_errors": [{"nodeid": "e.py", "path": "e.py"}],
}


def test_a_plugin_record_reads_back_whole(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(json.dumps(_PLUGIN_JSON), encoding="utf-8")

    record = read_suite_record(path)

    assert record == SuiteRecord(
        pid=10,
        ppid=9,
        exitstatus=1,
        collected=(RecordedTest("t.py::a", "t.py"), RecordedTest("t.py::b", "t.py")),
        selected=(RecordedTest("t.py::a", "t.py"),),
        outcomes={"t.py::a": RecordedOutcome("xfailed", xfail_strict=True)},
        finished=frozenset({"t.py::a"}),
        collector_skips=(RecordedTest("s.py", "s.py"),),
        collection_errors=(RecordedTest("e.py", "e.py"),),
    )
    assert (record.failures, record.passes, record.outcome_of("t.py::a")) == (1, 0, "xfailed")
    assert record.outcome_of("t.py::b") is None


def test_a_record_that_never_finished_collecting_has_no_run_set(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(json.dumps({**_PLUGIN_JSON, "selected": None}), encoding="utf-8")

    record = read_suite_record(path)

    assert record is not None and record.selected is None


@pytest.mark.parametrize(
    "content",
    [
        None,
        "{not json",
        "[]",
        json.dumps({**_PLUGIN_JSON, "pid": "10"}),
        json.dumps({**_PLUGIN_JSON, "exitstatus": True}),
        json.dumps({**_PLUGIN_JSON, "outcomes": {"t.py::a": {"outcome": "won"}}}),
        json.dumps({**_PLUGIN_JSON, "outcomes": {"t.py::a": {"outcome": "passed"}}}),
        json.dumps({**_PLUGIN_JSON, "finished": "t.py::a"}),
        json.dumps({**_PLUGIN_JSON, "collected": [{"nodeid": 1, "path": "t.py"}]}),
        json.dumps({k: v for k, v in _PLUGIN_JSON.items() if k != "ppid"}),
        json.dumps({**_PLUGIN_JSON, "collection_errors": ["e.py"]}),
    ],
    ids=[
        "missing",
        "bad-json",
        "not-an-object",
        "pid-str",
        "exitstatus-bool",
        "unknown-outcome",
        "no-strictness",
        "finished-str",
        "nodeid-int",
        "no-ppid",
        "collection-error-str",
    ],
)
def test_a_missing_or_malformed_record_reads_as_none(tmp_path: Path, content: str | None) -> None:
    path = tmp_path / "session.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")

    assert read_suite_record(path) is None


# --------------------------------------------------------------------------- #
# session_disagreement
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("record", "junit", "returncode"),
    [
        (_record({}, exitstatus=5), _junit(), 5),
        (_record({"t.py::a": "passed", "t.py::b": "failed"}, exitstatus=1), _junit(1, 1), 1),
        (
            _record(
                {}, exitstatus=2, selected=(), collection_errors=(RecordedTest("t.py", "t.py"),)
            ),
            _junit(errors=1),
            2,
        ),
        (_record({"t.py::a": "xfailed", "t.py::b": "xpassed"}), _junit(1, skipped=1), 0),
    ],
    ids=["no-tests-rc5", "one-failure-rc1", "collection-error-rc2", "xfail-and-xpass"],
)
def test_an_honest_session_agrees_with_its_reports(
    record: SuiteRecord, junit: JunitSummary, returncode: int
) -> None:
    assert session_disagreement(record, junit, returncode, engine_pid=_ENGINE) is None


def test_a_missing_record_is_no_record() -> None:
    reason = session_disagreement(None, _junit(1), 0, engine_pid=_ENGINE)

    assert reason == "it left no record of its pytest session"


def test_a_record_from_another_process_counts_as_no_record() -> None:
    """A test's own pytest subprocess is the engine's grandchild, not its child."""
    record = _record({"t.py::a": "passed"}, ppid=_ENGINE + 1)

    reason = session_disagreement(record, _junit(1), 0, engine_pid=_ENGINE)

    assert reason == "it left no record of its pytest session"


def test_an_exit_code_the_session_never_ended_with_disagrees() -> None:
    record = _record({"t.py::a": "failed"}, exitstatus=1)

    reason = session_disagreement(record, _junit(failed=1), 0, engine_pid=_ENGINE)

    assert reason == "it exited 0, but its pytest session ended 1"


def test_a_junit_report_that_hides_failures_disagrees() -> None:
    record = _record({"t.py::a": "failed", "t.py::b": "error"}, exitstatus=1)

    reason = session_disagreement(record, _junit(passed=2), 1, engine_pid=_ENGINE)

    assert reason == "its junit report hides 2 failed test(s)"


def test_a_junit_report_that_adds_passes_disagrees() -> None:
    record = _record({"t.py::a": "passed", "t.py::b": "failed"}, exitstatus=1)

    reason = session_disagreement(record, _junit(passed=9, failed=1), 1, engine_pid=_ENGINE)

    assert reason == "its junit report shows 8 passed test(s) its session never ran"


def test_a_session_that_stopped_before_collecting_disagrees() -> None:
    record = _record({}, selected=None)

    reason = session_disagreement(record, _junit(), 0, engine_pid=_ENGINE)

    assert reason == "it stopped before collecting its tests"


def test_a_session_that_stopped_after_some_tests_with_no_failure_disagrees() -> None:
    record = _record({"t.py::a": "passed"}, exitstatus=2)
    record = replace(record, selected=(*record.collected, RecordedTest("t.py::b", "t.py")))

    reason = session_disagreement(record, _junit(1), 2, engine_pid=_ENGINE)

    assert reason == "it stopped after 1 of 2 tests"


def test_a_session_that_stopped_after_a_failure_stays_a_graded_failure() -> None:
    """``-x``, ``maxfail`` or ``pytest.exit`` after a failure: the failure is the measurement."""
    record = _record({"t.py::a": "failed"}, exitstatus=1)
    record = replace(record, selected=(*record.collected, RecordedTest("t.py::b", "t.py")))

    assert session_disagreement(record, _junit(failed=1), 1, engine_pid=_ENGINE) is None


# --------------------------------------------------------------------------- #
# The ProjectHandle opt-in
# --------------------------------------------------------------------------- #


def test_the_recorded_command_runs_python_safe_path_and_loads_the_plugin(tmp_path: Path) -> None:
    reports = tmp_path / "reports"

    argv = default_test_cmd(reports, recorded=True)

    assert argv[:4] == [sys.executable, "-P", "-m", "pytest"]
    assert argv[-2:] == ["-p", SUITE_RECORD_PLUGIN]
    assert [a for a in argv if a not in ("-P", SUITE_RECORD_PLUGIN)][:-1] == default_test_cmd(
        reports
    )


def test_create_with_a_suite_record_omits_the_plugin_from_coverage(tmp_path: Path) -> None:
    record = tmp_path / "session" / "session.json"

    handle = ProjectHandle.create(tmp_path, tmp_path / "reports", suite_record=record)

    coveragerc = (tmp_path / "reports" / "coveragerc").read_text(encoding="utf-8")
    assert coveragerc == f"[run]\nomit =\n    {SUITE_RECORD_COVERAGE_OMIT}\n"
    assert handle.suite_record == record
    assert handle.env_overrides == {SUITE_RECORD_ENV: str(record)}
    assert handle.test_cmd == default_test_cmd(tmp_path / "reports", recorded=True)


def test_create_without_a_suite_record_is_unchanged(tmp_path: Path) -> None:
    handle = ProjectHandle.create(tmp_path, tmp_path / "reports")

    assert (tmp_path / "reports" / "coveragerc").read_text(encoding="utf-8") == "[run]\n"
    assert (handle.suite_record, handle.env_overrides) == (None, {})


#: A stand-in suite: its first run fails one of two tests, later runs pass both. It
#: writes a junit report and an honest record (``always``), no record (``never``), a
#: record from a grandchild (``spawn``), or (``fresh``) an honest one, failing again
#: when the record of an earlier run is still there.
_SCRIPTED_SUITE = textwrap.dedent(
    """\
    import json, os, subprocess, sys
    reports, record, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    marker = os.path.join(reports, "ran-once")
    stale = mode == "fresh" and os.path.exists(record)
    fail = 1 if stale or not os.path.exists(marker) else 0
    open(marker, "a").close()
    cases = '<testcase name="a"/>' + ('<testcase name="b"><failure/></testcase>' if fail else "")
    with open(os.path.join(reports, "junit.xml"), "w") as fh:
        fh.write(f"<testsuite>{cases}</testsuite>")
    outcomes = {"t.py::a": {"outcome": "passed", "xfail_strict": False}}
    if fail:
        outcomes["t.py::b"] = {"outcome": "failed", "xfail_strict": False}
    tests = [{"nodeid": n, "path": "t.py"} for n in outcomes]
    body = {"pid": os.getpid(), "ppid": os.getppid(), "exitstatus": fail, "collected": tests,
            "selected": tests, "outcomes": outcomes, "finished": list(outcomes),
            "collector_skips": [], "collection_errors": []}
    if mode == "spawn":
        code = f"import json, os; d = {body!r}; d['ppid'] = os.getppid(); "
        code += f"json.dump(d, open({record!r}, 'w'))"
        subprocess.run([sys.executable, "-c", code], check=True)
    elif mode in ("always", "fresh"):
        json.dump(body, open(record, "w"))
    sys.exit(fail)
    """
)


def _scripted_handle(tmp_path: Path, mode: str, flaky_retries: int = 0) -> ProjectHandle:
    """A handle running :data:`_SCRIPTED_SUITE` and reading its session record."""
    reports = tmp_path / "reports"
    record = tmp_path / "session" / "session.json"
    record.parent.mkdir()
    script = tmp_path / "suite.py"
    script.write_text(_SCRIPTED_SUITE, encoding="utf-8")
    handle = ProjectHandle.create(
        tmp_path,
        reports,
        test_cmd=[sys.executable, str(script), str(reports), str(record), mode],
        flaky_retries=flaky_retries,
        suite_record=record,
    )
    return handle


def test_an_honest_record_reaches_the_run_artifacts(tmp_path: Path) -> None:
    artifacts = _scripted_handle(tmp_path, "always").run()

    assert artifacts.record is not None
    assert artifacts.record.outcome_of("t.py::b") == "failed"


def test_a_stale_record_from_an_earlier_run_is_never_read(tmp_path: Path) -> None:
    """The record is removed before every run, so a planted or leftover one cannot pass for this one."""
    handle = _scripted_handle(tmp_path, "never")
    assert handle.suite_record is not None
    honest = {**_PLUGIN_JSON, "ppid": _ENGINE, "exitstatus": 1, "collection_errors": []}
    handle.suite_record.write_text(json.dumps(honest), encoding="utf-8")

    with pytest.raises(NoSuiteResultError) as raised:
        handle.run()

    assert raised.value.reason == "it left no record of its pytest session"
    assert "disagrees with its reports" in str(raised.value)


def test_a_flaky_retry_starts_without_the_first_runs_record(tmp_path: Path) -> None:
    """Each retry removes the record first, so it reads its own run's, never the first run's."""
    handle = _scripted_handle(tmp_path, "fresh", flaky_retries=1)

    assert handle.run().junit.failed == 1
    assert handle.best_pass_rate() == 1.0


def test_a_record_written_by_another_process_gives_no_result(tmp_path: Path) -> None:
    with pytest.raises(NoSuiteResultError) as raised:
        _scripted_handle(tmp_path, "spawn").run()

    assert raised.value.reason == "it left no record of its pytest session"
