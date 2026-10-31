"""Read eval scoring's own record of a pytest session, and say where it disagrees with the reports.

:mod:`.suite_record_plugin` writes the record inside the suite's pytest process;
:class:`~coding_agent_playbook.grading.execution_metrics.project.ProjectHandle`
(with ``suite_record`` set) reads it with :func:`read_suite_record` after each run
and fails the run (``NoSuiteResultError``) when :func:`session_disagreement`
finds a reason: the session left no record, its exit status or failures differ
from what the process and the junit report say, or it stopped before running
every selected test with no failure to show for it. Stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook.grading.execution_metrics.junit import JunitSummary

#: The module ``-p`` loads into the scoring suite's pytest.
SUITE_RECORD_PLUGIN: Final = "coding_agent_playbook.grading.execution_metrics.suite_record_plugin"

#: The variable carrying the record path to the plugin, which pops it at import.
SUITE_RECORD_ENV: Final = "PLAYBOOK_SUITE_RECORD"

#: The coverage ``omit`` pattern for the plugin. Why: with no ``--cov`` source the
#: plugin file, run from an editable install, entered the candidate's coverage report.
SUITE_RECORD_COVERAGE_OMIT: Final = (
    "*/coding_agent_playbook/grading/execution_metrics/suite_record_plugin.py"
)

#: The outcomes the plugin records for one test.
OUTCOMES: Final = frozenset({"passed", "failed", "error", "skipped", "xfailed", "xpassed"})

#: The outcomes that count against the run: a failure in or around the test call.
_FAILING: Final = frozenset({"failed", "error"})

#: The outcomes junit reports as a pass.
_PASSING: Final = frozenset({"passed", "xpassed"})


class _MalformedRecordError(ValueError):
    """A record field is missing or has the wrong type; the reader returns ``None``."""


@dataclass(frozen=True)
class RecordedTest:
    """One test or collector: its pytest node id and its path from where pytest started (POSIX)."""

    nodeid: str
    path: str


@dataclass(frozen=True)
class RecordedOutcome:
    """One test's outcome (one of :data:`OUTCOMES`) and whether its xfail marking was strict."""

    outcome: str
    xfail_strict: bool = False


@dataclass(frozen=True)
class SuiteRecord:
    """What one pytest session recorded about itself.

    ``collected`` is every test collected, ``selected`` the run set after
    deselection (``None``: collection never finished), ``finished`` the tests whose
    teardown ran, and ``collector_skips`` / ``collection_errors`` the collectors
    (modules, packages) that skipped or failed to collect.
    """

    pid: int
    ppid: int
    exitstatus: int
    collected: tuple[RecordedTest, ...]
    selected: tuple[RecordedTest, ...] | None
    outcomes: Mapping[str, RecordedOutcome]
    finished: frozenset[str]
    collector_skips: tuple[RecordedTest, ...] = ()
    collection_errors: tuple[str, ...] = ()

    @property
    def failures(self) -> int:
        """Failed or erroring tests, plus collectors that failed to collect."""
        failing = sum(1 for o in self.outcomes.values() if o.outcome in _FAILING)
        return failing + len(self.collection_errors)

    @property
    def passes(self) -> int:
        """Tests that passed, as junit counts them: a non-strict ``xpassed`` one included."""
        return sum(1 for o in self.outcomes.values() if o.outcome in _PASSING)

    def outcome_of(self, nodeid: str) -> str | None:
        """``nodeid``'s outcome, or ``None`` when it never reported one."""
        found = self.outcomes.get(nodeid)
        return None if found is None else found.outcome


