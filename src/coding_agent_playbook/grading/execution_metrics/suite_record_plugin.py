"""Eval scoring's pytest plugin: its own record of the session, beside the junit report.

Only eval scoring loads it, with ``python -P -m pytest ... -p <this module>``
(:func:`~coding_agent_playbook.grading.execution_metrics.project.default_test_cmd`
with ``recorded=True``); :mod:`.suite_record` reads what it writes. Why a second
record: the junit report lies in a directory the run's argv names, so a candidate
``conftest.py`` could rewrite it as all passed, and a run that ``pytest.exit()``
stopped early left a partial report that read as all passed too.

At import the plugin pops ``PLAYBOOK_SUITE_RECORD`` (the path to write, in a temp
dir that is not the report dir and not in argv), so the candidate's tests and their
subprocesses do not see it, and remembers this process's id: only that process
writes, once (``open(path, "x")``), at ``pytest_sessionfinish``. With a record path
it also appends the working directory to the *end* of ``sys.path``: ``-P`` keeps it
from being ``sys.path[0]``, so a planted ``pytest.py`` or ``coding_agent_playbook/``
cannot shadow the toolchain, while the candidate's top-level modules stay importable.

What it records (the JSON :func:`.suite_record.read_suite_record` parses): the
process and parent ids, pytest's exit status, every collected test (node id and
path relative to the directory pytest started in, POSIX) before and after
deselection, one outcome per test (``passed``, ``failed``, ``error``, ``skipped``,
``xfailed`` with ``xfail_strict``, ``xpassed``), the tests whose teardown ran, and
the collectors that skipped or failed. Stdlib only, no engine import: it runs inside
the candidate's pytest process.

It does not defend against code running in that process: a ``conftest.py`` can
patch this module or flip reports in a ``pytest_runtest_makereport`` wrapper.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

#: Equal to ``suite_record.SUITE_RECORD_ENV`` (a test pins it); a literal, since this
#: module imports nothing from the engine.
_RECORD_ENV = "PLAYBOOK_SUITE_RECORD"

#: Where to write the record; ``None`` (no eval scoring run) makes the plugin inert.
_RECORD_PATH: str | None = os.environ.pop(_RECORD_ENV, None)

#: The process that imported the plugin: a forked child of a test never writes.
_PID = os.getpid()

if _RECORD_PATH is not None:
    sys.path.append(os.getcwd())

#: An outcome's weight when one test reports several phases: the worst one wins.
_RANK = {"passed": 0, "xpassed": 1, "xfailed": 2, "skipped": 3, "failed": 4, "error": 4}

#: The ini names of the ``xfail(strict=...)`` default, newest first: pytest 9 reads
#: ``strict_xfail`` (alias ``xfail_strict``), then ``strict``; pytest 8 only ``xfail_strict``.
_STRICT_XFAIL_INI = ("strict_xfail", "xfail_strict", "strict")


class _Config(Protocol):
    def getini(self, name: str) -> object: ...


class _InvocationParams(Protocol):
    dir: Path


class _PluginConfig(_Config, Protocol):
    rootpath: Path
    invocation_params: _InvocationParams
    pluginmanager: _PluginManager


class _PluginManager(Protocol):
    def register(self, plugin: object, name: str) -> object: ...


class _Mark(Protocol):
    kwargs: Mapping[str, object]


class _Item(Protocol):
    nodeid: str
    path: Path
    config: _Config

    def iter_markers(self, name: str) -> Iterator[_Mark]: ...


class _ExcInfo(Protocol):
    typename: str


class _Call(Protocol):
    excinfo: _ExcInfo | None


class _Report(Protocol):
    nodeid: str
    when: str | None
    failed: bool
    skipped: bool


class _Session(Protocol):
    items: list[_Item]


def pytest_configure(config: _PluginConfig) -> None:
    """Register a :class:`SessionRecorder` when eval scoring asked for a record."""
    if _RECORD_PATH is None:
        return
    recorder = SessionRecorder(Path(_RECORD_PATH), config.rootpath, config.invocation_params.dir)
    config.pluginmanager.register(recorder, "playbook-suite-record")


class SessionRecorder:
    """Collects one session's tests and outcomes, and writes them once at its end.

    Example::

        >>> SessionRecorder(Path("r.json"), Path("."), Path(".")).record(0)["selected"] is None
        True
    """

    def __init__(self, record_path: Path, rootpath: Path, start_dir: Path) -> None:
        self._path = record_path
        self._root = rootpath
        self._start = start_dir
        self._collected: list[dict[str, str]] = []
        self._selected: list[dict[str, str]] | None = None
        self._outcomes: dict[str, str] = {}
        self._strict: dict[str, bool] = {}
        self._imperative: set[str] = set()
        self._finished: list[str] = []
        self._collector_skips: list[dict[str, str]] = []
        self._collection_errors: list[dict[str, str]] = []

    def pytest_itemcollected(self, item: _Item) -> None:
        self._collected.append(self._test(item.nodeid, item.path))

    def pytest_collection_finish(self, session: _Session) -> None:
        # After pytest_collection_modifyitems: the run set, deselection applied.
        self._selected = [self._test(item.nodeid, item.path) for item in session.items]

    def pytest_collectreport(self, report: _Report) -> None:
        # A collector's node id is relative to rootdir, which an ini file above the
        # start dir moves away from it: record its path from the start dir, as for tests.
        if not (report.failed or report.skipped):
            return
        entry = self._test(report.nodeid, self._root / report.nodeid.split("::")[0])
        (self._collection_errors if report.failed else self._collector_skips).append(entry)

    def pytest_runtest_makereport(self, item: _Item, call: _Call) -> None:
        # A plain impl of a firstresult hook: it returns None, so pytest's own still
        # builds the report. Read here, after the phase ran, so a marker the test
        # added at run time counts, and an imperative pytest.xfail() is seen.
        if call.excinfo is not None and call.excinfo.typename == "XFailed":
            self._imperative.add(item.nodeid)
        self._strict[item.nodeid] = _marked_strict(item)

    def pytest_runtest_logreport(self, report: _Report) -> None:
        outcome = _phase_outcome(report)
        previous = self._outcomes.get(report.nodeid)
        if previous is None or _RANK[outcome] > _RANK[previous]:
            self._outcomes[report.nodeid] = outcome
        if report.when == "teardown":
            self._finished.append(report.nodeid)

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        if os.getpid() != _PID:
            return
        with contextlib.suppress(OSError), self._path.open("x", encoding="utf-8") as fh:
            json.dump(self.record(int(exitstatus)), fh)

    def record(self, exitstatus: int) -> dict[str, object]:
        """The JSON-ready record of the session so far, ending with ``exitstatus``."""
        outcomes = {
            nodeid: {"outcome": outcome, "xfail_strict": self._strict_xfail(nodeid)}
            for nodeid, outcome in self._outcomes.items()
        }
        return {
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "exitstatus": exitstatus,
            "collected": self._collected,
            "selected": self._selected,
            "outcomes": outcomes,
            "finished": self._finished,
            "collector_skips": self._collector_skips,
            "collection_errors": self._collection_errors,
        }

    def _strict_xfail(self, nodeid: str) -> bool:
        """Strict markers only, and no imperative ``pytest.xfail()``, which never fails on a pass."""
        return self._strict.get(nodeid, False) and nodeid not in self._imperative

    def _test(self, nodeid: str, path: Path) -> dict[str, str]:
        """One test's entry: its node id and its path from where pytest started."""
        return {"nodeid": nodeid, "path": _relative(path, self._start)}


