"""Eval-sample paths shared by the eval hooks and sync (specs/prK-hook-pack.md §E.0.5, §E.1).

eval-sample-authoring-lint and guard-eval-fixtures both locate an edited file's
sample directory (``.../eval_samples/<id>/``); sync renders :data:`FIXTURE_GLOBS`
as ``guard_config.eval.fixture_globs`` and the ``eval_fixture`` path class
from the same constant; :data:`TEST_PATH_GLOBS` names the test-code paths. Stdlib-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = ["FIXTURE_GLOBS", "TEST_PATH_GLOBS", "SamplePath", "sample_path"]

#: The frozen eval fixtures (runtime glob grammar); an engine constant (§E.0.5 ``eval``).
FIXTURE_GLOBS: Final[tuple[str, ...]] = ("**/eval_samples/*/setup/**",)
TEST_PATH_GLOBS: Final = ("**/tests/**", "**/test/**", "test_*.py", "*_test.py", "conftest.py")

_SAMPLE = re.compile(r"(?P<dir>(?:.*/)?eval_samples/(?P<id>[^/]+))(?:/(?P<rest>.*))?")


@dataclass(frozen=True, slots=True)
class SamplePath:
    """Where a repo-relative path sits in an eval sample.

    ``sample_dir`` is the repo-relative ``.../eval_samples/<id>``, ``rest`` the
    path below it (``""`` for the directory itself).
    """

    sample_dir: str
    sample_id: str
    rest: str

    @property
    def in_setup(self) -> bool:
        """Whether the path is the sample's ``setup/`` dir or anything under it."""
        return self.rest == "setup" or self.rest.startswith("setup/")


def sample_path(repo_rel: str) -> SamplePath | None:
    """The eval sample holding ``repo_rel``, or ``None`` outside every ``eval_samples/<id>/``.

    Example::

        >>> sample_path("pkg/eval_samples/t1/setup/app.py").sample_dir
        'pkg/eval_samples/t1'
    """
    match = _SAMPLE.fullmatch(repo_rel)
    if match is None:
        return None
    return SamplePath(match["dir"], match["id"], match["rest"] or "")
