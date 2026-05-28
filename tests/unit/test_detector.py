"""Tests for coding_agent_playbook.detector (SPEC §8)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from coding_agent_playbook.detector import Facts, detect, evaluate_predicate


def _write(repo: Path, rel: str, content: str) -> Path:
    """Write a file inside ``repo`` (creating parents as needed)."""
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content), encoding="utf-8")
    return target


def _mkdir(repo: Path, rel: str) -> Path:
    """Create a directory inside ``repo``."""
    target = repo / rel
    target.mkdir(parents=True, exist_ok=True)
    return target


def test_detect_fastapi_app(tmp_path: Path) -> None:
    repo = tmp_path / "synthetic-repo"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "demo-api"
        requires-python = ">=3.12"
        dependencies = [
            "fastapi>=0.110",
            "pydantic>=2.0",
        ]

        [project.optional-dependencies]
        dev = [
            "pytest>=8.0",
        ]
        """,
    )
    _mkdir(repo, "src/demo_api")
    _write(repo, "Dockerfile", "FROM python:3.12-slim\n")
    _write(repo, ".github/workflows/ci.yml", "name: CI\n")

    facts = detect(repo)

    assert facts["project_kind"] == "python-application"
    frameworks = facts.get("frameworks", {})
    assert "fastapi" in frameworks
    assert "pydantic" in frameworks
    assert facts["has_dockerfile"] is True
    assert facts["has_ci"] is True
    assert facts["python_version"] == "3.12"


def test_detect_ml_research(tmp_path: Path) -> None:
    repo = tmp_path / "ml-repo"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "ml-thing"
        requires-python = ">=3.12"
        dependencies = [
            "torch>=2.0",
            "transformers",
            "numpy",
        ]
        """,
    )
    _mkdir(repo, "src/ml_thing")
    _write(repo, "notebooks/explore.ipynb", "{}\n")

    facts = detect(repo)

    assert facts["project_kind"] == "ml-research"
    ml_stack = facts.get("ml_stack", {})
    assert "torch" in ml_stack
    assert "transformers" in ml_stack
    assert "numpy" in ml_stack
    assert facts.get("has_notebooks") is True


def test_detect_notebook_only(tmp_path: Path) -> None:
    repo = tmp_path / "nb-only"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "nb-only"
        requires-python = ">=3.12"
        dependencies = []
        """,
    )
    _write(repo, "analysis.ipynb", "{}\n")

    facts = detect(repo)

    assert facts["project_kind"] == "notebook"
    assert facts.get("has_notebooks") is True


def test_detect_python_library(tmp_path: Path) -> None:
    repo = tmp_path / "lib"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "my-lib"
        requires-python = ">=3.12"
        dependencies = [
            "click>=8.0",
        ]
        """,
    )
    _mkdir(repo, "src/my_lib")

    facts = detect(repo)

    assert facts["project_kind"] == "python-library"
    # No notebooks and no fastapi, but src/ is present.
    assert facts.get("has_notebooks", False) is False


def test_detect_empty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()

    facts = detect(repo)

    assert facts["project_kind"] == "python-unknown"
    assert "python_version" not in facts
    assert "dependencies" not in facts
    assert "frameworks" not in facts


def test_detect_ignores_venv_when_walking_notebooks(tmp_path: Path) -> None:
    # Guard rail: an .ipynb inside .venv must NOT trip has_notebooks.
    repo = tmp_path / "no-real-nb"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "no-real-nb"
        requires-python = ">=3.12"
        dependencies = []
        """,
    )
    _write(repo, ".venv/share/notebook/template.ipynb", "{}\n")
    _mkdir(repo, "src/no_real_nb")

    facts = detect(repo)

    assert facts.get("has_notebooks", False) is False
    assert facts["project_kind"] == "python-library"


