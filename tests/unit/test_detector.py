"""Tests for coding_agent_playbook.detector (SPEC §8)."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.detector import Facts, detect, evaluate_predicate

if TYPE_CHECKING:
    from pathlib import Path


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
def test_evaluate_predicate_python_version(constraint: str, version: str, expected: bool) -> None:
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


def test_evaluate_predicate_has_ml_stack_all_present() -> None:
    facts: Facts = {"ml_stack": {"torch": ">=2.0", "numpy": ">=1.26"}}
    assert evaluate_predicate({"has_ml_stack": ["torch", "numpy"]}, facts) is True


def test_evaluate_predicate_has_ml_stack_one_missing_false() -> None:
    facts: Facts = {"ml_stack": {"torch": ">=2.0"}}
    assert evaluate_predicate({"has_ml_stack": ["torch", "tensorflow"]}, facts) is False


def test_evaluate_predicate_has_ml_stack_no_ml_stack_in_facts_false() -> None:
    # ML-stack operators read facts["ml_stack"], never facts["frameworks"].
    assert evaluate_predicate({"has_ml_stack": ["torch"]}, {}) is False


def test_evaluate_predicate_has_ml_stack_does_not_read_frameworks() -> None:
    # A framework is not an ML-stack dep — gating must not cross the two facts.
    facts: Facts = {"frameworks": {"torch": ">=2.0"}}
    assert evaluate_predicate({"has_ml_stack": ["torch"]}, facts) is False


def test_evaluate_predicate_any_ml_stack_one_present() -> None:
    facts: Facts = {"ml_stack": {"scikit-learn": ">=1.4"}}
    assert evaluate_predicate({"any_ml_stack": ["torch", "scikit-learn"]}, facts) is True


def test_evaluate_predicate_any_ml_stack_none_present_false() -> None:
    facts: Facts = {"ml_stack": {"numpy": ">=1.26"}}
    assert evaluate_predicate({"any_ml_stack": ["torch", "tensorflow"]}, facts) is False


def test_evaluate_predicate_any_ml_stack_empty_list_false() -> None:
    facts: Facts = {"ml_stack": {"torch": ">=2.0"}}
    assert evaluate_predicate({"any_ml_stack": []}, facts) is False


def test_evaluate_predicate_ml_stack_requires_list() -> None:
    facts: Facts = {"ml_stack": {"torch": ""}}
    with pytest.raises(ValueError, match="list of strings"):
        evaluate_predicate({"any_ml_stack": "torch"}, facts)


def test_evaluate_predicate_has_file_true(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n")
    assert evaluate_predicate({"has_file": ["Dockerfile"]}, {}, repo_root=tmp_path) is True


def test_evaluate_predicate_has_file_missing_false(tmp_path: Path) -> None:
    assert evaluate_predicate({"has_file": ["Dockerfile"]}, {}, repo_root=tmp_path) is False


def test_evaluate_predicate_has_file_all_must_exist(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12-slim\n")
    # Only one of two files exists → False.
    assert (
        evaluate_predicate({"has_file": ["Dockerfile", "Makefile"]}, {}, repo_root=tmp_path)
        is False
    )


def test_evaluate_predicate_has_file_supports_nested_paths(tmp_path: Path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
    assert (
        evaluate_predicate({"has_file": [".github/workflows/ci.yml"]}, {}, repo_root=tmp_path)
        is True
    )


def test_evaluate_predicate_has_file_without_repo_root_raises() -> None:
    with pytest.raises(ValueError, match="repo_root"):
        evaluate_predicate({"has_file": ["Dockerfile"]}, {})


def test_evaluate_predicate_boolean_true_matches_true_fact() -> None:
    facts: Facts = {"has_dockerfile": True}
    assert evaluate_predicate({"has_dockerfile": True}, facts) is True


def test_evaluate_predicate_boolean_true_false_when_fact_false() -> None:
    facts: Facts = {"has_dockerfile": False}
    assert evaluate_predicate({"has_dockerfile": True}, facts) is False


def test_evaluate_predicate_boolean_true_false_when_fact_absent() -> None:
    assert evaluate_predicate({"has_dockerfile": True}, {}) is False


def test_evaluate_predicate_boolean_false_matches_false_fact() -> None:
    # Explicit False matches an explicit False fact, but NOT absence.
    facts: Facts = {"has_dockerfile": False}
    assert evaluate_predicate({"has_dockerfile": False}, facts) is True


def test_evaluate_predicate_boolean_false_does_not_match_absent_fact() -> None:
    # The plan calls out "explicit False vs absent both fail" for True; the
    # symmetric case here is: False predicate against absent fact is False —
    # absence is not equivalent to False.
    assert evaluate_predicate({"has_dockerfile": False}, {}) is False


def test_evaluate_predicate_multiple_keys_anded_all_true() -> None:
    facts: Facts = {
        "python_version": "3.12",
        "frameworks": {"fastapi": ">=0.110"},
    }
    assert (
        evaluate_predicate({"python_version": ">=3.11", "has_framework": ["fastapi"]}, facts)
        is True
    )


def test_evaluate_predicate_multiple_keys_anded_one_false() -> None:
    facts: Facts = {
        "python_version": "3.10",
        "frameworks": {"fastapi": ">=0.110"},
    }
    assert (
        evaluate_predicate({"python_version": ">=3.11", "has_framework": ["fastapi"]}, facts)
        is False
    )


def test_evaluate_predicate_empty_predicate_returns_true() -> None:
    # Vacuous truth — no constraints means the predicate is satisfied.
    assert evaluate_predicate({}, {}) is True


def test_evaluate_predicate_unknown_key_raises() -> None:
    with pytest.raises(ValueError, match="unknown predicate"):
        evaluate_predicate({"wat": 1}, {})


def test_evaluate_predicate_unknown_key_with_string_value_raises() -> None:
    # Strings are not boolean, not a structured operator — must raise.
    with pytest.raises(ValueError, match="unknown predicate"):
        evaluate_predicate({"frobnicate": "yes"}, {})


def test_evaluate_predicate_unknown_key_with_bool_value_raises() -> None:
    """A typo'd predicate key paired with a bool value must raise ValueError,
    not silently match the boolean branch (code-quality review I1).
    Previously the dispatch matched on value-type-only, letting typos through."""
    with pytest.raises(ValueError, match="unknown predicate key"):
        evaluate_predicate({"has_dokerfile": True}, {"has_dockerfile": True})
    with pytest.raises(ValueError, match="unknown predicate key"):
        evaluate_predicate({"banking_mode_typo": False}, {})


def test_evaluate_predicate_python_version_with_non_string_raises() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        evaluate_predicate({"python_version": 3}, {"python_version": "3.12"})


def test_evaluate_predicate_python_version_invalid_value_in_facts_raises() -> None:
    # If facts carry a syntactically-invalid version, packaging surfaces it.
    with pytest.raises(ValueError, match="invalid python_version"):
        evaluate_predicate({"python_version": ">=3.11"}, {"python_version": "not.a.version"})


def test_detect_handles_missing_or_empty_requires_python(tmp_path: Path) -> None:
    repo = tmp_path / "no-req-py"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        dependencies = []
        """,
    )

    facts = detect(repo)

    assert "python_version" not in facts


