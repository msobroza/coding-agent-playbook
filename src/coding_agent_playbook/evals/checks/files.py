"""Deterministic file checks: the ``[expected]`` predicates as ``Check``.

The four ``[expected]`` file checks (``files_created``/``files_must_contain``/
``files_unchanged``/``files_forbidden``) are first-class
:class:`~coding_agent_playbook.grading.check.Check` instances. Unlike the
metric-backed checks these ignore the
:class:`~coding_agent_playbook.grading.check.MeasurementSet` and read the
candidate tree (:attr:`EvalContext.tree`) - and, for the unchanged check, the
baseline tree (:attr:`EvalContext.baseline_tree`) - directly.

Each is a pure gate (``weight=0.0``, ``required=True`` by default, DETERMINISTIC,
DETERMINISTIC-cost) whose ``passed`` comes **straight from the predicate**. The
result carries one
:class:`~coding_agent_playbook.grading.types.ScopeDetail` describing the path,
with ``score = 1.0`` when the predicate holds and ``0.0`` otherwise.

The ``slug`` id-sanitizer is the shared one defined in
:mod:`coding_agent_playbook.grading.check` (re-exported here as a thin wrapper
that pins the ``"path"`` fallback) so the families do not each carry their own
copy.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.check import Check
from coding_agent_playbook.grading.check import slug as _slug
from coding_agent_playbook.grading.check_registry import register_check
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, ScopeDetail

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.grading.check import MeasurementSet
    from coding_agent_playbook.grading.types import EvalContext


def slug(text: str) -> str:
    """Slug ``text`` for a file-check id, falling back to ``"path"`` when empty.

    A thin wrapper over the shared
    :func:`coding_agent_playbook.grading.check.slug` that pins the file-check
    fallback (the shared helper defaults to ``"criterion"``). Kept as a named
    function so existing ``files.slug`` imports keep working.
    """
    return _slug(text, fallback="path")


class _FileCheck(Check):
    """Shared base for the four deterministic file checks.

    Subclasses set :attr:`kind` (the id prefix) and implement :meth:`_holds` -
    the predicate over the candidate tree (and, for the unchanged check, the
    baseline tree). The base owns the descriptor attributes, the ``available()``
    gate (a candidate tree must be present), and turning the predicate into one
    :class:`CheckResult` with a single :class:`ScopeDetail`.
    """

    cost = CostTier.DETERMINISTIC
    determinism = Determinism.DETERMINISTIC

    #: Per-subclass id prefix (``file_exists``/``file_contains``/...).
    kind: str

    def __init__(self, path: str, *, weight: float = 0.0, required: bool = True) -> None:
        self.path = path
        self.weight = weight
        self.required = required
        self.id = f"{self.kind}:{path}"

    def available(self, ctx: EvalContext) -> bool:
        """True only when a candidate tree is present (the runner sets it)."""
        return ctx.tree is not None

    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult:
        """Run the predicate over the candidate tree into one BOOL result.

        ``measurements`` is ignored - file checks read ``ctx.tree`` /
        ``ctx.baseline_tree`` directly.
        """
        ok = ctx.tree is not None and self._holds(ctx.tree, ctx.baseline_tree)
        score = 1.0 if ok else 0.0
        detail = ScopeDetail(
            evaluator=self.id,
            scope_key=self.path,
            value=score,
            baseline=None,
            bound=None,
            score=score,
            level="ok" if ok else "fail",
            kind="absolute",
        )
        return CheckResult(
            check_id=self.id,
            passed=ok,
            score=score,
            weight=self.weight,
            required=self.required,
            determinism=self.determinism,
            cost=self.cost,
            status="run",
            subresults=(detail,),
        )

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        """Whether the check holds for ``self.path`` under ``tree``."""
        raise NotImplementedError


@register_check("file_exists")
class FileExistsCheck(_FileCheck):
    """``files_created`` - the path is a regular file under the candidate tree."""

    kind = "file_exists"

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        return (tree / self.path).is_file()


@register_check("file_contains")
class FileContainsCheck(_FileCheck):
    """``files_must_contain`` - the file exists and its text matches a regex.

    The id keys on path + pattern (``file_contains:<path>~/<pattern>/``) so two
    patterns over the same file do not collide.
    """

    kind = "file_contains"

    def __init__(
        self,
        path: str,
        pattern: str,
        *,
        weight: float = 0.0,
        required: bool = True,
    ) -> None:
        super().__init__(path, weight=weight, required=required)
        self.pattern = pattern
        self.id = f"{self.kind}:{path}~/{pattern}/"

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        return _file_matches(tree / self.path, self.pattern)


@register_check("file_unchanged")
class FileUnchangedCheck(_FileCheck):
    """``files_unchanged`` - the candidate file is byte-identical to the baseline.

    Requires a baseline tree (the pristine ``setup/`` snapshot); with no baseline
    tree the check cannot hold (``available`` is False, and ``_holds`` grades
    ``False`` defensively).
    """

    kind = "file_unchanged"

    def available(self, ctx: EvalContext) -> bool:
        """True only when both the candidate and baseline trees are present."""
        return ctx.tree is not None and ctx.baseline_tree is not None

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        if baseline_tree is None:
            return False
        return _files_equal(tree / self.path, baseline_tree / self.path)


@register_check("file_forbidden")
class FileForbiddenCheck(_FileCheck):
    """``files_forbidden`` - the path does **not** exist under the candidate tree."""

    kind = "file_forbidden"

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        return not (tree / self.path).exists()


def _file_matches(path: Path, pattern: str) -> bool:
    """True when ``path`` exists and its text matches the regex ``pattern``.

    Copied from ``expected.py`` (deleted in the cutover).
    """
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - unreadable file is rare
        return False
    return re.search(pattern, text) is not None


def _files_equal(a: Path, b: Path) -> bool:
    """True when both files exist and have byte-identical contents.

    Copied from ``expected.py`` (deleted in the cutover).
    """
    if not a.is_file() or not b.is_file():
        return False
    return a.read_bytes() == b.read_bytes()


__all__ = [
    "FileContainsCheck",
    "FileExistsCheck",
    "FileForbiddenCheck",
    "FileUnchangedCheck",
    "slug",
]
