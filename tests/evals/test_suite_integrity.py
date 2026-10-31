"""Unit tests of :func:`suite_violation`: one per rule, each exemption, and the id truncation."""

from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent_playbook.evals.run.suite_integrity import freeze_test_files, suite_violation
from coding_agent_playbook.grading.execution_metrics.suite_record import (
    RecordedOutcome,
    RecordedTest,
    SuiteRecord,
)

#: ``{nodeid: outcome}``; an outcome of ``"xfailed!"`` is a strict xfail.
Outcomes = dict[str, str]


def _record(
    outcomes: Outcomes,
    *,
    deselected: tuple[str, ...] = (),
    module_skips: tuple[str, ...] = (),
    collection_errors: tuple[str, ...] = (),
) -> SuiteRecord:
    """A record that ran ``outcomes`` and collected ``deselected`` without running them."""
    ran = tuple(_test(nodeid) for nodeid in outcomes)
    return SuiteRecord(
        pid=1,
        ppid=0,
        exitstatus=0,
        collected=ran + tuple(_test(nodeid) for nodeid in deselected),
        selected=ran,
        outcomes={n: _outcome(o) for n, o in outcomes.items()},
        finished=frozenset(outcomes),
        collector_skips=tuple(_test(path) for path in module_skips),
        collection_errors=tuple(_test(path) for path in collection_errors),
    )


def _test(nodeid: str) -> RecordedTest:
    return RecordedTest(nodeid, nodeid.split("::")[0])


def _outcome(outcome: str) -> RecordedOutcome:
    return RecordedOutcome(outcome.rstrip("!"), xfail_strict=outcome.endswith("!"))


_BASE = _record({"test_mod.py::test_small": "passed"})


def _files(
    candidate: dict[str, str], setup: dict[str, str]
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """The two file mappings; ``test_mod.py`` is the same in both unless one overrides it."""
    base = {"test_mod.py": "def test_small(): pass\n"}
    return (
        {name: text.encode() for name, text in {**base, **candidate}.items()},
        {name: text.encode() for name, text in {**base, **setup}.items()},
    )


def _violation(
    tmp_path: Path,
    candidate: SuiteRecord,
    baseline: SuiteRecord = _BASE,
    *,
    files: dict[str, str] | None = None,
    changed: tuple[str, ...] = (),
) -> str | None:
    candidate_files, setup_files = _files(files or {}, {})
    return suite_violation(
        candidate,
        baseline,
        candidate_files=candidate_files,
        setup_files=setup_files,
        changed_files=changed,
    )


def test_an_honest_run_counts(tmp_path: Path) -> None:
    candidate = _record({"test_mod.py::test_small": "passed", "test_new.py::test_pin": "xfailed!"})

    assert _violation(tmp_path, candidate) is None


# --------------------------------------------------------------------------- #
# Rule 1: a setup/ test that ran, in an unchanged file, is not in the run set
# --------------------------------------------------------------------------- #


def test_a_setup_test_left_unchanged_but_not_run_is_a_violation(tmp_path: Path) -> None:
    candidate = _record({"test_new.py::test_x": "passed"})

    reason = _violation(tmp_path, candidate)

    assert reason == "setup/ test(s) did not run: test_mod.py::test_small"


def test_a_setup_test_in_an_edited_file_may_go(tmp_path: Path) -> None:
    candidate = _record({"test_mod.py::test_renamed": "passed"})

    files = {"test_mod.py": "def test_renamed(): pass\n"}

    assert _violation(tmp_path, candidate, files=files, changed=("test_mod.py",)) is None


def test_a_setup_test_file_the_agent_did_not_change_counts_as_unchanged(tmp_path: Path) -> None:
    """Different bytes without a change by the agent: the suite touched it, so it still counts."""
    candidate = _record({"test_new.py::test_x": "passed"})
    files = {"test_mod.py": "def test_small(): pass\n# touched\n"}

    reason = _violation(tmp_path, candidate, files=files)

    assert reason == "setup/ test(s) did not run: test_mod.py::test_small"


def test_a_listed_setup_test_file_with_unchanged_bytes_still_counts_as_unchanged(
    tmp_path: Path,
) -> None:
    """git can list a file whose bytes did not change (a mode-only change): it still counts."""
    candidate = _record({"test_new.py::test_x": "passed"})

    reason = _violation(tmp_path, candidate, changed=("test_mod.py",))

    assert reason == "setup/ test(s) did not run: test_mod.py::test_small"


def test_a_deleted_setup_test_file_may_go(tmp_path: Path) -> None:
    candidate = _record({"test_new.py::test_x": "passed"})
    candidate_files, setup_files = _files({}, {})
    del candidate_files["test_mod.py"]

    reason = suite_violation(
        candidate,
        _BASE,
        candidate_files=candidate_files,
        setup_files=setup_files,
        changed_files=("test_mod.py",),
    )

    assert reason is None


def test_a_setup_test_the_baseline_skipped_may_stay_out(tmp_path: Path) -> None:
    baseline = _record({"test_mod.py::test_small": "passed", "test_mod.py::test_later": "skipped"})
    candidate = _record({"test_mod.py::test_small": "passed"})

    assert _violation(tmp_path, candidate, baseline) is None


# --------------------------------------------------------------------------- #
# Rule 2: a setup/ test that ran now skips or xfails
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("now", ["skipped", "xfailed", "xfailed!"])
def test_a_setup_test_that_now_skips_or_xfails_is_a_violation(tmp_path: Path, now: str) -> None:
    candidate = _record({"test_mod.py::test_small": now, "test_new.py::test_x": "passed"})

    reason = _violation(tmp_path, candidate)

    assert reason == "setup/ test(s) now skip or xfail: test_mod.py::test_small"


# --------------------------------------------------------------------------- #
# Rule 3: deselection
# --------------------------------------------------------------------------- #


def test_a_deselected_test_is_a_violation(tmp_path: Path) -> None:
    candidate = _record({"test_mod.py::test_small": "passed"}, deselected=("test_new.py::test_x",))

    reason = _violation(tmp_path, candidate)

    assert reason == "test(s) deselected during collection: test_new.py::test_x"


def test_a_test_the_baseline_deselected_too_may_stay_deselected(tmp_path: Path) -> None:
    baseline = _record(
        {"test_mod.py::test_small": "passed"}, deselected=("test_mod.py::test_slow",)
    )
    candidate = _record(
        {"test_mod.py::test_small": "passed"}, deselected=("test_mod.py::test_slow",)
    )

    assert _violation(tmp_path, candidate, baseline) is None


# --------------------------------------------------------------------------- #
# Rule 4: a changed test file that defines tests had none collected
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path", ["test_new.py", "tests/new_test.py"], ids=["test-prefix", "test-suffix"]
)
def test_a_changed_test_file_with_no_test_collected_is_a_violation(
    tmp_path: Path, path: str
) -> None:
    files = {path: "class TestNew:\n    def test_x(self): pass\n"}

    reason = _violation(tmp_path, _BASE, files=files, changed=(path,))

    assert reason == f"test file(s) define tests that never ran: {path}"


