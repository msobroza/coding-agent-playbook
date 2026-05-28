"""Tests for coding_agent_playbook.detector (SPEC §8)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from coding_agent_playbook.detector import detect


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


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
