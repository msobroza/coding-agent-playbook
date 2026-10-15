"""The dependency tables of a parsed ``pyproject.toml``, stdlib-only (SPEC §8; specs/prK-hook-pack.md §E.1).

``detector.detect()`` builds its ``dependencies`` / ``dev_dependencies`` facts
from these functions, and resync-on-detector-input-change compares an edited
``pyproject.toml`` against the names sync baked from those facts. The hook
runtime may not import ``detector`` on its cheap path (it imports
``packaging``), so the parser lives here, stdlib-only, and both sides share
it: the comparison can never disagree with the detector.

Names are PEP 503-normalized through ``_pep503`` (``pytest_asyncio`` is
``pytest-asyncio``), the one normalization the §E.4 dependency guard and its
twin also use; :func:`manifest_dependency_names` is their view of every
direct dependency.

Malformed tables (a string where a list belongs, a list where a table
belongs) contribute nothing; ``detect()`` never raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook._pep503 import canonical_name, requirement_name, split_requirement

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = [
    "DEV_GROUP_NAMES",
    "dependency_names",
    "dependency_specs",
    "manifest_dependency_names",
    "parse_dep_name",
    "parse_dep_spec",
]

#: Optional-dependency / dependency-group names whose contents count as dev
#: dependencies. Conservative but extensible: adding e.g. "docs" here would
#: extend coverage to documentation tooling.
DEV_GROUP_NAMES: Final = frozenset(
    {"dev", "test", "tests", "lint", "type", "typecheck", "dev-deps"}
)


def parse_dep_name(spec: str) -> str:
    """The PEP 503 name of a PEP 508 dependency spec (``""`` when it names none).

    Example::

        >>> parse_dep_name("Torch[cuda]>=2; os_name == 'nt'")
        'torch'
    """
    return requirement_name(spec)


def parse_dep_spec(spec: str) -> tuple[str, str]:
    """``(name, version_constraint)`` of a PEP 508 spec; the constraint is ``""`` without one.

    The marker (``; python_version >= '3.10'``) and the extras block are
    dropped; the constraint keeps its operator and value, never leading space.
    It is cut from the text after the *raw* name, so normalizing the name
    (``Foo_Bar`` -> ``foo-bar``) never loses it.

    Example::

        >>> parse_dep_spec("fastapi [all] == 0.110 ; python_version >= '3.10'")
        ('fastapi', '== 0.110')
    """
    name, tail = split_requirement(spec)
    if not name:
        return "", ""
    tail = tail.strip()
    semi = tail.find(";")
    if semi >= 0:
        tail = tail[:semi].rstrip()
    if tail.startswith("["):
        close = tail.find("]")
        if close >= 0:
            tail = tail[close + 1 :].lstrip()
    return name, tail.lstrip()


def dependency_specs(pyproject: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """``(runtime, dev)`` name -> constraint maps: ``[project].dependencies``, then the dev groups.

    Dev groups are the :data:`DEV_GROUP_NAMES` of PEP 621
    ``optional-dependencies`` and PEP 735 ``dependency-groups``.

    Example::

        >>> dependency_specs({"project": {"dependencies": ["torch>=2"]}})
        ({'torch': '>=2'}, {})
    """
    project = _table(pyproject.get("project"))
    runtime = _specs(_list(project.get("dependencies")))
    groups = (
        _table(project.get("optional-dependencies")),
        _table(pyproject.get("dependency-groups")),
    )
    dev: dict[str, str] = {}
    for table in groups:
        for group, entries in table.items():
            if group in DEV_GROUP_NAMES:
                dev.update(_specs(_list(entries)))
    return runtime, dev


def dependency_names(pyproject: Mapping[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    """``(runtime, dev)`` dependency name sets, as the detector would record them.

    Example::

        >>> dependency_names({"project": {"dependencies": ["Torch>=2"]}})
        (frozenset({'torch'}), frozenset())
    """
    runtime, dev = dependency_specs(pyproject)
    return frozenset(runtime), frozenset(dev)


def manifest_dependency_names(pyproject: Mapping[str, Any]) -> frozenset[str]:
    """Every direct dependency a ``pyproject.toml`` declares, in any group, PEP 503-normalized.

    Reads ``[project].dependencies``, every ``optional-dependencies`` and
    ``[dependency-groups]`` group, and Poetry's ``dependencies``,
    ``dev-dependencies`` and ``group.<name>.dependencies`` (Poetry's
    ``python`` entry is the interpreter, not a package).

    Example::

        >>> sorted(manifest_dependency_names({"tool": {"poetry": {"dependencies": {"python": "^3", "Django": "^5"}}}}))
        ['django']
    """
    project = _table(pyproject.get("project"))
    specs = list(_list(project.get("dependencies")))
    for table in (
        _table(project.get("optional-dependencies")),
        _table(pyproject.get("dependency-groups")),
    ):
        for entries in table.values():
            specs.extend(_list(entries))
    names = {requirement_name(spec) for spec in specs if isinstance(spec, str)}
    names.update(canonical_name(key) for key in _poetry_keys(pyproject) if key.lower() != "python")
    names.discard("")
    return frozenset(names)


def _poetry_keys(pyproject: Mapping[str, Any]) -> list[str]:
    poetry = _table(_table(pyproject.get("tool")).get("poetry"))
    keys = [*_table(poetry.get("dependencies")), *_table(poetry.get("dev-dependencies"))]
    for group in _table(poetry.get("group")).values():
        keys.extend(_table(_table(group).get("dependencies")))
    return keys


def _specs(entries: Iterable[object]) -> dict[str, str]:
    found: dict[str, str] = {}
    for raw in entries:
        if not isinstance(raw, str):
            continue  # PEP 735 ``{include-group = ...}`` tables and junk
        name, version = parse_dep_spec(raw)
        if name:
            found[name] = version
    return found


def _table(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []
