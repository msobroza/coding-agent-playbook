"""Unit tests for the catalog resolver (``catalog.py``).

Every test builds its own catalog tree under ``tmp_path``: the resolver must
not depend on where (or whether) the repository's own ``catalog/`` exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook import catalog
from coding_agent_playbook.catalog import (
    DEPRECATED_PACK_NAMESPACE,
    ENGINE_PACKAGE,
    PLUGIN_NAMESPACE,
    CatalogMissingError,
    bundled_plugins,
    canonical_overlay_list,
    canonical_overlay_name,
    catalog_layer_root,
    catalog_root,
    is_bundled_layer,
    is_plugin_namespace,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


def _make_tree(root: Path, plugins: Iterable[str] = ("superpowers",)) -> Path:
    """Create a minimal catalog root: ``core/rules/`` and ``plugins/<p>/skills/``."""
    (root / "core" / "rules").mkdir(parents=True)
    for plugin in plugins:
        (root / "plugins" / plugin / "skills").mkdir(parents=True)
    return root


# --- catalog_root ---------------------------------------------------


def test_packaged_root_wins(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "pkg"
    _make_tree(pkg / "_catalog")
    _make_tree(tmp_path / "catalog")
    assert catalog_root(pkg) == pkg / "_catalog"


def test_checkout_fallback(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "coding_agent_playbook"
    pkg.mkdir(parents=True)
    _make_tree(tmp_path / "catalog")
    assert catalog_root(pkg) == tmp_path / "catalog"


def test_packaged_without_core_is_not_accepted(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "pkg"
    (pkg / "_catalog" / "plugins").mkdir(parents=True)
    with pytest.raises(CatalogMissingError) as caught:
        catalog_root(pkg)
    assert caught.value.tried == (pkg / "_catalog", tmp_path / "catalog")


def test_checkout_without_core_is_not_accepted(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (tmp_path / "catalog" / "plugins" / "superpowers").mkdir(parents=True)
    with pytest.raises(CatalogMissingError):
        catalog_root(pkg)


def test_fallback_requires_src_parent(tmp_path: Path) -> None:
    pkg = tmp_path / "lib" / "pkg"
    pkg.mkdir(parents=True)
    _make_tree(tmp_path / "catalog")
    with pytest.raises(CatalogMissingError):
        catalog_root(pkg)


def test_missing_root_message_names_both_paths(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "pkg"
    with pytest.raises(CatalogMissingError) as caught:
        catalog_root(pkg)
    message = str(caught.value)
    assert str(pkg / "_catalog") in message
    assert str(tmp_path / "catalog") in message


def test_defaults_follow_the_monkeypatched_package_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Later tasks' end-to-end tests rely on this seam being read at call time.
    _make_tree(tmp_path / "catalog")
    monkeypatch.setattr(catalog, "_PACKAGE_DIR", tmp_path / "src" / "coding_agent_playbook")
    assert catalog_root() == tmp_path / "catalog"
    assert bundled_plugins() == [f"{PLUGIN_NAMESPACE}.superpowers"]
    assert catalog_layer_root(f"{PLUGIN_NAMESPACE}.superpowers") == (
        tmp_path / "catalog" / "plugins" / "superpowers"
    )


# --- bundled_plugins ---------------------------------------------------------


def test_bundled_plugins_lists_identifier_dirs_only(tmp_path: Path) -> None:
    root = _make_tree(
        tmp_path / "catalog",
        plugins=("superpowers", "python_design", ".hidden", "_private", "__pycache__", "bad-name"),
    )
    (root / "plugins" / "README.md").write_text("stray file\n")
    assert bundled_plugins(root) == [
        "coding_agent_playbook.plugins.python_design",
        "coding_agent_playbook.plugins.superpowers",
    ]


def test_bundled_plugins_sees_new_dir_without_caching(tmp_path: Path) -> None:
    # Review Focus 3: a plugin dir added by `git pull` in an editable install is
    # visible on the next call, without reinstalling.
    root = _make_tree(tmp_path / "catalog")
    assert bundled_plugins(root) == [f"{PLUGIN_NAMESPACE}.superpowers"]
    (root / "plugins" / "new_one" / "skills").mkdir(parents=True)
    assert f"{PLUGIN_NAMESPACE}.new_one" in bundled_plugins(root)


def test_bundled_plugins_without_plugins_dir_is_empty(tmp_path: Path) -> None:
    root = _make_tree(tmp_path / "catalog", plugins=())
    assert bundled_plugins(root) == []


# --- canonical names ---------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("coding_agent_playbook.packs.superpowers", "coding_agent_playbook.plugins.superpowers"),
        ("coding_agent_playbook.packs", "coding_agent_playbook.packs"),
        ("coding_agent_playbook.packsx.y", "coding_agent_playbook.packsx.y"),
        ("acme.rules", "acme.rules"),
        ("coding_agent_playbook.packs.", "coding_agent_playbook.packs."),
    ],
)
def test_canonical_overlay_name(name: str, expected: str) -> None:
    assert canonical_overlay_name(name) == expected


def test_canonical_overlay_list_keeps_order_and_duplicates() -> None:
    names = ["a", "coding_agent_playbook.packs.x", "coding_agent_playbook.plugins.x"]
    assert canonical_overlay_list(names) == (
        ["a", "coding_agent_playbook.plugins.x", "coding_agent_playbook.plugins.x"],
        ("coding_agent_playbook.packs.x",),
    )


def test_canonical_overlay_list_accepts_a_one_shot_iterable() -> None:
    names = iter(["coding_agent_playbook.packs.x", "b"])
    assert canonical_overlay_list(names) == (
        ["coding_agent_playbook.plugins.x", "b"],
        ("coding_agent_playbook.packs.x",),
    )


# --- namespace and layer predicates -----------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (PLUGIN_NAMESPACE, True),
        (DEPRECATED_PACK_NAMESPACE, True),
        (ENGINE_PACKAGE, False),
        (f"{PLUGIN_NAMESPACE}.x", False),
        (f"{DEPRECATED_PACK_NAMESPACE}.x", False),
        (f"{PLUGIN_NAMESPACE}.", False),
        ("acme", False),
    ],
)
def test_is_plugin_namespace(name: str, expected: bool) -> None:
    assert is_plugin_namespace(name) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (ENGINE_PACKAGE, True),
        (f"{PLUGIN_NAMESPACE}.x", True),
        (f"{DEPRECATED_PACK_NAMESPACE}.x", True),
        (PLUGIN_NAMESPACE, False),
        (DEPRECATED_PACK_NAMESPACE, False),
        ("acme", False),
        ("coding_agent_playbook.pluginsx", False),
    ],
)
def test_is_bundled_layer(name: str, expected: bool) -> None:
    assert is_bundled_layer(name) is expected


# --- catalog_layer_root -------------------------------------------------------


def test_catalog_layer_root_engine_and_plugin(tmp_path: Path) -> None:
    root = _make_tree(tmp_path / "catalog")
    assert catalog_layer_root(ENGINE_PACKAGE, catalog_dir=root) == root / "core"
    plugin_dir = root / "plugins" / "superpowers"
    assert catalog_layer_root(f"{PLUGIN_NAMESPACE}.superpowers", catalog_dir=root) == plugin_dir
    assert (
        catalog_layer_root(f"{DEPRECATED_PACK_NAMESPACE}.superpowers", catalog_dir=root)
        == plugin_dir
    )


@pytest.mark.parametrize("namespace", [PLUGIN_NAMESPACE, DEPRECATED_PACK_NAMESPACE])
@pytest.mark.parametrize(
    "leaf",
    [
        "",
        "..",
        "../core",
        "/tmp",
        "superpowers.skills",
        "superpowers/skills",
        "Superpowers",
        "__pycache__",
    ],
)
def test_catalog_layer_root_rejects_unsafe_leaves(
    tmp_path: Path, namespace: str, leaf: str
) -> None:
    # `__pycache__` exists on disk here, so only the leaf rule can reject it.
    root = _make_tree(tmp_path / "catalog", plugins=("superpowers", "__pycache__"))
    assert catalog_layer_root(f"{namespace}.{leaf}", catalog_dir=root) is None


@pytest.mark.parametrize("name", [PLUGIN_NAMESPACE, DEPRECATED_PACK_NAMESPACE, "acme"])
def test_catalog_layer_root_is_none_for_non_bundled_names(tmp_path: Path, name: str) -> None:
    root = _make_tree(tmp_path / "catalog")
    assert catalog_layer_root(name, catalog_dir=root) is None


@pytest.mark.parametrize("name", [ENGINE_PACKAGE, f"{PLUGIN_NAMESPACE}.superpowers"])
def test_catalog_layer_root_raises_when_root_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(catalog, "_PACKAGE_DIR", tmp_path)
    with pytest.raises(CatalogMissingError):
        catalog_layer_root(name)
