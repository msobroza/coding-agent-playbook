"""End-to-end ``playbook sync`` of the core skills in a synthetic repo (spec 6.10 items 7, C7).

Core ships ``python-coding``, ``python-testing``, ``python-tooling``,
``ml-data`` and ``web-application``; each is written only while one of its
member rules passes ``applies_if`` (ADR 0001). ``python-testing``'s members all
need pytest, so the skill follows the ``pytest`` dependency in and out of the
repo. ``python-tooling`` has an ungated member (``python-static-checks``), so it
stays, while ``web-application``'s two FastAPI rules follow ``fastapi``. The "Where guidance lives" map in
``AGENTS.md`` names only skills a sync writes, so it is absent when no enabled
adapter has a native skill root.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.config.files import FileSystemStateSource
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_TOOLING = "python-tooling"
_TESTING: Final = "python-testing"
_WEB: Final = "web-application"
#: python-tooling's ungated member, written in every synthetic repo, and web-application's
#: FastAPI pair.
_STATIC_CHECKS: Final = ["python-static-checks.md"]
#: The members gated on FastAPI alone; the httpx and SQLAlchemy members need more (D23).
_FASTAPI_RULES: Final = [
    "fastapi-app-wiring.md",
    "fastapi-error-boundaries.md",
    "fastapi-no-blocking-calls.md",
]

_CONFIG = """\
schema_version = 1
adapters_enabled = {adapters}
overlays_enabled = []

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[storage]
artifact_source = "filesystem"
state_source = "filesystem"
"""
_SKILL_ADAPTERS = '["continue", "claude_code", "opencode", "shared_skills"]'


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), check=False)


def _set_dependencies(repo: Path, dependencies: str) -> None:
    """Rewrite the synthetic ``pyproject.toml`` with ``dependencies`` (a TOML array)."""
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "synthetic"\nrequires-python = ">=3.12"\n'
        f"dependencies = {dependencies}\n",
        encoding="utf-8",
    )


def _skill_lock_paths(repo: Path, skill_id: str) -> list[str]:
    """The sorted lockfile paths under any root's ``<skill_id>/`` directory."""
    lockfile = FileSystemStateSource(repo_root=repo).load_lockfile()
    assert lockfile is not None
    return sorted(entry.path for entry in lockfile.entries if f"/{skill_id}/" in entry.path)


def _rule_files(repo: Path, root: str, skill_id: str) -> list[str]:
    """The sorted file names in ``repo/<root>/<skill_id>/rules/``."""
    return sorted(p.name for p in (repo / root / skill_id / "rules").iterdir())


def _synthetic_skill_repo(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    """A synthetic repo with every native skill root's adapter on and only ``click`` declared."""
    return make_synthetic_repo(
        tmp_path,
        config_text=_CONFIG.format(adapters=_SKILL_ADAPTERS),
        pyproject_extras={"dependencies": ["click"]},
    )


def test_python_testing_follows_the_pytest_dependency_in_and_out(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    repo = _synthetic_skill_repo(tmp_path, make_synthetic_repo)
    assert _sync.run(_ns(repo)) == 0
    assert [root for root in NATIVE_SKILL_ROOTS if (repo / root / _TESTING).exists()] == []

    _set_dependencies(repo, '["click", "pytest"]')
    assert _sync.run(_ns(repo)) == 0
    for root in NATIVE_SKILL_ROOTS:
        assert "pytest.md" in _rule_files(repo, root, _TESTING), root
    assert "skill `python-testing`" in (repo / "AGENTS.md").read_text(encoding="utf-8")

    _set_dependencies(repo, '["click"]')
    assert _sync.run(_ns(repo)) == 0
    assert [root for root in NATIVE_SKILL_ROOTS if (repo / root / _TESTING).exists()] == []
    assert _skill_lock_paths(repo, _TESTING) == []
    assert "skill `python-testing`" not in (repo / "AGENTS.md").read_text(encoding="utf-8")


def test_fastapi_rules_follow_the_fastapi_dependency_in_and_out(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path]
) -> None:
    """python-tooling stays for its ungated static-checks member; web-application's
    FastAPI-only members come and go with ``fastapi`` (prU L0-15, C-web-application-02)."""
    repo = _synthetic_skill_repo(tmp_path, make_synthetic_repo)
    assert _sync.run(_ns(repo)) == 0
    for root in NATIVE_SKILL_ROOTS:
        assert _rule_files(repo, root, _TOOLING) == _STATIC_CHECKS, root
        assert not (repo / root / _WEB).exists(), root

    _set_dependencies(repo, '["click", "fastapi"]')
    assert _sync.run(_ns(repo)) == 0
    for root in NATIVE_SKILL_ROOTS:
        assert _rule_files(repo, root, _TOOLING) == _STATIC_CHECKS, root
        assert _rule_files(repo, root, _WEB) == _FASTAPI_RULES, root
    assert "skill `web-application`" in (repo / "AGENTS.md").read_text(encoding="utf-8")

    _set_dependencies(repo, '["click"]')
    assert _sync.run(_ns(repo)) == 0
    for root in NATIVE_SKILL_ROOTS:
        assert _rule_files(repo, root, _TOOLING) == _STATIC_CHECKS, root
        assert not (repo / root / _WEB).exists(), root
    assert _skill_lock_paths(repo, _WEB) == []
    agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "skill `python-tooling`" in agents_md
    assert "skill `web-application`" not in agents_md


@pytest.mark.parametrize("adapters", ["[]", '["continue"]'], ids=["agents-md-only", "continue"])
def test_agents_md_has_no_where_map_when_no_enabled_adapter_writes_skills(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], adapters: str
) -> None:
    """Regression (C7): the map listed core skills that no enabled adapter wrote anywhere."""
    repo = make_synthetic_repo(tmp_path, config_text=_CONFIG.format(adapters=adapters))

    assert _sync.run(_ns(repo)) == 0

    agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Project context" in agents_md
    assert "## Where guidance lives" not in agents_md
    assert "skill `python-coding`" not in agents_md
    assert [root for root in NATIVE_SKILL_ROOTS if (repo / root).exists()] == []
