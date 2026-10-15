"""The stdlib-only dependency tables shared by ``detector`` and the resync hook (specs/prK-hook-pack.md §E.1).

resync-on-detector-input-change compares the dependency names of the edited
``pyproject.toml`` against the names sync baked from ``detect()``; one parser
for both sides means the comparison can never disagree with the detector.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook._pyproject_deps import (
    DEV_GROUP_NAMES,
    dependency_names,
    dependency_specs,
    manifest_dependency_names,
    parse_dep_name,
    parse_dep_spec,
)
from coding_agent_playbook.detector import detect

if TYPE_CHECKING:
    from pathlib import Path

_PYPROJECT = """\
[project]
name = "demo"
dependencies = ["Torch>=2", "numpy [extra] ; python_version >= '3.10'", "fastapi == 0.110", 3]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff"]
docs = ["mkdocs"]

[dependency-groups]
lint = ["mypy"]
"""


def test_dependency_specs_split_runtime_and_dev_groups() -> None:
    runtime, dev = dependency_specs(tomllib.loads(_PYPROJECT))

    assert runtime == {"torch": ">=2", "numpy": "", "fastapi": "== 0.110"}
    assert dev == {"pytest": ">=8", "ruff": "", "mypy": ""}
    assert "docs" not in DEV_GROUP_NAMES


def test_dependency_names_match_the_detector(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    facts = detect(tmp_path)

    runtime, dev = dependency_names(tomllib.loads(_PYPROJECT))

    assert runtime == frozenset(facts.get("dependencies", {}))
    assert dev == frozenset(facts.get("dev_dependencies", {}))


def test_parse_dep_name_and_malformed_tables() -> None:
    assert parse_dep_name("  Scikit-Learn[all]>=1; os_name == 'nt'") == "scikit-learn"
    assert dependency_specs({"project": {"dependencies": "torch"}, "dependency-groups": []}) == (
        {},
        {},
    )


def test_parse_dep_name_pep503() -> None:
    assert parse_dep_name("Foo_Bar @ https://x/y.whl") == "foo-bar"
    assert parse_dep_name("git+https://example.com/x.git") == ""


def test_parse_dep_spec_keeps_constraint_for_normalized_names() -> None:
    """Regression: the constraint was found with ``lower().find(name)``, which
    misses once the name is normalized (``foo_bar`` vs ``foo-bar``)."""
    assert parse_dep_spec("Foo_Bar>=1.0") == ("foo-bar", ">=1.0")
    assert parse_dep_spec("zope.interface [x] ~= 6.0 ; os_name == 'nt'") == (
        "zope-interface",
        "~= 6.0",
    )


_ALL_TABLES = """\
[project]
dependencies = ["Requests>=2", "numpy"]

[project.optional-dependencies]
docs = ["Sphinx"]
dev = ["pytest_asyncio"]

[dependency-groups]
lint = ["ruff", { include-group = "docs" }]

[tool.poetry.dependencies]
python = "^3.12"
Django = "^5"

[tool.poetry.dev-dependencies]
black = "*"

[tool.poetry.group.test.dependencies]
Hypothesis = "*"
"""


def test_manifest_dependency_names_covers_four_tables() -> None:
    names = manifest_dependency_names(tomllib.loads(_ALL_TABLES))

    assert names == frozenset(
        {
            "requests",
            "numpy",
            "sphinx",
            "pytest-asyncio",
            "ruff",
            "django",
            "black",
            "hypothesis",
        }
    )


def test_manifest_dependency_names_ignores_malformed_tables() -> None:
    pyproject = {"project": {"dependencies": "requests"}, "tool": {"poetry": []}}

    assert manifest_dependency_names(pyproject) == frozenset()
