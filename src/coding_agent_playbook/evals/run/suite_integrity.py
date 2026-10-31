"""Whether a candidate's test-suite result counts: no test hidden from it by skips, xfails or collection.

A junit pass rate leaves skipped and xfailed tests out of its denominator, and a
suite with no runnable test scores 1.0, so an agent could pass ``tests_pass`` by
skipping, xfailing, deselecting or never collecting the tests that fail.
:func:`suite_violation` compares the session records
(:mod:`~coding_agent_playbook.grading.execution_metrics.suite_record`) of the
candidate's suite and of the sample's ``setup/`` baseline suite, and returns the
first rule the candidate breaks; eval scoring then fails every execution check
with ``the test suite result does not count: <reason>``. The rules, in order:

1. a ``setup/`` test that ran in the baseline, in a file the candidate left
   byte-identical, is not in the candidate's run set (an edited or deleted setup
   test is the agent's to change, so it does not count as missing);
2. a ``setup/`` test that ran in the baseline now skips or xfails;
3. a collected test was deselected, unless the baseline deselected it too;
4. a test file the agent changed (``test_*.py`` / ``*_test.py``, defining a
   ``test*`` function or a ``Test*`` class pytest would collect) had no test
   collected, no collector skip and no collection error;
5. a test skipped, or a module skipped as a whole, that the baseline did not skip.
   Policy, with no opt-out until a sample needs one: a new skip hides a test, so
   it fails;
6. a test xfailed without ``strict=True`` (an imperative ``pytest.xfail()``
   included), unless the baseline xfailed it the same way. Policy: a non-strict
   xfail passes whatever the code does, so it hides a failure; a strict one that
   xfails still counts, which is how characterize/legacy-pricing pins a bug;
7. no test passed, and none failed either: with a failure the pass rate is a
   real measurement, while a run of skips and xfails alone scores a vacuous 1.0.

The rules judge the test files as the agent left them: the suite runs agent
code, which could edit an ignored test file during the run so that it looked
edited (rule 1) or defined no test (rule 4), or rewrite any copy the engine kept
on disk. So a file counts as changed only when the agent's ``changed_files``
(captured before the suite) name it, and rules 1 and 4 read the bytes
:func:`freeze_test_files` reads into engine memory before the suite runs, beside
the ``setup/`` files the engine read before any agent ran.

The reason lists at most three node ids, then ``+N more``: short, and free of
command output, so it fits a committed report. :func:`suite_violation` is pure:
it reads only the two records and the two in-memory file mappings.
"""

from __future__ import annotations

import ast
import fnmatch
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.grading.execution_metrics.suite_record import (
        RecordedTest,
        SuiteRecord,
    )

#: How many node ids a reason names before ``+N more``.
_LISTED: Final = 3

#: The longest node id a reason quotes in full; a parametrize id can be any length.
_ID_CHARS: Final = 120

#: The baseline outcomes of a test that ran.
_RAN: Final = frozenset({"passed", "failed", "error"})

#: pytest's default ``python_files`` patterns, matched on the file name.
_TEST_FILE_PATTERNS: Final = ("test_*.py", "*_test.py")


@dataclass(frozen=True)
class _Suites:
    """The two records a rule compares, with the file contents and the agent's changed files."""

    candidate: SuiteRecord
    baseline: SuiteRecord
    candidate_files: Mapping[str, bytes]
    setup_files: Mapping[str, bytes]
    changed_files: Sequence[str]


def suite_violation(
    candidate: SuiteRecord,
    baseline: SuiteRecord,
    *,
    candidate_files: Mapping[str, bytes],
    setup_files: Mapping[str, bytes],
    changed_files: Sequence[str],
) -> str | None:
    """The first rule ``candidate``'s suite breaks against ``baseline``'s; ``None`` when it counts.

    ``changed_files`` are the agent's changed paths, relative to the tree root as
    the records' paths are. ``candidate_files`` holds the agent's changed test files
    as it left them (:func:`freeze_test_files`); ``setup_files`` the sample's
    ``setup/`` files (relative POSIX path to bytes).

    Example::

        >>> suite_violation(cand, base, candidate_files={}, setup_files={}, changed_files=[])  # doctest: +SKIP
        'test(s) skipped: test_x.py::test_slow'
    """
    suites = _Suites(candidate, baseline, candidate_files, setup_files, changed_files)
    for rule in _RULES:
        reason = rule(suites)
        if reason is not None:
            return reason
    return None


