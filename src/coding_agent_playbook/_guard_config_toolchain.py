"""Hook config sync derives from the repository's pyproject (specs/prK-hook-pack.md §E.3).

Rendered into the hook records of ``guard_config.json`` (``gc:<hook-id>.*``),
never declared as consumer config keys, so the project's own files are their
one source. Machine-independent: ``pyproject.toml`` and the detector facts
only (§D.8.3).

- toolchain-missing-hint: ``install_hint``, how this project installs its dev
  tooling (``package_manager`` plus the dev extra or dependency group:
  ``uv sync --extra dev``, ``uv sync --group dev``, ``poetry install --with
  dev``, ``pip install -e ".[dev]"``), and ``cz_install_hint``, the same
  command when commitizen is a dev dependency, else ``""`` (the hook then
  suggests a user-level ``pipx install commitizen``);
- pytest-conventions-feedback: ``asyncio_marks``, whether ``async def test_*``
  needs ``@pytest.mark.asyncio``: pytest-asyncio is a detected framework (the
  rule body's own ``has_framework("pytest-asyncio")``) and
  ``[tool.pytest.ini_options] asyncio_mode`` is not ``auto``.
"""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.detector.pyproject_deps import DEV_GROUP_NAMES, parse_dep_name

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = [
    "PYTEST_HOOK_ID",
    "TOOLCHAIN_HOOK_ID",
    "ToolchainInputs",
    "asyncio_marks_required",
    "derived_hook_config",
    "install_hint",
    "read_toolchain_inputs",
    "with_derived_config",
]

TOOLCHAIN_HOOK_ID: Final = "toolchain-missing-hint"
PYTEST_HOOK_ID: Final = "pytest-conventions-feedback"
_PREFERRED: Final = "dev"


@dataclass(frozen=True)
class ToolchainInputs:
    """The derived values; empty strings when the project gives no answer.

    Example: ``ToolchainInputs(install_hint="uv sync --extra dev", cz_install_hint="")``.
    """

    install_hint: str = ""
    cz_install_hint: str = ""
    asyncio_marks: bool = False


def read_toolchain_inputs(repo_root: Path, facts: Mapping[str, Any]) -> ToolchainInputs:
    """The derived values of ``repo_root`` (its ``pyproject.toml``) and its detector ``facts``.

    A missing or malformed pyproject counts as an empty one.

    Example::

        >>> read_toolchain_inputs(Path("/no/such/repo"), {}).install_hint
        ''
    """
    pyproject = _load_pyproject(repo_root / "pyproject.toml")
    manager = facts.get("package_manager")
    hint = install_hint(manager if isinstance(manager, str) else None, pyproject)
    return ToolchainInputs(
        install_hint=hint,
        cz_install_hint=hint if hint and _dev_has(pyproject, "commitizen") else "",
        asyncio_marks=asyncio_marks_required(facts, pyproject),
    )


def install_hint(package_manager: str | None, pyproject: Mapping[str, Any]) -> str:
    """The command that installs the project's dev tooling, or ``""`` without a manager.

    Example::

        >>> install_hint("uv", {"project": {"optional-dependencies": {"dev": ["ruff"]}}})
        'uv sync --extra dev'
    """
    extra = _dev_name(_table(_table(pyproject, "project"), "optional-dependencies"))
    group = _dev_name(_table(pyproject, "dependency-groups"))
    if package_manager == "uv":
        if extra:
            return f"uv sync --extra {extra}"
        return f"uv sync --group {group}" if group else "uv sync"
    if package_manager == "poetry":
        poetry_groups = _table(_table(_table(pyproject, "tool"), "poetry"), "group")
        return f"poetry install --with {_dev_name(poetry_groups) or _PREFERRED}"
    if package_manager in ("pip", "pip-tools"):
        if extra:
            return f'pip install -e ".[{extra}]"'
        return f"pip install --group {group}" if group else "pip install -e ."
    return ""


def asyncio_marks_required(facts: Mapping[str, Any], pyproject: Mapping[str, Any]) -> bool:
    """Whether an ``async def test_*`` needs ``@pytest.mark.asyncio`` in this project.

    Example::

        >>> asyncio_marks_required({"frameworks": {"pytest-asyncio": ""}}, {})
        True
    """
    frameworks = facts.get("frameworks")
    if not isinstance(frameworks, dict) or "pytest-asyncio" not in frameworks:
        return False
    options = _table(_table(_table(pyproject, "tool"), "pytest"), "ini_options")
    return options.get("asyncio_mode") != "auto"


def derived_hook_config(inputs: ToolchainInputs) -> dict[str, dict[str, Any]]:
    """``hook id -> config keys`` to add to that hook's every handler.

    Example::

        >>> derived_hook_config(ToolchainInputs())["pytest-conventions-feedback"]
        {'asyncio_marks': False}
    """
    return {
        TOOLCHAIN_HOOK_ID: {
            "install_hint": inputs.install_hint,
            "cz_install_hint": inputs.cz_install_hint,
        },
        PYTEST_HOOK_ID: {"asyncio_marks": inputs.asyncio_marks},
    }


def with_derived_config(
    record: Mapping[str, Any], derived: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """``record`` (a ``ResolvedHook.to_json()``) with its derived keys in every handler config.

    Any other hook's record comes back unchanged (a copy).

    Example::

        >>> with_derived_config({"id": "x", "handlers": {}}, {"y": {"k": 1}})
        {'id': 'x', 'handlers': {}}
    """
    updated = copy.deepcopy(dict(record))
    extra = derived.get(str(updated.get("id")))
    handlers = updated.get("handlers")
    if extra is None or not isinstance(handlers, dict):
        return updated
    for handler in handlers.values():
        if isinstance(handler, dict):
            handler["config"] = {**handler.get("config", {}), **copy.deepcopy(dict(extra))}
    return updated


def _load_pyproject(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return {}


def _table(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def _dev_name(groups: Mapping[str, Any]) -> str:
    """``dev`` when declared, else the first other dev-group name declared (sorted), else ``""``."""
    if _PREFERRED in groups:
        return _PREFERRED
    return next((name for name in sorted(groups) if name in DEV_GROUP_NAMES), "")


def _dev_has(pyproject: Mapping[str, Any], package: str) -> bool:
    """Whether ``package`` is in the dev extra or dependency group :func:`install_hint` names."""
    for groups in (
        _table(_table(pyproject, "project"), "optional-dependencies"),
        _table(pyproject, "dependency-groups"),
    ):
        specs = groups.get(_dev_name(groups))
        if isinstance(specs, list) and any(
            isinstance(spec, str) and parse_dep_name(spec) == package for spec in specs
        ):
            return True
    return _poetry_dev_has(pyproject, package)


def _poetry_dev_has(pyproject: Mapping[str, Any], package: str) -> bool:
    poetry = _table(_table(pyproject, "tool"), "poetry")
    groups = _table(poetry, "group")
    deps = _table(_table(groups, _dev_name(groups) or _PREFERRED), "dependencies")
    return package in deps or package in _table(poetry, "dev-dependencies")