def read_suite_record(path: Path) -> SuiteRecord | None:
    """The record at ``path``; ``None`` when it is missing, not JSON, or not the plugin's shape.

    Example::

        >>> read_suite_record(Path("/no/such/record.json")) is None  # doctest: +SKIP
        True
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _record(raw)
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def session_disagreement(
    record: SuiteRecord | None, junit: JunitSummary, returncode: int, *, engine_pid: int
) -> str | None:
    """Why the suite's session disagrees with its process and junit report; ``None`` when it agrees.

    ``engine_pid`` is this process's id: the suite's pytest is its direct child, so
    a record whose parent is anyone else came from another process. A run that
    stopped early with a failure already recorded stays a graded failure.

    Example::

        >>> session_disagreement(None, junit, 0, engine_pid=os.getpid())  # doctest: +SKIP
        'it left no record of its pytest session'
    """
    if record is None or record.ppid != engine_pid:
        return "it left no record of its pytest session"
    if record.exitstatus != returncode:
        return f"it exited {returncode}, but its pytest session ended {record.exitstatus}"
    return _report_disagreement(record, junit) or _stopped_early(record)


def _report_disagreement(record: SuiteRecord, junit: JunitSummary) -> str | None:
    """Failures the junit report hides, or passes it adds; ``None`` when it agrees."""
    hidden = record.failures - (junit.failed + junit.errors)
    if hidden > 0:
        return f"its junit report hides {hidden} failed test(s)"
    added = junit.passed - record.passes
    if added > 0:
        return f"its junit report shows {added} passed test(s) its session never ran"
    return None


def _stopped_early(record: SuiteRecord) -> str | None:
    """Why a run with no failure did not finish every selected test; ``None`` when it did."""
    if record.failures:
        return None
    if record.selected is None:
        return "it stopped before collecting its tests"
    selected = {test.nodeid for test in record.selected}
    done = len(selected & record.finished)
    if done < len(selected):
        return f"it stopped after {done} of {len(selected)} tests"
    return None


def _record(raw: object) -> SuiteRecord:
    """Build a :class:`SuiteRecord` from the plugin's JSON; :class:`_MalformedRecordError` if off-shape."""
    data = _mapping(raw)
    selected = data.get("selected")
    return SuiteRecord(
        pid=_int(data.get("pid")),
        ppid=_int(data.get("ppid")),
        exitstatus=_int(data.get("exitstatus")),
        collected=_tests(data.get("collected")),
        selected=None if selected is None else _tests(selected),
        outcomes={_str(k): _outcome(v) for k, v in _mapping(data.get("outcomes")).items()},
        finished=frozenset(_str(n) for n in _list(data.get("finished"))),
        collector_skips=_tests(data.get("collector_skips")),
        collection_errors=tuple(_str(n) for n in _list(data.get("collection_errors"))),
    )


def _tests(raw: object) -> tuple[RecordedTest, ...]:
    return tuple(_test(entry) for entry in _list(raw))


def _test(raw: object) -> RecordedTest:
    entry = _mapping(raw)
    return RecordedTest(nodeid=_str(entry.get("nodeid")), path=_str(entry.get("path")))


def _outcome(raw: object) -> RecordedOutcome:
    entry = _mapping(raw)
    outcome = _str(entry.get("outcome"))
    strict = entry.get("xfail_strict")
    if outcome not in OUTCOMES or not isinstance(strict, bool):
        raise _MalformedRecordError(f"bad outcome {entry!r}; expected one of {sorted(OUTCOMES)}")
    return RecordedOutcome(outcome=outcome, xfail_strict=strict)


def _mapping(raw: object) -> Mapping[str, object]:
    if not isinstance(raw, dict):
        raise _MalformedRecordError(f"expected a JSON object, got {raw!r}")
    return raw


def _list(raw: object) -> list[object]:
    if not isinstance(raw, list):
        raise _MalformedRecordError(f"expected a JSON array, got {raw!r}")
    return raw


def _str(raw: object) -> str:
    if not isinstance(raw, str):
        raise _MalformedRecordError(f"expected a string, got {raw!r}")
    return raw


def _int(raw: object) -> int:
    # bool is an int subclass, and True is no process id or exit status.
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise _MalformedRecordError(f"expected an integer, got {raw!r}")
    return raw
