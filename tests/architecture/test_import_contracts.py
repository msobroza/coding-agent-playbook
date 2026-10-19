"""The import contracts in pyproject.toml hold, and their package lists track the tree (ADR 0002).

``test_import_contracts_hold`` runs import-linter in a fresh interpreter from the
repository root, so ``pytest -q`` enforces the layers, the stdlib leaves and the two
stacks built on them, command independence and the private-module rule without a
fifth CI command. The other tests close the gaps import-linter leaves open: it
skips an optional layer that does not exist (a typo would never be checked),
accepts an ``exhaustive_ignores`` entry that names nothing, cannot derive a
forbidden list from the tree, and checks only the contracts the table still lists.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Final

import pytest

from tests.engine_modules import (
    ENGINE,
    STDLIB_LEAVES,
    child_modules,
    non_leaf_modules,
    runtime_dependency_imports,
)
from tests.import_probe import probe_env

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_LINT_TIMEOUT_S: Final = 120
#: No cache: the run must see this checkout, and must not write .import_linter_cache/.
_LINT: Final = (
    "import sys; from importlinter.cli import lint_imports; "
    "sys.exit(lint_imports(config_filename='pyproject.toml', no_cache=True, no_logo=True))"
)
#: The contracts of ADR 0002, in pyproject.toml order. The lint run checks only what
#: the table configures, so a contract deleted from it would otherwise go unnoticed.
_CONTRACT_IDS: Final = (
    "engine-layers",
    "stdlib-leaves",
    "hook-runtime-stack",
    "grading-kernel",
    "command-independence",
    "private-modules",
    "twins-use-judges",
)
#: The top-level packages of ADR 0002's target layout that sit in engine-layers.
#: hook_runtime is a separate stack (hook-runtime-stack), never a layer.
_TARGET_PACKAGES: Final = frozenset(
    {
        "_plugin_registry",
        "adapters",
        "agent_harness",
        "artifacts",
        "catalog",
        "cli",
        "commands",
        "config",
        "detector",
        "evals",
        "generated_output",
        "grading",
        "hooks",
        "lockfile",
        "metrics_gate",
        "precommit",
        "rendering",
        "security",
        "skills",
        "sync",
        "toml_writer",
        "validation",
    }
)


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _contracts() -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = _pyproject()["tool"]["importlinter"]["contracts"]
    return contracts


def _contract(contract_id: str) -> dict[str, Any]:
    matches = [c for c in _contracts() if c["id"] == contract_id]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one [[tool.importlinter.contracts]] with id {contract_id!r}, "
            f"found {len(matches)}"
        )
    return matches[0]


def _layer_names(layers: list[str]) -> list[tuple[str, bool]]:
    """Each layer name with whether it is optional (parenthesised), in layer order."""
    names = []
    for layer in layers:
        separator = "|" if "|" in layer else ":"
        for raw in layer.split(separator):
            name = raw.strip()
            optional = name.startswith("(") and name.endswith(")")
            names.append((name.strip("()"), optional))
    return names


def _top_level_names() -> set[str]:
    return {name.rsplit(".", 1)[1] for name in child_modules(ENGINE)}


def test_import_linter_is_pinned_exactly() -> None:
    # The private_modules type uses importlinter.application.contract_utils, which
    # is not documented API: an upgrade is a deliberate PR that re-runs this directory.
    dev: list[str] = _pyproject()["project"]["optional-dependencies"]["dev"]

    pins = [requirement for requirement in dev if requirement.startswith("import-linter")]

    assert pins == [f"import-linter=={importlib.metadata.version('import-linter')}"], dev


def test_pyproject_configures_every_contract() -> None:
    assert [contract["id"] for contract in _contracts()] == list(_CONTRACT_IDS)


def test_import_contracts_hold() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _LINT],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_LINT_TIMEOUT_S,
        env={**probe_env(), "COLUMNS": "200"},
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Contracts: {len(_CONTRACT_IDS)} kept, 0 broken." in result.stdout, result.stdout


@pytest.mark.parametrize(
    ("contract_id", "stack"),
    [("hook-runtime-stack", "hook_runtime"), ("grading-kernel", "evaluators")],
)
def test_stack_contract_forbids_every_non_leaf_module(contract_id: str, stack: str) -> None:
    contract = _contract(contract_id)

    assert contract["source_modules"] == [f"{ENGINE}.{stack}"]
    expected = [*non_leaf_modules(stack), *runtime_dependency_imports()]
    assert contract["forbidden_modules"] == expected


def test_leaf_contract_covers_every_stdlib_leaf() -> None:
    contract = _contract("stdlib-leaves")

    assert contract["source_modules"] == sorted(f"{ENGINE}.{leaf}" for leaf in STDLIB_LEAVES)
    expected = [*non_leaf_modules(), *runtime_dependency_imports()]
    assert contract["forbidden_modules"] == expected


def test_layer_names_are_target_packages() -> None:
    names = _layer_names(_contract("engine-layers")["layers"])

    assert sorted(name for name, _ in names if name not in _TARGET_PACKAGES) == []


def test_a_layer_is_optional_exactly_until_its_package_exists() -> None:
    existing = _top_level_names()
    names = _layer_names(_contract("engine-layers")["layers"])

    assert sorted(name for name, optional in names if optional and name in existing) == []
    assert sorted(name for name, optional in names if not optional and name not in existing) == []


def test_exhaustive_ignores_are_exactly_the_unplaced_top_level_modules() -> None:
    contract = _contract("engine-layers")
    placed = {name for name, _ in _layer_names(contract["layers"])}

    assert contract["exhaustive"] is True
    assert contract["exhaustive_ignores"] == sorted(_top_level_names() - placed)


#: The guard-twin subpackage: its public modules are commands too (CONTEXT: Guard twin).
_TWINS: Final = f"{ENGINE}.commands.twins"
#: A public twins/ module that is a shared helper, not a command: init reads it (6.3.3).
_TWIN_SHARED_HELPERS: Final = frozenset({f"{_TWINS}.policy"})


def _public_children(package: str) -> list[str]:
    return [name for name in child_modules(package) if not name.rsplit(".", 1)[1].startswith("_")]


def test_command_independence_lists_every_command() -> None:
    flat = [name for name in _public_children(f"{ENGINE}.commands") if name != _TWINS]
    twins = [name for name in _public_children(_TWINS) if name not in _TWIN_SHARED_HELPERS]

    assert _contract("command-independence")["modules"] == sorted(flat + twins)


@pytest.mark.parametrize(
    ("layers", "expected"),
    [
        (["cli", "(sync)"], [("cli", False), ("sync", True)]),
        (["evals | (precommit)"], [("evals", False), ("precommit", True)]),
        (["detector : lockfile"], [("detector", False), ("lockfile", False)]),
    ],
)
def test_layer_names_reads_optional_and_sibling_layers(
    layers: list[str], expected: list[tuple[str, bool]]
) -> None:
    assert _layer_names(layers) == expected


def test_twins_use_judges_forbids_only_direct_handler_imports() -> None:
    contract = _contract("twins-use-judges")

    assert contract["type"] == "forbidden"
    assert contract["source_modules"] == [_TWINS]
    assert contract["forbidden_modules"] == [f"{ENGINE}.hook_runtime.handlers"]
    assert contract["allow_indirect_imports"] == "true"
    assert "ignore_imports" not in contract