def test_detect_handles_unparseable_requires_python(tmp_path: Path) -> None:
    # Bare "3.12" with no operator can't be parsed safely; we leave python_version unset.
    repo = tmp_path / "weird-req-py"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = "bogus-string"
        dependencies = []
        """,
    )

    facts = detect(repo)

    assert "python_version" not in facts


def test_detect_dependency_with_environment_marker(tmp_path: Path) -> None:
    repo = tmp_path / "with-env-marker"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = [
            "fastapi>=0.110; python_version >= '3.10'",
        ]
        """,
    )

    facts = detect(repo)

    deps = facts.get("dependencies", {})
    assert "fastapi" in deps
    assert "fastapi" in facts.get("frameworks", {})


def test_detect_dep_spec_strips_interior_whitespace(tmp_path: Path) -> None:
    """A spaced version constraint like ``fastapi == 0.110`` must yield a
    version with no leading whitespace inside the constraint string
    (code-quality review M3). Tested via detect() since _parse_dep_spec is
    a module-private helper."""
    repo = tmp_path / "spaced-deps"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        requires-python = ">=3.12"
        dependencies = [
            "fastapi == 0.110",
        ]
        """,
    )

    facts = detect(repo)
    deps = facts.get("dependencies", {})
    assert deps.get("fastapi") == "== 0.110"
    # No leading whitespace inside the version constraint.
    assert not deps.get("fastapi", "").startswith(" ")


def test_detect_handles_malformed_pyproject(tmp_path: Path) -> None:
    """A malformed pyproject.toml must not crash detect() — fall back to
    python-unknown like a missing pyproject would. The docstring guarantees
    detect() never raises (code-quality review C1)."""
    (tmp_path / "pyproject.toml").write_text("this is { not = valid toml")
    facts = detect(tmp_path)
    assert facts["project_kind"] == "python-unknown"
    # Other keys should be absent (no pyproject to read from)
    assert "dependencies" not in facts


def test_detect_skips_non_dev_optional_groups(tmp_path: Path) -> None:
    # An "extras" group named "docs" or "performance" must NOT inflate dev_dependencies.
    repo = tmp_path / "with-extras"
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
        docs = ["sphinx>=7.0"]
        dev = ["ruff>=0.5"]

        [dependency-groups]
        docs = ["mkdocs>=1.5"]
        dev = ["mypy>=1.10"]
        """,
    )

    facts = detect(repo)

    dev_deps = facts.get("dev_dependencies", {})
    assert "ruff" in dev_deps
    assert "mypy" in dev_deps
    # The docs-only entries must not appear as dev deps.
    assert "sphinx" not in dev_deps
    assert "mkdocs" not in dev_deps


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