def _setup_tests_not_run(s: _Suites) -> str | None:
    """Rule 1: setup tests that ran, in files left as they are, missing from the run set."""
    ran = _ids(s.candidate.selected or ())
    missing = [
        test.nodeid
        for test in s.baseline.selected or ()
        if s.baseline.outcome_of(test.nodeid) not in (None, "skipped")
        and test.nodeid not in ran
        and _unchanged(s, test.path)
    ]
    return _reason("setup/ test(s) did not run", missing)


def _unchanged(s: _Suites, path: str) -> bool:
    """Whether the agent left ``path`` as ``setup/`` has it.

    Why ``changed_files`` first: they were captured before the suite ran agent
    code, which could touch an ignored setup test file to make it look edited.
    """
    if path not in s.changed_files:
        return True
    ours = s.candidate_files.get(path)
    return ours is not None and ours == s.setup_files.get(path)


def _setup_tests_now_skipped(s: _Suites) -> str | None:
    """Rule 2: setup tests that ran in the baseline and now skip or xfail."""
    hidden = [
        nodeid
        for nodeid in s.baseline.outcomes
        if s.baseline.outcome_of(nodeid) in _RAN
        and s.candidate.outcome_of(nodeid) in ("skipped", "xfailed")
    ]
    return _reason("setup/ test(s) now skip or xfail", hidden)


def _deselected(s: _Suites) -> str | None:
    """Rule 3: collected tests left out of the run set, beyond the baseline's own."""
    baseline_deselected = _ids(s.baseline.collected) - _ids(s.baseline.selected or ())
    dropped = _ids(s.candidate.collected) - _ids(s.candidate.selected or ())
    return _reason("test(s) deselected during collection", dropped - baseline_deselected)


def _test_files_not_collected(s: _Suites) -> str | None:
    """Rule 4: changed test files that define tests none of which was collected."""
    seen = {test.path for test in (*s.candidate.collected, *s.candidate.collector_skips)}
    seen |= {test.path for test in s.candidate.collection_errors}
    uncollected = [
        path
        for path in s.changed_files
        if _is_test_file(path) and path not in seen and _defines_tests(s.candidate_files.get(path))
    ]
    return _reason("test file(s) define tests that never ran", uncollected)


def _new_skips(s: _Suites) -> str | None:
    """Rule 5: skipped tests and skipped collectors the baseline did not skip."""
    skipped = [n for n in s.candidate.outcomes if s.candidate.outcome_of(n) == "skipped"]
    tests = [n for n in skipped if s.baseline.outcome_of(n) != "skipped"]
    baseline_modules = _ids(s.baseline.collector_skips)
    modules = [t.nodeid for t in s.candidate.collector_skips if t.nodeid not in baseline_modules]
    return _reason("test(s) skipped", [*tests, *modules])


def _non_strict_xfails(s: _Suites) -> str | None:
    """Rule 6: tests xfailed without ``strict=True`` that the baseline did not xfail so."""
    lenient = [n for n in s.candidate.outcomes if _xfailed_leniently(s.candidate, n)]
    new = [n for n in lenient if not _xfailed_leniently(s.baseline, n)]
    return _reason("test(s) xfailed without strict=True", new)


def _nothing_passed(s: _Suites) -> str | None:
    """Rule 7: a run in which no test passed or failed, so its pass rate measures nothing."""
    # Why the record's passes: junit counts a lenient xpass as a pass, and so does
    # the record (7a104a50); one definition of a pass for one record.
    if s.candidate.failures or s.candidate.passes:
        return None
    return "no test ran and passed"