def _minimal_pyproject(repo: Path) -> None:
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = []
        """,
    )


def test_detect_package_manager_uv(tmp_path: Path) -> None:
    repo = tmp_path / "uv-repo"
    repo.mkdir()
    _minimal_pyproject(repo)
    _write(repo, "uv.lock", "# uv lock\n")

    facts = detect(repo)

    assert facts.get("package_manager") == "uv"


def test_detect_package_manager_poetry(tmp_path: Path) -> None:
    repo = tmp_path / "poetry-repo"
    repo.mkdir()
    _minimal_pyproject(repo)
    _write(repo, "poetry.lock", "# poetry lock\n")

    facts = detect(repo)

    assert facts.get("package_manager") == "poetry"


def test_detect_package_manager_pip_tools(tmp_path: Path) -> None:
    repo = tmp_path / "pt-repo"
    repo.mkdir()
    _minimal_pyproject(repo)
    _write(repo, "requirements.in", "requests\n")

    facts = detect(repo)

    assert facts.get("package_manager") == "pip-tools"


def test_detect_package_manager_pip_fallback(tmp_path: Path) -> None:
    repo = tmp_path / "pip-repo"
    repo.mkdir()
    _minimal_pyproject(repo)
    _write(repo, "requirements.txt", "requests\n")

    facts = detect(repo)

    assert facts.get("package_manager") == "pip"


def test_detect_package_manager_default_pip(tmp_path: Path) -> None:
    # No lockfile, no requirements — default to pip.
    repo = tmp_path / "bare-repo"
    repo.mkdir()
    _minimal_pyproject(repo)

    facts = detect(repo)

    assert facts.get("package_manager") == "pip"


def test_detect_package_manager_poetry_via_tool_section(tmp_path: Path) -> None:
    repo = tmp_path / "tool-poetry"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = []

        [tool.poetry]
        name = "x"
        """,
    )

    facts = detect(repo)

    assert facts.get("package_manager") == "poetry"


def test_detect_python_version_from_requires_python(tmp_path: Path) -> None:
    repo = tmp_path / "py-version"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12,<4"
        dependencies = []
        """,
    )

    facts = detect(repo)

    assert facts.get("python_version") == "3.12"


def test_detect_dev_dependencies_populated(tmp_path: Path) -> None:
    repo = tmp_path / "with-dev"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = []

        [project.optional-dependencies]
        dev = [
            "ruff>=0.5",
            "mypy>=1.10",
        ]
        """,
    )

    facts = detect(repo)

    dev_deps = facts.get("dev_dependencies", {})
    assert "ruff" in dev_deps
    assert "mypy" in dev_deps
    dev_tools = facts.get("dev_tools", set())
    assert "ruff" in dev_tools
    assert "mypy" in dev_tools


def test_detect_dev_dependencies_from_dependency_groups(tmp_path: Path) -> None:
    """PEP 735 ``[dependency-groups]`` table also feeds dev_dependencies."""
    repo = tmp_path / "with-dg"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = []

        [dependency-groups]
        dev = ["pyright>=1.1"]
        """,
    )

    facts = detect(repo)

    dev_deps = facts.get("dev_dependencies", {})
    assert "pyright" in dev_deps
    assert "pyright" in facts.get("dev_tools", set())


def test_detect_dev_tools_from_config_section(tmp_path: Path) -> None:
    # Even with no dep declared, ``[tool.ruff]`` etc. signals the tool is in use.
    repo = tmp_path / "config-only"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = []

        [tool.ruff]
        line-length = 100

        [tool.mypy]
        strict = true

        [tool.black]
        line-length = 100
        """,
    )

    facts = detect(repo)

    dev_tools = facts.get("dev_tools", set())
    assert {"ruff", "mypy", "black"}.issubset(dev_tools)


