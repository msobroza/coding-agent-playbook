"""The engine's own dev loop (``.pre-commit-config.yaml``) gives CI's verdict on content edits.

A maintainer who edits ``content/`` must not pass ``pre-commit`` locally and then
fail CI. Each pin guards one way that has happened or would happen silently:

* CI runs ``ruff format --check .``, which formats code blocks inside markdown
  (ruff >= 0.17), so the format hook must cover markdown too;
* pre-commit passes file names explicitly, and ruff then ignores
  ``extend-exclude`` unless ``force-exclude`` is on: the hooks would rewrite the
  vendored superpowers markdown, which must stay byte-identical;
* an unpinned ruff that starts formatting markdown turns CI red with no change
  in this repository;
* the content tests run only through the ``content`` marker, which
  ``--strict-markers`` requires to be registered.
"""

from __future__ import annotations

import tomllib
from typing import Any

import yaml

from tests._content import REPO_ROOT

_PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
_PYPROJECT = REPO_ROOT / "pyproject.toml"


def _hooks() -> dict[str, dict[str, Any]]:
    config = yaml.safe_load(_PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    return {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}


def _pyproject() -> dict[str, Any]:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_every_dev_hook_is_local_and_runs_from_path() -> None:
    config = yaml.safe_load(_PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    assert [repo["repo"] for repo in config["repos"]] == ["local"]
    assert {hook["language"] for hook in _hooks().values()} == {"system"}


def test_ruff_hooks_honour_extend_exclude_for_explicit_file_names() -> None:
    hooks = _hooks()
    assert hooks["ruff"]["entry"] == "ruff check --fix --force-exclude"
    assert hooks["ruff-format"]["entry"] == "ruff format --force-exclude"
    assert _pyproject()["tool"]["ruff"]["force-exclude"] is True


def test_ruff_format_hook_formats_markdown_like_ci() -> None:
    assert _hooks()["ruff-format"]["types_or"] == ["python", "pyi", "markdown"]


def test_content_checks_hook_runs_the_registered_content_marker() -> None:
    hook = _hooks()["content-checks"]
    assert hook["entry"] == "pytest -q --no-cov -p no:cacheprovider -m content"
    assert hook["files"] == "^content/"
    assert hook["pass_filenames"] is False
    markers = _pyproject()["tool"]["pytest"]["ini_options"]["markers"]
    assert any(marker.startswith("content:") for marker in markers), markers


def test_dev_extra_pins_ruff_exactly() -> None:
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    (ruff,) = [req for req in dev if req.startswith("ruff")]
    assert "==" in ruff, ruff
