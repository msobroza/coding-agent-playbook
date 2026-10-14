"""Tests for the ``is_secret_path`` mechanics (specs/prK-lifecycle-hooks.md §P7).

The catalog itself is pinned in ``test_patterns.py``; these tests cover how the
predicate reads a path: path-like inputs, ``~`` expansion, the default home,
lexical normalization, and that it never touches the filesystem.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from coding_agent_playbook.security.paths import is_secret_path

_HOME = "/home/dev"


def test_accepts_path_like_inputs() -> None:
    assert is_secret_path(PurePosixPath("deploy/.env"), home=_HOME, platform="linux") is True
    assert is_secret_path(PurePosixPath("src/app.py"), home=_HOME, platform="linux") is False


def test_accepts_a_path_like_home() -> None:
    home = PurePosixPath(_HOME)
    assert is_secret_path(f"{_HOME}/.aws/config", home=home, platform="linux") is True


def test_expands_a_leading_tilde_against_home() -> None:
    assert is_secret_path("~/.kube/config", home=_HOME, platform="linux") is True
    assert is_secret_path("~/notes/config", home=_HOME, platform="linux") is False


def test_bare_tilde_is_classified_as_the_home_path_itself() -> None:
    assert is_secret_path("~", home=_HOME, platform="linux") is False
    # A home whose own name is secret proves "~" was expanded, not matched literally.
    assert is_secret_path("~", home="/srv/.env", platform="linux") is True


def test_defaults_home_to_the_user_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/alt")
    assert is_secret_path("/home/alt/.docker/config.json", platform="linux") is True
    assert is_secret_path(f"{_HOME}/.docker/config.json", platform="linux") is False


def test_home_at_filesystem_root_anchors_every_absolute_path() -> None:
    assert is_secret_path("/.ssh/config", home="/", platform="linux") is True


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (f"{_HOME}/project/../.aws/config", True),
        (f"{_HOME}/./.ssh/config", True),
        ("notes/.env/../readme.md", False),
        ("deploy//.env", True),
    ],
)
def test_normalizes_lexically(path: str, expected: bool) -> None:
    assert is_secret_path(path, home=_HOME, platform="linux") is expected


def test_classifies_without_touching_the_filesystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=hunter2\n", encoding="utf-8")

    def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("is_secret_path touched the filesystem")

    for name in ("open", "read_text", "read_bytes", "stat", "exists", "resolve"):
        monkeypatch.setattr(Path, name, _forbidden)

    assert is_secret_path(secret, home=_HOME, platform="linux") is True