def test_detect_framework_includes_pytest_from_dev_deps(tmp_path: Path) -> None:
    """Testing frameworks (pytest) count as frameworks even when declared dev-only."""
    repo = tmp_path / "with-pytest"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = []

        [project.optional-dependencies]
        dev = ["pytest>=8.0", "pytest-asyncio"]
        """,
    )

    facts = detect(repo)

    frameworks = facts.get("frameworks", {})
    assert "pytest" in frameworks
    assert "pytest-asyncio" in frameworks


@pytest.mark.parametrize(
    ("constraint", "version", "expected"),
    [
        (">=3.11", "3.12", True),
        (">=3.11", "3.10", False),
        (">3.11", "3.12", True),
        (">3.11", "3.11", False),
        ("==3.12", "3.12", True),
        ("==3.12", "3.13", False),
        ("<=3.12", "3.12", True),
        ("<=3.12", "3.13", False),
        ("<3.13", "3.12", True),
        ("<3.13", "3.13", False),
        ("~=3.12", "3.12.5", True),
        ("~=3.12", "4.0", False),
    ],
)
def test_evaluate_predicate_python_version(
    constraint: str, version: str, expected: bool
) -> None:
    facts: Facts = {"python_version": version}
    assert evaluate_predicate({"python_version": constraint}, facts) is expected


def test_evaluate_predicate_python_version_absent_returns_false() -> None:
    # If facts lack python_version, the constraint can't be satisfied.
    assert evaluate_predicate({"python_version": ">=3.11"}, {}) is False


def test_evaluate_predicate_python_version_rejects_unknown_operator() -> None:
    facts: Facts = {"python_version": "3.12"}
    with pytest.raises(ValueError, match=r"must start with"):
        evaluate_predicate({"python_version": "@3.12"}, facts)


def test_evaluate_predicate_has_framework_all_present() -> None:
    facts: Facts = {"frameworks": {"fastapi": ">=0.110", "pydantic": ">=2.0"}}
    assert evaluate_predicate({"has_framework": ["fastapi", "pydantic"]}, facts) is True


def test_evaluate_predicate_has_framework_one_missing_false() -> None:
    facts: Facts = {"frameworks": {"fastapi": ">=0.110"}}
    assert evaluate_predicate({"has_framework": ["fastapi", "django"]}, facts) is False


def test_evaluate_predicate_has_framework_no_frameworks_in_facts_false() -> None:
    assert evaluate_predicate({"has_framework": ["fastapi"]}, {}) is False


def test_evaluate_predicate_has_framework_requires_list() -> None:
    facts: Facts = {"frameworks": {"fastapi": ""}}
    with pytest.raises(ValueError, match="list of strings"):
        evaluate_predicate({"has_framework": "fastapi"}, facts)


def test_evaluate_predicate_any_framework_one_present() -> None:
    facts: Facts = {"frameworks": {"pytest": ">=8.0"}}
    assert evaluate_predicate({"any_framework": ["pytest", "unittest"]}, facts) is True


def test_evaluate_predicate_any_framework_none_present_false() -> None:
    facts: Facts = {"frameworks": {"fastapi": ">=0.110"}}
    assert evaluate_predicate({"any_framework": ["pytest", "unittest"]}, facts) is False


def test_evaluate_predicate_any_framework_empty_list_false() -> None:
    # Vacuous "any of nothing" is False — there's no framework satisfying it.
    facts: Facts = {"frameworks": {"fastapi": ">=0.110"}}
    assert evaluate_predicate({"any_framework": []}, facts) is False


def test_evaluate_predicate_has_file_true(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n")
    assert (
        evaluate_predicate({"has_file": ["Dockerfile"]}, {}, repo_root=tmp_path) is True
    )


def test_evaluate_predicate_has_file_missing_false(tmp_path: Path) -> None:
    assert (
        evaluate_predicate({"has_file": ["Dockerfile"]}, {}, repo_root=tmp_path) is False
    )


def test_evaluate_predicate_has_file_all_must_exist(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n")
    # Only one of two files exists → False.
    assert (
        evaluate_predicate(
            {"has_file": ["Dockerfile", "Makefile"]}, {}, repo_root=tmp_path
        )
        is False
    )


def test_evaluate_predicate_has_file_supports_nested_paths(tmp_path: Path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    assert (
        evaluate_predicate(
            {"has_file": [".github/workflows/ci.yml"]}, {}, repo_root=tmp_path
        )
        is True
    )


def test_evaluate_predicate_has_file_without_repo_root_raises() -> None:
    with pytest.raises(ValueError, match="repo_root"):
        evaluate_predicate({"has_file": ["Dockerfile"]}, {})


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
