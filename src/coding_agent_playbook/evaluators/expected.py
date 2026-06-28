"""Expected-outcome evaluators — ``[expected]`` file checks, generalized (R3).

The four :class:`~coding_agent_playbook.evals.task.ExpectedOutcome` checks are
the same shape as every other evaluator: a graded BOOL over a scope. R1 compiled
them *inline* in :mod:`coding_agent_playbook.evals.scoring`; R3 lifts them into
real :class:`~coding_agent_playbook.evaluators.registry.Evaluator` instances so
``[expected]`` flows through the one :func:`~coding_agent_playbook.evaluators.grade.grade`
call that already handles ``[metrics]`` (static + execution) and ``[rubric]``
(judged) — one model, one report.

Like :class:`~coding_agent_playbook.evaluators.judged.JudgedCriterion`, these are
**parameterized** evaluators the eval block-compiler instantiates once per
``[expected]`` entry (each carries its own path/pattern), so they are deliberately
**not** registered singletons (no ``@register_evaluator``).

Each is ``value_kind=BOOL``, ``determinism=DETERMINISTIC``,
``higher_is_worse=False`` and carries a hard ``fail`` floor of ``1.0`` so a
``0.0`` (the check did not hold) gates the report — *must-be-true* semantics. They
read the **candidate tree** (:attr:`EvalContext.tree`) and, for the unchanged
check, the **baseline tree** (:attr:`EvalContext.baseline_tree`); both are set by
the runner and ignored by the static/execution/judged families.

:meth:`available` is ``True`` only when ``ctx.tree`` is set, so these never fire
in a tree-less context (e.g. a static-only metrics run).
"""

from __future__ import annotations

import re
from abc import abstractmethod
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.parse import scope_key
from coding_agent_playbook.evaluators.registry import Evaluator
from coding_agent_playbook.evaluators.scope import Determinism, Scope, ValueKind
from coding_agent_playbook.evaluators.types import (
    AbsoluteThreshold,
    Measurement,
    RegressionPolicy,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evaluators.types import EvalContext

#: A BOOL check is must-be-true: a ``fail`` floor of ``1.0`` means a ``0.0``
#: measurement (the check did not hold) breaches absolutely (gate failure).
_MUST_BE_TRUE = AbsoluteThreshold(fail=1.0)


class _ExpectedEvaluator(Evaluator):
    """Shared base for the four ``[expected]`` BOOL evaluators.

    Subclasses set :attr:`kind` (the slug used in the evaluator name) and
    implement :meth:`_holds` — the predicate over the candidate tree (and, for
    the unchanged check, the baseline tree). The base owns the descriptor
    attributes, the ``available()`` gate (a candidate tree must be present), and
    turning the predicate into one BOOL :class:`Measurement`.

    Scope is :attr:`Scope.FILE`: each instance grades one file path keyed on its
    own ``scope_key`` (the path), mirroring the FILE-scope static metrics.
    """

    #: Per-subclass slug used in ``expected:<kind>:<path>``.
    kind: str

    scope = Scope.FILE
    value_kind = ValueKind.BOOL
    determinism = Determinism.DETERMINISTIC
    higher_is_worse = False
    requires = None
    needs_project = False

    def __init__(self, path: str, *, scope_label: str | None = None) -> None:
        """``path`` is the tree-relative file this check applies to.

        ``scope_label`` overrides the scope key (the ``file_contains`` check
        keys on ``<path>~/<pattern>/`` so two patterns over the same file do not
        collide); it defaults to ``path``.
        """
        self.path = path
        self._scope_label = scope_label if scope_label is not None else path
        self.name = f"expected:{self.kind}:{self._scope_label}"
        # Must-be-true: a 0.0 BOOL breaches the absolute fail floor.
        self.default_absolute = _MUST_BE_TRUE
        # Deterministic check: any worsening (True -> False) is a regression too,
        # but the absolute floor already gates a False outright.
        self.default_regression = RegressionPolicy(max_worsening=0.0)
        self.default_weight = 0.0

    def available(self, ctx: EvalContext) -> bool:
        """True only when a candidate tree is present (the runner sets it)."""
        return ctx.tree is not None

    def evaluate(self, ctx: EvalContext) -> list[Measurement]:
        """Run the predicate over the candidate tree into one BOOL measurement.

        Returns ``[]`` when no candidate tree is present so a stray call in a
        tree-less context is a no-op rather than a crash.
        """
        if ctx.tree is None:
            return []
        ok = self._holds(ctx.tree, ctx.baseline_tree)
        return [
            Measurement(
                evaluator=self.name,
                scope_key=scope_key(self._scope_label, None),
                value=1.0 if ok else 0.0,
            )
        ]

    @abstractmethod
    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        """Whether the check holds for ``self.path`` under ``tree``."""


class FileExists(_ExpectedEvaluator):
    """``files_created`` — the path is a regular file under the candidate tree."""

    kind = "file_exists"

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        return (tree / self.path).is_file()


class FileContains(_ExpectedEvaluator):
    """``files_must_contain`` — the file exists and its text matches a regex."""

    kind = "file_contains"

    def __init__(self, path: str, pattern: str) -> None:
        super().__init__(path, scope_label=f"{path}~/{pattern}/")
        self.pattern = pattern

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        return _file_matches(tree / self.path, self.pattern)


class FileUnchanged(_ExpectedEvaluator):
    """``files_unchanged`` — the candidate file is byte-identical to the baseline.

    Requires a baseline tree (the pristine ``setup/`` snapshot); with no baseline
    tree the check cannot hold and grades ``False``.
    """

    kind = "file_unchanged"

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        if baseline_tree is None:
            return False
        return _files_equal(tree / self.path, baseline_tree / self.path)


class FileForbidden(_ExpectedEvaluator):
    """``files_forbidden`` — the path does **not** exist under the candidate tree."""

    kind = "file_forbidden"

    def _holds(self, tree: Path, baseline_tree: Path | None) -> bool:
        return not (tree / self.path).exists()


def _file_matches(path: Path, pattern: str) -> bool:
    """True when ``path`` exists and its text matches the regex ``pattern``."""
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - unreadable file is rare
        return False
    return re.search(pattern, text) is not None


def _files_equal(a: Path, b: Path) -> bool:
    """True when both files exist and have byte-identical contents."""
    if not a.is_file() or not b.is_file():
        return False
    return a.read_bytes() == b.read_bytes()
