"""Engine module names as tests pin them, checked against the installed package tree.

Two kinds of guard are keyed on module names, and both pass vacuously once a
module moves:

- a probe asserting that a module is *not* loaded: the old name is simply never
  imported again;
- the hook hot path's forbidden engine packages, which were a hand-kept list that
  a new top-level package escaped.

So every engine module a probe pins goes through ``engine_module``, which raises
``StaleModulePin`` when the name no longer resolves, and what a stack must not
import is derived, never listed: every top-level engine module outside
``STDLIB_LEAVES`` (``non_leaf_modules``) and every runtime dependency of the engine
(``runtime_dependency_imports``, read from pyproject.toml). A new top-level package
or a new dependency is forbidden to the hook runtime, the grading kernel and the
leaves until it is admitted on purpose. tests/architecture/test_import_contracts.py
pins pyproject.toml's import-linter contracts to these functions.

Stdlib-only. Only the pytest process imports it, never a probe's child interpreter.
"""

from __future__ import annotations

import functools
import importlib.metadata
import importlib.util
import pkgutil
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator, Set

ENGINE: Final = "coding_agent_playbook"
_PYPROJECT: Final = Path(__file__).resolve().parents[1] / "pyproject.toml"
_REQUIREMENT_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: Top-level engine modules that import only the stdlib and each other. They are
#: the only engine modules the hook runtime and the grading kernel may import, so
#: the dispatch hot path may load them. A module joins only when it is stdlib-only
#: and one of those stacks needs it. A dotted entry (``"catalog.roots"``) admits
#: that module and the docstring-only packages above it, never its siblings.
STDLIB_LEAVES: Final = frozenset(
    {
        "_atomic_io",
        "_pep503",
        "_pyproject_deps",
        "_sentinel",
        "catalog",
        "lockfile",
        "security",
    }
)


class StaleModulePin(AssertionError):
    """A test pins an engine module name that no longer resolves."""


def engine_module(name: str) -> str:
    """Return ``name`` after checking that it resolves to an engine module.

    Raises ``StaleModulePin`` when the module moved or was renamed, so an
    assertion that it is *not* loaded fails instead of passing vacuously.

    Example::

        >>> engine_module("coding_agent_playbook.hook_runtime.dispatch")
        'coding_agent_playbook.hook_runtime.dispatch'
    """
    if not name.startswith(f"{ENGINE}."):
        raise ValueError(f"expected a dotted module name under {ENGINE!r}, got {name!r}")
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:  # a parent package is gone as well
        spec = None
    if spec is None:
        raise StaleModulePin(f"{name!r} no longer resolves: pin the module's new path")
    return name


def child_modules(package: str) -> tuple[str, ...]:
    """Dotted names of the modules and packages directly inside ``package``, sorted.

    Example::

        >>> f"{ENGINE}.hook_runtime" in child_modules(ENGINE)
        True
    """
    spec = importlib.util.find_spec(package)
    if spec is None or spec.submodule_search_locations is None:
        raise ValueError(f"expected an importable package, got {package!r}")
    infos = pkgutil.iter_modules(spec.submodule_search_locations)
    return tuple(sorted(f"{package}.{info.name}" for info in infos))


def _outside(package: str, allowed: Set[str]) -> Iterator[str]:
    for child in child_modules(package):
        if child in allowed:
            continue
        if any(name.startswith(f"{child}.") for name in allowed):
            yield from _outside(child, allowed)
        else:
            yield child


def non_leaf_modules(
    stack: str | None = None, *, root: str = ENGINE, leaves: Set[str] = STDLIB_LEAVES
) -> tuple[str, ...]:
    """The modules under ``root`` that ``stack`` (or, for ``None``, a leaf) must not import.

    Every top-level module except ``stack`` itself and ``leaves``, sorted; under a
    package that holds a dotted leaf, the leaf's siblings are listed instead.

    Example::

        >>> f"{ENGINE}.cli" in non_leaf_modules("hook_runtime")
        True
    """
    allowed = {f"{root}.{leaf}" for leaf in leaves}
    if stack is not None:
        if f"{root}.{stack}" not in child_modules(root):
            raise ValueError(f"{stack!r} is not a top-level package of {root!r}")
        allowed.add(f"{root}.{stack}")
    return tuple(_outside(root, allowed))


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@functools.cache
def runtime_dependency_imports(pyproject: Path = _PYPROJECT) -> tuple[str, ...]:
    """Top-level import names of the engine's ``[project].dependencies``, sorted.

    Example::

        >>> runtime_dependency_imports()
        ('jinja2', 'packaging', 'yaml')
    """
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    wanted: set[str] = set()
    for requirement in project["dependencies"]:
        match = _REQUIREMENT_NAME.match(requirement)
        if match is None:
            raise ValueError(f"unparseable requirement {requirement!r} in {pyproject}")
        wanted.add(_normalized(match.group()))
    provided = importlib.metadata.packages_distributions().items()
    names = {name for name, dists in provided if wanted & {_normalized(d) for d in dists}}
    return tuple(sorted(name for name in names if not name.startswith("_")))
