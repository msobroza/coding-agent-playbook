"""The spec-driven framework choice and its ``framework.toml`` (D57, D71; prU L0-19)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.config.framework import (
    FrameworkMetadataError,
    bundled_framework_names,
    framework_layers,
    framework_package,
    layers_with_framework,
    metadata_problems,
    read_framework_metadata,
)
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.config.schema import ConfigError

if TYPE_CHECKING:
    from collections.abc import Callable

_SUPERPOWERS = "coding_agent_playbook.plugins.superpowers"
_MATTPOCOCK = "coding_agent_playbook.plugins.mattpocock_skills"


def _config_data(**extra: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": {"name": "x", "kind": "python-library"},
        "engine": {"version": "0.1"},
        **extra,
    }


def test_the_bundled_frameworks_are_named_by_their_framework_toml() -> None:
    assert bundled_framework_names() == {"mattpocock": _MATTPOCOCK, "superpowers": _SUPERPOWERS}


@pytest.mark.parametrize(
    ("choice", "package"),
    [
        ("superpowers", _SUPERPOWERS),
        ("mattpocock", _MATTPOCOCK),
        ("none", None),
        ("acme.framework", "acme.framework"),
        ("coding_agent_playbook.packs.superpowers", _SUPERPOWERS),
    ],
)
def test_framework_package_resolves_short_names_and_keeps_module_names(
    choice: str, package: str | None
) -> None:
    assert framework_package(choice) == package


def test_layers_with_framework_puts_the_framework_first_once() -> None:
    assert layers_with_framework(["acme.rules", _MATTPOCOCK], "mattpocock") == [
        _MATTPOCOCK,
        "acme.rules",
    ]
    assert layers_with_framework(["acme.rules"], None) == ["acme.rules"]


def test_framework_layers_are_the_layers_shipping_framework_toml() -> None:
    layers = ["coding_agent_playbook", _SUPERPOWERS, "no_such_overlay", _MATTPOCOCK]

    assert framework_layers(layers) == [_SUPERPOWERS, _MATTPOCOCK]


def test_read_framework_metadata_of_a_bundled_framework() -> None:
    metadata = read_framework_metadata(_MATTPOCOCK)

    assert metadata is not None
    assert (metadata.name, metadata.package) == ("mattpocock", _MATTPOCOCK)
    assert metadata.description
    assert dict(metadata.layout_aliases) == {}


def test_read_framework_metadata_is_none_for_a_layer_without_one() -> None:
    assert read_framework_metadata("coding_agent_playbook") is None


def test_read_framework_metadata_reads_an_overlay_resources_root(
    make_package: Callable[..., str],
) -> None:
    package = _overlay_with_framework_toml(
        make_package,
        'name = "acme"\ndescription = "Acme flow"\n'
        '[layout_aliases]\n"docs/acme/plans/" = "plans"\n',
    )

    metadata = read_framework_metadata(package)

    assert metadata is not None
    assert metadata.name == "acme"
    assert dict(metadata.layout_aliases) == {"docs/acme/plans/": "plans"}


def test_read_framework_metadata_raises_with_every_problem(
    make_package: Callable[..., str],
) -> None:
    package = _overlay_with_framework_toml(
        make_package, 'name = "acme"\ncapabilities = {}\n[layout_aliases]\n"/abs/" = "nope"\n'
    )

    with pytest.raises(FrameworkMetadataError) as caught:
        read_framework_metadata(package)

    message = str(caught.value)
    assert "description" in message
    assert "'capabilities'" in message
    assert "'nope'" in message
    assert "'/abs/'" in message


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ({"name": "a", "description": "b"}, []),
        ({"name": "a", "description": "b", "layout_aliases": {"docs/x/": "specs"}}, []),
        ({"description": "b"}, ["name must be a non-empty string, got None"]),
        (
            {"name": "a", "description": "b", "layout_aliases": {"docs/x/": "decisions"}},
            [
                "layout_aliases 'docs/x/' maps to unknown layout key 'decisions'; "
                "known keys: glossary, context_map, adr, architecture, specs, plans, "
                "research, agents, scratch"
            ],
        ),
        (
            {"name": "a", "description": "b", "layout_aliases": {"docs/x": "specs"}},
            [
                "layout_aliases 'docs/x' is not a path prefix: write a relative "
                "directory path ending with '/', without '..'"
            ],
        ),
        (
            {"name": "a", "description": "b", "layout_aliases": {"../x/": "specs"}},
            [
                "layout_aliases '../x/' is not a path prefix: write a relative "
                "directory path ending with '/', without '..'"
            ],
        ),
        (
            {"name": "a", "description": "b", "extra": 1},
            ["unknown key 'extra'; allowed keys: name, description, layout_aliases"],
        ),
    ],
)
def test_metadata_problems(table: dict[str, object], expected: list[str]) -> None:
    assert metadata_problems(table) == expected


def test_config_reads_and_writes_the_framework_key() -> None:
    config = Config.from_dict(_config_data(framework="mattpocock"))

    assert config.framework == "mattpocock"
    assert config.to_dict()["framework"] == "mattpocock"
    assert config.layers_enabled == [_MATTPOCOCK]


def test_config_without_a_framework_key_writes_none_back() -> None:
    config = Config.from_dict(_config_data(overlays_enabled=["acme.rules"]))

    assert config.framework is None
    assert "framework" not in config.to_dict()
    assert config.layers_enabled == ["acme.rules"]


def test_config_framework_none_enables_no_layer() -> None:
    config = Config(1, ProjectMeta("x", "python-library"), "0.1", framework="none")

    assert config.layers_enabled == []


@pytest.mark.parametrize("value", [1, "", "  ", ["superpowers"]])
def test_config_refuses_a_framework_that_is_not_a_name(value: object) -> None:
    with pytest.raises(ConfigError, match="framework must be"):
        Config.from_dict(_config_data(framework=value), source="c.toml")


def _overlay_with_framework_toml(make_package: Callable[..., str], text: str) -> str:
    """An importable overlay package whose ``resources/framework.toml`` holds ``text``."""
    name = make_package("acme_framework_overlay", resources=True)
    package_dir = Path(importlib.import_module(name).__path__[0])
    (package_dir / "resources" / "framework.toml").write_text(text, encoding="utf-8")
    return name