def _phase_outcome(report: _Report) -> str:
    """What one phase report says about its test: ``error`` is a failure outside the call."""
    xfail = hasattr(report, "wasxfail")
    if report.failed:
        return "failed" if report.when == "call" else "error"
    if report.skipped:
        return "xfailed" if xfail else "skipped"
    return "xpassed" if xfail and report.when == "call" else "passed"


def _marked_strict(item: _Item) -> bool:
    """Whether ``item`` carries ``xfail`` markers and every one of them is strict.

    Why every one: pytest applies the first marker whose condition holds, and a
    strict marker with a false condition must not vouch for a non-strict one.
    """
    marks = list(item.iter_markers("xfail"))
    return bool(marks) and all(_strict(mark, item.config) for mark in marks)


def _strict(mark: _Mark, config: _Config) -> bool:
    """A marker's ``strict``, else the ini default of this pytest version."""
    value = mark.kwargs.get("strict")
    return bool(value) if value is not None else _ini_strict(config)


def _ini_strict(config: _Config) -> bool:
    """The configured default of ``xfail(strict=...)``; ``False`` when no name is known."""
    for name in _STRICT_XFAIL_INI:
        try:
            value = config.getini(name)
        except ValueError:
            continue
        if value is not None:
            return bool(value)
    return False


def _relative(path: Path, start: Path) -> str:
    """``path`` relative to ``start`` as POSIX, or absolute when it lies elsewhere."""
    try:
        return Path(path).relative_to(start).as_posix()
    except ValueError:
        return Path(path).as_posix()
