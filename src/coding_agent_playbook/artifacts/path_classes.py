"""Eval-task paths shared by the eval hooks and sync (specs/prK-hook-pack.md §E.0.5, §E.1).

eval-task-authoring-lint and guard-eval-fixtures both locate an edited file's
task directory (``.../eval_tasks/<id>/``); sync renders :data:`FIXTURE_GLOBS`
as ``guard_config.eval.fixture_globs`` and the ``eval_fixture`` path class
from the same constant; :data:`TEST_PATH_GLOBS` is test code. Stdlib-only (``re``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = ["FIXTURE_GLOBS", "TEST_PATH_GLOBS", "TaskPath", "task_path"]

#: The frozen eval fixtures (runtime glob grammar); an engine constant (§E.0.5 ``eval``).
FIXTURE_GLOBS: Final[tuple[str, ...]] = ("**/eval_tasks/*/setup/**",)
TEST_PATH_GLOBS: Final = ("**/tests/**", "**/test/**", "test_*.py", "*_test.py", "conftest.py")

_TASK = re.compile(r"(?P<dir>(?:.*/)?eval_tasks/(?P<id>[^/]+))(?:/(?P<rest>.*))?")


@dataclass(frozen=True, slots=True)
class TaskPath:
    """Where a repo-relative path sits in an eval task.

    ``task_dir`` is the repo-relative ``.../eval_tasks/<id>``, ``rest`` the
    path below it (``""`` for the directory itself).
    """

    task_dir: str
    task_id: str
    rest: str

    @property
    def in_setup(self) -> bool:
        """Whether the path is the task's ``setup/`` dir or anything under it."""
        return self.rest == "setup" or self.rest.startswith("setup/")


def task_path(repo_rel: str) -> TaskPath | None:
    """The eval task holding ``repo_rel``, or ``None`` outside every ``eval_tasks/<id>/``.

    Example::

        >>> task_path("pkg/eval_tasks/t1/setup/app.py").task_dir
        'pkg/eval_tasks/t1'
    """
    match = _TASK.fullmatch(repo_rel)
    if match is None:
        return None
    return TaskPath(match["dir"], match["id"], match["rest"] or "")
