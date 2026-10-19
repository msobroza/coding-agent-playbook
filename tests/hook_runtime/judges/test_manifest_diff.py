"""The dependency names a manifest edit adds (specs/prK-hook-pack.md §E.4).

Only NEWLY declared names and package indexes count, names PEP 503-normalized,
for each manifest kind dependency-allowlist-guard and ``playbook check-deps`` read.
"""

from __future__ import annotations

from typing import Final

import pytest

from coding_agent_playbook.hook_runtime.judges.manifest_diff import (
    LOCKFILES,
    added_indexes,
    added_names,
    manifest_kind,
)

SETUP_CFG: Final = """\
[metadata]
name = demo
[options]
install_requires =
    requests
    click>=8
packages = find:
[options.extras_require]
dev = pytest
    ruff
[options.entry_points]
console_scripts =
    demo = demo.cli:main
"""
ENVIRONMENT: Final = """\
name: demo
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26
  - conda-forge::scipy
  - pip
  - pip:
    - Rich>=13
"""


@pytest.mark.parametrize(
    ("basename", "kind"),
    [
        ("pyproject.toml", "pyproject"),
        ("requirements.txt", "requirements"),
        ("Requirements-Dev.IN", "requirements"),
        ("setup.cfg", "setup_cfg"),
        ("environment.yml", "conda_env"),
        ("uv.lock", None),
        ("README.md", None),
    ],
)
def test_manifest_kind(basename: str, kind: str | None) -> None:
    assert manifest_kind(basename) == kind


def test_pyproject_counts_only_new_names_across_tables() -> None:
    before = '[project]\nname = "d"\ndependencies = ["Foo_Bar>=1"]\n'
    after = (
        '[project]\nname = "d"\ndependencies = ["foo.bar>=2"]\n'
        '[project.optional-dependencies]\ndocs = ["mkdocs"]\n'
        '[dependency-groups]\ndev = ["pytest"]\n'
        '[tool.poetry.dependencies]\npython = "^3.12"\nDjango = "^5"\n'
    )

    assert added_names("pyproject", before, after) == frozenset({"mkdocs", "pytest", "django"})
    assert added_names("pyproject", before, "[project") is None


def test_setup_cfg_reads_dependency_keys_only() -> None:
    expected = frozenset({"requests", "click", "pytest", "ruff"})

    assert added_names("setup_cfg", None, SETUP_CFG) == expected


def test_environment_yml_reads_the_dependencies_list_only() -> None:
    assert added_names("conda_env", None, ENVIRONMENT) == frozenset({"numpy", "scipy", "rich"})


def test_requirements_diff_ignores_repins() -> None:
    assert added_names("requirements", "flask==3\n", "Flask==3.1\nrich\n") == frozenset({"rich"})


def test_lockfiles_name_their_regenerating_command() -> None:
    assert LOCKFILES == {"uv.lock": "uv lock", "poetry.lock": "poetry lock"}


def test_added_indexes_from_requirements_and_pyproject() -> None:
    torch = "https://download.pytorch.org/whl/cu121"
    uv_index = f'[[tool.uv.index]]\nname = "pt"\nurl = "{torch}"\n'
    poetry = '[[tool.poetry.source]]\nname = "corp"\nurl = "https://pypi.corp/simple"\n'

    requirements = added_indexes(
        "requirements", "-i https://p/simple\n", f"-i https://p/simple\n--extra-index-url={torch}\n"
    )
    pyproject = added_indexes(
        "pyproject", '[tool.uv]\nindex-url = "https://p/simple"\n', uv_index + poetry
    )

    assert requirements == [("extra", torch)]
    assert pyproject == [("extra", torch), ("extra", "https://pypi.corp/simple")]
    assert added_indexes("pyproject", None, "[tool") == []
    assert added_indexes("setup_cfg", None, SETUP_CFG) == []
