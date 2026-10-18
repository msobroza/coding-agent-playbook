"""``tests.engine_modules``: pinned engine names resolve, and forbidden lists track the tree."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.engine_modules import (
    ENGINE,
    STDLIB_LEAVES,
    StaleModulePin,
    child_modules,
    engine_module,
    non_leaf_modules,
    runtime_dependency_imports,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_engine_module_returns_a_name_that_resolves() -> None:
    assert engine_module(f"{ENGINE}.hook_runtime.dispatch") == f"{ENGINE}.hook_runtime.dispatch"


@pytest.mark.parametrize("name", [f"{ENGINE}.no_such_module", f"{ENGINE}.no_such_package.x"])
def test_engine_module_fails_for_a_moved_module(name: str) -> None:
    with pytest.raises(StaleModulePin, match="no longer resolves"):
        engine_module(name)


def test_engine_module_rejects_a_name_outside_the_engine() -> None:
    with pytest.raises(ValueError, match="under 'coding_agent_playbook'"):
        engine_module("json")


@pytest.mark.parametrize("leaf", sorted(STDLIB_LEAVES))
def test_every_stdlib_leaf_resolves(leaf: str) -> None:
    engine_module(f"{ENGINE}.{leaf}")


def test_child_modules_lists_modules_and_packages(make_package: Callable[..., str]) -> None:
    make_package("lane0_pkg")
    make_package("lane0_pkg.sub")

    assert child_modules("lane0_pkg") == ("lane0_pkg.sub",)


def test_child_modules_rejects_a_plain_module() -> None:
    with pytest.raises(ValueError, match="importable package"):
        child_modules(f"{ENGINE}.gate_scan")


def test_non_leaf_modules_forbids_a_new_top_level_package(
    make_package: Callable[..., str],
) -> None:
    for name in ("lane0_eng", "lane0_eng.runtime", "lane0_eng.leaf", "lane0_eng.brand_new"):
        make_package(name)

    forbidden = non_leaf_modules("runtime", root="lane0_eng", leaves={"leaf"})

    assert forbidden == ("lane0_eng.brand_new",)


def test_non_leaf_modules_lists_the_siblings_of_a_dotted_leaf(
    make_package: Callable[..., str],
) -> None:
    for name in ("lane0_art", "lane0_art.runtime", "lane0_art.artifacts"):
        make_package(name)
    for name in ("lane0_art.artifacts.hook_schema", "lane0_art.artifacts.frontmatter"):
        make_package(name)

    forbidden = non_leaf_modules("runtime", root="lane0_art", leaves={"artifacts.hook_schema"})

    assert forbidden == ("lane0_art.artifacts.frontmatter",)


def test_non_leaf_modules_rejects_an_unknown_stack() -> None:
    with pytest.raises(ValueError, match="not a top-level package"):
        non_leaf_modules("evaluators_renamed")


def test_non_leaf_modules_without_a_stack_forbids_every_stack(
    make_package: Callable[..., str],
) -> None:
    for name in ("lane0_all", "lane0_all.runtime", "lane0_all.leaf"):
        make_package(name)

    assert non_leaf_modules(root="lane0_all", leaves={"leaf"}) == ("lane0_all.runtime",)


def test_runtime_dependency_imports_reads_the_dependency_table(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\ndependencies = ["PyYAML>=6.0", "packaging>=24.0"]\n', encoding="utf-8"
    )

    assert runtime_dependency_imports(pyproject) == ("packaging", "yaml")


def test_runtime_dependency_imports_are_the_engine_dependencies() -> None:
    assert runtime_dependency_imports() == ("jinja2", "packaging", "yaml")
