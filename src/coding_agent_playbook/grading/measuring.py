"""The grading kernel's one measuring pass: the tree walk, the per-file loop, the suite loop.

Eval scoring (:mod:`coding_agent_playbook.evals.run.scoring`) and the metrics gate
(:mod:`coding_agent_playbook.metrics_gate.run`) both measure through this module.
:func:`python_files` is the one walk that skips ``IGNORED_DIRS``; :class:`SourceMeter`,
:func:`measure_tree` and :func:`measure_files` are the per-file loop with its byte cap
and hostile-source handling; :func:`measure_suite` runs every execution metric over
one project handle. :func:`measured_metrics` is the pass's promise: a metric-backed
check over a non-judge metric is available at grade time exactly when its metric is
named in ``EvalContext.measured_metrics``, whether or not a file produced a row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.grading.check import _MetricCheck
from coding_agent_playbook.grading.compose import AllOf, AnyOf, Not
from coding_agent_playbook.grading.parse import parse_module
from coding_agent_playbook.grading.rubric import Rubric
from coding_agent_playbook.grading.types import MAX_FILE_BYTES, EvalContext

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from coding_agent_playbook.grading.check import Check
    from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle
    from coding_agent_playbook.grading.metric import Metric
    from coding_agent_playbook.grading.types import Measurement, MeasureSetup

#: Directory names never recursed into when :func:`python_files` walks a tree.
IGNORED_DIRS: Final[frozenset[str]] = frozenset(
    {"__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".git", ".tox", ".mypy_cache"}
)

#: The MODULE label the execution metrics key their suite-wide measurements on.
SUITE_LABEL: Final = "suite"

#: What a hostile or broken source can raise while it is parsed and measured
#: (prK §F.0.3 item 7). CPython reports a parser stack overflow on a deeply
#: nested source as MemoryError ("too complex to parse"), not RecursionError.
#: UnicodeDecodeError is a ValueError.
_BAD_SOURCE_ERRORS = (SyntaxError, RecursionError, MemoryError, ValueError)


class _SkippedSource(Exception):
    """Why one source file is not measured: the text after ``skipped <label>: ``."""


# --------------------------------------------------------------------------- #
# The tree walk
# --------------------------------------------------------------------------- #


def python_files(root: Path) -> list[Path]:
    """Every ``*.py`` under ``root``, sorted, skipping dot dirs and ``IGNORED_DIRS``.

    Paths are ``root`` joined with the relative path, never resolved, so a label
    ``relative_to(root)`` always works (a macOS ``/tmp`` -> ``/private/tmp`` link
    included). A ``root`` that is not a directory holds none.

    Example::

        >>> [p.name for p in python_files(Path("src/coding_agent_playbook/grading"))][:2]
        ['__init__.py', 'baseline_git.py']
    """
    if not root.is_dir():
        return []
    found: list[Path] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and not _ignored_dir(entry.name):
            found.extend(python_files(entry))
        elif entry.is_file() and entry.suffix == ".py":
            found.append(entry)
    return found


def _ignored_dir(name: str) -> bool:
    """Whether the walk skips a directory called ``name``: a dot dir or one of ``IGNORED_DIRS``."""
    return name.startswith(".") or name in IGNORED_DIRS


# --------------------------------------------------------------------------- #
# The per-file loop
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TreeMeasurements:
    """One tree measured file by file: the rows, the files skipped and why, the measured count.

    ``skipped`` holds ``(label, reason)`` for each file that could not be read,
    parsed or measured; ``measured_count`` counts the others.
    """

    measurements: tuple[Measurement, ...]
    skipped: tuple[tuple[str, str], ...]
    measured_count: int


@dataclass(frozen=True)
class SourceMeter:
    """Reads and measures Python sources with a set of static metrics.

    A file over ``setup.max_file_bytes`` is never read into the parser;
    ``setup.tool_paths`` and ``setup.tool_setup`` are how a subprocess-backed
    metric (``ruff_violations``) finds and runs its tool.

    Example::

        >>> meter = SourceMeter([get_metric("cyclomatic_complexity")], MeasureSetup())
        >>> meter.measure("def f():\\n    return 1\\n", "a.py")
        [Measurement(evaluator='cyclomatic_complexity', scope_key='a.py::f', value=1.0)]
    """

    metrics: Sequence[Metric]
    setup: MeasureSetup

    def measure(self, source: str, label: str) -> list[Measurement]:
        """Parse ``source`` and run every available metric over it.

        Raises what a broken source makes the parser or a metric raise
        (:data:`_BAD_SOURCE_ERRORS`); the caller skips or drops the file.
        """
        module = parse_module(source, label)
        ctx = EvalContext(
            module=module,
            source=source,
            label=label,
            tool_paths=self.setup.tool_paths,
            tool_setup=self.setup.tool_setup,
        )
        return _measure_available(self.metrics, ctx)

    def measure_or_drop(self, source: str, label: str) -> list[Measurement]:
        """Measure a baseline source; one that breaks the parser or a metric yields nothing (all-new)."""
        try:
            return self.measure(source, label)
        except _BAD_SOURCE_ERRORS:
            return []

    def measure_file_or_drop(self, path: Path, label: str) -> list[Measurement]:
        """Measure a baseline file; one that is unreadable, too large or broken yields nothing (all-new).

        Example::

            >>> meter.measure_file_or_drop(Path("base/huge.py"), "huge.py")  # doctest: +SKIP
            []
        """
        try:
            source = self.read(path)
        except _SkippedSource:
            return []
        return self.measure_or_drop(source, label)

    def read(self, path: Path) -> str:
        """``path`` as UTF-8 text; raises :class:`_SkippedSource` when unreadable or too large."""
        cap = self.setup.max_file_bytes
        try:
            size = path.stat().st_size
            source = None if size > cap else path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _SkippedSource(f"unreadable ({exc})") from exc
        if source is None:
            raise _SkippedSource(f"too large ({size} bytes, over the {cap}-byte cap)")
        return source

    def decode_blob(self, raw: bytes) -> str | None:
        """A git baseline blob as text, like ``git show`` under ``text=True``: UTF-8, universal newlines.

        ``None`` (the file counts as all-new, like one that does not parse) when
        the blob is over the cap or not UTF-8.
        """
        return decode_source_blob(raw, self.setup.max_file_bytes)


def decode_source_blob(raw: bytes, max_file_bytes: int = MAX_FILE_BYTES) -> str | None:
    """A baseline blob as the text the gate measures: UTF-8 with universal newlines.

    ``None`` when it is over ``max_file_bytes`` or not UTF-8. A Stop stage
    decodes a ``HEAD`` blob with it to ask the gate's ruff memo about the same text.

    Example::

        >>> decode_source_blob(b"x = 1\\r\\n")
        'x = 1\\n'
    """
    if len(raw) > max_file_bytes:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def measure_tree(root: Path, meter: SourceMeter) -> TreeMeasurements:
    """Measure every ``python_files(root)`` file, labelled root-relative (posix).

    Example::

        >>> measure_tree(Path("setup"), SourceMeter(static_metrics(), MeasureSetup())).skipped
        ... # doctest: +SKIP
        (('broken.py', 'unparseable (invalid syntax)'),)
    """
    labelled = [(path, path.relative_to(root).as_posix()) for path in python_files(root)]
    return measure_files(labelled, meter)


def measure_files(files: Sequence[tuple[Path, str]], meter: SourceMeter) -> TreeMeasurements:
    """Measure each ``(path, label)``; one that cannot be read, parsed or measured is skipped.

    A hostile file costs a note, never a traceback: the gate runs inside hooks.

    Example::

        >>> measure_files([(Path("big.py"), "big.py")], meter).skipped  # doctest: +SKIP
        (('big.py', 'too large (2000000 bytes, over the 1000000-byte cap)'),)
    """
    measurements: list[Measurement] = []
    skipped: list[tuple[str, str]] = []
    for path, label in files:
        reason = _measure_file(path, label, meter, measurements)
        if reason is not None:
            skipped.append((label, reason))
    return TreeMeasurements(tuple(measurements), tuple(skipped), len(files) - len(skipped))


def _measure_file(
    path: Path, label: str, meter: SourceMeter, into: list[Measurement]
) -> str | None:
    """Measure one file into ``into``; the skip reason, or ``None`` once measured."""
    try:
        into.extend(meter.measure(meter.read(path), label))
    except _SkippedSource as exc:
        return str(exc)
    except _BAD_SOURCE_ERRORS as exc:
        return _skip_reason(exc)
    return None


def _skip_reason(exc: Exception) -> str:
    """The note for a source that broke the parser or a metric."""
    if isinstance(exc, SyntaxError):
        return f"unparseable ({exc.msg})"
    if isinstance(exc, MemoryError):
        return "unparseable (too complex to parse)"
    if isinstance(exc, RecursionError):
        return "too deeply nested to measure"
    return f"unmeasurable ({exc})"


# --------------------------------------------------------------------------- #
# The suite loop
# --------------------------------------------------------------------------- #


def measure_suite(
    project: ProjectHandle, metrics: Sequence[Metric], setup: MeasureSetup
) -> list[Measurement]:
    """Run every execution metric over one handle (the suite runs once).

    Every metric reads the same cached :meth:`ProjectHandle.run`. Raises the
    ``RuntimeError`` a metric raises; the caller applies its policy (eval scoring
    measures nothing, the gate raises ``MetricsGateUsageError``).

    Example::

        >>> measure_suite(ProjectHandle.create(root, reports), execution_metrics(), MeasureSetup())
        ... # doctest: +SKIP
        [Measurement(evaluator='coverage', scope_key='suite', value=87.5), ...]
    """
    ctx = EvalContext(
        module=None,
        source="",
        label=SUITE_LABEL,
        project=project,
        tool_paths=setup.tool_paths,
        tool_setup=setup.tool_setup,
    )
    return _measure_available(metrics, ctx)


def _measure_available(metrics: Iterable[Metric], ctx: EvalContext) -> list[Measurement]:
    """Every metric that can run in ``ctx``, measured in order."""
    measurements: list[Measurement] = []
    for metric in metrics:
        if metric.available(ctx):
            measurements.extend(metric.measure(ctx))
    return measurements


# --------------------------------------------------------------------------- #
# What the pass measures, and what it promises grading
# --------------------------------------------------------------------------- #


def referenced_metrics(checks: Sequence[Check], *, nested: bool = False) -> list[Metric]:
    """Every :class:`Metric` the check tree references, deduped by name, first seen first.

    Walks ``checks``, descending the boolean composers (``AllOf``/``AnyOf``/``Not``
    via their ``children``) and pulling the metric off every metric-backed check
    (``ThresholdCheck``/``NonRegressionCheck``). A metric that is itself a
    :class:`~coding_agent_playbook.grading.rubric.Rubric` is one metric, because its
    own :meth:`~coding_agent_playbook.grading.rubric.Rubric.measure` grades its
    checks; only ``nested=True`` (the availability set) also descends into them.
    File and judge-only checks carry no metric.

    Example::

        >>> [m.name for m in referenced_metrics([ThresholdCheck(get_metric("wmc"))])]
        ['wmc']
    """
    found: dict[str, Metric] = {}
    for check in checks:
        _collect(check, found, nested=nested)
    return list(found.values())


def _collect(check: Check, found: dict[str, Metric], *, nested: bool) -> None:
    """Add the metrics under ``check`` to ``found``, first seen first."""
    if isinstance(check, _MetricCheck):
        _collect_metric(check.metric, found, nested=nested)
    elif isinstance(check, (AllOf, AnyOf, Not)):
        for child in check.children:
            _collect(child, found, nested=nested)


def _collect_metric(metric: Metric, found: dict[str, Metric], *, nested: bool) -> None:
    """Add ``metric`` once; with ``nested``, a new rubric's own metrics follow it."""
    if metric.name in found:
        return
    found[metric.name] = metric
    if nested and isinstance(metric, Rubric):
        for check in metric.checks:
            _collect(check, found, nested=nested)


def measured_metrics(metrics: Iterable[Metric], setup: MeasureSetup) -> frozenset[str]:
    """The names of the non-judge ``metrics`` that can run with ``setup``: the pass's promise.

    A metric-backed check over a non-judge metric is available at grade time
    exactly when its metric is named here (``EvalContext.measured_metrics``),
    whether or not a file produced a row; a judged metric asks its judge instead.

    Example::

        >>> sorted(measured_metrics([get_metric("wmc"), get_metric("ruff_violations")], MeasureSetup()))
        ['wmc']
    """
    return frozenset(metric.name for metric in metrics if _promised(metric, setup))


def _promised(metric: Metric, setup: MeasureSetup) -> bool:
    """Whether the pass measures ``metric``: not judge-backed, and ``setup`` can run it."""
    return not metric.needs_judge and metric.runnable(setup)
