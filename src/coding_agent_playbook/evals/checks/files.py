"""Deterministic file checks: the ``[expected]`` predicates as ``Check``.

The four ``[expected]`` file checks (``files_created``/``files_must_contain``/
``files_unchanged``/``files_forbidden``) are first-class
:class:`~coding_agent_playbook.grading.check.Check` instances. Unlike the
metric-backed checks these ignore the
:class:`~coding_agent_playbook.grading.check.MeasurementSet` and read the
candidate tree (:attr:`EvalContext.tree`) - and, for the unchanged check, the
baseline tree (:attr:`EvalContext.baseline_tree`) - directly.

In eval scoring ``ctx.tree`` is not the live candidate repo: :func:`freeze_file_inputs`
reads the paths these checks name into engine memory before the scoring suite
runs, and scoring writes them to a fresh temporary tree only after the suite
exited. Why: the suite runs agent code as the same user, so a ``conftest.py``
could run edited code and then put the original bytes back, a test could create
a file the agent never wrote, and a copy kept on disk during the suite could be
rewritten.

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
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.check import Check
from coding_agent_playbook.grading.check import slug as _slug
from coding_agent_playbook.grading.check_registry import register_check
from coding_agent_playbook.grading.measuring import iter_checks
from coding_agent_playbook.grading.scope import CostTier, Determinism
from coding_agent_playbook.grading.types import CheckResult, ScopeDetail

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
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

    Requires a baseline tree (in eval scoring, the sample's ``setup/`` as the
    engine read it before any agent ran); with no baseline
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


@dataclass(frozen=True)
class FrozenFileInputs:
    """The paths the file checks name, as they were when frozen, held in engine memory.

    ``files`` maps a relative POSIX path to its bytes and ``dirs`` names the paths
    that were directories; any other named path was missing.

    Example::

        >>> FrozenFileInputs({"a.py": b"x"}, frozenset()).write_tree(Path(tmp))  # doctest: +SKIP
        PosixPath('/tmp/...')
    """

    files: Mapping[str, bytes]
    dirs: frozenset[str]

    def write_tree(self, dest: Path) -> Path:
        """Write the frozen paths under ``dest`` (created if missing): files' bytes, directories."""
        dest.mkdir(parents=True, exist_ok=True)
        for rel in sorted(self.dirs):
            (dest / rel).mkdir(parents=True, exist_ok=True)
        for rel, data in self.files.items():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(data)
        return dest


def freeze_file_inputs(checks: Sequence[Check], tree: Path) -> FrozenFileInputs:
    """Read each path a file check under ``checks`` names from ``tree`` into memory.

    A file is read by content (a symlink is followed, so a later change to its
    target does not reach the frozen bytes), a directory is recorded as one, and a
    missing path stays missing, so every file check answers over
    :meth:`FrozenFileInputs.write_tree` as it would have over ``tree`` at this
    moment. Nothing is written: a copy on disk could be rewritten by the agent
    code the scoring suite runs. An unreadable file becomes an empty one: it
    still exists. A path that is absolute or climbs out with ``..`` raises
    :exc:`ValueError` naming it, as it would grade a file outside the tree.

    Example::

        >>> freeze_file_inputs(rubric.checks, candidate.tree).files  # doctest: +SKIP
        mappingproxy({'mod.py': b'def f(): ...'})
    """
    files: dict[str, bytes] = {}
    dirs: set[str] = set()
    for check in iter_checks(checks):
        if isinstance(check, _FileCheck):
            _freeze_path(check, tree, files, dirs)
    return FrozenFileInputs(MappingProxyType(files), frozenset(dirs))


def _freeze_path(check: _FileCheck, tree: Path, files: dict[str, bytes], dirs: set[str]) -> None:
    """Record ``check.path`` of ``tree`` in ``files`` (its bytes) or ``dirs`` (a directory)."""
    rel = PurePosixPath(check.path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(
            f"file check {check.id!r} names {check.path!r}; "
            "expected a relative path inside the candidate tree"
        )
    source = tree / rel
    if source.is_file():
        files[rel.as_posix()] = _bytes_or_empty(source)
    elif source.exists():
        dirs.add(rel.as_posix())


def _bytes_or_empty(source: Path) -> bytes:
    """``source``'s bytes; empty when it cannot be read."""
    try:
        return source.read_bytes()
    except OSError:
        return b""


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
    "FrozenFileInputs",
    "freeze_file_inputs",
    "slug",
]
