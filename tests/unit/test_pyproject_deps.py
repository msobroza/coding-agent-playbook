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
    parse_dep_name,
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
