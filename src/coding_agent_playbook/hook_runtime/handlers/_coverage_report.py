"""What the ``coverage`` Stop stage measures and says (specs/prK-hook-pack.md §F.1.2).

- :func:`port_changed_lines`: the Python lines changed since a diff base,
  listed through the hook's hardened ``GitPort`` (``git diff <base>`` added
  lines plus every line of an untracked file), the shape
  ``grading.execution_metrics.git_diff.changed_lines`` gives the CLI;
- :func:`coverage_lines`: the at most four lines of a failing grade, e.g.::

      coverage: 62.5% of 24 changed lines executed (min 80%)
      "src/pkg/a.py": 12-15, 40 · "src/pkg/b.py": 3 (+2 files)
      total 84.1% -> 83.7% vs HEAD (must not drop)
      Add or extend tests for these lines, then re-run.

  Paths are quoted as data; line ranges come from ``changed_line_coverage``,
  the pure core the metric and the CLI share;
- :func:`head_snapshot` / :func:`write_snapshot_rows`: the coverage snapshot of a
  green run, ``<state>/coverage/<tree>.json`` in ``--emit-measurements`` format,
  read back as the total-coverage baseline once that tree is ``HEAD^{tree}``.

A private module: it registers no handler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.grading.execution_metrics.diff_coverage import format_ranges
from coding_agent_playbook.grading.execution_metrics.git_diff import every_line
from coding_agent_playbook.hook_runtime.caps import quote_data

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.grading.execution_metrics.diff_coverage import DiffCoverage
    from coding_agent_playbook.grading.types import ScopeDetail
    from coding_agent_playbook.hook_runtime.git.safe_git import GitPort
    from coding_agent_playbook.hook_runtime.state import StateStore

__all__ = [
    "ADVICE_LINE",
    "MAX_LINES",
    "NO_SNAPSHOT_LINE",
    "SNAPSHOT_DIR",
    "CoverageGrade",
    "coverage_lines",
    "head_snapshot",
    "port_changed_lines",
    "suite_total",
    "write_snapshot_rows",
]

MAX_LINES: Final = 4
#: Files named on the ranges line before ``(+N files)``.
SHOWN_FILES: Final = 2
NO_SNAPSHOT_LINE: Final = "total coverage not compared (no cached baseline for HEAD)"
ADVICE_LINE: Final = "Add or extend tests for these lines, then re-run."
_PY: Final = ".py"
#: ``<state>/coverage/<tree>.json`` (specs/prK-lifecycle-hooks.md §D.6.1).
SNAPSHOT_DIR: Final = "coverage"


def port_changed_lines(git: GitPort, root: Path, base: str) -> dict[str, frozenset[int]]:
    """``{repo-relative .py path: line numbers}`` changed since ``base``, through ``git``.

    Raises what ``git`` raises (``GitError``); the stage treats that as no change.

    Example: ``port_changed_lines(ctx.git, root, "HEAD") == {"src/a.py": frozenset({3, 4})}``.
    """
    found: dict[str, set[int]] = {}
    for added in git.diff_worktree(base).added:
        if added.path.endswith(_PY):
            found.setdefault(added.path, set()).add(added.line)
    for rel in git.ls_untracked():
        if rel.endswith(_PY):
            found.setdefault(rel, set()).update(every_line(root / rel))
    return {path: frozenset(lines) for path, lines in found.items() if lines}


@dataclass(frozen=True, slots=True)
class CoverageGrade:
    """One graded run: the changed-line detail plus the gate's two findings that can fail it.

    ``diff`` is ``None`` when ``diff_coverage`` measured nothing; ``total`` is the
    suite-total ``coverage`` row (a regression only against a snapshot); ``rows``
    are every ``coverage`` row, the snapshot a green run leaves.
    """

    detail: DiffCoverage
    diff: ScopeDetail | None
    total: ScopeDetail | None
    compared: bool
    rows: tuple[ScopeDetail, ...] = ()

    @property
    def diff_failed(self) -> bool:
        """Changed lines were executed below the ``diff_coverage`` bound."""
        return self.diff is not None and self.diff.level == "fail"

    @property
    def total_dropped(self) -> bool:
        """The suite total dropped below the snapshot's (never without one)."""
        total = self.total
        return total is not None and total.kind == "regression" and total.level == "fail"

    @property
    def passed(self) -> bool:
        """Neither the changed lines nor the total failed."""
        return not self.diff_failed and not self.total_dropped