@pytest.mark.parametrize(
    ("files", "candidate"),
    [
        ({"test_new.py": "x = 1\n"}, _BASE),
        ({"test_new.py": "def test_x(:\n"}, _BASE),
        ({"helpers.py": "def test_x(): pass\n"}, _BASE),
        (
            {"test_new.py": "def test_x(): pass\n"},
            _record({"test_mod.py::test_small": "passed"}, collection_errors=("test_new.py",)),
        ),
    ],
    ids=["defines-no-test", "does-not-parse", "not-a-test-file", "collection-error"],
)
def test_a_changed_file_is_exempt_when_pytest_would_not_or_could_not_collect_it(
    tmp_path: Path, files: dict[str, str], candidate: SuiteRecord
) -> None:
    assert _violation(tmp_path, candidate, files=files, changed=tuple(files)) is None


@pytest.mark.parametrize(
    "helper",
    [
        "class TestClock:\n    def __init__(self, now):\n        self.now = now\n",
        "class TestClock:\n    def __new__(cls):\n        return object.__new__(cls)\n",
        "class TestClock:\n    __test__ = False\n\n    def test_tick(self): pass\n",
    ],
    ids=["init", "new", "dunder-test-false"],
)
def test_a_test_class_pytest_refuses_to_collect_defines_no_tests(
    tmp_path: Path, helper: str
) -> None:
    """A helper such as a ``TestClock`` fake yields no test item, so nothing is hidden."""
    files = {"test_support.py": helper}

    assert _violation(tmp_path, _BASE, files=files, changed=("test_support.py",)) is None


def test_a_test_class_that_only_inherits_its_tests_still_defines_tests(tmp_path: Path) -> None:
    """``class TestX(Base): pass`` collects ``Base``'s tests: exempting it would hide them."""
    files = {"test_new.py": "from base import Base\n\n\nclass TestX(Base):\n    pass\n"}

    reason = _violation(tmp_path, _BASE, files=files, changed=("test_new.py",))

    assert reason == "test file(s) define tests that never ran: test_new.py"


# --------------------------------------------------------------------------- #
# Rule 5: new skips
# --------------------------------------------------------------------------- #


def test_a_new_skipped_test_is_a_violation(tmp_path: Path) -> None:
    candidate = _record({"test_mod.py::test_small": "passed", "test_new.py::test_x": "skipped"})

    assert _violation(tmp_path, candidate) == "test(s) skipped: test_new.py::test_x"


def test_a_new_module_skip_is_a_violation_not_an_uncollected_file(tmp_path: Path) -> None:
    candidate = _record({"test_mod.py::test_small": "passed"}, module_skips=("test_new.py",))
    files = {"test_new.py": "def test_x(): pass\n"}

    reason = _violation(tmp_path, candidate, files=files, changed=("test_new.py",))

    assert reason == "test(s) skipped: test_new.py"