_RULES: Final[tuple[Callable[[_Suites], str | None], ...]] = (
    _setup_tests_not_run,
    _setup_tests_now_skipped,
    _deselected,
    _test_files_not_collected,
    _new_skips,
    _non_strict_xfails,
    _nothing_passed,
)


def freeze_test_files(tree: Path, changed_files: Sequence[str]) -> dict[str, bytes]:
    """Read the changed test files of ``tree`` into memory before the suite runs.

    Only ``test_*.py`` / ``*_test.py`` paths that exist as files are read; a path
    that is absolute, climbs out with ``..``, or cannot be read is left out (it
    defines no tests). Nothing is written: a copy on disk could be rewritten by the
    agent code the suite runs.

    Example::

        >>> freeze_test_files(candidate.tree, candidate.changed_files)  # doctest: +SKIP
        {'tests/test_new.py': b'def test_x(): ...'}
    """
    frozen: dict[str, bytes] = {}
    for path in changed_files:
        if _is_test_file(path) and _inside(path) and (tree / path).is_file():
            _read_into(tree / path, path, frozen)
    return frozen


def _inside(path: str) -> bool:
    pure = PurePosixPath(path)
    return not pure.is_absolute() and ".." not in pure.parts


def _read_into(source: Path, path: str, frozen: dict[str, bytes]) -> None:
    """Add ``source``'s bytes to ``frozen`` under ``path``; an unreadable file is left out."""
    try:
        frozen[path] = source.read_bytes()
    except OSError:
        return


def _xfailed_leniently(record: SuiteRecord, nodeid: str) -> bool:
    found = record.outcomes.get(nodeid)
    return found is not None and found.outcome == "xfailed" and not found.xfail_strict


def _ids(tests: Iterable[RecordedTest]) -> set[str]:
    """The node ids of ``tests``."""
    return {test.nodeid for test in tests}


def _is_test_file(path: str) -> bool:
    """Whether ``path``'s name matches pytest's default test-file patterns."""
    name = PurePosixPath(path).name
    return any(fnmatch.fnmatch(name, pattern) for pattern in _TEST_FILE_PATTERNS)


def _defines_tests(source: bytes | None) -> bool:
    """Whether ``source`` defines a module-level ``test*`` function or ``Test*`` class.

    A missing (unreadable) or unparseable file defines none here: it is a
    collection error, graded as a failure on its own.
    """
    if source is None:
        return False
    try:
        module = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return any(_is_test_node(node) for node in module.body)


def _is_test_node(node: ast.stmt) -> bool:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return node.name.startswith("test")
    if not isinstance(node, ast.ClassDef) or not node.name.startswith("Test"):
        return False
    return not any(_refuses_collection(stmt) for stmt in node.body)


def _refuses_collection(stmt: ast.stmt) -> bool:
    """Whether a class-body ``stmt`` makes pytest skip its ``Test*`` class.

    Why: pytest collects no class that defines ``__init__`` or ``__new__`` (a
    ``TestClock`` fake, say) or sets ``__test__ = False``, so such a class hides
    no test. A class with no ``test*`` method still counts: it may inherit them.
    """
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
        return stmt.name in ("__init__", "__new__")
    if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.Constant):
        return False
    named = any(isinstance(t, ast.Name) and t.id == "__test__" for t in stmt.targets)
    return named and stmt.value.value is False


def _reason(label: str, ids: Iterable[str]) -> str | None:
    """``"<label>: a, b, c +N more"`` over the sorted ``ids``; ``None`` when there are none."""
    found = sorted(set(ids))
    if not found:
        return None
    shown = ", ".join(_short(nodeid) for nodeid in found[:_LISTED])
    more = len(found) - _LISTED
    return f"{label}: {shown}" + (f" +{more} more" if more > 0 else "")


def _short(nodeid: str) -> str:
    return nodeid if len(nodeid) <= _ID_CHARS else nodeid[: _ID_CHARS - 3] + "..."
