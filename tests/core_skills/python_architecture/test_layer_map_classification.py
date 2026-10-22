"""Tests for ``scripts/layer_map.py`` in the core python-architecture skill: layers, container packages and overrides.

Shared trees and run helpers live in ``_scripts.py``; the ``layer_map`` and ``run_map``
fixtures in ``conftest.py`` (prU D2, D25).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.core_skills.python_architecture._scripts import (
    API_PACKAGE_TREE,
    CLEAN_TREE,
    LAYER_FIRST_TREE,
    ROUTER_IMPORTS_ORM,
    Outcome,
    write_tree,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import ModuleType

pytestmark = pytest.mark.catalog


# --- container packages -------------------------------------------------------------


def test_top_level_package_named_like_a_layer_does_not_swallow_its_layers(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: every module under a top-level api/ package used to be interface,
    # so domain -> interface and domain/application -> db imports passed with exit 0.
    write_tree(tmp_path, API_PACKAGE_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["container_packages"] == ["api"]
    assert report["layers"] == {
        "api.db": "infrastructure",
        "api.db.session": "infrastructure",
        "api.domain": "domain",
        "api.domain.order": "domain",
        "api.routers": "interface",
        "api.routers.orders": "interface",
        "api.services": "application",
        "api.services.pay": "application",
    }
    assert report["unlayered"] == ["api", "api.config", "main"]
    found = {(v["importer"], v["imported"]) for v in report["violations"]}
    assert found == {
        ("api.services.pay", "api.db.session"),
        ("api.domain.order", "api.routers.orders"),
        ("api.domain.order", "api.db.session"),
    }


def test_container_packages_are_listed_in_the_text_report(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, API_PACKAGE_TREE)
    outcome = run_map()
    assert "container packages (named like a layer, holding other layers): api" in outcome.out
    assert "Rule violations: 3" in outcome.out


def test_enclosing_package_above_root_does_not_swallow_its_layers(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # Regression: with services/__init__.py present, ROOT=services/billing named every
    # module services.billing.*, so all of them were application code.
    files = {
        "services/__init__.py": "",
        "services/billing/__init__.py": "",
        "services/billing/domain/__init__.py": "",
        "services/billing/domain/invoice.py": "from services.billing.db import store\n",
        "services/billing/db/__init__.py": "",
        "services/billing/db/store.py": "",
    }
    write_tree(tmp_path, files)
    outcome = run_map("services/billing", "--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["container_packages"] == ["services"]
    assert report["layers"]["services.billing.domain.invoice"] == "domain"
    assert [(v["from_layer"], v["to_layer"]) for v in report["violations"]] == [
        ("domain", "infrastructure")
    ]


def test_layer_first_top_level_packages_stay_layers(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, LAYER_FIRST_TREE)
    outcome = run_map("--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["container_packages"] == []
    assert report["layers"]["db.models"] == "infrastructure"
    assert [(v["importer"], v["imported"]) for v in report["violations"]] == [
        ("services.lending", "db.models")
    ]


def test_a_multi_part_layer_name_overrules_a_container(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    # The documented escape hatch: api/models/ holding request schemas stays interface.
    write_tree(tmp_path, {**API_PACKAGE_TREE, "api/models/__init__.py": "", "api/models/io.py": ""})
    assert run_map("--json").report()["layers"]["api.models.io"] == "domain"
    names = "interface=api,routers,routes,endpoints,views,cli,api/models"
    report = run_map(".", "--layer", names, "--json").report()
    assert report["layers"]["api.models.io"] == "interface"
    assert report["layers"]["api.db.session"] == "infrastructure"


def test_container_packages_need_other_layers_inside_and_no_layered_sibling(
    layer_map: ModuleType,
) -> None:
    rules = layer_map.build_rules([], [], [])
    containers = layer_map.container_packages
    packaged = ["api.routers.orders", "api.db.session", "api.services.pay", "setup"]
    assert containers(packaged, rules) == {("api",)}
    # A layer-first sibling makes the top level the layer axis.
    assert containers(["api.db.session", "services.lending"], rules) == frozenset()
    # Nothing inside names another layer: api/ is just the interface layer.
    assert containers(["api.routes", "api.schemas", "core.rules"], rules) == frozenset()
    # One other layer inside is not enough either: api/models/ may hold request schemas.
    assert containers(["api.routes", "api.models.io", "core.rules"], rules) == frozenset()
    # Nested: rentals/api/ alone beside unlayered packages holds two other layers.
    nested = ["rentals.api.db.rows", "rentals.api.services.loans", "rentals.core"]
    assert containers(nested, rules) == {("rentals", "api")}
    # One other layer inside is not enough: db/models.py (ORM tables) stays in db.
    orm = ["shop.db.models", "shop.db.repositories", "shop.core.rules"]
    assert containers(orm, rules) == frozenset()
    assert layer_map.classify("shop.db.models", rules, containers(orm, rules)) == "infrastructure"


# --- overrides ----------------------------------------------------------------------


def test_layer_and_allow_overrides_change_classification_and_rules(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(
        tmp_path,
        {
            "rentals/http/handlers.py": "from rentals.store.tables import BikeTable\n",
            "rentals/store/tables.py": "",
        },
    )
    assert run_map("--json").report()["layers"] == {}
    layers = ("--layer", "interface=http", "--layer", "infrastructure=store")
    remapped = run_map(".", *layers, "--json")
    assert remapped.code == 1
    assert remapped.report()["layers"] == {
        "rentals.http.handlers": "interface",
        "rentals.store.tables": "infrastructure",
    }
    allowed = run_map(".", *layers, "--allow", "interface=infrastructure", "--json")
    assert allowed.code == 0
    assert allowed.report()["rules"]["interface"] == ["infrastructure"]


def test_layer_override_replaces_the_default_names(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, ROUTER_IMPORTS_ORM)
    outcome = run_map(".", "--layer", "interface=http", "--json")
    assert outcome.code == 0
    assert "rentals.routers.bikes" in outcome.report()["unlayered"]


def test_new_layer_with_a_path_pattern_may_import_only_itself(
    tmp_path: Path, run_map: Callable[..., Outcome]
) -> None:
    write_tree(tmp_path, {**CLEAN_TREE, "rentals/jobs/nightly.py": "import rentals.domain.bike\n"})
    outcome = run_map(".", "--layer", "worker=rentals/jobs", "--json")
    report = outcome.report()
    assert outcome.code == 1
    assert report["layers"]["rentals.jobs.nightly"] == "worker"
    assert report["rules"]["worker"] == []
    assert report["violations"][0]["to_layer"] == "domain"


def test_classify_prefers_the_outermost_matching_part(layer_map: ModuleType) -> None:
    rules = layer_map.build_rules([], [], [])
    assert layer_map.classify("rentals.api.models.payloads", rules) == "interface"
    assert layer_map.classify("rentals.domain.services.pricing", rules) == "domain"
    assert layer_map.classify("rentals.db", rules) == "infrastructure"
    assert layer_map.classify("rentals.billing", rules) is None
