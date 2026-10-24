"""Tests for coding_agent_playbook.detector.facts (SPEC §8)."""

from __future__ import annotations

import pathlib
import textwrap
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.security.paths import is_secret_path

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
    assert facts["has_ci"] is False


@pytest.mark.parametrize("ci_file", [".github/workflows/ci.yml", ".gitlab-ci.yml"])
def test_detect_has_ci_on_either_forge(tmp_path: Path, ci_file: str) -> None:
    """prF §14: a GitLab pipeline counts as CI just as a GitHub workflow does."""
    _write(tmp_path, ci_file, "lint:\n  script: [ruff check .]\n")

    assert detect(tmp_path)["has_ci"] is True


def test_detect_gitlab_ci_include_alone_is_no_pipeline(tmp_path: Path) -> None:
    """GitLab runs the root ``.gitlab-ci.yml``; a file it would include runs nothing alone."""
    _write(tmp_path, ".gitlab/ci/lint.yml", "lint:\n  script: [ruff check .]\n")

    assert detect(tmp_path)["has_ci"] is False


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


#: Secret files the detector must never open (SPEC §17.3; security/patterns.py).
_SECRET_FIXTURES = (
    ".env",
    "deploy/.env.production",
    "certs/server.pem",
    "tls/private.key",
    "config/credentials.json",
    "notebooks/aws_credentials.ipynb",
    ".npmrc",
    ".pypirc",
    "pip.conf",
    "uv.toml",
    "id_rsa",
    "infra/prod.tfvars",
)


def test_detector_never_opens_secret_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "secret-repo"
    repo.mkdir()
    _minimal_pyproject(repo)
    for rel in _SECRET_FIXTURES:
        _write(repo, rel, "TOKEN=hunter2\n")
    opened: list[Path] = []

    def _spy(name: str) -> Any:
        original = getattr(pathlib.Path, name)

        def _recording(self: pathlib.Path, *args: Any, **kwargs: Any) -> Any:
            opened.append(self)
            return original(self, *args, **kwargs)

        return _recording

    for name in ("open", "read_text", "read_bytes"):
        monkeypatch.setattr(pathlib.Path, name, _spy(name))

    detect(repo)

    assert repo / "pyproject.toml" in opened  # the spy saw the detector's real read
    assert [p for p in opened if is_secret_path(p, home=str(tmp_path / "home"))] == []


def test_detect_skips_secret_notebooks(tmp_path: Path) -> None:
    # A notebook keeps its cell outputs, so one named like a credential store is a
    # secret path; the notebook walk skips it instead of counting it.
    repo = tmp_path / "secret-nb"
    repo.mkdir()
    _minimal_pyproject(repo)
    _write(repo, "notebooks/aws_credentials.ipynb", "{}\n")
    _mkdir(repo, "src/secret_nb")

    facts = detect(repo)

    assert facts.get("has_notebooks", False) is False
    assert facts["project_kind"] == "python-library"


def test_detect_skips_home_anchored_secret_notebooks_for_a_relative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #268 (H7): a repo under ``~/.ssh/`` matched the ``~/.ssh/**`` secret glob only
    # when spelled absolute, so ``--repo-root ../probe`` counted its notebook and
    # flipped project_kind to ml-research across five rendered files.
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    repo = _mkdir(home, ".ssh/probe")
    _minimal_pyproject(repo)
    _write(repo, "nb/a.ipynb", "{}\n")
    _mkdir(repo, "src/probe")
    monkeypatch.chdir(_mkdir(home, ".ssh/sib"))

    relative, absolute = detect(pathlib.Path("../probe")), detect(repo)

    assert absolute.get("has_notebooks", False) is False
    assert relative.get("has_notebooks", False) is False
    assert relative["project_kind"] == absolute["project_kind"] == "python-library"


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


def test_detect_underscore_dependency_matches_known_framework(tmp_path: Path) -> None:
    """PEP 503 (prK §E.4): ``pytest_asyncio`` is the ``pytest-asyncio`` framework."""
    repo = tmp_path / "underscore-deps"
    repo.mkdir()
    _write(
        repo,
        "pyproject.toml",
        """\
        [project]
        name = "x"
        dependencies = ["Pydantic_Core>=2"]

        [project.optional-dependencies]
        dev = ["pytest_asyncio>=0.23"]
        """,
    )

    facts = detect(repo)

    assert facts.get("frameworks", {}).get("pytest-asyncio") == ">=0.23"
    assert facts.get("dependencies") == {"pydantic-core": ">=2"}