def coverage_lines(grade: CoverageGrade) -> list[str]:
    """The stage's lines for a failing ``grade`` (``[]`` when it passed), at most :data:`MAX_LINES`.

    Example::

        >>> coverage_lines(grade)[0]  # doctest: +SKIP
        'coverage: 62.5% of 24 changed lines executed (min 80%)'
    """
    if grade.passed:
        return []
    lines: list[str] = []
    if grade.diff_failed and grade.diff is not None:
        lines.extend(_diff_lines(grade.detail, grade.diff))
    if grade.total_dropped and grade.total is not None:
        lines.append(_total_line(grade.total, prefix=not lines))
    elif not grade.compared:
        lines.append(NO_SNAPSHOT_LINE)
    lines.append(ADVICE_LINE)
    return lines[:MAX_LINES]


def _diff_lines(detail: DiffCoverage, finding: ScopeDetail) -> list[str]:
    bound = "" if finding.bound is None else f" (min {finding.bound * 100:g}%)"
    head = f"coverage: {finding.value:.1f}% of {detail.executable} changed lines executed{bound}"
    missed = [item for item in detail.files if item.uncovered]
    shown = [f"{quote_data(item.path)}: {format_ranges(item.uncovered)}" for item in missed]
    ranges = " · ".join(shown[:SHOWN_FILES])
    if len(shown) > SHOWN_FILES:
        ranges += f" (+{len(shown) - SHOWN_FILES} files)"
    return [head, ranges] if ranges else [head]


def _total_line(finding: ScopeDetail, *, prefix: bool) -> str:
    before = "?" if finding.baseline is None else f"{finding.baseline:.1f}%"
    text = f"total {before} -> {finding.value:.1f}% vs HEAD (must not drop)"
    return f"coverage: {text}" if prefix else text


def suite_total(findings: Sequence[ScopeDetail], label: str) -> ScopeDetail | None:
    """The ``coverage`` row keyed on the suite ``label`` (the total), if graded.

    Example: ``suite_total(result.report.findings, "suite").value == 83.7``.
    """
    return next((f for f in findings if f.evaluator == "coverage" and f.scope_key == label), None)


def head_snapshot(store: StateStore, head_tree: str | None) -> Path | None:
    """``<state>/coverage/<head_tree>.json`` when it is a readable snapshot, else ``None``.

    Example: ``head_snapshot(ctx.session.store, plan.head_tree)`` after a green run of that tree.
    """
    from coding_agent_playbook.metrics_gate.snapshot import SnapshotError, read_snapshot

    if head_tree is None:
        return None
    try:
        path = store.path(f"{SNAPSHOT_DIR}/{head_tree}.json")
        read_snapshot(path)
    except (SnapshotError, ValueError):
        return None
    return path


def write_snapshot_rows(store: StateStore, tree: str, rows: Sequence[ScopeDetail]) -> None:
    """Remember a green run's ``coverage`` ``rows`` under ``tree``; stateless writes nothing.

    Example: ``write_snapshot_rows(ctx.session.store, fingerprint.tree_id, grade.rows)``.
    """
    from coding_agent_playbook.grading.types import Measurement
    from coding_agent_playbook.hook_runtime.state import StateUnavailable
    from coding_agent_playbook.metrics_gate.snapshot import snapshot_document

    if not rows:
        return
    measured = [Measurement(row.evaluator, row.scope_key, row.value) for row in rows]
    try:
        store.write_json(f"{SNAPSHOT_DIR}/{tree}.json", snapshot_document(measured, tree=tree))
    except (StateUnavailable, ValueError):
        return  # the next commit simply has no cached baseline
