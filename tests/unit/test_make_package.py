"""Regression test for the ``make_package`` fixture in ``tests/conftest.py``.

Python's import system caches the listing of each ``sys.path`` directory and
reads it again only when the directory's mtime changes. The kernel stamps
mtimes from a coarse clock (one tick is 4 ms at HZ=250), so a package written
just after an import from the same root can leave the root's mtime unchanged
and stay invisible. ``test_set_level_rule[H14]`` failed that way in about four
runs out of five.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def test_a_package_built_after_an_import_from_the_same_root_is_importable(
    make_package: Callable[..., str],
) -> None:
    first = make_package("pkg_built_first")
    module_file = importlib.import_module(first).__file__
    assert module_file is not None
    root = Path(module_file).parents[1]
    cached_mtime = os.stat(root).st_mtime_ns

    second = make_package("pkg_built_second")
    # A write in the same clock tick as the import leaves this mtime in place.
    os.utime(root, ns=(cached_mtime, cached_mtime))

    assert importlib.import_module(second).__name__ == second