def test_a_skip_already_in_the_baseline_is_not_new(tmp_path: Path) -> None:
    outcomes = {"test_mod.py::test_small": "passed", "test_mod.py::test_later": "skipped"}
    baseline = _record(outcomes, module_skips=("test_gpu.py",))
    candidate = _record(outcomes, module_skips=("test_gpu.py",))

    assert _violation(tmp_path, candidate, baseline) is None


# --------------------------------------------------------------------------- #
# Rule 6: non-strict xfails
# --------------------------------------------------------------------------- #


def test_a_non_strict_xfail_is_a_violation(tmp_path: Path) -> None:
    candidate = _record({"test_mod.py::test_small": "passed", "test_new.py::test_x": "xfailed"})

    assert (
        _violation(tmp_path, candidate)
        == "test(s) xfailed without strict=True: test_new.py::test_x"
    )


def test_a_non_strict_xfail_already_in_the_baseline_is_not_new(tmp_path: Path) -> None:
    outcomes = {"test_mod.py::test_small": "passed", "test_mod.py::test_bug": "xfailed"}

    assert _violation(tmp_path, _record(outcomes), _record(outcomes)) is None


# --------------------------------------------------------------------------- #
# Rule 7: nothing passed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "outcomes",
    [{}, {"test_new.py::test_x": "skipped"}, {"test_new.py::test_x": "xfailed!"}],
    ids=["no-tests", "only-skipped", "only-strict-xfailed"],
)
def test_a_run_where_no_test_passed_is_a_violation(tmp_path: Path, outcomes: Outcomes) -> None:
    """The baseline ran the same, so only rule 7 can fire."""
    assert _violation(tmp_path, _record(outcomes), _record(outcomes)) == "no test ran and passed"


def test_a_lenient_xfail_that_now_xpasses_is_a_pass(tmp_path: Path) -> None:
    """Regression: rule 7 counted only ``passed``, while the record and junit count ``xpassed``."""
    baseline = _record({"test_mod.py::test_bug": "xfailed"})
    candidate = _record({"test_mod.py::test_bug": "xpassed"})

    assert _violation(tmp_path, candidate, baseline) is None


def test_a_run_where_every_test_failed_is_a_measured_failure(tmp_path: Path) -> None:
    """A pass rate of 0 is a real measurement: tests_pass grades it, with its scope details."""
    candidate = _record({"test_mod.py::test_small": "failed"})

    assert _violation(tmp_path, candidate) is None


# --------------------------------------------------------------------------- #
# Order and wording
# --------------------------------------------------------------------------- #


def test_the_first_rule_broken_is_the_reason(tmp_path: Path) -> None:
    """A run breaking rules 1, 5 and 7 names the missing setup test."""
    candidate = _record({"test_new.py::test_x": "skipped"})

    assert _violation(tmp_path, candidate) == "setup/ test(s) did not run: test_mod.py::test_small"


def test_a_reason_names_three_ids_then_how_many_more(tmp_path: Path) -> None:
    skipped = {f"test_new.py::test_{i}": "skipped" for i in range(5)}
    candidate = _record({"test_mod.py::test_small": "passed", **skipped})

    reason = _violation(tmp_path, candidate)

    assert reason == (
        "test(s) skipped: test_new.py::test_0, test_new.py::test_1, test_new.py::test_2 +2 more"
    )


def test_a_long_node_id_is_shortened(tmp_path: Path) -> None:
    long_id = "test_new.py::test_x[" + "a" * 200 + "]"
    candidate = _record({"test_mod.py::test_small": "passed", long_id: "skipped"})

    reason = _violation(tmp_path, candidate)

    assert reason is not None and reason.endswith("...")
    assert len(reason) == len("test(s) skipped: ") + 120


# --------------------------------------------------------------------------- #
# freeze_test_files
# --------------------------------------------------------------------------- #


def test_freeze_test_files_reads_only_the_changed_test_files_that_exist(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    for name in ("test_a.py", "tests/b_test.py", "helpers.py", "test_unchanged.py"):
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        (tree / name).write_text(name, encoding="utf-8")
    changed = ("test_a.py", "tests/b_test.py", "helpers.py", "test_gone.py", "../test_x.py")

    frozen = freeze_test_files(tree, changed)

    assert frozen == {"test_a.py": b"test_a.py", "tests/b_test.py": b"tests/b_test.py"}
    (tree / "test_a.py").write_text("changed by the suite", encoding="utf-8")
    assert frozen["test_a.py"] == b"test_a.py"


def test_freeze_test_files_leaves_out_a_file_it_cannot_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "test_a.py").write_text("def test_x(): pass\n", encoding="utf-8")

    def _refuse(self: Path) -> bytes:
        raise PermissionError(13, "denied", str(self))

    monkeypatch.setattr(Path, "read_bytes", _refuse)

    frozen = freeze_test_files(tree, ("test_a.py",))

    assert frozen == {}
