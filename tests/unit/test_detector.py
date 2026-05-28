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


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
